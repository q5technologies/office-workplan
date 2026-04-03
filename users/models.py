# users/models.py
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

