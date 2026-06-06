import os
import json
import fitz  # PyMuPDF
import requests
from django.conf import settings
from .models import StudyMaterial, Question

def extract_text_from_pdf(pdf_path):
    """Extracts raw text content from local PDF textbooks."""
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text

def generate_ai_quiz(material_id):
    """
    Generates 5 multiple choice questions based on study materials
    using the highly stable Gemini REST API instead of the gRPC client.
    """
    try:
        material = StudyMaterial.objects.get(id=material_id)
        if not material.extracted_text:
            return False, "No extracted text found in study material."

        # Fetch embedded API key from Django settings
        api_key = getattr(settings, "AI_API_KEY", "") or os.environ.get("AI_API_KEY", "")
        if not api_key:
            return False, "Gemini API key is not configured inside settings.py."

        # Direct REST endpoint bypasses local gRPC socket hanging issues
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        
        prompt = f"""
        Analyze the following educational text and generate exactly 5 high-quality multiple choice questions (MCQs) 
        testing different concepts from the text.
        
        Educational Text:
        {material.extracted_text[:8000]}
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
                                    "question_text": {"type": "STRING"},
                                    "option_a": {"type": "STRING"},
                                    "option_b": {"type": "STRING"},
                                    "option_c": {"type": "STRING"},
                                    "option_d": {"type": "STRING"},
                                    "correct_answer": {"type": "STRING"},
                                    "concept_tag": {"type": "STRING"},
                                    "difficulty": {"type": "STRING"}
                                },
                                "required": ["question_text", "option_a", "option_b", "option_c", "option_d", "correct_answer", "concept_tag", "difficulty"]
                            }
                        }
                    },
                    "required": ["questions"]
                },
                "temperature": 0.3
            }
        }
        
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=25)
        
        if response.status_code != 200:
            return False, f"Gemini API returned status {response.status_code}: {response.text}"
            
        res_data = response.json()
        raw_text = res_data['candidates'][0]['content']['parts'][0]['text']
        
        data = json.loads(raw_text)
        for q_data in data.get('questions', []):
            Question.objects.create(
                material=material,
                question_text=q_data['question_text'],
                option_a=q_data['option_a'],
                option_b=q_data['option_b'],
                option_c=q_data['option_c'],
                option_d=q_data['option_d'],
                correct_answer=q_data['correct_answer'].strip().upper()[:1],
                concept_tag=q_data['concept_tag'],
                difficulty=q_data['difficulty'].upper()
            )
        return True, None
    except Exception as e:
        return False, str(e)