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

from .models import Task, Note
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
                return qs.filter(Q(id=request.user.id) | Q(profile__assigned_supervisor=request.user)).distinct()
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

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'tenant', 'assigned_supervisor', 'is_on_leave', 'created_by']
    list_editable = ['is_on_leave'] 
    list_filter = ['is_on_leave', 'role']
    readonly_fields = ['created_by']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs
        try:
            role = request.user.profile.role
            tenant = request.user.profile.tenant
            if role in ['SUBSCRIBER', 'HEAD']:
                return qs.filter(tenant=tenant)
            elif role == 'SUP':
                return qs.filter(Q(user=request.user) | Q(assigned_supervisor=request.user))
        except: pass
        return qs.filter(user=request.user)


# ==========================================
# TASK & NOTE MANAGEMENT
# ==========================================
class NoteInline(admin.TabularInline):
    model = Note
    extra = 1
    readonly_fields = ('user', 'created_at')


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
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs.none()
        try:
            role = request.user.profile.role
            tenant = request.user.profile.tenant
            if role in ['SUBSCRIBER', 'HEAD']:
                return qs.filter(owner__profile__tenant=tenant).distinct()
            elif role == 'SUP':
                return qs.filter(
                    Q(owner__profile__tenant=tenant) &
                    (Q(owner=request.user) | Q(supervisor=request.user) | Q(owner__profile__assigned_supervisor=request.user))
                ).distinct()
        except: pass
        return qs.filter(owner=request.user).distinct()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if request.user.is_superuser:
            kwargs["queryset"] = User.objects.none() 
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name in ["owner", "supervisor"]:
            try:
                role = request.user.profile.role
                tenant = request.user.profile.tenant
                if role in ['SUBSCRIBER', 'HEAD']:
                    kwargs["queryset"] = User.objects.filter(profile__tenant=tenant).distinct()
                elif role == 'SUP':
                    kwargs["queryset"] = User.objects.filter(
                        Q(id=request.user.id) | Q(profile__assigned_supervisor=request.user)
                    ).distinct()
                else:
                    kwargs["queryset"] = User.objects.filter(id=request.user.id)
            except:
                kwargs["queryset"] = User.objects.none()

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not getattr(obj, 'owner', None):
            obj.owner = request.user
        super().save_model(request, obj, form, change)


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ('task_link', 'text', 'user', 'created_at')
    list_display_links = ('text',) 
    
    def task_link(self, obj):
        url = reverse('admin:tasks_task_change', args=[obj.task.id])
        return format_html('<a href="{}" style="color: #2563eb; font-weight: bold;">{}</a>', url, obj.task.title)
    
    task_link.short_description = 'Task'
    task_link.admin_order_field = 'task__title' 

    def get_readonly_fields(self, request, obj=None):
        return ('created_at', 'user')

    def save_model(self, request, obj, form, change):
        if not obj.pk: 
            obj.user = request.user
        super().save_model(request, obj, form, change)

    list_filter = (
        ('user', admin.RelatedOnlyFieldListFilter), 
        'created_at',                               
    )
    date_hierarchy = 'created_at' 

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser: return qs.none()
        try:
            role = request.user.profile.role
            tenant = request.user.profile.tenant
            if role in ['SUBSCRIBER', 'HEAD']:
                return qs.filter(task__owner__profile__tenant=tenant).distinct()
            elif role == 'SUP':
                return qs.filter(
                    Q(task__owner__profile__tenant=tenant) &
                    (Q(task__owner=request.user) | Q(task__supervisor=request.user) | Q(task__owner__profile__assigned_supervisor=request.user))
                ).distinct()
        except: pass
        return qs.filter(user=request.user).distinct()