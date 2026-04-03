from django.shortcuts import render
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action  # <--- Add this import
from django.db.models import Q 
from .models import Task, Note
from users.models import Profile # Make sure to import your Profile model
from .serializers import TaskSerializer, NoteSerializer, ProfileSerializer, ChangePasswordSerializer
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist

# 1. Your original Generic Views (Maintained)
class TaskListCreateView(generics.ListCreateAPIView):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Task.objects.filter(Q(owner=user) | Q(supervisor=user)).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class TaskRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Task.objects.all()
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Task.objects.filter(models.Q(owner=user) | models.Q(supervisor=user)).distinct()

class NoteCreateView(generics.CreateAPIView):
    queryset = Note.objects.all()
    serializer_class = NoteSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

# 2. Your TaskViewSet with the NEW add_note action
class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = user.profile.role

        if role == 'HEAD':
            return Task.objects.all().order_by('-created_at')
        
        elif role == 'SUP':
            # 1. Tasks where they are the Supervisor of the TASK
            # 2. Tasks they OWN personally
            # 3. Tasks owned by SUBs who report to them (Reporting Line)
            subordinate_ids = Profile.objects.filter(assigned_supervisor=user).values_list('user_id', flat=True)
            
            return Task.objects.filter(
                Q(supervisor=user) | 
                Q(owner=user) | 
                Q(owner_id__in=subordinate_ids)
            ).distinct().order_by('-created_at')
        
        elif role == 'SUB':
            return Task.objects.filter(owner=user).order_by('-created_at')
            
        return Task.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        role = user.profile.role

        # 1. Logic for SUBORDINATES (Maintain existing)
        if role == 'SUB':
            assigned_sup = user.profile.assigned_supervisor
            serializer.save(owner=user, supervisor=assigned_sup)
        
        # 2. Logic for HEAD (New Logic)
        elif role == 'HEAD':
            # Check if a supervisor was selected in the frontend dropdown
            assigned_sup_user = serializer.validated_data.get('supervisor')

            if assigned_sup_user:
                # SWAP: The selected SUP becomes the "Owner" (Worker)
                # The HEAD (current user) becomes the "Supervisor"
                serializer.save(owner=assigned_sup_user, supervisor=user)
            else:
                # HEAD creates a task for themselves
                serializer.save(owner=user, supervisor=None)

        # 3. Logic for SUPERVISORS (Maintain existing)
        else:
            serializer.save(owner=user)

    # --- THE ADD_NOTE CODE ---
    @action(detail=True, methods=['post'])
    def add_note(self, request, pk=None):
        """
        Custom endpoint: /api/tasks/{id}/add_note/
        """
        task = self.get_object()
        # We pass the text from the mobile app into the serializer
        serializer = NoteSerializer(data=request.data)
        
        if serializer.is_valid():
            # We manually link the current logged-in user and the specific task
            serializer.save(user=request.user, task=task)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def supervisors(self, request):
        """Returns a list of all users with the SUP role."""
        # This assumes your User model has a related profile with a role field
        sups = User.objects.filter(profile__role='SUP')
        data = [{"id": u.id, "username": u.username} for u in sups]
        return Response(data)

    @action(detail=True, methods=['patch'])
    def assign_supervisor(self, request, pk=None):
        """Allows HEAD to assign a specific SUP to a task, unless already assigned."""
        if request.user.profile.role != 'HEAD':
            return Response({"detail": "Only the Head of Department can assign supervisors."}, status=403)
        
        task = self.get_object()

        # LOCKING LOGIC: If a supervisor is already there, HEAD cannot change it
        if task.supervisor is not None:
            return Response({"detail": "This task is already under Supervisor management."}, status=403)
        
        sup_id = request.data.get('supervisor_id')
        if not sup_id:
            return Response({"detail": "Supervisor ID is required."}, status=400)

        try:
            supervisor = User.objects.get(id=sup_id, profile__role='SUP')
            task.supervisor = supervisor
            task.save()
            return Response({"status": "success", "message": f"Task assigned to {supervisor.username}"})
        except User.DoesNotExist:
            return Response({"error": "Selected user is not a valid Supervisor."}, status=400)
        
    @action(detail=False, methods=['get'])
    def subordinates(self, request):
        """
        Returns a list of subordinates. 
        If SUP: Returns only those assigned to them.
        If HEAD: Returns everyone.
        """
        user = request.user
        role = user.profile.role
        
        if role == 'HEAD':
            # Head sees all subordinates in the organization
            subs = User.objects.filter(profile__role='SUB')
        elif role == 'SUP':
            # Supervisor sees ONLY subordinates assigned to them in their Profile
            subs = User.objects.filter(profile__role='SUB', profile__assigned_supervisor=user)
        else:
            # Subordinates shouldn't really be calling this, but return empty just in case
            return Response([])

        data = [{"id": u.id, "username": u.username} for u in subs]
        return Response(data)

    @action(detail=True, methods=['patch'])
    def assign_to_subordinate(self, request, pk=None):
        task = self.get_object()
        user = request.user
        role = user.profile.role

        # LOCKING LOGIC: HEAD cannot reassign tasks that already have a Supervisor
        if role == 'HEAD' and task.supervisor is not None:
            return Response({"detail": "Only the assigned Supervisor can reassign this task."}, status=403)

        # Permission Logic
        is_head = (role == 'HEAD')
        is_assigned_sup = (task.supervisor == user)
        is_owner = (task.owner == user)

        if not (is_head or is_assigned_sup or is_owner):
            return Response({"detail": "Permission denied."}, status=403)

        subordinate_id = request.data.get('subordinate_id')
        if not subordinate_id:
            return Response({"detail": "Subordinate ID is required."}, status=400)

        try:
            subordinate = User.objects.get(id=subordinate_id)
            task.owner = subordinate
            if role == 'SUP':
                task.supervisor = user
            task.save()
            return Response({'status': 'Task reassigned'})
        except User.DoesNotExist:
            return Response({"detail": "Subordinate not found."}, status=404)
        
    def perform_update(self, serializer):
        user = self.request.user
        role = user.profile.role
        task = self.get_object()

        if role == 'HEAD' and task.supervisor is not None:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("This task is locked under Supervisor management.")

        # Allow update if the user is the Supervisor OR the Owner
        if role == 'SUP' and not (task.supervisor == user or task.owner == user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have permission to edit this task.")

        serializer.save()

    def partial_update(self, request, *args, **kwargs):
        user = request.user
        task = self.get_object()
        role = user.profile.role
        
        if role == 'HEAD' and task.supervisor is not None:
            return Response(
                {"error": "Task is locked. Only the assigned Supervisor can make changes."},
                status=status.HTTP_403_FORBIDDEN
            )
            
        # Add the same check here to prevent 403 on PATCH requests
        if role == 'SUP' and not (task.supervisor == user or task.owner == user):
             return Response(
                {"detail": "You do not have permission to edit this task."}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
        return super().partial_update(request, *args, **kwargs)
                
class ProfileViewSet(viewsets.ModelViewSet):
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def me(self, request):
        """
        Endpoint: /api/profiles/me/
        Safely returns the profile of the currently logged-in user.
        """
        try:
            # This is where the 500 error usually happens if the profile is missing
            profile = request.user.profile
            serializer = self.get_serializer(profile)
            return Response(serializer.data)
        except (ObjectDoesNotExist, AttributeError):
            return Response(
                {"error": "No profile found for this user. Please create one in the admin panel."}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """
        Endpoint: /api/profiles/change_password/
        Allows a logged-in user to update their own password.
        """
        serializer = ChangePasswordSerializer(data=request.data)
        
        if serializer.is_valid():
            user = request.user
            # Check if the old password is correct
            if not user.check_password(serializer.data.get('old_password')):
                return Response({"old_password": ["Wrong current password."]}, 
                                status=status.HTTP_400_BAD_REQUEST)
            
            # Set and save the new password
            user.set_password(serializer.data.get('new_password'))
            user.save()
            
            return Response({"message": "Password updated successfully!"}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def link_subordinate(self, request):
        """
        Endpoint: /api/profiles/link_subordinate/
        Allows HEAD to assign a SUB to a SUP.
        """
        # 1. Safety check: Does the requester even have a profile?
        try:
            requesting_user_profile = request.user.profile
        except (ObjectDoesNotExist, AttributeError):
            return Response({"error": "Your user account has no profile assigned."}, status=403)

        # 2. Role check
        if requesting_user_profile.role != 'HEAD':
            return Response({"error": "Only HEAD users can set reporting lines"}, status=403)

        sub_id = request.data.get('subordinate_id')
        sup_id = request.data.get('supervisor_id')

        if not sub_id or not sup_id:
            return Response({"error": "Both subordinate_id and supervisor_id are required."}, status=400)

        try:
            # 3. Look for the profile of the subordinate
            sub_profile = Profile.objects.get(user_id=sub_id, role='SUB')
            
            # 4. Look for the user object of the supervisor (must have SUP role)
            sup_user = User.objects.get(id=sup_id, profile__role='SUP')
            
            # 5. Perform the link
            sub_profile.assigned_supervisor = sup_user
            sub_profile.save()
            
            return Response({
                "message": f"Success: {sub_profile.user.username} now reports to {sup_user.username}"
            })

        except Profile.DoesNotExist:
            return Response({"error": "Subordinate profile not found or role is not 'SUB'"}, status=404)
        except User.DoesNotExist:
            return Response({"error": "Supervisor not found or role is not 'SUP'"}, status=404)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=500)
        
def index_view(request):
    """
    This is the landing page for your PWA.
    It will load your base.html which contains the PWA meta tags.
    """
    return render(request, 'index.html')