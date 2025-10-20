# app\services\mcp_manager.py
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
        
        question = """
    Evaluate this prior authorization request. Be PRACTICAL and understand clinical documentation standards.
    
    CRITICAL RULES FOR TIME:
    - 1 month = 4 weeks = ~30 days
    - 3 months = 12 weeks = ~90 days
    - 6 months = 24 weeks = ~180 days
    - If a note says "3 months", that EXCEEDS a "6 weeks" requirement!
    
    CRITICAL RULES FOR DOCUMENTATION:
    When a clinician writes: "Failed conservative management x [duration] including:"
    → That duration applies to ALL listed treatments below it
    → This is STANDARD medical documentation
    
    Example:
    "Failed conservative management x 6 months including:
    - Physical therapy
    - NSAIDs
    - Activity modification"
    
    This means: ALL three were tried during the 6-month period. Each one was part of the 6-month plan.
    
    CRITICAL RULES FOR "AT LEAST" REQUIREMENTS:
    If policy says: "Failed at least TWO of the following for ≥6 weeks"
    → Once you find TWO that meet the requirement, the criterion is SATISFIED
    → You do NOT need all items to have explicit durations
    → You do NOT need to verify the third, fourth, or fifth items
    
    STEP-BY-STEP EVALUATION:
    
    Step 1: Check Diagnosis
    Does patient have required diagnosis code or clinical diagnosis mentioned in coverage criteria?
    → If YES = ✅
    
    Step 2: Check Procedure
    Is requested CPT code in covered procedures?
    → If YES = ✅
    
    Step 3: Evaluate Medical Necessity Criteria
    For EACH criterion in coverage_policy.coverage_criteria:
    
    A. RECOGNIZE PATTERNS:
       Pattern 1: "Failed conservative therapy x [duration] including [list]"
       → Duration applies to entire list
    
       Pattern 2: "at least TWO of: [list]" for minimum duration
       → Once TWO items meet duration, criterion is MET
       → Don't require all items to have durations
    
       Pattern 3: "[item] ([details])"
       → Details in parentheses count as documentation
       → "NSAIDs (ibuprofen 800mg TID x 3 months)" = FULLY DOCUMENTED
    
    B. TIME COMPARISON (Use this logic):
       Required: "≥6 weeks"
       Found: "3 months" or "12 weeks" or "90 days"
       Comparison: 3 months = 12 weeks = ~90 days > 6 weeks ✅ EXCEEDS requirement
    
       Required: "≥12 weeks"
       Found: "3 months"
       Comparison: 3 months = 12 weeks ✅ MEETS requirement
    
    C. COUNT MODALITIES (for "at least X" requirements):
       If policy says "at least TWO modalities for ≥6 weeks":
    
       Count modalities that meet ≥6 weeks:
       1. Physical therapy (12 sessions) ✅
       2. NSAIDs (3 months = 12 weeks) ✅
    
       Result: Found 2 modalities ≥ 6 weeks
       Requirement: at least 2 modalities ≥ 6 weeks
       → Criterion is MET ✅
    
       Do NOT deny because other items lack explicit durations!
    
    Step 4: Check Exclusions
    Any exclusion criteria present?
    
    Step 5: Make Decision
    
    DECISION LOGIC:
    ```
    IF Diagnosis ✅ AND Procedure ✅ AND All required criteria MET ✅ AND No exclusions ✅:
    → final_decision = "approved"
    ELSE IF Missing diagnosis OR procedure not covered OR has exclusion:
    → final_decision = "denied"
    ELSE:
    → final_decision = "needs_more_info" (only if truly unclear)
    ```
    COMMON MISTAKES TO AVOID:
    ❌ Treating "12 weeks" as insufficient for "≥6 weeks" requirement
       ✅ 12 weeks > 6 weeks, so requirement is MET
    
    ❌ Requiring ALL modalities to have durations when policy says "at least TWO"
       ✅ Once TWO modalities meet duration, requirement is MET
    
    ❌ Ignoring "x 6 months including:" as a duration statement
       ✅ This means ALL listed items were tried during that period
    
    ❌ Treating parenthetical details as missing documentation
       ✅ "(ibuprofen 800mg TID x 3 months)" is COMPLETE documentation
    
    ❌ Denying because you want "more detail" when requirements are met
       ✅ If medical necessity is met, approve - don't ask for documentation perfection
    
    VALIDATION CHECKLIST (Before returning decision):
    □ Did I convert time correctly? (3 months = 12 weeks = exceeds 6 weeks)
    □ Did I recognize "x [duration] including:" applies to all items?
    □ Did I stop counting after finding enough items for "at least X" requirement?
    □ Did I check if medical necessity is actually met, not just documentation format?
    
    EXAMPLE - This Should Be APPROVED:
    
    Patient has radiculopathy (M54.16) ✅
    Requests MRI (CPT 72148) ✅
    
    Criteria check:
    1. Clinical findings present (positive SLR, weakness) ✅
    2. Duration ≥6 weeks: Has 6 months (24 weeks) ✅
    3. Failed conservative therapy ≥6 weeks with at least TWO modalities:
    
       Note says: "Failed conservative management x 6 months including:
       - Physical therapy (12 sessions)
       - NSAIDs (ibuprofen 800mg TID x 3 months)
       - Muscle relaxants
       - Activity modification"
    
       Analysis:
       - "x 6 months including:" means all items tried during 6 months ✅
       - Physical therapy: 12 sessions during 6-month period ✅
       - NSAIDs: 3 months = 12 weeks (explicitly stated) ✅
       - That's TWO modalities both exceeding 6 weeks ✅
       - Requirement: "at least TWO" → MET ✅
       - Don't need to verify durations of muscle relaxants/activity mod
    
    4. No red flags/exclusions ✅
    
    Result: All criteria MET → final_decision = "approved", confidence = 0.90
    
    Return JSON:
    {
      "final_decision": "approved" | "denied" | "needs_more_info",
      "answer": "Brief summary",
      "reasoning": [
        "Step 1: Diagnosis - [result]",
        "Step 2: Procedure - [result]",
        "Step 3: Criteria - [X/Y met with specifics]",
        "Step 4: Exclusions - [result]",
        "Step 5: Decision logic"
      ],
      "confidence": 0.0-1.0,
      "citations": [{"claim": "...", "source": "..."}]
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