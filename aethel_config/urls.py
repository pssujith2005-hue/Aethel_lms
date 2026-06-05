from django.contrib import admin
from django.urls import path
from core.views import (
    landing_page, auth_portal, dashboard, courses, 
    ai_lab, analytics, take_quiz, profile_view, 
    doubt_solver_view, study_quest_view
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', landing_page, name='landing'),
    path('auth/', auth_portal, name='auth_portal'),
    path('dashboard/', dashboard, name='dashboard'),
    path('courses/', courses, name='courses'),
    path('ai-lab/', ai_lab, name='ai_lab'),
    path('analytics/', analytics, name='analytics'),
    path('quiz/<int:material_id>/', take_quiz, name='take_quiz'), 
    path('profile/', profile_view, name='profile'),
    path('doubt-solver/', doubt_solver_view, name='doubt_solver'),
    path('study-quest/', study_quest_view, name='study_quest'),
]