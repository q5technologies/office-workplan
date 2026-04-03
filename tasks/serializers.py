from rest_framework import serializers
from .models import Task, Note, User
from users.models import Profile
from django.contrib.auth.models import User

class NoteSerializer(serializers.ModelSerializer):
    # Change task to read_only=True
    task = serializers.PrimaryKeyRelatedField(read_only=True)
    user = serializers.StringRelatedField(read_only=True)
    created_at = serializers.DateTimeField(format="%d %b, %H:%M", read_only=True)

    class Meta:
        model = Note 
        fields = ['id', 'task', 'user', 'text', 'created_at']


class TaskSerializer(serializers.ModelSerializer):
    description = serializers.CharField(required=False, allow_blank=True)
    supervisor_id = serializers.ReadOnlyField(source='supervisor.id')
    supervisor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), 
        required=False, 
        allow_null=True
    )
    supervisor_name = serializers.ReadOnlyField(source='supervisor.username')
    notes = NoteSerializer(many=True, read_only=True)
    owner_name = serializers.ReadOnlyField(source='owner.username')
    owner_id = serializers.ReadOnlyField(source='owner.id')
    created_at = serializers.DateTimeField(format="%d %b %Y", read_only=True)
    
    # This provides the human-readable version of the status (e.g., "Cancelled")
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Task
        fields = ['id', 'title', 'description', 'owner_name', 'owner_id', 'supervisor_name',
            'supervisor',
            'supervisor_id',
            'status',          # The code (NS, IP, CP, CN, PP)
            'status_display',  # The readable name
            'notes', 
            'created_at', 
            'expected_completion_date'
        ]

class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username')
    # Add this line to expose the User ID
    user_id = serializers.ReadOnlyField(source='user.id') 

    class Meta:
        model = Profile
        # Add 'user_id' to the fields list
        fields = ['id', 'user_id', 'username', 'role', 'assigned_supervisor']

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)

    def validate_new_password(self, value):
        # Optional: Add extra validation like checking for numbers/symbols here
        return value