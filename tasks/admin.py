from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User, Permission
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
    
    # --- ENFORCE MAX USERS LIMIT IN DJANGO ADMIN ---
    def has_add_permission(self, request):
        can_add = super().has_add_permission(request)
        if not can_add:
            return False

        try:
            profile = request.user.profile
            if profile.role == 'SUBSCRIBER' and profile.tenant:
                current_user_count = Profile.objects.filter(tenant=profile.tenant).count()
                if current_user_count >= profile.tenant.max_users:
                    return False
        except Exception:
            pass

        return True
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs.filter(
                Q(id=request.user.id) | 
                Q(profile__role='SUBSCRIBER') |
                Q(profile__tenant__isnull=True)
            ).distinct()
        
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

    # --- FIX: ONLY VISUALLY LOCK THE SUPERUSER FIELD ---
    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        
        # If the person logged in is NOT the master system owner...
        if not request.user.is_superuser:
            # We ONLY lock superuser. Permissions and Groups remain editable!
            if 'is_superuser' not in readonly: readonly.append('is_superuser')
            
        return tuple(readonly)

    # --- NEW: FILTER OUT DANGEROUS PERMISSIONS ---
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # Intercept the permissions box before it loads on the screen
        if not request.user.is_superuser:
            if db_field.name == "user_permissions":
                # Remove any permission related to Subscriptions or Tokens from the list
                kwargs["queryset"] = db_field.related_model.objects.exclude(
                    Q(content_type__model__icontains='subscription') |
                    Q(content_type__model__icontains='token') |
                    Q(codename__icontains='token')
                )
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        # --- HARD LOCK SUPERUSER STATUS IN DATABASE ---
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
            tenant = None
            if hasattr(request.user, 'profile'):
                tenant = request.user.profile.tenant

            Profile.objects.filter(user=obj).update(
                created_by=request.user,
                tenant=tenant
            )

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'tenant', 'assigned_supervisor', 'is_on_leave', 'created_by']
    list_editable = ['is_on_leave']
    readonly_fields = ['created_by']

    # --- NEW: ENFORCE MAX USERS LIMIT IN DJANGO ADMIN ---
    def has_add_permission(self, request):
        can_add = super().has_add_permission(request)
        if not can_add:
            return False

        try:
            profile = request.user.profile
            if profile.role == 'SUBSCRIBER' and profile.tenant:
                current_user_count = Profile.objects.filter(tenant=profile.tenant).count()
                if current_user_count >= profile.tenant.max_users:
                    return False
        except Exception:
            pass

        return True
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            # Mirrors the strict bulletproof privacy applied to the User Admin
            return qs.filter(
                Q(user=request.user) | 
                Q(role='SUBSCRIBER') |
                Q(tenant__isnull=True)
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
            # FIX: Auto-assign the tenant if a profile is created manually
            if not obj.tenant and hasattr(request.user, 'profile'):
                obj.tenant = request.user.profile.tenant
                
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
    list_filter = (('owner', admin.RelatedOnlyFieldListFilter), 'created_at')
    inlines = [NoteInline]
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            # STRICT PRIVACY: Superadmins see NO tasks from tenant companies.
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

    # --- NEW: ADMIN PANEL FILTERS ---
    list_filter = (
        ('user', admin.RelatedOnlyFieldListFilter), # Filters by individual (maintains privacy!)
        'created_at',                               # Side-bar date filter
    )
    date_hierarchy = 'created_at' # Top-bar date/month drill-down

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            # STRICT PRIVACY: Superadmins see NO notes from tenant companies.
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