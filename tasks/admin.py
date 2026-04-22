from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db.models import Q
from .models import Task, Note
from users.models import Profile, Subscription # <--- IMPORT Subscription

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
            # MULTI-TENANT PRIVACY: Superuser ONLY sees:
            # 1. Themselves
            # 2. Other Admins (Staff and Superusers)
            # 3. SUBSCRIBERs (The company account owners)
            # 4. NEW ADDITION: Users who don't belong to a tenant yet (so you don't lose new accounts!)
            return qs.filter(
                Q(id=request.user.id) | 
                Q(is_staff=True) | Q(is_superuser=True) |
                Q(profile__role='SUBSCRIBER') |
                Q(profile__tenant__isnull=True)  # <--- This prevents newly created users from vanishing
            ).distinct()
        
        # Assigned admins only see themselves, those they created, and those they supervise
        return qs.filter(
            Q(id=request.user.id) | 
            Q(profile__created_by=request.user) | 
            Q(profile__assigned_supervisor=request.user)
        ).distinct()

    def save_model(self, request, obj, form, change):
        # Trigger cascading deactivation
        if change:
            # Fetch the old user state from the database before this save commits
            old_user = User.objects.get(pk=obj.pk)
            
            # Check if the user WAS active, but is NOW deactivated
            # For SaaS: If you deactivate a Subscriber, this locks out their whole company
            if old_user.is_active and not obj.is_active:
                # Deactivate all users created by this admin in one bulk query
                User.objects.filter(profile__created_by=obj).update(is_active=False)
                
        super().save_model(request, obj, form, change)

        # 3. Handle Creator Tagging (for brand new users)
        if not change: 
            # The signal in models.py has already created the profile.
            # We now update that profile to set YOU as the creator.
            Profile.objects.filter(user=obj).update(created_by=request.user)

admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    # Added tenant to the list display so you can easily see what company they belong to
    list_display = ['user', 'role', 'tenant', 'assigned_supervisor', 'created_by']
    readonly_fields = ['created_by']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            # Mirrors the UserAdmin privacy logic for the Profile page
            return qs.filter(
                Q(user=request.user) | 
                Q(user__is_staff=True) | Q(user__is_superuser=True) |
                Q(role='SUBSCRIBER')
            ).distinct()

        return qs.filter(
            Q(user=request.user) | 
            Q(created_by=request.user) | 
            Q(assigned_supervisor=request.user)
        ).distinct()

    def save_model(self, request, obj, form, change):
        """Automatically tag the creator when a profile is first saved."""
        if not obj.pk: 
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


# ==========================================
# 2. TASK & NOTE PRIVACY (Updated for SaaS Privacy)
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
            # STRICT PRIVACY: Superadmins see NO tasks from tenant companies.
            return qs.none()

        # Admins see tasks they own, tasks they supervise, or tasks 
        # belonging to users they originally created.
        return qs.filter(
            Q(owner=request.user) | 
            Q(supervisor=request.user) |
            Q(owner__profile__created_by=request.user)
        ).distinct()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """Restricts selection to only users within the admin's 'visibility' bubble."""
        if request.user.is_superuser:
            kwargs["queryset"] = User.objects.none() # Prevent superadmin from assigning company tasks
            return super().formfield_for_foreignkey(db_field, request, **kwargs)

        if db_field.name in ["owner", "supervisor"]:
            kwargs["queryset"] = User.objects.filter(
                Q(id=request.user.id) | 
                Q(profile__created_by=request.user) | 
                Q(profile__assigned_supervisor=request.user)
            ).distinct()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not getattr(obj, 'owner', None):
            obj.owner = request.user
        super().save_model(request, obj, form, change)

@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ('task', 'user', 'created_at')
    readonly_fields = ('created_at',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            # STRICT PRIVACY: Superadmins see NO notes from tenant companies.
            return qs.none()

        return qs.filter(
            Q(task__owner=request.user) | Q(task__supervisor=request.user)
        ).distinct()