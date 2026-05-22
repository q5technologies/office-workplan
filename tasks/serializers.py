from rest_framework import serializers
from .models import Task, Note, User
from users.models import Profile, Subscription
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

    class Meta:
        model = Profile
        # Add 'user_id' to the fields list
        fields = ['id', 'user_id', 'username', 'role', 'assigned_supervisor', 'is_on_leave']

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