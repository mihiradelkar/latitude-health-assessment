import json
import re
from typing import Dict, List, Optional, Tuple
from anthropic import Anthropic
from app.utils.config import settings
from app.models.clinical_note import (
    StructuredClinicalNote, 
    Medication, 
    Allergy, 
    LabResult,
    ConservativeTreatment,
    ClinicalTimeline
)
import logging

logger = logging.getLogger(__name__)

class LLMService:
    """Enhanced LLM Service with medical-specific processing"""
    
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.default_model
        
        # Medical abbreviation expansions
        self.medical_abbreviations = {
            "htn": "hypertension",
            "dm": "diabetes mellitus", 
            "dm2": "type 2 diabetes mellitus",
            "cad": "coronary artery disease",
            "chf": "congestive heart failure",
            "copd": "chronic obstructive pulmonary disease",
            "gerd": "gastroesophageal reflux disease",
            "bid": "twice daily",
            "tid": "three times daily",
            "qd": "once daily",
            "prn": "as needed",
            "po": "by mouth",
            "mg": "milligrams",
            "hx": "history",
            "sx": "symptoms",
            "tx": "treatment",
            "dx": "diagnosis",
            "pt": "patient",
            "c/o": "complains of",
            "s/p": "status post",
            "r/o": "rule out",
            "w/": "with",
            "w/o": "without",
            "nsaids": "nonsteroidal anti-inflammatory drugs",
            "mi": "myocardial infarction",
            "cva": "cerebrovascular accident",
            "mvd": "mitral valve disease",
            "af": "atrial fibrillation",
            "nkda": "no known drug allergies",
            "nka": "no known allergies"
        }
        
    def _preprocess_clinical_text(self, text: str) -> str:
        """Preprocess clinical text to improve extraction"""
        # Expand abbreviations
        processed = text
        for abbr, expansion in self.medical_abbreviations.items():
            # Case-insensitive replacement with word boundaries
            pattern = r'\b' + re.escape(abbr) + r'\b'
            processed = re.sub(pattern, f"{abbr} ({expansion})", processed, flags=re.IGNORECASE)
        return processed
    
    def _extract_json_from_response(self, text: str) -> str:
        """Extract JSON from LLM response"""
        text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
        text = text.strip()
        
        start = text.find('{')
        end = text.rfind('}')
        
        if start != -1 and end != -1:
            return text[start:end+1]
        return text
    
    async def structure_clinical_note(self, note_text: str) -> StructuredClinicalNote:
        """Enhanced clinical note extraction with validation"""
        
        # Preprocess the text
        processed_text = self._preprocess_clinical_text(note_text)
        
        # First pass: Extract with medical context
        extraction_result = await self._extract_medical_data(processed_text)
        
        # Second pass: Validate critical fields
        validated_result = await self._validate_extraction(extraction_result, processed_text)
        
        # Add confidence scores
        validated_result['confidence_scores'] = self._calculate_confidence(validated_result)
        
        # Create structured note
        return self._create_structured_note(validated_result, note_text)
    
    async def _extract_medical_data(self, text: str) -> Dict:
        """First pass: Extract medical data with focused prompts"""
        
        prompt = """You are a medical data extraction specialist. Extract structured information from this clinical note.

CLINICAL NOTE:
{text}

EXTRACTION INSTRUCTIONS:
1. Be precise - extract exactly what's written, don't infer
2. For medications: include drug name, dose, frequency, route
3. For diagnoses: extract both the condition name AND any ICD-10 codes mentioned
4. For procedures: extract procedure name AND any CPT codes mentioned
5. For dates/durations: preserve exact timeframes (e.g., "3 months", "6 weeks")
6. For conservative treatments: note duration for EACH modality when specified

CRITICAL: When you see patterns like:
- "Failed conservative management x 6 months including:" → The 6 months applies to ALL items listed after
- "Physical therapy (12 sessions)" → Extract both the modality AND the specifics
- "NSAIDs x 3 months" → Extract the duration explicitly

Return a JSON object with these exact fields:
````json
{{
  "chief_complaint": "exact complaint as written",
  "history_present_illness": "full HPI text",
  "symptom_duration": "extract specific duration (e.g., '3 months', '6 weeks')",
  "past_medical_history": ["condition 1", "condition 2"],
  "current_medications": [
    {{"name": "metformin", "dosage": "1000mg", "frequency": "twice daily", "route": "oral", "duration": "if mentioned"}}
  ],
  "allergies": [
    {{"substance": "penicillin", "reaction": "rash", "severity": "mild"}}
  ],
  "conservative_treatments": [
    {{
      "modality": "physical therapy",
      "details": "12 sessions",
      "duration": "3 months",
      "outcome": "failed" 
    }}
  ],
  "physical_exam": "exam findings text",
  "labs_imaging": [
    {{"test_name": "MRI lumbar spine", "value": "disc herniation L4-L5", "date": "if mentioned"}}
  ],
  "assessment_plan": "full assessment and plan",
  "diagnoses": [
    {{"code": "M54.5", "system": "ICD-10", "display": "Low back pain"}}
  ],
  "procedures_requested": [
    {{"code": "62323", "system": "CPT", "display": "Epidural injection"}}
  ],
  "clinical_timeline": {{
    "symptom_onset": "date or duration",
    "conservative_treatment_start": "date or duration",
    "conservative_treatment_duration": "total duration"
  }}
}}
```""".format(text=text[:3500])  # Limit text to avoid token overflow
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text
            json_text = self._extract_json_from_response(response_text)
            return json.loads(json_text)
            
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            # Return minimal structure on error
            return {
                "chief_complaint": None,
                "history_present_illness": None,
                "past_medical_history": [],
                "current_medications": [],
                "conservative_treatments": [],
                "diagnoses": [],
                "procedures_requested": []
            }
    
    async def _validate_extraction(self, extraction: Dict, original_text: str) -> Dict:
        """Second pass: Validate critical fields for accuracy"""
        
        validation_prompt = """Review this extraction and verify accuracy against the original text.

ORIGINAL TEXT (excerpt):
{text}

EXTRACTION TO VALIDATE:
{extraction}

FOCUS ON:
1. Are durations correctly extracted? (e.g., "3 months" not just "months")
2. Are conservative treatments properly identified with their durations?
3. Are all medications captured with correct dosages?
4. Are diagnosis codes (ICD-10) correctly matched?

If you find errors, return the corrected JSON. If the extraction is accurate, return it unchanged.
Pay special attention to:
- Duration arithmetic (3 months = 12 weeks = 90 days)
- Treatment timelines
- Medication dosages

Return ONLY the JSON object.""".format(
            text=original_text[:1500],
            extraction=json.dumps(extraction, indent=2)
        )
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                temperature=0.1,
                messages=[{"role": "user", "content": validation_prompt}]
            )
            
            response_text = message.content[0].text
            json_text = self._extract_json_from_response(response_text)
            return json.loads(json_text)
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return extraction  # Return original if validation fails
    
    def _calculate_confidence(self, data: Dict) -> Dict[str, float]:
        """Calculate confidence scores for each section"""
        
        confidence = {}
        
        # Chief complaint - high confidence if present and specific
        if data.get('chief_complaint'):
            cc_text = data['chief_complaint'].lower()
            if any(word in cc_text for word in ['pain', 'discomfort', 'weakness', 'numbness']):
                confidence['chief_complaint'] = 0.95
            else:
                confidence['chief_complaint'] = 0.85
        else:
            confidence['chief_complaint'] = 0.0
        
        # Medications - check for complete information
        if data.get('current_medications'):
            complete_meds = sum(
                1 for med in data['current_medications']
                if med.get('name') and med.get('dosage')
            )
            confidence['medications'] = complete_meds / len(data['current_medications']) if data['current_medications'] else 0
        else:
            confidence['medications'] = 0.0
        
        # Conservative treatments - critical for prior auth
        if data.get('conservative_treatments'):
            treatments_with_duration = sum(
                1 for tx in data['conservative_treatments']
                if tx.get('duration') or tx.get('details')
            )
            confidence['conservative_treatments'] = treatments_with_duration / len(data['conservative_treatments'])
        else:
            confidence['conservative_treatments'] = 0.0
        
        # Diagnoses
        if data.get('diagnoses'):
            coded_diagnoses = sum(1 for dx in data['diagnoses'] if dx.get('code'))
            confidence['diagnoses'] = coded_diagnoses / len(data['diagnoses']) if data['diagnoses'] else 0
        else:
            confidence['diagnoses'] = 0.0
        
        # Overall confidence
        confidence['overall'] = sum(confidence.values()) / len(confidence) if confidence else 0.0
        
        return confidence
    
    def _create_structured_note(self, data: Dict, original_text: str) -> StructuredClinicalNote:
        """Create final structured note with all extracted data"""

        # Convert medications to Medication objects
        medications = []
        for med in data.get('current_medications', []):
            medications.append(Medication(**med))

        # Convert allergies to Allergy objects
        allergies = []
        for allergy in data.get('allergies', []):
            allergies.append(Allergy(**allergy))

        # Convert labs to LabResult objects
        labs = []
        for lab in data.get('labs_imaging', []):
            labs.append(LabResult(
                test_name=lab.get('test_name'),
                value=lab.get('value', ''),
                unit=lab.get('unit'),
                reference_range=lab.get('reference_range'),
                date=lab.get('date')
            ))

        # Convert conservative treatments to ConservativeTreatment objects
        conservative_treatments = []
        for tx in data.get('conservative_treatments', []):
            conservative_treatments.append(ConservativeTreatment(
                modality=tx.get('modality'),
                details=tx.get('details'),
                duration=tx.get('duration'),
                duration_weeks=tx.get('duration_weeks'),
                sessions=tx.get('sessions'),
                outcome=tx.get('outcome')
            ))

        # Create clinical timeline
        timeline_data = data.get('clinical_timeline', {})
        clinical_timeline = ClinicalTimeline(
            symptom_onset=timeline_data.get('symptom_onset'),
            conservative_treatment_start=timeline_data.get('conservative_treatment_start'),
            conservative_treatment_duration=timeline_data.get('conservative_treatment_duration'),
            total_duration_weeks=timeline_data.get('total_duration_weeks')
        ) if timeline_data else None

        # Calculate confidence scores
        confidence_scores = data.get('confidence_scores', {})
        if not confidence_scores:
            confidence_scores = self._calculate_confidence(data)

        note = StructuredClinicalNote(
            raw_note=original_text,
            chief_complaint=data.get('chief_complaint'),
            history_present_illness=data.get('history_present_illness'),
            past_medical_history=data.get('past_medical_history', []),
            current_medications=medications,
            allergies=allergies,
            physical_exam=data.get('physical_exam'),
            labs_imaging=labs,
            assessment_plan=data.get('assessment_plan'),
            diagnoses=data.get('diagnoses', []),
            procedures=data.get('procedures_requested', []),
            symptom_duration=data.get('symptom_duration'),
            conservative_treatments=conservative_treatments,
            clinical_timeline=clinical_timeline,
            confidence_scores=confidence_scores
        )

        logger.info(f"Extraction confidence: {confidence_scores.get('overall', 0):.2%}")

        return note
    
    async def query_with_context(self, question: str, context: dict) -> dict:
        """Query LLM with structured context - used by MCP"""
        # Keep your existing implementation but we'll improve it next
        return await self._query_with_improved_context(question, context)
    
    async def _query_with_improved_context(self, question: str, context: dict) -> dict:
        """Improved context querying with better structure"""
        
        # We'll enhance this in the next step
        prompt = f"""You are a clinical decision support expert. Answer based on the provided context.

CONTEXT:
{json.dumps(context, indent=2)}

QUESTION: {question}

Return a JSON response with:
{{
  "final_decision": "approved" | "denied" | "needs_more_info",
  "confidence": 0.0-1.0,
  "reasoning": ["reason 1", "reason 2"],
  "evidence": {{"key_finding": "supporting evidence"}},
  "missing_info": ["if any"]
}}"""
        
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text
            json_text = self._extract_json_from_response(response_text)
            return json.loads(json_text)
            
        except Exception as e:
            logger.error(f"Context query error: {e}")
            return {
                "final_decision": "needs_more_info",
                "confidence": 0.0,
                "reasoning": ["Error processing request"],
                "evidence": {},
                "missing_info": ["Unable to process"]
            }

# Singleton instance
llm_service = LLMService()