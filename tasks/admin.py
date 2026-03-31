
from django.contrib import admin
from .models import Task, Note
from users.models import Profile

class NoteInline(admin.TabularInline):
    model = Note
    extra = 1  # Provides one empty slot for a new note automatically
    fields = ['user', 'text'] # We omit 'created_at' as it's automatic

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'supervisor', 'status', 'created_at')
    inlines = [NoteInline]

@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ('task', 'user', 'created_at')
    readonly_fields = ('created_at',) # Ensure the timestamp is visible but not editable

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'assigned_supervisor']
    list_filter = ['role']
    search_fields = ['user__username']