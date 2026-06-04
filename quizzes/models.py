from django.db import models
from django.contrib.auth.models import User

class StudyMaterial(models.Model):
    """Stores metadata about documents uploaded by the student."""
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='textbooks/')
    extracted_text = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Question(models.Model):
    """Stores AI-generated multiple-choice questions."""
    DIFFICULTY_CHOICES = [
        ('EASY', 'Easy'),
        ('MEDIUM', 'Medium'),
        ('HARD', 'Hard'),
    ]
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    option_a = models.CharField(max_length=500)
    option_b = models.CharField(max_length=500)
    option_c = models.CharField(max_length=500)
    option_d = models.CharField(max_length=500)
    correct_answer = models.CharField(max_length=1, help_text="Store as A, B, C, or D")
    concept_tag = models.CharField(max_length=100, help_text="e.g., ACID_Properties, Virtualization")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='MEDIUM')

    def __str__(self):
        return f"{self.concept_tag} ({self.difficulty}) - {self.question_text[:50]}"

# Ensure this exact class block is present at the bottom of the file
class StudentPerformance(models.Model):
    """Tracks concept mastery percentages over time to drive the adaptive engine."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    concept_tag = models.CharField(max_length=100)
    correct_count = models.IntegerField(default=0)
    total_count = models.IntegerField(default=0)

    @property
    def mastery_percentage(self):
        if self.total_count == 0:
            return 0
        return round((self.correct_count / self.total_count) * 100)

    class Meta:
        unique_together = ('user', 'concept_tag')

    def __str__(self):
        return f"{self.concept_tag} - {self.mastery_percentage}%"