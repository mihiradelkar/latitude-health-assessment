import json
import re
from anthropic import Anthropic
from app.utils.config import settings
from app.models.clinical_note import StructuredClinicalNote

class LLMService:
    """Service for interacting with LLMs"""
    
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.default_model
    
    def _extract_json_from_response(self, text: str) -> str:
        """
        Extract JSON from LLM response, handling markdown code blocks and extra text
        """
        # Remove markdown code blocks if present
        text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
        text = text.strip()
        
        # Try to find JSON object in the text
        # Look for content between first { and last }
        start = text.find('{')
        end = text.rfind('}')
        
        if start != -1 and end != -1:
            return text[start:end+1]
        
        return text
    
    async def structure_clinical_note(self, note_text: str) -> StructuredClinicalNote:
        """
        Use LLM to extract structured data from clinical note
        """
        
        prompt = f"""Extract structured medical information from this clinical note and return it as valid JSON.

Clinical Note:
{note_text}

Return ONLY a JSON object with this structure (no markdown, no explanations, just the JSON):
{{
  "chief_complaint": "string or null",
  "history_present_illness": "string or null",
  "past_medical_history": ["string"] or [],
  "current_medications": [
    {{
      "name": "medication name",
      "dosage": "amount with unit",
      "frequency": "how often",
      "route": "administration route or null"
    }}
  ] or [],
  "allergies": [
    {{
      "substance": "allergen",
      "reaction": "reaction type",
      "severity": "mild/moderate/severe or null"
    }}
  ] or [],
  "physical_exam": "string or null",
  "labs_imaging": [
    {{
      "test_name": "test name",
      "value": "result",
      "unit": "unit",
      "reference_range": "normal range or null"
    }}
  ] or [],
  "assessment_plan": "string or null",
  "diagnoses": [
    {{
      "code": "ICD-10 code",
      "system": "ICD-10",
      "display": "diagnosis description"
    }}
  ] or [],
  "procedures": [
    {{
      "code": "CPT code",
      "system": "CPT",
      "display": "procedure description"
    }}
  ] or []
}}

Rules:
- Return ONLY the JSON object, nothing else
- Use empty list for missing information
- Extract ICD-10 codes from diagnoses where mentioned
- Extract CPT codes from procedures where mentioned
- Parse all medications with their details"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=settings.max_tokens,
                temperature=0.1,  # Lower temperature for more consistent JSON
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract text from response
            response_text = message.content[0].text
            
            # Debug: print what we got
            # print("\n" + "="*50)
            # print("RAW LLM RESPONSE:")
            # print("="*50)
            # print(response_text[:500])  # Print first 500 chars
            # print("="*50 + "\n")
            
            # Clean and extract JSON
            json_text = self._extract_json_from_response(response_text)
            
            # print("EXTRACTED JSON:")
            # print("="*50)
            # print(json_text[:500])
            # print("="*50 + "\n")
            
            # Parse JSON
            structured_data = json.loads(json_text)
            
            # Create StructuredClinicalNote object
            result = StructuredClinicalNote(
                raw_note=note_text,
                chief_complaint=structured_data.get('chief_complaint'),
                history_present_illness=structured_data.get('history_present_illness'),
                past_medical_history=structured_data.get('past_medical_history'),
                current_medications=structured_data.get('current_medications'),
                allergies=structured_data.get('allergies'),
                physical_exam=structured_data.get('physical_exam'),
                labs_imaging=structured_data.get('labs_imaging'),
                assessment_plan=structured_data.get('assessment_plan'),
                diagnoses=structured_data.get('diagnoses'),
                procedures=structured_data.get('procedures')
            )
            
            print("✅ Successfully parsed and structured clinical note\n")
            return result
            
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON parsing error: {e}")
            # print(f"Attempted to parse: {json_text[:200]}...")
            raise ValueError(f"Failed to parse LLM response as JSON: {str(e)}")
        except Exception as e:
            print(f"\n❌ LLM service error: {e}")
            raise
    
    async def query_with_context(self, question: str, context: dict) -> dict:
        """
        Query LLM with structured context (MCP pattern)
        """
        
        prompt = f"""You are a clinical decision support expert. Answer the question using the provided context.
    
    Context:
    {json.dumps(context, indent=2)}
    
    Question: {question}
    
    Return ONLY valid JSON with this exact structure:
    {{
      "final_decision": "approved" | "denied" | "needs_more_info",
      "answer": "detailed explanation of the decision",
      "reasoning": [
        "specific reason 1",
        "specific reason 2"
      ],
      "confidence": 0.85,
      "citations": [
        {{
          "claim": "specific claim made",
          "source": "where in context this comes from (e.g., patient_data.conditions[0] or coverage_policy.coverage_criteria[1])"
        }}
      ]
    }}
    
    CRITICAL: The "final_decision" field must be EXACTLY one of these three strings:
    - "approved"
    - "denied"  
    - "needs_more_info"
    
    Return ONLY the JSON, no additional text."""
    
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=settings.max_tokens,
                temperature=0.1,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = message.content[0].text
            json_text = self._extract_json_from_response(response_text)
            result = json.loads(json_text)
            
            # Validate that final_decision exists and is valid
            if 'final_decision' not in result:
                print("⚠️  Warning: LLM didn't return final_decision, defaulting to needs_more_info")
                result['final_decision'] = 'needs_more_info'
            
            valid_decisions = {'approved', 'denied', 'needs_more_info'}
            if result['final_decision'] not in valid_decisions:
                print(f"⚠️  Warning: Invalid decision '{result['final_decision']}', defaulting to needs_more_info")
                result['final_decision'] = 'needs_more_info'
            
            return result
            
        except Exception as e:
            print(f"Query error: {e}")
            raise

# Singleton instance
llm_service = LLMService()