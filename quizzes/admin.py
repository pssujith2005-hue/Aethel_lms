from django.contrib import admin
from .models import StudyMaterial, Question, StudentPerformance

admin.site.register(StudyMaterial)
admin.site.register(Question)
admin.site.register(StudentPerformance)