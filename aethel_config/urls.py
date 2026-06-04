from django.contrib import admin
from django.urls import path
# FIXED: Added take_quiz, courses, ai_lab, and analytics to the import line
from core.views import landing_page, auth_portal, dashboard, courses, ai_lab, analytics, take_quiz

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', landing_page, name='landing'),
    path('auth/', auth_portal, name='auth_portal'),
    path('dashboard/', dashboard, name='dashboard'),
    path('courses/', courses, name='courses'),
    path('ai-lab/', ai_lab, name='ai_lab'),
    path('analytics/', analytics, name='analytics'),
    
    # FIXED: Changed <int=material_id> to <int:material_id>
    path('quiz/<int:material_id>/', take_quiz, name='take_quiz'), 
]