from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.core.files.storage import FileSystemStorage
from django.core.files.base import ContentFile
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import login as django_login, update_session_auth_hash
from django.conf import settings
from quizzes.models import StudyMaterial, Question, StudentPerformance, StudentProfile, MockTestAttempt
from quizzes.ai_engine import extract_text_from_pdf, generate_ai_quiz
import requests
import json
import base64
import random

def landing_page(request):
    return render(request, 'landing.html')


def get_or_create_profile(user):
    """Helper to ensure every user has a profile with default badges."""
    if not user or user.is_anonymous:
        return None
    profile, created = StudentProfile.objects.get_or_create(user=user)
    if created:
        profile.unlock_badge(
            "Novice Scholar", 
            "Joined the elite Aethel Study League.", 
            "fa-solid fa-seedling text-success"
        )
    return profile


def auth_portal(request):
    """
    Handles student registration and login sessions.
    Automatically provisions gamification profiles.
    """
    if request.method == 'POST':
        username = request.POST.get('username') or request.POST.get('name') or request.POST.get('signUpName') or 'Student User'
        email = request.POST.get('email') or request.POST.get('loginEmail') or request.POST.get('signUpEmail') or 'student@lbsmca.in'
        password = request.POST.get('password') or request.POST.get('loginPassword') or request.POST.get('signUpPassword') or 'temporary_password_123'
        
        request.session['profile_full_name'] = username
        request.session['profile_email'] = email
        
        try:
            user_obj = User.objects.filter(email=email).first()
            if not user_obj:
                user_obj = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=username
                )
                messages.success(request, f"Welcome to Aethel, {username}! Account created.")
            else:
                if not user_obj.check_password(password):
                    messages.error(request, "Incorrect password. Please try again.")
                    return render(request, 'auth.html')
                
                user_obj.first_name = username
                user_obj.save()
                messages.success(request, f"Welcome back, {username}! Signed in.")
            
            django_login(request, user_obj)
            get_or_create_profile(user_obj) # Set up gamification profile
        except Exception as e:
            print(f"Auth logging exception: {e}")
            messages.success(request, f"Welcome back, {username}!")
            
        return redirect('dashboard')
        
    return render(request, 'auth.html')


def dashboard(request):
    performances = StudentPerformance.objects.all()
    profile = get_or_create_profile(request.user) if request.user.is_authenticated else None
    
    context = {
        'active_nav': 'dashboard',
        'performances': performances,
        'profile': profile
    }
    return render(request, 'dashboard.html', context)


# ================= GUEST REDIRECT FALLBACK =================

def courses(request):
    """
    Fallback view to satisfy legacy routing and import requirements in urls.py.
    Automatically redirects students to the active Mock Test Arena.
    """
    return redirect('mock_tests')


# ================= GAMIFIED LEADERBOARD VIEW =================

def leaderboard_view(request):
    """
    Renders top performing students in descending order based on earned total points.
    Creates structured dummy candidates if the database is newly initialized.
    """
    # Ensure current user has a profile
    if request.user.is_authenticated:
        get_or_create_profile(request.user)

    # 1. Self-provision competitive dummy candidates on empty database
    dummy_names = [
        ("Sujith P S", 480, [("NIMCET Conqueror", "fa-solid fa-fire text-danger")]),
        ("Anjali Krishna", 420, [("Math Specialist", "fa-solid fa-calculator text-primary")]),
        ("Rohit Nair", 350, [("Sprint King", "fa-solid fa-bolt text-warning")]),
        ("Sneha Jose", 290, [("SCERT Topper", "fa-solid fa-medal text-success")]),
        ("Gautham V", 180, [("Fast Learner", "fa-solid fa-rocket text-info")])
    ]

    for username, pts, badges in dummy_names:
        email = f"{username.lower().replace(' ', '')}@lbsmca.in"
        d_user, created = User.objects.get_or_create(username=email, defaults={'email': email, 'first_name': username})
        if created:
            d_user.set_password("dummyPass123!")
            d_user.save()
        
        d_profile, p_created = StudentProfile.objects.get_or_create(user=d_user)
        if p_created or d_profile.total_points == 0:
            d_profile.total_points = pts
            d_profile.save()
            # Unlock default badges
            for b_name, b_icon in badges:
                d_profile.unlock_badge(b_name, "Awarded for mock test performance.", b_icon)

    # 2. Fetch all profiles sorted in decreasing order of points
    leaderboard_profiles = StudentProfile.objects.all().order_by('-total_points')

    context = {
        'active_nav': 'leaderboard',
        'leaderboard': leaderboard_profiles,
    }
    return render(request, 'leaderboard.html', context)


