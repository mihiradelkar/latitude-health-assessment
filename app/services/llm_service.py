import json
from anthropic import Anthropic
from app.utils.config import settings
from app.models.clinical_note import StructuredClinicalNote

class LLMService:
    """Service for interacting with LLMs"""
    
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.default_model
    
    async def structure_clinical_note(self, note_text: str) -> StructuredClinicalNote:
        """
        Use LLM to extract structured data from clinical note
        """
        
        prompt = f"""You are a medical data extraction expert. Extract structured information from the following clinical note.

Clinical Note:
{note_text}

Extract and return ONLY valid JSON with this exact structure:
{{
  "chief_complaint": "brief description",
  "history_present_illness": "detailed HPI",
  "past_medical_history": ["condition1", "condition2"],
  "current_medications": [
    {{
      "name": "medication name",
      "dosage": "dosage amount",
      "frequency": "frequency",
      "route": "administration route"
    }}
  ],
  "allergies": [
    {{
      "substance": "allergen",
      "reaction": "reaction type",
      "severity": "mild/moderate/severe"
    }}
  ],
  "physical_exam": "physical exam findings",
  "labs_imaging": [
    {{
      "test_name": "test name",
      "value": "result value",
      "unit": "unit",
      "reference_range": "normal range"
    }}
  ],
  "assessment_plan": "clinical assessment and plan",
  "diagnoses": [
    {{
      "code": "ICD-10 code",
      "system": "ICD-10",
      "display": "diagnosis description"
    }}
  ],
  "procedures": [
    {{
      "code": "CPT code",
      "system": "CPT",
      "display": "procedure description"
    }}
  ]
}}

Important:
- Extract ALL medications with complete details
- Include ALL diagnoses with ICD-10 codes where possible
- Include relevant lab values with units
- If information is not present in the note, use null or empty array
- Return ONLY the JSON, no additional text"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=settings.max_tokens,
                temperature=settings.temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract JSON from response
            response_text = message.content[0].text
            
            # Try to parse JSON
            structured_data = json.loads(response_text)
            
            # Create StructuredClinicalNote object
            return StructuredClinicalNote(
                raw_note=note_text,
                **structured_data
            )
            
        except json.JSONDecodeError as e:
            print(f"JSON parsing error: {e}")
            print(f"Response: {response_text}")
            raise ValueError("Failed to parse LLM response as JSON")
        except Exception as e:
            print(f"LLM service error: {e}")
            raise
    
    async def query_with_context(self, question: str, context: dict) -> dict:
        """
        Query LLM with structured context (MCP pattern)
        """
        
        prompt = f"""You are a clinical decision support expert. Answer the following question using the provided context.

Context:
{json.dumps(context, indent=2)}

Question: {question}

Provide your response as JSON with this structure:
{{
  "answer": "detailed answer",
  "reasoning": ["reason 1", "reason 2"],
  "confidence": 0.0-1.0,
  "citations": [
    {{
      "claim": "specific claim",
      "source": "where in context this comes from"
    }}
  ]
}}

Return ONLY valid JSON."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=settings.max_tokens,
                temperature=settings.temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = message.content[0].text
            return json.loads(response_text)
            
        except Exception as e:
            print(f"Query error: {e}")
            raise

# Singleton instance
llm_service = LLMService()