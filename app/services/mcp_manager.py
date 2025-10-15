# app/services/mcp_manager.py
from typing import Dict, Any, List, Optional, Tuple
import json
import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class MCPContextManager:
    """
    Enhanced Model Context Protocol Manager
    Implements smarter context building and decision logic
    """
    
    def __init__(self):
        self.context_cache = {}
        self.decision_patterns = self._load_decision_patterns()
        
    def _load_decision_patterns(self) -> Dict:
        """Load common approval/denial patterns for quick matching"""
        return {
            'auto_approve_patterns': [
                {
                    'name': 'clear_conservative_failure',
                    'conditions': [
                        'conservative_treatment_duration >= 6_weeks',
                        'multiple_modalities_tried >= 2',
                        'documented_failure == true'
                    ]
                },
                {
                    'name': 'urgent_medical_necessity',
                    'conditions': [
                        'red_flags_present == true',
                        'progressive_symptoms == true',
                        'neurological_deficits == true'
                    ]
                }
            ],
            'auto_deny_patterns': [
                {
                    'name': 'no_conservative_treatment',
                    'conditions': [
                        'conservative_treatment_duration == 0',
                        'first_line_treatment_attempted == false'
                    ]
                },
                {
                    'name': 'excluded_diagnosis',
                    'conditions': [
                        'diagnosis_in_exclusion_list == true'
                    ]
                }
            ]
        }
    
    def build_patient_context(self, fhir_bundle: Dict[str, Any]) -> Dict[str, Any]:
        """Build enhanced patient context with key indicators"""
        
        context = {
            "patient": {},
            "conditions": [],
            "medications": [],
            "procedures": [],
            "observations": [],
            "allergies": [],
            "red_flags": [],
            "treatment_timeline": {},
            "key_indicators": {}
        }
        
        # Extract from FHIR bundle
        for entry in fhir_bundle.get('entry', []):
            resource = entry.get('resource', {})
            resource_type = resource.get('resourceType')
            
            if resource_type == 'Patient':
                context['patient'] = {
                    "id": resource.get('id'),
                    "active": resource.get('active', True)
                }
            
            elif resource_type == 'Condition':
                condition = self._extract_condition(resource)
                context['conditions'].append(condition)
                
                if self._is_red_flag_condition(condition):
                    context['red_flags'].append(condition)
            
            elif resource_type == 'MedicationRequest':
                med = self._extract_medication(resource)
                context['medications'].append(med)
                
                if self._is_pain_medication(med['name']):
                    context['key_indicators']['on_pain_meds'] = True
            
            elif resource_type == 'Procedure':
                proc = self._extract_procedure(resource)
                context['procedures'].append(proc)
            
            elif resource_type == 'Observation':
                obs = self._extract_observation(resource)
                context['observations'].append(obs)
            
            elif resource_type == 'AllergyIntolerance':
                allergy = {
                    "substance": resource.get('code', {}).get('text'),
                    "reaction": None
                }
                reactions = resource.get('reaction', [])
                if reactions:
                    allergy['reaction'] = reactions[0].get('manifestation', [{}])[0].get('text')
                context['allergies'].append(allergy)
        
        # Calculate treatment timeline
        context['treatment_timeline'] = self._calculate_treatment_timeline(context)
        
        # Add key indicators
        context['key_indicators'].update({
            'has_red_flags': len(context['red_flags']) > 0,
            'condition_count': len(context['conditions']),
            'medication_count': len(context['medications']),
            'chronic_condition': self._has_chronic_condition(context['conditions'])
        })
        
        return context
    
    def _extract_condition(self, resource: Dict) -> Dict:
        """Extract condition with enhanced details"""
        code_info = resource.get('code', {}).get('coding', [{}])[0]
        return {
            "code": code_info.get('code'),
            "display": code_info.get('display') or resource.get('code', {}).get('text', ''),
            "status": resource.get('clinicalStatus', {}).get('coding', [{}])[0].get('code'),
            "onset": resource.get('onsetDateTime'),
            "severity": resource.get('severity', {}).get('coding', [{}])[0].get('code') if resource.get('severity') else None
        }
    
    def _extract_medication(self, resource: Dict) -> Dict:
        """Extract medication details"""
        med_concept = resource.get('medicationCodeableConcept', {})
        dosage_info = resource.get('dosageInstruction', [{}])[0] if resource.get('dosageInstruction') else {}
        return {
            "name": med_concept.get('text', ''),
            "dosage": dosage_info.get('text', ''),
            "status": resource.get('status'),
            "timing": dosage_info.get('timing', {}).get('repeat', {}).get('period', '')
        }
    
    def _extract_procedure(self, resource: Dict) -> Dict:
        """Extract procedure details"""
        code_info = resource.get('code', {}).get('coding', [{}])[0]
        return {
            "code": code_info.get('code'),
            "display": code_info.get('display') or resource.get('code', {}).get('text', ''),
            "status": resource.get('status'),
            "performed_date": resource.get('performedDateTime')
        }
    
    def _extract_observation(self, resource: Dict) -> Dict:
        """Extract observation details"""
        return {
            "test": resource.get('code', {}).get('text'),
            "value": resource.get('valueString'),
            "status": resource.get('status'),
            "date": resource.get('effectiveDateTime')
        }
    
    def _is_red_flag_condition(self, condition: Dict) -> bool:
        """Check if condition is a red flag requiring urgent attention"""
        red_flag_keywords = [
            'cauda equina', 'progressive neurological', 'paralysis', 
            'loss of bowel', 'loss of bladder', 'severe pain',
            'cancer', 'tumor', 'metastasis', 'fracture'
        ]
        
        display = (condition.get('display', '') or '').lower()
        return any(keyword in display for keyword in red_flag_keywords)
    
    def _is_pain_medication(self, med_name: str) -> bool:
        """Check if medication is for pain management"""
        pain_meds = [
            'ibuprofen', 'naproxen', 'meloxicam', 'celecoxib',
            'tramadol', 'gabapentin', 'pregabalin', 'duloxetine',
            'acetaminophen', 'aspirin', 'diclofenac'
        ]
        med_lower = med_name.lower()
        return any(med in med_lower for med in pain_meds)
    
    def _has_chronic_condition(self, conditions: List[Dict]) -> bool:
        """Check if patient has chronic conditions"""
        chronic_keywords = [
            'chronic', 'diabetes', 'hypertension', 'arthritis',
            'fibromyalgia', 'neuropathy', 'stenosis'
        ]
        
        for condition in conditions:
            display = (condition.get('display', '') or '').lower()
            if any(keyword in display for keyword in chronic_keywords):
                return True
        return False
    
    def _calculate_treatment_timeline(self, context: Dict) -> Dict:
        """Calculate treatment timeline from context"""
        timeline = {
            'symptom_onset': None,
            'treatment_start': None,
            'treatment_duration_weeks': 0,
            'modalities_tried': []
        }
        return timeline
    
    def build_guideline_context(self, guideline_data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced guideline context with parsed criteria"""
        
        context = {
            "title": guideline_data.get('title'),
            "coverage_criteria": guideline_data.get('coverage_criteria', []),
            "exclusion_criteria": guideline_data.get('exclusion_criteria', []),
            "required_documentation": guideline_data.get('required_documentation', []),
            "covered_icd10_codes": guideline_data.get('covered_icd10_codes', []),
            "covered_cpt_codes": guideline_data.get('covered_cpt_codes', []),
            "parsed_criteria": self._parse_criteria(guideline_data.get('coverage_criteria', []))
        }
        
        return context
    
    def _parse_criteria(self, criteria_list: List[str]) -> List[Dict]:
        """Parse criteria into structured format for better matching"""
        parsed = []
        
        for criterion in criteria_list:
            parsed_criterion = {
                'original': criterion,
                'type': self._determine_criterion_type(criterion),
                'requirements': self._extract_requirements(criterion)
            }
            parsed.append(parsed_criterion)
        
        return parsed
    
    def _determine_criterion_type(self, criterion: str) -> str:
        """Determine what type of criterion this is"""
        criterion_lower = criterion.lower()
        
        if 'conservative' in criterion_lower or 'therapy' in criterion_lower:
            return 'conservative_treatment'
        elif 'duration' in criterion_lower or 'weeks' in criterion_lower or 'months' in criterion_lower:
            return 'duration'
        elif 'document' in criterion_lower:
            return 'documentation'
        elif 'diagnosis' in criterion_lower or 'icd' in criterion_lower:
            return 'diagnosis'
        else:
            return 'other'
    
    def _extract_requirements(self, criterion: str) -> Dict:
        """Extract specific requirements from criterion text"""
        requirements = {}
        
        # Extract duration requirements
        duration_match = re.search(r'(\d+)\s*(weeks?|months?)', criterion.lower())
        if duration_match:
            num = int(duration_match.group(1))
            unit = duration_match.group(2)
            requirements['duration_weeks'] = num if 'week' in unit else num * 4
        
        # Extract modality count requirements
        modality_match = re.search(r'at least (\w+)', criterion.lower())
        if modality_match:
            word = modality_match.group(1)
            number_map = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5}
            requirements['minimum_modalities'] = number_map.get(word, 2)
        
        return requirements
    
    async def evaluate_coverage(
        self, 
        patient_context: Dict[str, Any], 
        guideline_context: Dict[str, Any],
        clinical_note: str
    ) -> Dict[str, Any]:
        """Enhanced evaluation with multi-step decision process"""
        
        # Step 1: Quick rule-based checks
        quick_decision = self._quick_rule_check(patient_context, guideline_context)
        if quick_decision:
            logger.info(f"Quick decision made: {quick_decision['decision']}")
            return quick_decision
        
        # Step 2: Extract conservative treatment details from note
        treatment_info = await self._extract_treatment_details(clinical_note)
        
        # Step 3: Build focused context for LLM
        focused_context = self._build_focused_context(
            patient_context, 
            guideline_context, 
            treatment_info
        )
        
        # Step 4: Get LLM evaluation with improved prompt
        llm_result = await self._get_llm_evaluation(focused_context, clinical_note)
        
        # Step 5: Validate LLM result
        validated_result = self._validate_llm_decision(llm_result, patient_context, guideline_context)
        
        return validated_result
    
    def _quick_rule_check(self, patient_context: Dict, guideline_context: Dict) -> Optional[Dict]:
        """Perform quick rule-based checks for obvious cases"""
        return None  # No quick decision, need full evaluation
    
    async def _extract_treatment_details(self, clinical_note: str) -> Dict:
        """Extract conservative treatment details from clinical note"""
        
        # Import llm_service here to avoid circular import
        from app.services.llm_service import llm_service
        
        prompt = """Extract ONLY conservative treatment information from this note.

CLINICAL NOTE:
{note}

Focus on:
1. What conservative treatments were tried
2. Duration of EACH treatment
3. Outcome of each treatment

Return JSON:
{{
  "treatments": [
    {{
      "modality": "physical therapy",
      "duration": "12 weeks",
      "sessions": "24 sessions",
      "outcome": "minimal improvement"
    }}
  ],
  "total_conservative_duration": "6 months",
  "treatments_failed": true
}}""".format(note=clinical_note[:2000])
        
        try:
            result = await llm_service.query_with_context(prompt, {})
            return result
        except:
            return {"treatments": [], "total_conservative_duration": "unknown"}
    
    def _build_focused_context(self, patient_context: Dict, guideline_context: Dict, treatment_info: Dict) -> Dict:
        """Build focused context with only relevant information"""
        
        return {
            "key_facts": {
                "primary_diagnosis": patient_context['conditions'][0] if patient_context['conditions'] else None,
                "symptom_duration": treatment_info.get('total_conservative_duration'),
                "treatments_tried": len(treatment_info.get('treatments', [])),
                "has_red_flags": patient_context['key_indicators'].get('has_red_flags'),
                "treatment_details": treatment_info.get('treatments', [])
            },
            "requirements": {
                "coverage_criteria": guideline_context['coverage_criteria'],
                "minimum_duration": self._extract_minimum_duration(guideline_context),
                "minimum_modalities": self._extract_minimum_modalities(guideline_context)
            }
        }
    
    def _extract_minimum_duration(self, guideline_context: Dict) -> int:
        """Extract minimum duration requirement in weeks"""
        for criterion in guideline_context.get('parsed_criteria', []):
            if criterion['type'] == 'duration':
                return criterion['requirements'].get('duration_weeks', 6)
        return 6  # Default to 6 weeks
    
    def _extract_minimum_modalities(self, guideline_context: Dict) -> int:
        """Extract minimum number of modalities required"""
        for criterion in guideline_context.get('parsed_criteria', []):
            if criterion['type'] == 'conservative_treatment':
                return criterion['requirements'].get('minimum_modalities', 2)
        return 2  # Default to 2 modalities
    
    async def _get_llm_evaluation(self, focused_context: Dict, clinical_note: str) -> Dict:
        """Get LLM evaluation with improved, focused prompt"""
        
        # Import llm_service here
        from app.services.llm_service import llm_service
        
        prompt = """You are evaluating a prior authorization request. Be practical and understand medical documentation.

PATIENT FACTS:
{facts}

REQUIREMENTS:
{requirements}

KEY QUESTION: Does this patient meet the coverage requirements?

EVALUATION RULES:
1. Conservative treatment duration: {min_duration} weeks minimum required
   - 3 months = 12 weeks (MEETS 6 week requirement)
   - 6 months = 24 weeks (EXCEEDS any normal requirement)

2. Number of modalities: {min_modalities} different treatments required
   - Count DISTINCT treatment types (PT, NSAIDs, injections, etc.)

3. Documentation: Must be mentioned in the note to count

RETURN JSON:
{{
  "final_decision": "approved" | "denied" | "needs_more_info",
  "criteria_met": [
    {{"requirement": "...", "met": true, "evidence": "..."}}
  ],
  "confidence": 0.0-1.0,
  "reasoning": ["clear reason 1", "clear reason 2"]
}}""".format(
            facts=json.dumps(focused_context['key_facts'], indent=2),
            requirements=json.dumps(focused_context['requirements'], indent=2),
            min_duration=focused_context['requirements']['minimum_duration'],
            min_modalities=focused_context['requirements']['minimum_modalities']
        )
        
        result = await llm_service.query_with_context(prompt, {})
        return result
    
    def _validate_llm_decision(self, llm_result: Dict, patient_context: Dict, guideline_context: Dict) -> Dict:
        """Validate and potentially override LLM decision"""
        
        if 'final_decision' not in llm_result:
            llm_result['final_decision'] = 'needs_more_info'
        
        valid_decisions = {'approved', 'denied', 'needs_more_info'}
        if llm_result['final_decision'] not in valid_decisions:
            llm_result['final_decision'] = 'needs_more_info'
        
        confidence = llm_result.get('confidence', 0.5)
        
        if llm_result['final_decision'] == 'approved':
            criteria_met = llm_result.get('criteria_met', [])
            if len([c for c in criteria_met if c.get('met')]) >= 2:
                confidence = min(confidence + 0.1, 0.95)
        
        llm_result['confidence'] = confidence
        llm_result['validated'] = True
        
        return llm_result
    
    async def extract_guideline_criteria(self, guideline_text: str) -> Dict[str, Any]:
        """Extract structured criteria from guideline text"""
        
        # Import llm_service here
        from app.services.llm_service import llm_service
        
        prompt = """Extract coverage criteria from this medical guideline. Be specific about requirements.

GUIDELINE TEXT:
{text}

Return JSON:
{{
  "title": "guideline title",
  "coverage_criteria": [
    "Failed conservative treatment for at least 6 weeks",
    "Tried at least TWO of: physical therapy, NSAIDs, activity modification"
  ],
  "exclusion_criteria": ["list exclusions"],
  "required_documentation": ["list requirements"],
  "covered_icd10_codes": [{{"code": "M54.5", "description": "Low back pain"}}],
  "covered_cpt_codes": [{{"code": "62323", "description": "Epidural injection"}}]
}}""".format(text=guideline_text[:3500])
        
        try:
            message = llm_service.client.messages.create(
                model=llm_service.model,
                max_tokens=4000,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}]
            )
            
            response_text = message.content[0].text
            json_text = llm_service._extract_json_from_response(response_text)
            return json.loads(json_text)
            
        except Exception as e:
            logger.error(f"Error extracting guideline: {e}")
            raise
    
    def generate_prior_auth_justification(
        self, 
        decision: Dict[str, Any],
        patient_context: Dict[str, Any],
        guideline_context: Dict[str, Any]
    ) -> str:
        """Generate clear, concise justification"""
        
        justification = []
        
        justification.append(f"PRIOR AUTHORIZATION DECISION: {decision.get('decision', 'Unknown')}")
        justification.append("=" * 60)
        
        justification.append("\nDECISION SUMMARY:")
        justification.append(f"Confidence: {decision.get('confidence_score', 0):.0%}")
        
        justification.append("\nCRITERIA EVALUATION:")
        for item in decision.get('matched_criteria', []):
            justification.append(f"✓ {item}")
        for item in decision.get('unmatched_criteria', []):
            justification.append(f"✗ {item}")
        
        justification.append("\nCLINICAL REASONING:")
        for i, reason in enumerate(decision.get('reasoning', []), 1):
            justification.append(f"{i}. {reason}")
        
        return "\n".join(justification)

# Singleton instance
mcp_manager = MCPContextManager()