# ================= DYNAMIC MOCK TESTS SYSTEM =================

def mock_tests_view(request):
    """
    Handles launching, conducting, and evaluating structured mock tests.
    Generates dynamic syllabus-aligned questions on demand using Gemini REST.
    """
    if not request.user.is_authenticated:
        messages.warning(request, "Please sign in to attempt Mock Exams and earn ranks.")
        return redirect('auth_portal')

    profile = get_or_create_profile(request.user)

    # 1. Detect target exam or default standard
    target_exam = request.session.get('target_exam', 'lbs_mca')
    exam_names = {
        'lbs_mca': 'LBS MCA Entrance Exam',
        'cusat_cat': 'CUSAT CAT MCA Entrance',
        'nimcet': 'NIMCET Common Entrance',
        'class_10_kerala': 'Kerala SSLC Class 10 Board',
        'class_10_cbse': 'CBSE Class 10 Board'
    }
    active_exam_name = exam_names.get(target_exam, 'LBS MCA Entrance Exam')

    # 2. Handle Test Initiation (Launch API request to draft fresh questions)
    if request.method == 'POST' and request.POST.get('action') == 'generate_mock':
        api_key = getattr(settings, "AI_API_KEY", "")
        if not api_key:
            return JsonResponse({'error': 'AI Key missing. Contact site admin.'}, status=500)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        prompt = f"""
        You are "Aethel Exam Board". Generate exactly 10 high-quality multiple choice questions (MCQs)
        for a timed mock test matching the actual syllabus of: {active_exam_name}.
        
        Include balanced questions covering core syllabus topics (e.g. Mathematics, Computer Science, or Board syllabus).
        Make sure the questions are challenging and clear.
        """

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "questions": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "id": {"type": "INTEGER"},
                                    "question_text": {"type": "STRING"},
                                    "option_a": {"type": "STRING"},
                                    "option_b": {"type": "STRING"},
                                    "option_c": {"type": "STRING"},
                                    "option_d": {"type": "STRING"},
                                    "correct_answer": {"type": "STRING"}
                                },
                                "required": ["id", "question_text", "option_a", "option_b", "option_c", "option_d", "correct_answer"]
                            }
                        }
                    },
                    "required": ["questions"]
                },
                "temperature": 0.4
            }
        }

        try:
            response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
            if response.status_code != 200:
                return JsonResponse({'error': f"Gemini REST Error: {response.text}"}, status=500)
                
            res_data = response.json()
            questions_text = res_data['candidates'][0]['content']['parts'][0]['text']
            
            # Save raw questions inside the student session to evaluate upon submission securely
            request.session['active_mock_questions'] = questions_text
            request.session['active_mock_exam_name'] = active_exam_name
            
            return JsonResponse({'success': True, 'data': json.loads(questions_text)})
        except Exception as e:
            return JsonResponse({'error': f"Connection Error: {str(e)}"}, status=500)

    # 3. Handle Test Evaluation and Submission
    if request.method == 'POST' and request.POST.get('action') == 'submit_mock':
        raw_questions = request.session.get('active_mock_questions', '')
        saved_exam_name = request.session.get('active_mock_exam_name', active_exam_name)
        
        if not raw_questions:
            return JsonResponse({'error': 'No active exam session was found. Please restart.'}, status=400)
            
        try:
            questions_data = json.loads(raw_questions).get('questions', [])
            user_answers = json.loads(request.POST.get('answers', '{}'))
            
            correct_count = 0
            evaluated_details = []
            
            for q in questions_data:
                q_id = str(q['id'])
                selected = user_answers.get(q_id, '').strip().upper()
                correct = q['correct_answer'].strip().upper()
                
                is_correct = (selected == correct)
                if is_correct:
                    correct_count += 1
                    
                evaluated_details.append({
                    'question_text': q['question_text'],
                    'option_a': q['option_a'],
                    'option_b': q['option_b'],
                    'option_c': q['option_c'],
                    'option_d': q['option_d'],
                    'correct': correct,
                    'selected': selected,
                    'is_correct': is_correct
                })
                
            total_q = len(questions_data)
            percentage = round((correct_count / total_q) * 100, 1) if total_q > 0 else 0
            
            # Points Award System: 15 points per correct answer!
            points_earned = correct_count * 15
            profile.add_points(points_earned)
            
            # Dynamic Badge Engine
            unlocked_badges = []
            if percentage >= 90:
                unlocked = profile.unlock_badge(
                    "Centum Master", 
                    "Scored 90%+ in a dynamic competitive mock exam.", 
                    "fa-solid fa-crown text-warning"
                )
                if unlocked: unlocked_badges.append("Centum Master")
            if correct_count >= 5:
                unlocked = profile.unlock_badge(
                    "Syllabus Conqueror", 
                    "Passed a comprehensive board blueprint test.", 
                    "fa-solid fa-shield-halved text-primary"
                )
                if unlocked: unlocked_badges.append("Syllabus Conqueror")
                
            # Log the attempt
            MockTestAttempt.objects.create(
                user=request.user,
                exam_name=saved_exam_name,
                score=correct_count,
                total_questions=total_q,
                percentage=percentage,
                points_earned=points_earned
            )
            
            # Clear current session questions
            if 'active_mock_questions' in request.session:
                del request.session['active_mock_questions']
                
            return JsonResponse({
                'success': True,
                'score': correct_count,
                'total': total_q,
                'percentage': percentage,
                'points_earned': points_earned,
                'unlocked_badges': unlocked_badges,
                'details': evaluated_details
            })
            
        except Exception as e:
            return JsonResponse({'error': f"Submission Evaluation failed: {str(e)}"}, status=500)

    # 4. Normal render of the screen showing past records
    past_attempts = MockTestAttempt.objects.filter(user=request.user).order_by('-completed_at')
    
    context = {
        'active_nav': 'mock_tests',
        'active_exam_name': active_exam_name,
        'profile': profile,
        'attempts': past_attempts,
    }
    return render(request, 'mock_tests.html', context)


