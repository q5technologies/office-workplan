from django.db import models
from django.contrib.auth.models import User

class Task(models.Model):
    # Define the available statuses
    class Status(models.TextChoices):
        NOT_STARTED = 'NS', 'Not Started'
        IN_PROGRESS = 'IP', 'In Progress'
        COMPLETED = 'CP', 'Completed'
        CANCELLED = 'CN', 'Cancelled'
        POSTPONED = 'PP', 'Postponed'

    title = models.CharField(max_length=200)
    description = models.TextField()
    
    # The person who planned the work
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='my_tasks')
    
    # The supervisor who oversees it
    supervisor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='supervised_tasks')
    
    # Replacement for is_completed
    status = models.CharField(
        max_length=2,
        choices=Status.choices,
        default=Status.NOT_STARTED,
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    expected_completion_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
    
    class Meta:
        ordering = ['-created_at']  # Newest tasks first

class Note(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='notes')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True) # Automatic timestamp

    def __str__(self):
        return f"Note by {self.user.username} on {self.task.title}"
    
