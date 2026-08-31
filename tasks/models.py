from django.db import models
from django.contrib.auth.models import User

class Objective(models.Model):
    title = models.CharField(max_length=200)
    
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='objectives')
    
    # Optional target number (e.g., 5000 for a sales goal, or left blank for a qualitative goal)
    target_number = models.IntegerField(null=True, blank=True) 

    # --- What you have actually achieved so far ---
    actual_number = models.IntegerField(null=True, blank=True, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    # Dynamic calculation of target achievement ---
    @property
    def completion_percentage(self):
        # If there is no target, we can't calculate a percentage
        if not self.target_number or self.target_number <= 0:
            return None
            
        actual = self.actual_number if self.actual_number else 0
        pct = (actual / self.target_number) * 100
        return round(pct, 1)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']

class Task(models.Model):
    # Define the available statuses
    class Status(models.TextChoices):
        NOT_STARTED = 'NS', 'Not Started'
        IN_PROGRESS = 'IP', 'In Progress'
        COMPLETED = 'CP', 'Completed'
        CANCELLED = 'CN', 'Cancelled'
        POSTPONED = 'PP', 'Postponed'

    title = models.CharField(max_length=200)
    
    # The person who planned the work
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='my_tasks')
    
    # The supervisor who oversees it
    supervisor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='supervised_tasks')
    #Link task to an optional Objective
    objective = models.ForeignKey(Objective, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
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
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True) # Automatic timestamp

    def __str__(self):
        # Truncate the text to 60 characters so it fits neatly in the dropdown
        short_text = (self.text[:60] + '...') if len(self.text) > 60 else self.text
        return f"{self.user.username}: {short_text} ({self.created_at.strftime('%Y-%m-%d')})"
    
    class Meta:
        ordering = ['created_at']  # Newest notes first

class MonthlyWorkplan(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workplans')
    # Store the month by saving the 1st day of the targeted month (e.g., 2026-08-01)
    month = models.DateField() 
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('owner', 'month')
        ordering = ['-month']

    def __str__(self):
        return f"{self.owner.username} - {self.month.strftime('%Y-%m')}"

class WorkplanActivity(models.Model):
    # Matches the TextChoices structure from your Task model
    class Status(models.TextChoices):
        PENDING = 'PD', 'Pending'
        COMPLETED = 'CP', 'Completed'
        POSTPONED = 'PP', 'Postponed'

    workplan = models.ForeignKey(MonthlyWorkplan, on_delete=models.CASCADE, related_name='activities')
    date = models.DateField()
    task = models.ForeignKey('Task', on_delete=models.SET_NULL, null=True, blank=True, related_name='workplan_activities')
    description = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(
        max_length=2,
        choices=Status.choices,
        default=Status.PENDING,
    )

    def __str__(self):
        return f"{self.date} - {self.description}"
        
    class Meta:
        ordering = ['date'] # Chronological order for the PDF printout
        verbose_name_plural = 'Workplan Activities'