# ================= OTHER VIEWS (UNTOUCHED CORE FEATURES) =================

def ai_lab(request):
    if request.method == 'POST' and request.FILES.get('lecture_file'):
        uploaded_file = request.FILES['lecture_file']
        education_tier = request.POST.get('education_tier', 'OTHER')
        grade_or_semester = request.POST.get('grade_or_semester', '').strip()
        subject = request.POST.get('subject', '').strip()
        course_name = request.POST.get('course_name', '').strip()
        custom_title = request.POST.get('title', '').strip()

        final_title = custom_title if custom_title else uploaded_file.name.replace(".pdf", "")
        fs = FileSystemStorage()
        filename = fs.save(f"textbooks/{uploaded_file.name}", uploaded_file)
        file_path = fs.path(filename)
        
        material = StudyMaterial.objects.create(
            title=final_title,
            file=filename,
            education_tier=education_tier,
            grade_or_semester=grade_or_semester,
            subject=subject,
            course_name=course_name
        )
        material.extracted_text = extract_text_from_pdf(file_path)
        material.save()
        
        success, error_message = generate_ai_quiz(material.id)
        if success:
            messages.success(request, f"'{final_title}' successfully uploaded! AI Quiz generated.")
            return redirect('take_quiz', material_id=material.id)
        else:
            messages.error(request, f"Material uploaded but quiz generation failed: {error_message}")
            return redirect('mock_tests')
            
    return render(request, 'ai_lab.html', {'active_nav': 'ai_lab'})


