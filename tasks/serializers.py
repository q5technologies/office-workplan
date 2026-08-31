from rest_framework import serializers
from .models import Task, Note, User, Objective, MonthlyWorkplan, WorkplanActivity
from users.models import Profile, Subscription
from django.contrib.auth.models import User

class NoteSerializer(serializers.ModelSerializer):
    task = serializers.PrimaryKeyRelatedField(read_only=True)
    user = serializers.StringRelatedField(read_only=True)
    created_at = serializers.DateTimeField(format="%d %b, %H:%M", read_only=True)
    
    # --- NEW: Allow the mobile app to send an ID to reply to ---
    reply_to_id = serializers.PrimaryKeyRelatedField(
        queryset=Note.objects.all(), source='reply_to', required=False, allow_null=True, write_only=True
    )
    
    # --- NEW: Recursively fetch nested replies ---
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Note 
        fields = ['id', 'task', 'user', 'text', 'created_at', 'reply_to_id', 'replies']

    def get_replies(self, obj):
        # If this note has replies, serialize them and send them inside this note!
        if obj.replies.exists():
            return NoteSerializer(obj.replies.all().order_by('created_at'), many=True).data
        return []

class ObjectiveSerializer(serializers.ModelSerializer):
    owner_name = serializers.ReadOnlyField(source='owner.username')

    # This automatically counts how many tasks are attached to this objective
    tasks_count = serializers.SerializerMethodField()
    # --- Allow frontends to send an 'owner_id' to assign it to someone else ---
    owner_id = serializers.IntegerField(write_only=True, required=False)

    # --- NEW: Expose the computed percentage to the API ---
    completion_percentage = serializers.ReadOnlyField()

    class Meta:
        model = Objective
        fields = ['id', 'title', 'description', 'owner', 'owner_name', 'target_number', 'actual_number', 'completion_percentage', 'tasks_count', 'created_at']
        read_only_fields = ['owner']

    def get_tasks_count(self, obj):
        return obj.tasks.count()


class TaskSerializer(serializers.ModelSerializer):
    description = serializers.CharField(required=False, allow_blank=True)
    # --- NEW: Objective Fields ---
    objective = serializers.PrimaryKeyRelatedField(
        queryset=Objective.objects.all(), 
        required=False, 
        allow_null=True
    )
    objective_title = serializers.ReadOnlyField(source='objective.title')
    supervisor_id = serializers.ReadOnlyField(source='supervisor.id')
    supervisor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), 
        required=False, 
        allow_null=True
    )
    supervisor_name = serializers.ReadOnlyField(source='supervisor.username')
    notes = NoteSerializer(many=True, read_only=True)
    
    # Ensures the frontend doesn't crash validation by sending empty owner fields
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    
    owner_name = serializers.ReadOnlyField(source='owner.username')
    owner_id = serializers.ReadOnlyField(source='owner.id')
    created_at = serializers.DateTimeField(format="%d %b %Y", read_only=True)

    class Meta:
        model = Task
        fields = '__all__'


    # --- FIX: INTERCEPT FRONTEND STRINGIFIED NULLS ---
    def to_internal_value(self, data):
        # If the frontend sends FormData, it arrives as an immutable QueryDict.
        # We temporarily unlock it to clean the data.
        if hasattr(data, '_mutable'):
            data._mutable = True
            
        # Catch React/Axios sending literal "null" text and convert it to real Python None
        if data.get('supervisor') in ['null', 'undefined', '', 'None']:
            data['supervisor'] = None
            
        if data.get('expected_completion_date') in ['null', 'undefined', '', 'None']:
            data['expected_completion_date'] = None
            
        return super().to_internal_value(data)

class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username')
    # Add this line to expose the User ID
    user_id = serializers.ReadOnlyField(source='user.id') 
    #Handle multiple supervisors as a list of User IDs
    assigned_supervisors = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Profile
        # Add 'user_id' to the fields list
        fields = ['id', 'user_id', 'username', 'role', 'assigned_supervisors', 'is_on_leave']

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, min_length=8)

    def validate_new_password(self, value):
        # Optional: Add extra validation like checking for numbers/symbols here
        return value
    
class TenantUserCreateSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=['HEAD', 'SUP', 'SUB'], write_only=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'password', 'first_name', 'last_name', 'role']

    def create(self, validated_data):
        role = validated_data.pop('role')
        user = User.objects.create_user(**validated_data)
        
        # Link the new user to the creator's tenant
        creator_profile = self.context['request'].user.profile
        user.profile.role = role
        user.profile.tenant = creator_profile.tenant
        user.profile.created_by = self.context['request'].user
        user.profile.save()
        
        return user

class WorkplanActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkplanActivity
        fields = '__all__'

class MonthlyWorkplanSerializer(serializers.ModelSerializer):
    activities = WorkplanActivitySerializer(many=True, read_only=True)

    class Meta:
        model = MonthlyWorkplan
        fields = ['id', 'owner', 'month', 'activities', 'created_at']