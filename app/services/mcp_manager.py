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
        
        # Extremely explicit decision logic
        question = """
    Evaluate this prior authorization request step-by-step.
    
    STEP-BY-STEP EVALUATION:
    
    Step 1: Check Diagnosis Match
    Question: Does patient_data.conditions contain ANY code from coverage_policy.covered_icd10_codes?
    → If YES: ✅ Proceed to Step 2
    → If NO: ❌ STOP → final_decision = "denied"
    
    Step 2: Check Procedure Coverage
    Question: Does patient_data.procedures contain ANY code from coverage_policy.covered_cpt_codes?
    → If YES: ✅ Proceed to Step 3  
    → If NO: ❌ STOP → final_decision = "denied"
    
    Step 3: Evaluate Each Medical Necessity Criterion
    For EACH item in coverage_policy.coverage_criteria, determine if it's MET:
    
    MET = Information exists ANYWHERE:
    - In clinical_context (clinical notes)
    - In patient_data.conditions
    - In patient_data.medications  
    - In patient_data.observations
    - In patient_data.procedures
    
    Examples:
    - Criterion: "pain for 6+ weeks" → "pain for past 6 weeks" in notes = ✅ MET
    - Criterion: "failed PT minimum 4 weeks" → "PT for 3 months" in notes = ✅ MET
    - Criterion: "pain 5/10+" → "pain rated 8/10" in notes = ✅ MET
    - Criterion: "MRI confirmed" → "MRI shows herniation" in notes = ✅ MET
    
    NOT MET = Information is completely absent:
    - Criterion: "failed PT" → NO mention of PT anywhere = ❌ NOT MET
    
    Count Results:
    - Total criteria: X
    - MET: Y
    - NOT MET: Z
    
    Step 4: Check Exclusions
    Question: Does patient have ANY condition/factor from coverage_policy.exclusion_criteria?
    → If YES: ❌ STOP → final_decision = "denied"
    → If NO: ✅ Proceed to Step 5
    
    Step 5: FINAL DECISION (Follow this logic EXACTLY):
    
    DECISION TREE:
    ```
    IF (Diagnosis ✅) AND (Procedure ✅) AND (ALL criteria MET) AND (No exclusions ✅):
    → final_decision = "approved"
    → confidence = 0.9 or higher
    ELSE IF (Diagnosis ❌) OR (Procedure ❌) OR (Exclusion exists ❌):
    → final_decision = "denied"
    → confidence = 0.9 or higher
    ELSE IF (Most criteria MET but 1-2 NOT MET):
    → final_decision = "denied" (requirements not fulfilled)
    → confidence = 0.85 or higher
    ELSE IF (Many criteria NOT MET due to no information):
    → final_decision = "needs_more_info"
    → confidence = 0.3-0.6
    ```
    CRITICAL RULES (Follow These Exactly):
    
    Rule 1: If ALL medical necessity criteria are MET → MUST be "approved"
            Never say "needs_more_info" if all criteria are already met!
    
    Rule 2: If most criteria are MET but 1-2 are clearly NOT MET → "denied"
            (Patient didn't fulfill requirements)
    
    Rule 3: Only use "needs_more_info" if MANY criteria have no information at all
            (You genuinely cannot determine if patient qualifies)
    
    Rule 4: "needs_more_info" should be RARE (<10% of cases)
    
    VALIDATION CHECK (Before returning your decision):
    
    Self-check: Did I find that all criteria are MET?
    → If YES: My decision MUST be "approved" (not needs_more_info)
    → If NO: Check how many are NOT MET
       - 1-2 NOT MET = "denied"  
       - 3+ NOT MET = "needs_more_info" only if truly no information
    
    EXAMPLES:
    
    Example A - APPROVED:
    ✅ Diagnosis: M51.16 (matches covered codes)
    ✅ Procedure: CPT 62323 (matches covered codes)
    ✅ All 7 criteria checked:
       1. Pain 6+ weeks: "pain for past 6 weeks" in notes → MET
       2. MRI confirmed: "MRI shows herniation" in notes → MET
       3. Failed PT 4+ weeks: "PT for 3 months" in notes → MET
       4. Failed NSAIDs: "ibuprofen 600mg" + "minimal relief" → MET
       5. Activity modification: "pain interferes with activities" → MET
       6. Pain 5/10+: "pain rated 8/10" in notes → MET
       7. No emergency: No cauda equina mentioned → MET
    ✅ No exclusions
    Result: 7/7 criteria MET
    → final_decision: "approved", confidence: 0.95
    
    Example B - DENIED:
    ✅ Diagnosis: M51.16 (matches)
    ✅ Procedure: CPT 62323 (matches)
    ❌ Criteria results:
       1. Pain 6+ weeks: Only "2 weeks of pain" → NOT MET
       2. MRI confirmed: No imaging mentioned → NOT MET
       3. Failed PT: No PT mentioned → NOT MET
       4. Failed NSAIDs: Taking ibuprofen → MET
       5-7: Various → Some MET, some NOT MET
    Result: Only 2/7 criteria MET clearly
    → final_decision: "denied", confidence: 0.90
    (Patient doesn't meet requirements)
    
    Example C - NEEDS_MORE_INFO:
    ✅ Diagnosis: M51.16 (matches)
    ✅ Procedure: CPT 62323 (matches)
    ? Criteria results:
       Clinical notes say: "chronic back pain, some treatments tried"
       Cannot determine: Which treatments? How long? What results?
       Only 1/7 criteria can be confirmed
    Result: 1/7 MET, 6/7 completely unknown
    → final_decision: "needs_more_info", confidence: 0.45
    
    RETURN FORMAT:
    {
      "final_decision": "approved" | "denied" | "needs_more_info",
      "answer": "1-2 sentence summary",
      "reasoning": [
        "Step 1: Diagnosis - [result]",
        "Step 2: Procedure - [result]",  
        "Step 3: Criteria evaluation - [X/Y met]",
        "Criterion 1: [met/not met] because...",
        "Criterion 2: [met/not met] because...",
        ...
        "Step 4: Exclusions - [result]",
        "Step 5: Final decision - [logic applied]"
      ],
      "confidence": 0.0-1.0,
      "citations": [{"claim": "...", "source": "..."}]
    }
    
    REMEMBER: If you found that ALL criteria are MET, you CANNOT say "needs_more_info". 
    You must say "approved". There is no logical reason to need more info if everything is already confirmed!
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