def take_quiz(request, material_id):
    material = get_object_or_404(StudyMaterial, id=material_id)
    questions = material.questions.all()
    
    if request.method == 'POST':
        score = 0
        for q in questions:
            user_ans = request.POST.get(f"question_{q.id}")
            perf, created = StudentPerformance.objects.get_or_create(
                user=request.user if request.user.is_authenticated else None,
                concept_tag=q.concept_tag
            )
            perf.total_count += 1
            if user_ans == q.correct_answer:
                score += 1
                perf.correct_count += 1
            perf.save()
        messages.success(request, f"Quiz submitted successfully! Performance logged.")
        return redirect('analytics')

    return render(request, 'quiz_page.html', {'material': material, 'questions': questions})


def analytics(request):
    performances = StudentPerformance.objects.all()
    return render(request, 'analytics.html', {'active_nav': 'analytics', 'performances': performances})


def profile_view(request):
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        if form_type == 'update_password':
            current_pwd = request.POST.get('current_password')
            new_pwd = request.POST.get('new_password')
            re_new_pwd = request.POST.get('re_new_password')
            
            if new_pwd != re_new_pwd:
                messages.error(request, "New passwords do not match.")
                return redirect('profile')
            
            if request.user.is_authenticated:
                if not request.user.check_password(current_pwd):
                    messages.error(request, "Incorrect current password.")
                    return redirect('profile')
                request.user.set_password(new_pwd)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, "Password updated successfully!")
            return redirect('profile')
        else:
            full_name = request.POST.get('full_name')
            email = request.POST.get('email')
            prep_track = request.POST.get('prep_track')
            education_level = request.POST.get('education_level', 'ug')
            
            request.session['profile_full_name'] = full_name
            request.session['profile_email'] = email
            request.session['target_exam'] = prep_track
            request.session['education_level'] = education_level
            
            if request.user.is_authenticated:
                request.user.first_name = full_name
                request.user.email = email
                request.user.save()
            messages.success(request, "Successfully saved profile settings!")
            return redirect('profile')

    total_uploaded = StudyMaterial.objects.count()
    completed_performances = StudentPerformance.objects.all()
    context = {
        'active_nav': 'profile',
        'total_uploaded': total_uploaded,
        'completed_performances': completed_performances,
        'current_prep_track': request.session.get('target_exam', 'lbs_mca'),
    }
    return render(request, 'profile.html', context)


def simplify_notes_api(request):
    """
    API Endpoint: Simplifies complex curriculum note structures for students on demand
    using the highly stable HTTP/1.1 REST API model.
    """
    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            notes_text = body.get('text', '')
            grade = body.get('grade', 'Class 10')
            
            if not notes_text:
                return JsonResponse({'error': 'No study guide text was provided.'}, status=400)
                
            api_key = getattr(settings, "AI_API_KEY", "")
            if not api_key:
                return JsonResponse({'error': 'AI configuration key is missing.'}, status=500)
                
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            prompt = f"""
            You are "Aethel Simplified Explainer". Take the following complex study notes segment 
            and explain it in highly intuitive, simplified terms suitable for a student studying in: {grade}.
            
            Use analogies, clear language, and break down complex formulas into easy-to-grasp concepts.
            Format your response clearly using standard Markdown tags.
            
            Syllabus Content to Simplify:
            ---
            {notes_text}
            """
            
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            }
            
            response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
            if response.status_code != 200:
                return JsonResponse({'error': f"Gemini API Error: {response.text}"}, status=500)
                
            res_data = response.json()
            simplified_text = res_data['candidates'][0]['content']['parts'][0]['text']
            
            return JsonResponse({
                'success': True,
                'simplified_text': simplified_text
            })
            
        except Exception as e:
            return JsonResponse({'error': f"Failed to simplify text: {str(e)}"}, status=500)
            
    return JsonResponse({'error': 'Only POST requests are allowed.'}, status=405)


