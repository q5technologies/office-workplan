from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Permission, Group
from django.db.models import Q
from django.db import models
from django.core.exceptions import ObjectDoesNotExist
from django.forms import Textarea
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from django.urls import reverse

from .models import Task, Note, Objective
from users.models import Profile, Subscription

# ==========================================
# CUSTOM UI WIDGETS
# ==========================================
class AutoResizeTextarea(Textarea):
    """A custom widget that forces TextFields to auto-grow as the user types."""
    def render(self, name, value, attrs=None, renderer=None):
        if attrs is None:
            attrs = {}
        # Start the box small (2 rows) and hide the default ugly scrollbar
        attrs.update({'rows': '2', 'style': 'width: 100%; min-height: 50px; resize: none; overflow: hidden;'})
        
        html = super().render(name, value, attrs, renderer)
        
        # Inject a tiny piece of JavaScript to handle the resizing math
        script = f"""
        <script>
            (function() {{
                const initResize = () => {{
                    const tx = document.getElementsByName('{name}')[0];
                    if (tx) {{
                        tx.style.height = 'auto';
                        tx.style.height = (tx.scrollHeight + 2) + 'px';
                        tx.addEventListener('input', function() {{
                            this.style.height = 'auto';
                            this.style.height = (this.scrollHeight + 2) + 'px';
                        }});
                    }}
                }};
                window.addEventListener('load', initResize);
                setTimeout(initResize, 100); 
            }})();
        </script>
        """
        return mark_safe(html + script)


# ==========================================
# SUBSCRIPTION MANAGEMENT
# ==========================================
@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'max_users', 'is_active', 'expiry_date')
    list_filter = ('is_active',)
    search_fields = ('name', 'owner__username')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if request.user.is_superuser and db_field.name == "owner":
            # Only allow subscriptions to be owned by actual Subscribers
            kwargs["queryset"] = User.objects.filter(profile__role='SUBSCRIBER')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

# ==========================================
# SECURE GROUP MANAGEMENT
# ==========================================
class CustomGroupAdmin(GroupAdmin):
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # Prevent non-superadmins from adding dangerous permissions to a Group
        if not request.user.is_superuser:
            if db_field.name == "permissions":
                kwargs["queryset"] = db_field.related_model.objects.exclude(
                    Q(content_type__model__icontains='subscription') |
                    Q(content_type__model__icontains='token') |
                    Q(codename__icontains='token')
                )
        return super().formfield_for_manytomany(db_field, request, **kwargs)

admin.site.unregister(Group)
admin.site.register(Group, CustomGroupAdmin)


# ==========================================
# USER & PROFILE MANAGEMENT
# ==========================================
class CustomUserAdmin(UserAdmin):
    
    def has_add_permission(self, request):
        can_add = super().has_add_permission(request)
        if not can_add: return False
        try:
            profile = request.user.profile
            if profile.role == 'SUBSCRIBER' and profile.tenant:
                if Profile.objects.filter(tenant=profile.tenant).count() >= profile.tenant.max_users:
                    return False
        except Exception:
            pass
        return True
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs.filter(
                Q(id=request.user.id) | Q(profile__role='SUBSCRIBER') | Q(profile__tenant__isnull=True)
            ).distinct()
        
        try:
            role = request.user.profile.role
            tenant = request.user.profile.tenant
            if role in ['SUBSCRIBER', 'HEAD']:
                return qs.filter(profile__tenant=tenant).distinct()
            elif role == 'SUP':
                return qs.filter(Q(id=request.user.id) | Q(profile__assigned_supervisors=request.user)).distinct()
        except:
            pass
        return qs.filter(id=request.user.id).distinct()

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            if 'is_superuser' not in readonly: readonly.append('is_superuser')
        return tuple(readonly)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            if db_field.name == "user_permissions":
                kwargs["queryset"] = db_field.related_model.objects.exclude(
                    Q(content_type__model__icontains='subscription') | Q(content_type__model__icontains='token') | Q(codename__icontains='token')
                )
            elif db_field.name == "groups":
                kwargs["queryset"] = db_field.related_model.objects.exclude(
                    Q(permissions__content_type__model__icontains='subscription') | Q(permissions__content_type__model__icontains='token') | Q(permissions__codename__icontains='token')
                ).distinct()
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser:
            obj.is_superuser = False
        try:
            if hasattr(obj, 'profile') and obj.profile.tenant is not None:
                obj.is_superuser = False
        except Exception:
            pass

        if change:
            old_user = User.objects.get(pk=obj.pk)
            if old_user.is_active and not obj.is_active:
                User.objects.filter(profile__created_by=obj).update(is_active=False)
                
        super().save_model(request, obj, form, change)

        if not change: 
            tenant = request.user.profile.tenant if hasattr(request.user, 'profile') else None
            Profile.objects.filter(user=obj).update(created_by=request.user, tenant=tenant)

        # --- NEW FIX: Automatically assign SUBSCRIBER role if created by Superuser ---
        if request.user.is_superuser and not obj.is_superuser:
            profile, created = Profile.objects.get_or_create(user=obj)
            
            if profile.role != 'SUBSCRIBER':
                profile.role = 'SUBSCRIBER'
                profile.save()

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    change_list_template = 'admin_profile_changelist.html'
    list_display = ['user', 'role', 'tenant', 'get_supervisors', 'is_on_leave', 'created_by']
    list_editable = ['is_on_leave'] 
    list_filter = ['is_on_leave', 'role']
    readonly_fields = ['created_by']

    # FIX: Custom method to display all supervisors in a comma-separated list
    def get_supervisors(self, obj):
        return ", ".join([sup.username for sup in obj.assigned_supervisors.all()])
    get_supervisors.short_description = 'Supervisors'

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: 
            #Superusers ONLY see Subscribers and their own profile
            return qs.filter(Q(role='SUBSCRIBER') | Q(user=request.user)).distinct()
        try:
            role = request.user.profile.role
            tenant = request.user.profile.tenant
            if role in ['SUBSCRIBER', 'HEAD']:
                return qs.filter(tenant=tenant)
            elif role == 'SUP':
                # FIX: Check if the user is IN the assigned_supervisors list
                return qs.filter(Q(user=request.user) | Q(assigned_supervisors=request.user)).distinct()
        except: pass
        return qs.filter(user=request.user)
    
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if request.user.is_superuser and db_field.name == "user":
            # Only show Subscribers and Superusers in the User dropdown
            kwargs["queryset"] = User.objects.filter(Q(profile__role='SUBSCRIBER') | Q(is_superuser=True)).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if request.user.is_superuser and db_field.name == "assigned_supervisors":
            # Only show Subscribers in the Supervisors list
            kwargs["queryset"] = User.objects.filter(profile__role='SUBSCRIBER')
        return super().formfield_for_manytomany(db_field, request, **kwargs)


