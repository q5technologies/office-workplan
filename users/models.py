# users/models.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    USER_ROLES = (('HEAD', 'Head'), ('SUP', 'Supervisor'), ('SUB', 'Subordinate'))
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=USER_ROLES)
    
    # New Field: Points to a User who has the 'SUP' role
    assigned_supervisor = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='my_subordinates'
    )

    def __str__(self):
        return f"{self.user.username} - {self.role}"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
        """Automatically creates a Profile whenever a new User is created."""
        if created:
            # Defaults to 'SUB' (Subordinate) unless you change it in Admin later
            Profile.objects.get_or_create(user=instance, defaults={'role': 'SUB'})

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
        """Ensures the profile is saved whenever the user is updated."""
        try:
            instance.profile.save()
        except Profile.DoesNotExist:
            # Fallback for old users created before this signal was added
            Profile.objects.create(user=instance, role='SUB')