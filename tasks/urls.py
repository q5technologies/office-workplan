from django.urls import path
from .views import TaskListCreateView, NoteCreateView, TaskRetrieveUpdateDestroyView, supervisor_report_view, SupervisorRatingView

urlpatterns = [
    path('tasks/', TaskListCreateView.as_view(), name='task-list'),
    path('tasks/<int:pk>/', TaskRetrieveUpdateDestroyView.as_view(), name='task-detail'),
    path('notes/', NoteCreateView.as_view(), name='note-create'),
    path('supervisor-report/', supervisor_report_view, name='supervisor-report'),
    path('supervisor-ratings/', SupervisorRatingView.as_view(), name='supervisor-ratings'),
]