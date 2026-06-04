import os
import json
import pypdf
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import List
from django.conf import settings # FIXED: Imported settings to safely read your API key
from .models import StudyMaterial, Question

# Pydantic Blueprint forces Gemini to return strict structural data profiles
class AIQuestionSchema(BaseModel):
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_answer: str # Must be A, B, C, or D
    concept_tag: str

class QuizGenerationSchema(BaseModel):
    quiz_title: str
    questions: List[AIQuestionSchema]

def extract_text_from_pdf(file_path):
    """Reads a PDF local address path and compiles the string context data."""
    text = ""
    try:
        with open(file_path, 'rb') as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        print(f"Error parsing PDF metadata: {e}")
    return text

def generate_ai_quiz(material_id):
    """Fetches text context background details and populates question structures via Gemini."""
    material = StudyMaterial.objects.get(id=material_id)
    
    if not material.extracted_text:
        return False

    # FIXED: Explicitly pass your safe configuration key from settings straight to the GenAI client init
    client = genai.Client(api_key=settings.AI_API_KEY)
    
    prompt = f"""
    You are an expert academic evaluator. Analyze the following textbook/lecture transcript notes context
    and generate a comprehensive multi-choice concept evaluation quiz based on it.
    
    Context material content source:
    ---
    {material.extracted_text[:8000]}
    ---
    
    Generate exactly 5 questions. Provide distinct concept tags for different topics found.
    The correct_answer field value must be strictly exactly one character: 'A', 'B', 'C', or 'D'.
    """

    try:
        # Call the Gemini Flash model with forced structured output configurations
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QuizGenerationSchema,
                temperature=0.3,
            ),
        )
        
        # Safely parse structural response text payload string back to native dictionary items
        data = json.loads(response.text)
        
        # Save each parsed item cleanly to the database
        for item in data['questions']:
            Question.objects.create(
                material=material,
                question_text=item['question_text'],
                option_a=item['option_a'],
                option_b=item['option_b'],
                option_c=item['option_c'],
                option_d=item['option_d'],
                correct_answer=item['correct_answer'].upper().strip(),
                concept_tag=item['concept_tag'].replace(" ", "_"),
                difficulty='MEDIUM' # Start baseline at medium difficulty
            )
        return True
    except Exception as e:
        print(f"Failed to generate or store AI content safely: {e}")
        return False