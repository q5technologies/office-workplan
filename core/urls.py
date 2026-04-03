"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.authtoken import views as auth_views # Added 'as auth_views'
from users.views import get_user_profile # Import the new view
from rest_framework.routers import DefaultRouter
from tasks.views import TaskViewSet, NoteCreateView, TaskListCreateView, ProfileViewSet, index_view

router = DefaultRouter()
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'profiles', ProfileViewSet, basename='profile')
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', index_view, name='index'),
    path('', include('pwa.urls')),
    path('api/', include(router.urls)), # This handles /api/tasks/ AND /api/profiles/
    path('api-token-auth/', auth_views.obtain_auth_token),
    # REMOVE THIS LINE: path('api/profile/', get_user_profile, name='user-profile'), 
    path('api-auth/', include('rest_framework.urls')),
    path('api/notes/', NoteCreateView.as_view(), name='note-create'),
    path('api/task-list/', TaskListCreateView.as_view(), name='task-list'),
]
admin.site.site_header = "Office Workplan"
admin.site.site_title = "Office Workplan Portal"
admin.site.index_title = "Welcome to the Office Workplan Administration"