from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.storage import FileSystemStorage
from django.contrib import messages
from quizzes.models import StudyMaterial, Question, StudentPerformance
from quizzes.ai_engine import extract_text_from_pdf, generate_ai_quiz

def landing_page(request):
    return render(request, 'landing.html')

def auth_portal(request):
    if request.method == 'POST':
        return redirect('dashboard')
    return render(request, 'auth.html')

def dashboard(request):
    performances = StudentPerformance.objects.all()
    context = {
        'active_nav': 'dashboard',
        'performances': performances
    }
    return render(request, 'dashboard.html', context)

def courses(request):
    materials = StudyMaterial.objects.all()
    return render(request, 'courses.html', {'active_nav': 'courses', 'materials': materials})

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
        
        extracted = extract_text_from_pdf(file_path)
        if not extracted or len(extracted.strip()) == 0:
            messages.error(request, "Failed to extract text from the PDF. Ensure it is not a scanned image.")
            return render(request, 'ai_lab.html', {'active_nav': 'ai_lab'})

        material.extracted_text = extracted
        material.save()
        
        success, error_message = generate_ai_quiz(material.id)
        if success:
            messages.success(request, "Quiz successfully generated!")
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
        return redirect('analytics')

    return render(request, 'quiz_page.html', {'material': material, 'questions': questions})

def analytics(request):
    performances = StudentPerformance.objects.all()
    return render(request, 'analytics.html', {'active_nav': 'analytics', 'performances': performances})

def profile_view(request):
    """Renders user demographic settings, targets, and allows simulated post adjustments."""
    if request.method == 'POST':
        # Simulated profile save handler
        full_name = request.POST.get('full_name')
        prep_track = request.POST.get('prep_track')
        
        # Display a success toast notification
        messages.success(request, f"Successfully saved profile settings for {full_name}!")
        return redirect('profile')

    # Fetch simple stats to populate in the summary cards
    total_uploaded = StudyMaterial.objects.count()
    completed_performances = StudentPerformance.objects.all()
    
    context = {
        'active_nav': 'profile',
        'total_uploaded': total_uploaded,
        'completed_performances': completed_performances,
    }
    return render(request, 'profile.html', context)