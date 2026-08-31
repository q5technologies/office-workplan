from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskListCreateView, NoteCreateView, TaskRetrieveUpdateDestroyView, SupervisorRatingView, supervisor_report_view
from tasks.views import supervisor_report_view
from .views import MonthlyWorkplanViewSet 

# Register the ViewSet with a router
router = DefaultRouter()
router.register(r'workplans', MonthlyWorkplanViewSet, basename='workplan')

urlpatterns = [
    path('tasks/', TaskListCreateView.as_view(), name='task-list'),
    path('tasks/<int:pk>/', TaskRetrieveUpdateDestroyView.as_view(), name='task-detail'),
    path('notes/', NoteCreateView.as_view(), name='note-create'),
    path('supervisor-report/', supervisor_report_view, name='supervisor-report'),
    path('supervisor-ratings/', SupervisorRatingView.as_view(), name='supervisor-ratings'),
    
    # Append the router URLs for the workplan endpoints
    path('', include(router.urls)),
]