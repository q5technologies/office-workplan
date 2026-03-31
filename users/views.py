from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Profile # Make sure to import your Profile model

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_profile(request):
    user = request.user
    # Fetch the profile linked to this user
    profile = user.profile 
    
    return Response({
        'username': user.username,
        'email': user.email,
        'role': profile.role,  # 'HEAD', 'SUP', or 'SUB'
        'id': user.id
    })