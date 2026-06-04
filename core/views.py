from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.core.files.storage import FileSystemStorage
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth import login as django_login
from django.conf import settings
from quizzes.models import StudyMaterial, Question, StudentPerformance
from quizzes.ai_engine import extract_text_from_pdf, generate_ai_quiz
from google import genai
from google.genai import types
from PIL import Image
import os

def landing_page(request):
    return render(request, 'landing.html')

def auth_portal(request):
    if request.method == 'POST':
        username = request.POST.get('username') or request.POST.get('name') or request.POST.get('signUpName') or 'Student User'
        email = request.POST.get('email') or request.POST.get('loginEmail') or request.POST.get('signUpEmail') or 'student@lbsmca.in'
        
        request.session['profile_full_name'] = username
        request.session['profile_email'] = email
        
        try:
            user_obj = User.objects.filter(email=email).first()
            if not user_obj:
                user_obj = User.objects.create_user(
                    username=email,
                    email=email,
                    password='temporary_password_123',
                    first_name=username
                )
            else:
                user_obj.first_name = username
                user_obj.save()
            django_login(request, user_obj)
        except Exception as e:
            print(f"Auth logging exception: {e}")
            
        messages.success(request, f"Welcome back, {username}! Signed in successfully.")
        return redirect('dashboard')
        
    return render(request, 'auth.html')

def dashboard(request):
    performances = StudentPerformance.objects.all()
    full_name = request.session.get('profile_full_name', 'Student User')
    email = request.session.get('profile_email', 'student@lbsmca.in')
    
    context = {
        'active_nav': 'dashboard',
        'performances': performances,
        'profile_name': full_name,
        'profile_email': email,
    }
    return render(request, 'dashboard.html', context)

def courses(request):
    materials = StudyMaterial.objects.all()
    
    exam_database = {
        'lbs_mca': {
            'name': 'LBS MCA Entrance Exam',
            'official_url': 'https://lbscentre.kerala.gov.in/',
            'brief_info': 'The state-level entrance exam conducted by LBS Centre for Science & Technology for admission to Master of Computer Applications (MCA) courses across Kerala.',
            'pattern': '120 MCQs to be completed in 120 minutes. No negative marking.',
            'syllabus': {
                'Mathematics': ['Matrices & Determinants', 'Set Theory', 'Trigonometry', 'Probability & Statistics'],
                'Computer Science': ['Binary Arithmetic', 'Basic Logic Gates', 'C Programming', 'Data Structures Basics'],
                'Logical Reasoning': ['Coding-Decoding', 'Series Completion', 'Blood Relations', 'Syllogisms']
            },
            'materials': [
                {'title': 'LBS MCA Official Syllabus Blueprint', 'category': 'Syllabus', 'icon': 'fa-file-pdf', 'file_url': '#'},
                {'title': 'Ultimate Maths & Stats Cheat Sheet', 'category': 'Formula Guide', 'icon': 'fa-arrow-down-long', 'file_url': '#'}
            ]
        },
        'cusat_cat': {
            'name': 'CUSAT CAT MCA Entrance',
            'official_url': 'https://admissions.cusat.ac.in/',
            'brief_info': 'Conducted by Cochin University of Science and Technology for admitting top-tier talents to their flagship MCA programme.',
            'pattern': '150 Multiple Choice Questions focusing heavily on Advanced Mathematics (60%), Computer Awareness, and Logical Reasoning.',
            'syllabus': {
                'Advanced Mathematics': ['Coordinate Geometry', 'Three-Dimensional Space', 'Limits & Continuity', 'Integration', 'Vectors'],
                'Computer Concepts': ['Data Representation', 'Basic Computer Organization', 'High-Level Programming Concepts']
            },
            'materials': [
                {'title': 'CUSAT CAT MCA Study Plan & Guide', 'category': 'Prep Blueprint', 'icon': 'fa-file-pdf', 'file_url': '#'}
            ]
        },
        'nimcet': {
            'name': 'NIMCET (NIT MCA Common Entrance)',
            'official_url': 'https://www.nimcet.in/',
            'brief_info': 'The national-level entrance test for admission to the master of computer applications (MCA) program offered at participating National Institutes of Technology (NITs).',
            'pattern': '120 MCQs (Maths: 50, Analytical Ability: 40, Computer Awareness: 10, English: 20). Scoring: +4, -1.',
            'syllabus': {
                'Mathematics': ['Set Theory, Relations & Functions', 'Algebra', 'Coordinate Geometry & Vectors', 'Calculus'],
                'Computer Awareness': ['Integer representation', 'Venn Diagrams & Boolean Algebra', 'Logic Gates circuits']
            },
            'materials': [
                {'title': 'NIMCET Crackers Strategy Playbook', 'category': 'Study Guide', 'icon': 'fa-compass', 'file_url': '#'}
            ]
        }
    }

    selected_exam = request.GET.get('exam', request.session.get('target_exam', 'lbs_mca'))
    if selected_exam not in exam_database:
        selected_exam = 'lbs_mca'
    
    request.session['target_exam'] = selected_exam
    
    context = {
        'active_nav': 'courses',
        'materials': materials,
        'exam_data': exam_database[selected_exam],
        'selected_exam_key': selected_exam,
    }
    return render(request, 'courses.html', context)

