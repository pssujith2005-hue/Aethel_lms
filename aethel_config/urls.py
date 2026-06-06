from django.contrib import admin
from django.urls import path
from core import views
from core.views import (
    landing_page, auth_portal, dashboard, courses, 
    ai_lab, analytics, take_quiz, profile_view, 
    doubt_solver_view, study_quest_view
)
urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.landing_page, name='landing'),
    path('auth/', views.auth_portal, name='auth_portal'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Restructured Workspace Routes
    path('mock-tests/', views.mock_tests_view, name='mock_tests'),
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),
    
    path('ai-lab/', views.ai_lab, name='ai_lab'),
    path('quiz/<int:material_id>/', views.take_quiz, name='take_quiz'),
    path('analytics/', views.analytics, name='analytics'),
    path('profile/', views.profile_view, name='profile'),
    
    # APIs
    path('api/simplify-notes/', views.simplify_notes_api, name='simplify_notes_api'),
    path('api/doubt-solver/', views.doubt_solver_view, name='doubt_solver'),
    path('api/study-quest/', views.study_quest_view, name='study_quest'),
]