def doubt_solver_view(request):
    if request.method == 'POST':
        question_text = request.POST.get('question', '')
        education_level = request.POST.get('level', 'ug')
        uploaded_image = request.FILES.get('image')

        level_map = {
            'middle_school': 'Middle School student (Class 5 to 8). Keep answers simple.',
            'high_school': 'High School student (Class 9 to 10).',
            'higher_secondary': 'Class 11 to 12 student.',
            'ug': 'Undergraduate University student.',
            'pg': 'Postgraduate Master Scholar.'
        }
        audience_directive = level_map.get(education_level, 'Undergraduate student.')

        if not question_text and not uploaded_image:
            return JsonResponse({'error': 'Please provide a query or image.'}, status=400)

        api_key = getattr(settings, "AI_API_KEY", "")
        if not api_key:
            return JsonResponse({'error': 'AI configuration key is missing.'}, status=500)

        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            prompt = f"""
            You are "Aethel AI Tutor". Assist a student at this level: {audience_directive}
            Use standard LaTeX notation ($...$ or $$...$$) for formulas.
            
            Student query: {question_text}
            """
            
            parts = [{"text": prompt}]
            
            if uploaded_image:
                image_bytes = uploaded_image.read()
                b64_image = base64.b64encode(image_bytes).decode('utf-8')
                mime = uploaded_image.content_type or "image/png"
                parts.append({
                    "inlineData": {
                        "mimeType": mime,
                        "data": b64_image
                    }
                })

            payload = {
                "contents": [{
                    "parts": parts
                }]
            }
            
            response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
            if response.status_code != 200:
                return JsonResponse({'error': f"Gemini Error: {response.text}"}, status=500)
                
            res_data = response.json()
            answer = res_data['candidates'][0]['content']['parts'][0]['text']
            return JsonResponse({'answer': answer})
        except Exception as e:
            return JsonResponse({'error': f'AI Error: {str(e)}'}, status=500)

    total_uploaded = StudyMaterial.objects.count()
    context = {
        'active_nav': 'doubt_solver',
        'total_uploaded': total_uploaded,
        'current_education_level': request.session.get('education_level', 'ug'),
    }
    return render(request, 'doubt_solver.html', context)


def study_quest_view(request):
    if request.method == 'POST':
        topic = request.POST.get('topic', 'General Science')
        education_level = request.POST.get('level', 'ug')

        level_labels = {
            'middle_school': 'Class 5 to 8. Keep it simple.',
            'high_school': 'Class 9 to 10. Core concepts.',
            'higher_secondary': 'Class 11 to 12. Physics/Math focus.',
            'ug': 'Undergrad level.',
            'pg': 'Postgraduate research level.'
        }
        audience_directive = level_labels.get(education_level, 'Undergraduate level.')

        api_key = getattr(settings, "AI_API_KEY", "")
        if not api_key:
            return JsonResponse({'error': 'AI API Key is missing.'}, status=500)

        prompt = f"""
        You are "Aethel Game Master". The topic is: "{topic}".
        Target level: {audience_directive}
        Generate the study quest dataset matching the required Schema structure.
        """
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            
            payload = {
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {
                        "type": "OBJECT",
                        "properties": {
                            "boss_name": {"type": "STRING"},
                            "boss_title": {"type": "STRING"},
                            "flashcards": {
                                "type": "ARRAY",
                                "items": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "front_prompt": {"type": "STRING"},
                                        "back_answer": {"type": "STRING"}
                                    },
                                    "required": ["front_prompt", "back_answer"]
                                }
                            },
                            "battle_questions": {
                                "type": "ARRAY",
                                "items": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "question_text": {"type": "STRING"},
                                        "option_a": {"type": "STRING"},
                                        "option_b": {"type": "STRING"},
                                        "option_c": {"type": "STRING"},
                                        "option_d": {"type": "STRING"},
                                        "correct_answer": {"type": "STRING"},
                                        "critical_explanation": {"type": "STRING"}
                                    },
                                    "required": ["question_text", "option_a", "option_b", "option_c", "option_d", "correct_answer", "critical_explanation"]
                                }
                            }
                        },
                        "required": ["boss_name", "boss_title", "flashcards", "battle_questions"]
                    },
                    "temperature": 0.4
                }
            }
            
            response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
            if response.status_code != 200:
                return JsonResponse({'error': f"Gemini Error: {response.text}"}, status=500)
                
            res_data = response.json()
            raw_text = res_data['candidates'][0]['content']['parts'][0]['text']
            return JsonResponse(json.loads(raw_text))
        except Exception as e:
            return JsonResponse({'error': f'Failed to summon Boss: {str(e)}'}, status=500)

    context = {
        'active_nav': 'study_quest',
        'current_education_level': request.session.get('education_level', 'ug'),
    }
    return render(request, 'study_quest.html', context)