# ==========================================
# TASK & NOTE MANAGEMENT
# ==========================================
class NoteInline(admin.TabularInline):
    model = Note
    extra = 0
    fields = ('user', 'text', 'created_at')
    readonly_fields = ('user', 'created_at')

    formfield_overrides = {
        models.TextField: {'widget': AutoResizeTextarea},
    }

    # Restrict notes to only show notes for the specific task
    def get_queryset(self, request):
        return super().get_queryset(request).order_by('created_at')

    # --- NEW: IMMUTABLE INLINE NOTES ---
    def has_change_permission(self, request, obj=None):
        # Returning False makes existing notes read-only plain text.
        # It still allows the blank "extra" row at the bottom for adding new notes!
        return False

    def has_delete_permission(self, request, obj=None):
        # This completely hides the "Delete" checkbox on inline notes.
        return False
    

class TaskInline(admin.StackedInline): # <--- FIX: Changed from TabularInline to StackedInline!
    model = Task
    extra = 1
    # To make the field card collapsible ---
    fieldsets = (
        ('Task Details', {
            'classes': ('collapse',), # This magic word adds the Show/Hide button!
            'fields': ('title', 'status', 'owner', 'supervisor', 'display_notes')
        }),
    )
    readonly_fields = ('display_notes',)

    def display_notes(self, obj):
        if not obj.pk:
            return "Save this task first to add and view notes."
            
        # --- FIX: Only fetch top-level notes for the initial loop ---
        top_notes = obj.notes.filter(reply_to__isnull=True).order_by('created_at') # Limit to 5 most recent top-level notes
        
        if not top_notes:
            return "No notes yet."
            
        html = "<div style='background-color: #f8fafc; padding: 15px; border-radius: 6px; border: 1px solid #e2e8f0; margin-top: 5px;'>"
        for n in top_notes:
            # Top Level Note
            html += f"<div style='margin-bottom: 8px; border-bottom: 1px solid #f1f5f9; padding-bottom: 8px;'>"
            html += f"<strong style='color: #2563eb;'>{n.user.username}</strong> "
            html += f"<span style='color: #64748b; font-size: 11px; margin-left: 5px;'>({n.created_at.strftime('%d %b %Y, %H:%M')})</span><br>"
            html += f"<span style='color: #334155; font-size: 13px;'>{n.text}</span>"
            
            # --- NEW: Nested Replies Loop ---
            # Order replies oldest to newest so they read like a chat history
            for reply in n.replies.all().order_by('created_at'):
                html += f"<div style='margin-top: 8px; margin-left: 20px; padding-left: 10px; border-left: 2px solid #cbd5e1;'>"
                html += f"<strong style='color: #0f766e;'>{reply.user.username}</strong> "
                html += f"<span style='color: #64748b; font-size: 11px; margin-left: 5px;'>({reply.created_at.strftime('%d %b %Y, %H:%M')})</span><br>"
                html += f"<span style='color: #475569; font-size: 13px;'>{reply.text}</span>"
                html += "</div>"
                
            html += "</div>"
        html += "</div>"
        
        return mark_safe(html)
        
    display_notes.short_description = "Task Notes (Recent)"

    # --- KEEP YOUR EXISTING DROPDOWN SECURITY LOGIC EXACTLY AS IT WAS ---
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if request.user.is_superuser:
            if db_field.name in ["owner", "supervisor"]:
                kwargs["queryset"] = User.objects.all()
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name in ["owner", "supervisor"]:
            try:
                role = request.user.profile.role
                tenant = request.user.profile.tenant
                
                if role in ['SUBSCRIBER', 'HEAD']:
                    kwargs["queryset"] = User.objects.filter(profile__tenant=tenant).distinct()
                elif role == 'SUP':
                    subordinate_ids = Profile.objects.filter(assigned_supervisors=request.user, tenant=tenant).values_list('user_id', flat=True)
                    kwargs["queryset"] = User.objects.filter(Q(id=request.user.id) | Q(id__in=subordinate_ids)).distinct()
                else:
                    kwargs["queryset"] = User.objects.filter(id=request.user.id)
            except Exception:
                kwargs["queryset"] = User.objects.none()
                    
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'supervisor', 'status', 'created_at')
    list_filter = (('owner', admin.RelatedOnlyFieldListFilter), 'created_at')
    inlines = [NoteInline]

    formfield_overrides = {
        models.TextField: {'widget': AutoResizeTextarea},
    }

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, Note) and not getattr(instance, 'user_id', None):
                instance.user = request.user
            instance.save()
        formset.save_m2m()

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('notes', 'notes__user')
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs 
            
        try:
            role = request.user.profile.role
            tenant = request.user.profile.tenant
            if role in ['SUBSCRIBER', 'HEAD']:
                return qs.filter(owner__profile__tenant=tenant).distinct()
            elif role == 'SUP':
                return qs.filter(
                    Q(owner__profile__tenant=tenant) &
                    # FIX: Plural 'assigned_supervisors'
                    (Q(owner=request.user) | Q(supervisor=request.user) | Q(owner__profile__assigned_supervisors=request.user))
                ).distinct()
            elif role == 'SUB':
                return qs.filter(owner=request.user).distinct()
        except Exception:
            pass
        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # 1. FIX: Allow Superusers to see all users instead of an empty list
        if request.user.is_superuser:
            if db_field.name in ["owner", "supervisor"]:
                kwargs["queryset"] = User.objects.all() 
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name in ["owner", "supervisor"]:
            try:
                role = request.user.profile.role
                tenant = request.user.profile.tenant
                if role in ['SUBSCRIBER', 'HEAD']:
                    kwargs["queryset"] = User.objects.filter(profile__tenant=tenant).distinct()
                elif role == 'SUP':
                    # 2. FIX: Updated to 'assigned_supervisors' to support the new multiple-supervisor database structure
                    kwargs["queryset"] = User.objects.filter(
                        Q(id=request.user.id) | Q(profile__assigned_supervisors=request.user)
                    ).distinct()
                else:
                    kwargs["queryset"] = User.objects.filter(id=request.user.id)
            except Exception:
                kwargs["queryset"] = User.objects.none()

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not getattr(obj, 'owner', None):
            obj.owner = request.user
        super().save_model(request, obj, form, change)


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    # Safe list display without URL routing lookups
    list_display = ('get_objective', 'get_task', 'text', 'user', 'created_at')
    list_display_links = ('text',) # Make the note text the clickable link to edit
    
    # 1. Safely grab the Objective Title with a clickable link
    def get_objective(self, obj):
        try:
            if obj.task and obj.task.objective:
                # Dynamically get the app and model name
                app_label = obj.task.objective._meta.app_label
                model_name = obj.task.objective._meta.model_name
                url = reverse(f'admin:{app_label}_{model_name}_change', args=[obj.task.objective.id])
                return format_html('<a href="{}" style="color: #2563eb; font-weight: bold;">{}</a>', url, obj.task.objective.title)
        except Exception:
            pass
        return "-"
    get_objective.short_description = 'Objective'
    get_objective.admin_order_field = 'task__objective__title'
    
    # 2. Safely grab the Task Title with a clickable link
    def get_task(self, obj):
        try:
            if obj.task:
                # Dynamically get the app and model name
                app_label = obj.task._meta.app_label
                model_name = obj.task._meta.model_name
                url = reverse(f'admin:{app_label}_{model_name}_change', args=[obj.task.id])
                return format_html('<a href="{}" style="color: #2563eb; font-weight: bold;">{}</a>', url, obj.task.title)
        except Exception:
            pass
        return "-"
    get_task.short_description = 'Task'
    get_task.admin_order_field = 'task__title'

    # --- IMMUTABLE SETTINGS ---
    def get_readonly_fields(self, request, obj=None):
        return ('created_at', 'user')

    def save_model(self, request, obj, form, change):
        if not obj.pk: 
            obj.user = request.user
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        if obj is not None:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    # --- FILTERS & SEARCH ---
    list_filter = ('created_at', ('user', admin.RelatedOnlyFieldListFilter))
    search_fields = ('text', 'user__username', 'task__title')
    date_hierarchy = 'created_at' 

    # --- SECURITY & HIERARCHY ---
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs 
            
        try:
            role = request.user.profile.role
            tenant = request.user.profile.tenant
            if role in ['SUBSCRIBER', 'HEAD']:
                return qs.filter(task__owner__profile__tenant=tenant).distinct()
            elif role == 'SUP':
                return qs.filter(
                    Q(task__owner__profile__tenant=tenant) &
                    (Q(task__owner=request.user) | Q(task__supervisor=request.user) | Q(task__owner__profile__assigned_supervisors=request.user))
                ).distinct()
            elif role == 'SUB':
                return qs.filter(task__owner=request.user).distinct()
        except Exception:
            pass
        return qs.none()
    
