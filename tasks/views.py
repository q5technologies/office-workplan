from django.shortcuts import render
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied 
from django.db.models import Q, Prefetch
from django.utils import timezone 
from .models import Task, Note
from users.models import Profile, Subscription 
from .serializers import TaskSerializer, NoteSerializer, ProfileSerializer, ChangePasswordSerializer, TenantUserCreateSerializer
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse

# --- Native CSV & PDF Imports ---
import csv
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# ==========================================
# SUBSCRIPTION SECURITY MIXIN
# ==========================================
class IsActiveSubscriberMixin:
    """Ensures the user's tenant account is active and not expired"""
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not request.user.is_authenticated: return
        try:
            tenant = request.user.profile.tenant
        except ObjectDoesNotExist:
            raise PermissionDenied("User profile not found.")
        if not tenant:
            raise PermissionDenied("You do not belong to an active subscription/tenant.")
        
        if not tenant.is_active or (tenant.expiry_date and timezone.now() > tenant.expiry_date):
            if tenant.is_active:  
                tenant.is_active = False
                tenant.save()
            raise PermissionDenied("Subscription expired or deactivated. Please renew.")

# ==========================================
# SUBSCRIBER USER CREATION VIEW
# ==========================================
class SubscriberCreateUserView(IsActiveSubscriberMixin, generics.CreateAPIView):
    serializer_class = TenantUserCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        if request.user.profile.role != 'SUBSCRIBER':
            return Response({"error": "Only subscribers can create users."}, status=status.HTTP_403_FORBIDDEN)
        tenant = request.user.profile.tenant
        current_users = Profile.objects.filter(tenant=tenant).count()
        if current_users >= tenant.max_users:
            return Response({"error": f"Subscription limit reached ({tenant.max_users} users)."}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)


