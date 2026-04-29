from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db.models import Q
from .models import Task, Note
from users.models import Profile, Subscription

# ==========================================
# NEW: SUBSCRIPTION MANAGEMENT
# ==========================================
@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'max_users', 'is_active', 'expiry_date')
    list_filter = ('is_active',)
    search_fields = ('name', 'owner__username')


# ==========================================
# 1. USER & PROFILE MANAGEMENT
# ==========================================

class CustomUserAdmin(UserAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs.filter(
                Q(id=request.user.id) | 
                Q(is_staff=True) | Q(is_superuser=True) |
                Q(profile__role='SUBSCRIBER') |
                Q(profile__tenant__isnull=True)
            ).distinct()
        
        # FIX: HEAD and SUBSCRIBER see ALL users in their tenant
        try:
            role = request.user.profile.role
            tenant = request.user.profile.tenant
            if role in ['SUBSCRIBER', 'HEAD']:
                return qs.filter(profile__tenant=tenant).distinct()
            elif role == 'SUP':
                return qs.filter(
                    Q(id=request.user.id) | 
                    Q(profile__assigned_supervisor=request.user)
                ).distinct()
        except:
            pass

        return qs.filter(id=request.user.id).distinct()

    def save_model(self, request, obj, form, change):
        if change:
            old_user = User.objects.get(pk=obj.pk)
            if old_user.is_active and not obj.is_active:
                User.objects.filter(profile__created_by=obj).update(is_active=False)
                
        super().save_model(request, obj, form, change)

        if not change: 
            Profile.objects.filter(user=obj).update(created_by=request.user)

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'tenant', 'assigned_supervisor', 'created_by']
    readonly_fields = ['created_by']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs.filter(
                Q(user=request.user) | 
                Q(user__is_staff=True) | Q(user__is_superuser=True) |
                Q(role='SUBSCRIBER')
            ).distinct()

        # FIX: HEAD and SUBSCRIBER see ALL profiles in their tenant
        try:
            role = request.user.profile.role
            tenant = request.user.profile.tenant
            if role in ['SUBSCRIBER', 'HEAD']:
                return qs.filter(tenant=tenant).distinct()
            elif role == 'SUP':
                return qs.filter(
                    Q(user=request.user) | 
                    Q(assigned_supervisor=request.user)
                ).distinct()
        except:
            pass

        return qs.filter(user=request.user).distinct()

    def save_model(self, request, obj, form, change):
        if not obj.pk: 
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ==========================================
# 2. TASK & NOTE PRIVACY
# ==========================================

class NoteInline(admin.TabularInline):
    model = Note
    extra = 1
    fields = ['user', 'text']

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'supervisor', 'status', 'created_at')
    inlines = [NoteInline]
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs.none()

        # FIX: HEAD and SUBSCRIBER see ALL tasks in their tenant
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
        except:
            pass
            
        return qs.filter(owner=request.user).distinct()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if request.user.is_superuser:
            kwargs["queryset"] = User.objects.none() 
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        # FIX: Ensure dropdown options only show people within the same company
        if db_field.name in ["owner", "supervisor"]:
            try:
                role = request.user.profile.role
                tenant = request.user.profile.tenant
                if role in ['SUBSCRIBER', 'HEAD']:
                    kwargs["queryset"] = User.objects.filter(profile__tenant=tenant).distinct()
                elif role == 'SUP':
                    kwargs["queryset"] = User.objects.filter(
                        Q(id=request.user.id) | 
                        Q(profile__assigned_supervisor=request.user)
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
    list_display = ('task', 'text', 'user', 'created_at')
    readonly_fields = ('created_at',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs.none()

        # FIX: HEAD and SUBSCRIBER see ALL notes in their tenant
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
        except:
            pass

        return qs.filter(task__owner=request.user).distinct()