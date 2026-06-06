from django.db import models
from django.contrib.auth.models import User
import json

class StudyMaterial(models.Model):
    """Stores metadata about documents uploaded by the student or admins, classified by tier."""
    
    TIER_CHOICES = [
        ('ENTRANCE', 'Entrance Exam Prep'),
        ('SCHOOL_KERALA', 'School - Kerala State Syllabus'),
        ('SCHOOL_CBSE', 'School - CBSE'),
        ('UG', 'Undergraduate (UG) Course'),
        ('PG', 'Postgraduate (PG) Course'),
        ('OTHER', 'General / Other Resource'),
    ]

    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='textbooks/')
    extracted_text = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    education_tier = models.CharField(
        max_length=30, 
        choices=TIER_CHOICES, 
        default='ENTRANCE',
        help_text="Categorizes this document's educational track"
    )
    grade_or_semester = models.CharField(
        max_length=100, 
        blank=True, 
        null=True, 
        help_text="e.g., 'Class 5', 'Class 10', 'BCA Semester 3', 'MSc Physics Semester 1'"
    )
    subject = models.CharField(
        max_length=150, 
        blank=True, 
        null=True, 
        help_text="e.g., Mathematics, Computer Science, Biology, Chemistry, Malayalam"
    )
    course_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
        help_text="The specific program (e.g., BCA, BSc Computer Science, BCom, MCA, MSc, etc.)"
    )

    @property
    def safe_url(self):
        """
        Guarantees file URL resolution without ever throwing a NoneType error.
        If the Django storage engine is misconfigured, it manually constructs a string path.
        """
        if not self.file or not self.file.name:
            return ""
        try:
            return self.file.url
        except Exception:
            clean_name = self.file.name
            if clean_name.startswith('textbooks/'):
                return f"/textbooks/{clean_name[10:]}"
            return f"/textbooks/{clean_name}"

    def __str__(self):
        return f"[{self.get_education_tier_display()}] {self.title} ({self.grade_or_semester or 'All Standards'})"


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


# ================= GAMIFICATION PROFILE MODELS =================

class StudentProfile(models.Model):
    """Stores gamified profile metrics, badges, and overall test points."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    total_points = models.IntegerField(default=0)
    badges_count = models.IntegerField(default=0)
    unlocked_badges_json = models.TextField(default="[]")  # Serialized list of dictionaries representing badges

    def add_points(self, points):
        self.total_points += points
        self.save()

    def unlock_badge(self, name, description, icon_class):
        try:
            badges = json.loads(self.unlocked_badges_json)
        except Exception:
            badges = []
        
        # Avoid duplicate badges
        if not any(b['name'] == name for b in badges):
            badges.append({
                'name': name,
                'description': description,
                'icon': icon_class
            })
            self.unlocked_badges_json = json.dumps(badges)
            self.badges_count = len(badges)
            self.save()
            return True
        return False

    @property
    def badge_list(self):
        try:
            return json.loads(self.unlocked_badges_json)
        except Exception:
            return []

    def __str__(self):
        return f"{self.user.username} - {self.total_points} Points"


class MockTestAttempt(models.Model):
    """Records the history of completed dynamic mock examinations."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mock_attempts')
    exam_name = models.CharField(max_length=150)  # e.g. 'LBS MCA Entrance Exam'
    score = models.IntegerField()
    total_questions = models.IntegerField()
    percentage = models.FloatField()
    points_earned = models.IntegerField(default=0)
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.exam_name} ({self.score}/{self.total_questions})"