# ==========================================
# ORIGINAL VIEWS (UPDATED FOR TENANT ISOLATION)
# ==========================================
class TaskListCreateView(IsActiveSubscriberMixin, generics.ListCreateAPIView):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = user.profile.role
        tenant = user.profile.tenant
        
        if role in ['HEAD', 'SUBSCRIBER']:
            return Task.objects.filter(owner__profile__tenant=tenant).order_by('-created_at')
        elif role == 'SUP':
            subordinate_ids = Profile.objects.filter(assigned_supervisor=user, tenant=tenant).values_list('user_id', flat=True)
            return Task.objects.filter(
                Q(owner__profile__tenant=tenant) & 
                (Q(supervisor=user) | Q(owner=user) | Q(owner_id__in=subordinate_ids))
            ).distinct().order_by('-created_at')
        else:
            return Task.objects.filter(owner=user, owner__profile__tenant=tenant).order_by('-created_at')

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class TaskRetrieveUpdateDestroyView(IsActiveSubscriberMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = user.profile.role
        tenant = user.profile.tenant
        
        if role in ['HEAD', 'SUBSCRIBER']:
            return Task.objects.filter(owner__profile__tenant=tenant)
        elif role == 'SUP':
            subordinate_ids = Profile.objects.filter(assigned_supervisor=user, tenant=tenant).values_list('user_id', flat=True)
            return Task.objects.filter(
                Q(owner__profile__tenant=tenant) & 
                (Q(supervisor=user) | Q(owner=user) | Q(owner_id__in=subordinate_ids))
            ).distinct()
        else:
            return Task.objects.filter(owner=user, owner__profile__tenant=tenant)

class NoteCreateView(IsActiveSubscriberMixin, generics.CreateAPIView):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer
    permission_classes = [permissions.IsAuthenticated]
    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class TaskViewSet(IsActiveSubscriberMixin, viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = user.profile.role
        tenant = user.profile.tenant 

        if role in ['HEAD', 'SUBSCRIBER']:
            return Task.objects.filter(owner__profile__tenant=tenant).order_by('-created_at')
        elif role == 'SUP':
            subordinate_ids = Profile.objects.filter(assigned_supervisor=user, tenant=tenant).values_list('user_id', flat=True)
            return Task.objects.filter(
                Q(owner__profile__tenant=tenant) & 
                (Q(supervisor=user) | Q(owner=user) | Q(owner_id__in=subordinate_ids))
            ).distinct().order_by('-created_at')
        elif role == 'SUB':
            return Task.objects.filter(owner=user, owner__profile__tenant=tenant).order_by('-created_at')
        return Task.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        role = user.profile.role
        if role == 'SUB':
            assigned_sup = user.profile.assigned_supervisor
            serializer.save(owner=user, supervisor=assigned_sup)
        elif role in ['HEAD', 'SUBSCRIBER']:
            assigned_sup_user = serializer.validated_data.get('supervisor')
            if assigned_sup_user:
                serializer.save(owner=assigned_sup_user, supervisor=user)
            else:
                serializer.save(owner=user, supervisor=None)
        else:
            serializer.save(owner=user)

    @action(detail=True, methods=['post'])
    def add_note(self, request, pk=None):
        task = self.get_object()
        serializer = NoteSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(user=request.user, task=task)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def supervisors(self, request):
        tenant = request.user.profile.tenant
        sups = User.objects.filter(profile__role='SUP', profile__tenant=tenant)
        data = [{"id": u.id, "username": u.username} for u in sups]
        return Response(data)

    @action(detail=True, methods=['patch'])
    def assign_supervisor(self, request, pk=None):
        if request.user.profile.role not in ['HEAD', 'SUBSCRIBER']:
            return Response({"detail": "Only the Head or Subscriber can assign supervisors."}, status=403)
        task = self.get_object()
        if task.supervisor is not None:
            return Response({"detail": "This task is already under Supervisor management."}, status=403)
        sup_id = request.data.get('supervisor_id')
        if not sup_id: return Response({"detail": "Supervisor ID is required."}, status=400)
        try:
            tenant = request.user.profile.tenant
            supervisor = User.objects.get(id=sup_id, profile__role='SUP', profile__tenant=tenant)
            task.supervisor = supervisor
            task.save()
            return Response({"status": "success", "message": f"Task assigned to {supervisor.username}"})
        except User.DoesNotExist:
            return Response({"error": "Selected user is not a valid Supervisor in your organization."}, status=400)
        
    @action(detail=False, methods=['get'])
    def subordinates(self, request):
        user = request.user
        role = user.profile.role
        tenant = user.profile.tenant
        if role in ['HEAD', 'SUBSCRIBER']:
            subs = User.objects.filter(profile__role='SUB', profile__tenant=tenant)
        elif role == 'SUP':
            subs = User.objects.filter(profile__role='SUB', profile__assigned_supervisor=user, profile__tenant=tenant)
        else:
            return Response([])
        data = [{"id": u.id, "username": u.username} for u in subs]
        return Response(data)

    @action(detail=True, methods=['patch'])
    def assign_to_subordinate(self, request, pk=None):
        task = self.get_object()
        user = request.user
        role = user.profile.role
        if role == 'HEAD' and task.supervisor is not None:
            return Response({"detail": "Only the assigned Supervisor can reassign this task."}, status=403)
        is_head = (role == 'HEAD' or role == 'SUBSCRIBER')
        is_assigned_sup = (task.supervisor == user)
        is_owner = (task.owner == user)
        if not (is_head or is_assigned_sup or is_owner):
            return Response({"detail": "Permission denied."}, status=403)
        subordinate_id = request.data.get('subordinate_id')
        if not subordinate_id: return Response({"detail": "Subordinate ID is required."}, status=400)
        try:
            tenant = request.user.profile.tenant
            subordinate = User.objects.get(id=subordinate_id, profile__tenant=tenant)
            task.owner = subordinate
            if role == 'SUP': task.supervisor = user
            task.save()
            return Response({'status': 'Task reassigned'})
        except User.DoesNotExist:
            return Response({"detail": "Subordinate not found."}, status=404)
        
    def perform_update(self, serializer):
        user = self.request.user
        role = user.profile.role
        task = self.get_object()
        if role == 'HEAD' and task.supervisor is not None:
            raise PermissionDenied("This task is locked under Supervisor management.")
        if role == 'SUP' and not (task.supervisor == user or task.owner == user):
            raise PermissionDenied("You do not have permission to edit this task.")
        serializer.save()

    def partial_update(self, request, *args, **kwargs):
        user = request.user
        task = self.get_object()
        role = user.profile.role
        if role == 'HEAD' and task.supervisor is not None:
            return Response({"error": "Task is locked."}, status=status.HTTP_403_FORBIDDEN)
        if role == 'SUP' and not (task.supervisor == user or task.owner == user):
             return Response({"detail": "Permission denied."}, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)
                

class ProfileViewSet(IsActiveSubscriberMixin, viewsets.ModelViewSet):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def me(self, request):
        try:
            profile = request.user.profile
            return Response(self.get_serializer(profile).data)
        except ObjectDoesNotExist:
            return Response({"error": "No profile found."}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def report_targets(self, request):
        user = request.user
        try:
            tenant = user.profile.tenant
        except ObjectDoesNotExist:
            return Response([])

        if user.profile.role in ['SUBSCRIBER', 'HEAD']:
            targets = User.objects.filter(profile__tenant=tenant)
        elif user.profile.role == 'SUP':
            targets = User.objects.filter(
                Q(id=user.id) | Q(profile__assigned_supervisor=user), 
                profile__tenant=tenant
            )
        else:
            return Response([])

        data = [{"id": u.id, "username": f"{u.username} ({u.profile.role})"} for u in targets]
        return Response(data)

    # ==========================================
    # ENHANCED: TEAM REPORT (MODIFIED WORK RATE)
    # ==========================================
    @action(detail=False, methods=['get'])
    def team_report(self, request):
        user = request.user
        try:
            profile = user.profile
        except ObjectDoesNotExist:
            return Response({"error": "Profile not found."}, status=404)

        if profile.role not in ['SUBSCRIBER', 'HEAD', 'SUP']:
            return Response({"error": "Permission denied."}, status=403)

        tenant = profile.tenant

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        export_format = request.query_params.get('export', '').lower()
        target_user_id = request.query_params.get('user_id') 

        # Filter tasks by Date Range
        task_queryset = Task.objects.all()
        if start_date: task_queryset = task_queryset.filter(created_at__date__gte=start_date)
        if end_date: task_queryset = task_queryset.filter(created_at__date__lte=end_date)

        # Gather targets
        if profile.role in ['SUBSCRIBER', 'HEAD']:
            target_users = User.objects.filter(profile__tenant=tenant)
        else: 
            target_users = User.objects.filter(
                Q(id=user.id) | Q(profile__assigned_supervisor=user), 
                profile__tenant=tenant
            )

        # Filter by individual dropdown selection
        if target_user_id and target_user_id != 'all':
            target_users = target_users.filter(id=target_user_id)

        target_users = target_users.select_related('profile').prefetch_related(
            Prefetch('my_tasks', queryset=task_queryset), 
            'my_tasks__notes', 
            'my_tasks__notes__user'
        ).distinct()

        report_data = []

        for t_user in target_users:
            user_tasks = t_user.my_tasks.all()
            total_tasks = len(user_tasks)
            
            productive_tasks = 0
            task_list = []
            
            for task in user_tasks:
                task_notes = [{"user": note.user.username, "text": note.text, "created_at": note.created_at.strftime("%d %b %Y, %H:%M")} for note in task.notes.all()]
                
                # --- NEW SCORING SYSTEM ---
                # Count notes explicitly written by the assigned user (the owner)
                owner_notes_count = sum(1 for note in task.notes.all() if note.user == t_user)
                
                # Task counts as "Productive" if it's completed OR (In Progress AND has 4+ notes from the owner)
                if task.status == 'CP' or (task.status == 'IP' and owner_notes_count >= 4):
                    productive_tasks += 1

                task_list.append({"id": task.id, "title": task.title, "status_display": task.get_status_display(), "notes": task_notes})

            perf_pct = 0
            if total_tasks > 0:
                perf_pct = round((productive_tasks / total_tasks) * 100, 1)

            # Note: We keep the JSON key as "completed_tasks" so the React Native mobile app doesn't break, 
            # but it is mathematically representing "Productive Tasks" now.
            report_data.append({
                "username": t_user.username, "role": t_user.profile.role,
                "total_tasks": total_tasks, "completed_tasks": productive_tasks,
                "performance_percentage": perf_pct, "tasks": task_list
            })

        # --- EXPORT TO CSV ---
        if export_format == 'csv':
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="workplan_report_{timezone.now().strftime("%Y%m%d")}.csv"'
            writer = csv.writer(response)
            writer.writerow(['Username', 'Role', 'Total Tasks', 'Completed/Active', 'Performance (%)', 'Task ID', 'Task Title', 'Status', 'Notes'])
            for data in report_data:
                if not data['tasks']:
                    writer.writerow([data['username'], data['role'], 0, 0, '0.0', 'N/A', 'No Tasks in Range', 'N/A', ''])
                else:
                    for task in data['tasks']:
                        notes_str = " | ".join([f"[{n['created_at']}] {n['user']}: {n['text']}" for n in task['notes']])
                        writer.writerow([data['username'], data['role'], data['total_tasks'], data['completed_tasks'], data['performance_percentage'], task['id'], task['title'], task['status_display'], notes_str])
            return response

        # --- EXPORT TO PDF ---
        elif export_format == 'pdf':
            response = HttpResponse(content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="workplan_report_{timezone.now().strftime("%Y%m%d")}.pdf"'
            doc = SimpleDocTemplate(response, pagesize=letter)
            styles = getSampleStyleSheet()
            elements = []

            elements.append(Paragraph("Team Performance Report", styles['Title']))
            elements.append(Spacer(1, 12))

            if start_date and end_date:
                elements.append(Paragraph(f"<b>Date Range:</b> {start_date} to {end_date}", styles['Normal']))
                elements.append(Spacer(1, 12))

            for data in report_data:
                elements.append(Paragraph(f"<b>{data['username']}</b> (Role: {data['role']})", styles['Heading2']))
                elements.append(Paragraph(
                    f"<b>Work Rate Performance:</b> <font color='{'green' if data['performance_percentage'] >= 50 else 'red'}'>{data['performance_percentage']}%</font> "
                    f"<i>({data['completed_tasks']} out of {data['total_tasks']} Tasks Completed or Highly Active)</i>", 
                    styles['Normal']
                ))
                elements.append(Spacer(1, 6))

                if not data['tasks']:
                    elements.append(Paragraph("<i>No tasks found for this user in the specified period.</i>", styles['Normal']))
                else:
                    for task in data['tasks']:
                        elements.append(Paragraph(f"<b>Task:</b> {task['title']} | <b>Status:</b> {task['status_display']}", styles['Heading4']))
                        if not task['notes']:
                            elements.append(Paragraph("<i>  - No notes.</i>", styles['Normal']))
                        else:
                            for note in task['notes']:
                                elements.append(Paragraph(f"  - <b>{note['user']}</b> ({note['created_at']}): {note['text']}", styles['Normal']))
                        elements.append(Spacer(1, 6))
                elements.append(Spacer(1, 12))

            doc.build(elements)
            return response

        return Response(report_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.data.get('old_password')):
                return Response({"old_password": ["Wrong current password."]}, 
                                status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(serializer.data.get('new_password'))
            user.save()
            return Response({"message": "Password updated successfully!"}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def link_subordinate(self, request):
        try:
            requesting_user_profile = request.user.profile
        except (ObjectDoesNotExist, AttributeError):
            return Response({"error": "Your user account has no profile assigned."}, status=403)

        if requesting_user_profile.role not in ['HEAD', 'SUBSCRIBER']:
            return Response({"error": "Only HEAD users or Subscribers can set reporting lines"}, status=403)

        sub_id = request.data.get('subordinate_id')
        sup_id = request.data.get('supervisor_id')

        if not sub_id or not sup_id:
            return Response({"error": "Both subordinate_id and supervisor_id are required."}, status=400)

        try:
            tenant = requesting_user_profile.tenant
            sub_profile = Profile.objects.get(user_id=sub_id, role='SUB', tenant=tenant)
            sup_user = User.objects.get(id=sup_id, profile__role='SUP', profile__tenant=tenant)
            
            sub_profile.assigned_supervisor = sup_user
            sub_profile.save()
            
            return Response({"message": f"Success: {sub_profile.user.username} now reports to {sup_user.username}"})

        except Profile.DoesNotExist:
            return Response({"error": "Subordinate profile not found in your organization."}, status=404)
        except User.DoesNotExist:
            return Response({"error": "Supervisor not found in your organization."}, status=404)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=500)
        
def index_view(request):
    return render(request, 'index.html')