from typing import Dict, Any, List
import json
from app.services.llm_service import llm_service


class MCPContextManager:
    """
    Model Context Protocol Manager
    Manages context and orchestrates LLM interactions for clinical decision support
    """
    
    def __init__(self):
        self.context_cache = {}
    
    def build_patient_context(self, fhir_bundle: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build structured patient context from FHIR Bundle for LLM consumption
        """
        context = {
            "patient": {},
            "conditions": [],
            "medications": [],
            "procedures": [],
            "observations": [],
            "allergies": []
        }
        
        # Extract resources from bundle
        for entry in fhir_bundle.get('entry', []):
            resource = entry.get('resource', {})
            resource_type = resource.get('resourceType')
            
            if resource_type == 'Patient':
                context['patient'] = {
                    "id": resource.get('id'),
                    "active": resource.get('active', True)
                }
            
            elif resource_type == 'Condition':
                code = resource.get('code', {}).get('coding', [{}])[0]
                context['conditions'].append({
                    "code": code.get('code'),
                    "display": code.get('display'),
                    "status": resource.get('clinicalStatus', {}).get('coding', [{}])[0].get('code')
                })
            
            elif resource_type == 'MedicationRequest':
                med_concept = resource.get('medicationCodeableConcept', {})
                dosage = resource.get('dosageInstruction', [{}])[0] if resource.get('dosageInstruction') else {}
                context['medications'].append({
                    "name": med_concept.get('text'),
                    "dosage": dosage.get('text'),
                    "status": resource.get('status')
                })
            
            elif resource_type == 'Procedure':
                code = resource.get('code', {}).get('coding', [{}])[0]
                context['procedures'].append({
                    "code": code.get('code'),
                    "display": code.get('display'),
                    "status": resource.get('status')
                })
            
            elif resource_type == 'Observation':
                context['observations'].append({
                    "test": resource.get('code', {}).get('text'),
                    "value": resource.get('valueString'),
                    "status": resource.get('status')
                })
            
            elif resource_type == 'AllergyIntolerance':
                reactions = resource.get('reaction', [])
                reaction_text = reactions[0].get('manifestation', [{}])[0].get('text') if reactions else None
                context['allergies'].append({
                    "substance": resource.get('code', {}).get('text'),
                    "reaction": reaction_text
                })
        
        return context
    
    def build_guideline_context(self, guideline_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Structure guideline/policy data for LLM consumption
        """
        return {
            "title": guideline_data.get('title'),
            "coverage_criteria": guideline_data.get('coverage_criteria', []),
            "exclusion_criteria": guideline_data.get('exclusion_criteria', []),
            "required_documentation": guideline_data.get('required_documentation', []),
            "covered_icd10_codes": guideline_data.get('covered_icd10_codes', []),
            "covered_cpt_codes": guideline_data.get('covered_cpt_codes', [])
        }
    
    async def evaluate_coverage(
        self, 
        patient_context: Dict[str, Any], 
        guideline_context: Dict[str, Any],
        clinical_note: str
    ) -> Dict[str, Any]:
        """
        Use LLM with MCP to evaluate if patient meets coverage criteria
        """
        
        # Build combined context
        combined_context = {
            "patient_data": patient_context,
            "coverage_policy": guideline_context,
            "clinical_context": clinical_note[:2000]
        }
        
        # Much simpler, clearer prompt with examples
        question = """
    Evaluate this prior authorization request by checking if the patient meets the medical criteria.
    
    DECISION RULES (Simple and Clear):
    
    ✅ "approved" = Patient meets ALL medical requirements
       - Has the required diagnosis (ICD-10 code matches)
       - Requested procedure is covered (CPT code matches)  
       - Meets all medical necessity requirements
       - No exclusions apply
       - Information is available (anywhere: structured data, observations, OR clinical notes)
    
    ❌ "denied" = Patient does NOT meet medical requirements
       - Missing required diagnosis
       - Procedure not covered
       - Fails specific medical criteria (e.g., treatment too short, wrong diagnosis)
       - Has exclusion that applies
    
    ⚠️ "needs_more_info" = Cannot make decision (RARE - use sparingly)
       - Absolutely no information about critical requirement
       - Contradictory information
       - Use ONLY when you truly cannot determine if criteria are met
    
    EVALUATION STEPS:
    
    Step 1: Check Diagnosis
    → Does patient_data.conditions contain ANY of coverage_policy.covered_icd10_codes?
    → If YES = ✅ | If NO = ❌ denied
    
    Step 2: Check Procedure Coverage  
    → Does patient_data.procedures contain ANY of coverage_policy.covered_cpt_codes?
    → If YES = ✅ | If NO = ❌ denied
    
    Step 3: Check Medical Necessity (coverage_policy.coverage_criteria)
    For EACH criterion, check if information exists ANYWHERE (patient_data, observations, OR clinical_context):
    
    Example criteria checks:
    - "pain for 6 weeks" → Look for: "pain for 6 weeks", "pain for 18 months", "pain for past 6 weeks" = ✅ MET
    - "failed physical therapy" → Look for: "PT for 3 months", "physical therapy", "completed PT" = ✅ MET  
    - "MRI confirmed" → Look for: "MRI shows", "MRI Lumbar Spine", imaging results = ✅ MET
    - "pain rated 5/10+" → Look for: "pain 8/10", "rated 7/10", any pain scale = ✅ MET
    
    IF all criteria have supporting info (in ANY form) = ✅ proceed
    IF any criterion has ZERO mention = check if truly critical
    IF critical criterion completely missing = ⚠️ needs_more_info
    
    Step 4: Check Exclusions
    → Does patient have any coverage_policy.exclusion_criteria?
    → If YES = ❌ denied | If NO = ✅ proceed
    
    FINAL DECISION:
    - Diagnosis ✅ + Procedure ✅ + Criteria ✅ + No Exclusions ✅ = "approved"
    - Any medical requirement failed = "denied"  
    - Cannot determine due to missing info = "needs_more_info" (rare)
    
    IMPORTANT - What Counts as "Documented":
    ✅ Mentioned in clinical_context (e.g., "patient had PT for 3 months")
    ✅ In patient_data.observations (e.g., HbA1c value)
    ✅ In patient_data.medications (e.g., taking ibuprofen)
    ✅ In patient_data.conditions (e.g., diagnosis code)
    
    Don't require perfect formatting - if the information exists anywhere, it counts!
    
    EXAMPLES OF GOOD DECISIONS:
    
    Example 1 - APPROVED:
    - Patient has M51.16 ✅ (matches covered ICD-10)
    - Requests CPT 62323 ✅ (matches covered CPT)
    - Clinical notes say "PT for 3 months" ✅ (meets "minimum 4 weeks PT")
    - Clinical notes say "pain 8/10" ✅ (meets "pain 5/10+")
    - Clinical notes say "MRI shows herniation" ✅ (meets "MRI confirmed")
    - No exclusions ✅
    → final_decision: "approved"
    
    Example 2 - DENIED:
    - Patient has M54.5 (acute back strain) ❌ (NOT in covered ICD-10 codes)
    - Only 2 weeks of symptoms ❌ (fails "minimum 6 weeks" criterion)  
    → final_decision: "denied"
    
    Example 3 - DENIED (not needs_more_info):
    - Patient has required diagnosis ✅
    - No mention of physical therapy at all ❌ (but this is a REQUIREMENT)
    - Policy clearly requires "failed PT" and there's zero evidence of PT
    → final_decision: "denied" (didn't meet requirement, not just missing doc)
    
    Example 4 - NEEDS_MORE_INFO (rare):
    - Patient has required diagnosis ✅
    - Clinical notes are extremely vague: "some back pain, maybe tried something"
    - Truly cannot determine if ANY treatments were attempted
    → final_decision: "needs_more_info"
    
    Return JSON with:
    {
      "final_decision": "approved" | "denied" | "needs_more_info",
      "answer": "1-2 sentence summary of decision",
      "reasoning": ["criterion 1: met/not met because...", "criterion 2: ..."],
      "confidence": 0.0-1.0,
      "citations": [{"claim": "...", "source": "patient_data.conditions[0]"}]
    }
    """
        
        result = await llm_service.query_with_context(question, combined_context)
        return result
    
    async def extract_guideline_criteria(self, guideline_text: str) -> Dict[str, Any]:
        """
        Use LLM to extract structured criteria from unstructured guideline documents
        """
        
        prompt = f"""Extract coverage criteria from this clinical guideline/policy document.

Guideline Text:
{guideline_text[:4000]}  

Return ONLY valid JSON with this structure:
{{
  "title": "guideline title",
  "coverage_criteria": [
    "criterion 1",
    "criterion 2"
  ],
  "exclusion_criteria": [
    "exclusion 1"
  ],
  "required_documentation": [
    "documentation requirement 1"
  ],
  "covered_icd10_codes": [
    {{"code": "E11.9", "description": "Type 2 Diabetes"}}
  ],
  "covered_cpt_codes": [
    {{"code": "62323", "description": "Epidural injection"}}
  ]
}}

Focus on:
- Medical necessity criteria
- Diagnosis requirements (ICD-10 codes)
- Procedure coverage (CPT codes)
- Documentation requirements
- Exclusions or contraindications"""

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
            print(f"Error extracting guideline criteria: {e}")
            raise
    
    def generate_prior_auth_justification(
        self, 
        decision: Dict[str, Any],
        patient_context: Dict[str, Any],
        guideline_context: Dict[str, Any]
    ) -> str:
        """
        Generate human-readable justification for prior auth decision
        """
        
        justification = []
        
        justification.append(f"PRIOR AUTHORIZATION DECISION: {decision.get('answer', 'Unknown')}\n")
        justification.append("="*60)
        
        justification.append("\nCLINICAL SUMMARY:")
        justification.append(f"Patient ID: {patient_context['patient'].get('id')}")
        justification.append(f"Number of Conditions: {len(patient_context['conditions'])}")
        justification.append(f"Requested Procedures: {len(patient_context['procedures'])}")
        
        justification.append("\nREASONING:")
        for i, reason in enumerate(decision.get('reasoning', []), 1):
            justification.append(f"{i}. {reason}")
        
        justification.append("\nCITATIONS:")
        for citation in decision.get('citations', []):
            justification.append(f"• {citation.get('claim')}")
            justification.append(f"  Source: {citation.get('source')}")
        
        justification.append(f"\nCONFIDENCE SCORE: {decision.get('confidence', 0):.2f}")
        
        return "\n".join(justification)


# Singleton instance
mcp_manager = MCPContextManager()