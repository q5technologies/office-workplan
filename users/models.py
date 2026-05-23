from django.db import models
from django.db.models import Q
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta

# ==========================================
# NEW: SUBSCRIPTION (TENANT) MODEL
# ==========================================
class Subscription(models.Model):
    name = models.CharField(max_length=255, help_text="Company or Subscriber Name")
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name='owned_subscription')
    max_users = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expiry_date = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.expiry_date:
            # Default to 1 year subscription
            self.expiry_date = timezone.now() + timedelta(days=365)
        
        # 1. Save the subscription state to the database first
        super().save(*args, **kwargs)

        # 2. BULLETPROOF DB SYNC: Bypass Python memory and force a direct database update.
        # This explicitly removes 'is_staff' and 'is_active', ensuring they CANNOT access the Django Admin.
        User.objects.filter(pk=self.owner_id).update(
            is_active=self.is_active,
            is_staff=self.is_active 
        )

        # 3. Instantly lock or unlock all employees (HEAD, SUP, SUB) under this company
        User.objects.filter(profile__tenant=self).update(is_active=self.is_active)

    @property
    def is_expired(self):
        return timezone.now() > self.expiry_date

    def __str__(self):
        status = "Active" if self.is_active and not self.is_expired else "Expired/Inactive"
        return f"{self.name} ({status}) - Limit: {self.max_users}"

# ==========================================
# UPDATED: PROFILE MODEL
# ==========================================
class Profile(models.Model):
    USER_ROLES = (
        ('SUBSCRIBER', 'Subscriber'), # New Role for the account owner
        ('HEAD', 'Head'), 
        ('SUP', 'Supervisor'), 
        ('SUB', 'Subordinate')
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=15, choices=USER_ROLES)
    
    # Link every user to a subscription/tenant
    tenant = models.ForeignKey(
        Subscription, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='members'
    )
    
    assigned_supervisors = models.ManyToManyField(User, related_name='supervised_profiles', blank=True)
    
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_profiles'
    )
    is_on_leave = models.BooleanField(default=False, help_text="Designates whether this user is currently on leave.")

    def __str__(self):
        return f"{self.user.username} - {self.role}"

    
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance, defaults={'role': 'SUB'})

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()