def ai_lab(request):
    if request.method == 'POST' and request.FILES.get('lecture_file'):
        uploaded_file = request.FILES['lecture_file']
        
        fs = FileSystemStorage()
        filename = fs.save(f"textbooks/{uploaded_file.name}", uploaded_file)
        file_path = fs.path(filename)
        
        material = StudyMaterial.objects.create(
            title=uploaded_file.name.replace(".pdf", ""),
            file=filename
        )
        
        material.extracted_text = extract_text_from_pdf(file_path)
        material.save()
        
        success, error_message = generate_ai_quiz(material.id)
        if success:
            messages.success(request, "Quiz successfully generated by Aethel.ai!")
            return redirect('take_quiz', material_id=material.id)
        else:
            messages.error(request, error_message)
            
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
            
        messages.success(request, f"Successfully saved profile settings!")
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


def doubt_solver_view(request):
    """
    Renders the dynamic Doubt Solver page and processes multimodal queries.
    Uses genai.Client with the saved API key to handle text + images.
    """
    if request.method == 'POST':
        # Check if the request is an AJAX/Fetch API message submission
        question_text = request.POST.get('question', '')
        education_level = request.POST.get('level', 'ug') # Grab active educational layer
        uploaded_image = request.FILES.get('image')

        # Map internal levels to friendly academic labels for the system prompt
        level_map = {
            'middle_school': 'Middle School student (Class 5 to 8). Keep answers clear, supportive, use simple words, and avoid overly dense notation.',
            'high_school': 'High School student (Class 9 to 10). Explain the logical basis and formulas step-by-step.',
            'higher_secondary': 'Higher Secondary student (Class 11 to 12). Focus on deep structural understanding and exact formulas.',
            'ug': 'Undergraduate University student. Keep it highly analytical and technical.',
            'pg': 'Postgraduate Master Scholar. Provide rigorous academic proofs, structural details, and professional references.'
        }
        audience_directive = level_map.get(education_level, 'Undergraduate student.')

        if not question_text and not uploaded_image:
            return JsonResponse({'error': 'Please provide either a question or an image.'}, status=400)

        if not settings.AI_API_KEY:
            return JsonResponse({'error': 'AI configuration settings key is missing. Please add AI_API_KEY to your .env file.'}, status=500)

        try:
            # Initialize Gemini
            client = genai.Client(api_key=settings.AI_API_KEY)
            
            prompt = f"""
            You are "Aethel AI Tutor", a highly compassionate, world-class personal teacher.
            You are assisting a student at the following tier level: {audience_directive}

            Provide a clear, detailed, and beautifully structured explanation.
            If the question contains mathematical equations, use standard LaTeX notation (like $...$ for inline or $$...$$ for block formulas).
            Be encouraging! If an image is provided, examine it carefully to extract text, handwritten notes, diagrams, or questions.
            
            Student's question: {question_text}
            """

            contents = [prompt]

            # If there's an image, convert to PIL.Image and append to contents list
            if uploaded_image:
                try:
                    pil_img = Image.open(uploaded_image)
                    contents.append(pil_img)
                except Exception as img_err:
                    return JsonResponse({'error': f'Failed to process the uploaded image: {str(img_err)}'}, status=400)

            # Call Gemini
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents,
            )

            return JsonResponse({'answer': response.text})

        except Exception as e:
            return JsonResponse({'error': f'AI Engine Encountered an Error: {str(e)}'}, status=500)

    # If GET, render the interactive chatbot interface page
    total_uploaded = StudyMaterial.objects.count()
    context = {
        'active_nav': 'doubt_solver',
        'total_uploaded': total_uploaded,
        'current_education_level': request.session.get('education_level', 'ug'),
    }
    return render(request, 'doubt_solver.html', context)