@admin.register(Objective)
class ObjectiveAdmin(admin.ModelAdmin):
    # --- FIX: Replaced 'actual_number' with the visual 'achievement_rating' ---
    list_display = ['title', 'owner', 'target_number', 'actual_number', 'achievement_rating', 'created_at']
    list_filter = ['created_at']
    search_fields = ['title']
    inlines = [TaskInline]

    # --- NEW: Visual Progress Bar ---
    def achievement_rating(self, obj):
        pct = obj.completion_percentage
        if pct is None:
            return "-"
            
        # Determine color based on performance
        if pct >= 100:
            color = "#22c55e" # Green
        elif pct >= 50:
            color = "#f59e0b" # Yellow
        else:
            color = "#ef4444" # Red
            
        capped_pct = min(pct, 100) # Prevents the bar from breaking if they exceed 100%
        
        # Returns a mini progress bar and the percentage number
        return format_html(
            '''<div style="width: 100px; background-color: #e2e8f0; border-radius: 4px; overflow: hidden; display: inline-block; vertical-align: middle;">
                <div style="width: {}%; background-color: {}; height: 8px;"></div>
               </div>
               <span style="margin-left: 8px; font-weight: bold; color: {};">{}%</span>''',
            capped_pct, color, color, pct
        )
    achievement_rating.short_description = "Target Achieved"

    formfield_overrides = {
        models.TextField: {'widget': AutoResizeTextarea},
    }

    # 1. Filter the main table so users only see what they are allowed to see
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs 

        try:
            role = request.user.profile.role
            tenant = request.user.profile.tenant
            if role in ['HEAD', 'SUBSCRIBER']:
                return qs.filter(owner__profile__tenant=tenant)
            elif role == 'SUP':
                subordinate_ids = Profile.objects.filter(assigned_supervisors=request.user, tenant=tenant).values_list('user_id', flat=True)
                return qs.filter(Q(owner=request.user) | Q(owner_id__in=subordinate_ids)).distinct()
            elif role == 'SUB':
                return qs.filter(owner=request.user)
        except Exception:
            pass
        return qs.none()

    # 2. Secure the "Owner" dropdown so they can only assign objectives to allowed people
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "owner" and not request.user.is_superuser:
            try:
                role = request.user.profile.role
                tenant = request.user.profile.tenant
                if role in ['HEAD', 'SUBSCRIBER']:
                    # Heads can pick anyone in the company
                    kwargs["queryset"] = User.objects.filter(profile__tenant=tenant)
                elif role == 'SUP':
                    # Supervisors can pick themselves or their direct subordinates
                    subordinate_ids = Profile.objects.filter(assigned_supervisors=request.user, tenant=tenant).values_list('user_id', flat=True)
                    kwargs["queryset"] = User.objects.filter(Q(id=request.user.id) | Q(id__in=subordinate_ids)).distinct()
                else:
                    # Subordinates can only pick themselves
                    kwargs["queryset"] = User.objects.filter(id=request.user.id)
            except Exception:
                kwargs["queryset"] = User.objects.none()
                
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # 3. FIX: Instantly force the Objectives menu to appear for everyone
    def has_module_permission(self, request): return True
    def has_view_permission(self, request, obj=None): return True
    def has_add_permission(self, request): return True
    def has_change_permission(self, request, obj=None): return True
    def has_delete_permission(self, request, obj=None): return True