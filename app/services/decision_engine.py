# app/services/decision_engine.py
from typing import Dict, Any, List, Optional, Tuple
from app.services.mcp_manager import mcp_manager
from app.models.prior_auth import PriorAuthDecision, Citation
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class PriorAuthDecisionEngine:
    """
    Enhanced decision engine with multi-layer validation
    """
    
    def __init__(self):
        self.mcp = mcp_manager
        self.decision_thresholds = {
            'auto_approve': 0.85,
            'auto_deny': 0.85,
            'needs_review': 0.60
        }
    
    async def evaluate(
        self,
        fhir_bundle: Dict[str, Any],
        guideline_criteria: Dict[str, Any],
        clinical_note: str
    ) -> PriorAuthDecision:
        """
        Multi-step evaluation process for accuracy
        """
        
        logger.info("Starting prior auth evaluation")
        
        # Step 1: Build comprehensive contexts
        patient_context = self.mcp.build_patient_context(fhir_bundle)
        guideline_context = self.mcp.build_guideline_context(guideline_criteria)
        
        # Step 2: Pre-flight checks
        preflight_result = self._preflight_checks(patient_context, guideline_context)
        if preflight_result:
            logger.info(f"Preflight decision: {preflight_result.decision}")
            return preflight_result
        
        # Step 3: Extract treatment information from note
        treatment_analysis = await self._analyze_treatments(clinical_note)
        
        # Step 4: Structured evaluation
        evaluation_result = await self._structured_evaluation(
            patient_context,
            guideline_context,
            treatment_analysis,
            clinical_note
        )
        
        # Step 5: Build final decision with confidence
        decision = self._build_final_decision(
            evaluation_result,
            patient_context,
            guideline_context,
            treatment_analysis
        )
        
        # Step 6: Add audit trail
        decision = self._add_audit_trail(decision, patient_context)
        
        logger.info(f"Final decision: {decision.decision} (confidence: {decision.confidence_score:.2f})")
        
        return decision
    
    def _preflight_checks(
        self,
        patient_context: Dict,
        guideline_context: Dict
    ) -> Optional[PriorAuthDecision]:
        """
        Quick checks for obvious approvals or denials
        """
        
        # Check for exclusions
        exclusion_found = self._check_exclusions(patient_context, guideline_context)
        if exclusion_found:
            return PriorAuthDecision(
                decision="denied",
                reasoning=[f"Exclusion criteria met: {exclusion_found}"],
                matched_criteria=[],
                unmatched_criteria=guideline_context.get('coverage_criteria', []),
                citations=[],
                confidence_score=0.95,
                requires_additional_documentation=None
            )
        
        # Check for red flags that require immediate approval
        if patient_context['key_indicators'].get('has_red_flags'):
            red_flags = patient_context.get('red_flags', [])
            if self._requires_urgent_approval(red_flags):
                return PriorAuthDecision(
                    decision="approved",
                    reasoning=["Urgent medical necessity due to red flags"],
                    matched_criteria=["Urgent medical necessity"],
                    unmatched_criteria=[],
                    citations=[Citation(
                        claim="Patient has red flag conditions requiring urgent intervention",
                        source="Clinical assessment",
                        source_section="Conditions"
                    )],
                    confidence_score=0.95,
                    requires_additional_documentation=None
                )
        
        return None
    
    def _check_exclusions(self, patient_context: Dict, guideline_context: Dict) -> Optional[str]:
        """Check if any exclusion criteria are met"""
        
        exclusions = guideline_context.get('exclusion_criteria', [])
        patient_conditions = [c.get('display', '').lower() for c in patient_context.get('conditions', [])]
        
        for exclusion in exclusions:
            exclusion_lower = exclusion.lower()
            for condition in patient_conditions:
                if exclusion_lower in condition or condition in exclusion_lower:
                    return exclusion
        
        return None
    
    def _requires_urgent_approval(self, red_flags: List[Dict]) -> bool:
        """Check if red flags warrant urgent approval"""
        
        urgent_keywords = ['cauda equina', 'progressive paralysis', 'cancer', 'fracture']
        for flag in red_flags:
            display = flag.get('display', '').lower()
            if any(keyword in display for keyword in urgent_keywords):
                return True
        return False
    
    async def _analyze_treatments(self, clinical_note: str) -> Dict[str, Any]:
        """Detailed analysis of conservative treatments"""
        
        # Import llm_service here to avoid circular import
        from app.services.llm_service import llm_service
        
        prompt = """Analyze conservative treatments in this clinical note. Be specific about durations.

CLINICAL NOTE:
{note}

Extract the following information:

1. For EACH conservative treatment mentioned:
   - Name of treatment
   - Duration (in weeks/months)
   - Number of sessions (if applicable)
   - Outcome/result

2. Overall treatment timeline:
   - When did conservative treatment start?
   - Total duration of conservative treatment
   - Were treatments concurrent or sequential?

3. Key facts:
   - Were at least 2 different modalities tried?
   - Was the total duration at least 6 weeks?
   - Did treatments fail to provide relief?

IMPORTANT PATTERNS TO RECOGNIZE:
- "Failed conservative management x 6 months including:" means ALL listed items were tried during 6 months
- "NSAIDs (3 months)" means NSAIDs were used for 3 months
- "Physical therapy (12 sessions over 6 weeks)" means PT for 6 weeks

Return JSON:
{{
  "treatments": [
    {{
      "name": "physical therapy",
      "duration_weeks": 6,
      "sessions": 12,
      "outcome": "minimal improvement"
    }}
  ],
  "timeline": {{
    "total_duration_weeks": 24,
    "start_date_relative": "6 months ago",
    "concurrent": true
  }},
  "key_facts": {{
    "modality_count": 3,
    "duration_adequate": true,
    "treatment_failed": true
  }}
}}""".format(note=clinical_note[:2500])
        
        try:
            response = await llm_service.query_with_context(prompt, {})
            logger.info(f"Treatment analysis: {response.get('key_facts')}")
            return response
        except Exception as e:
            logger.error(f"Treatment analysis failed: {e}")
            return {
                "treatments": [],
                "timeline": {"total_duration_weeks": 0},
                "key_facts": {"modality_count": 0, "duration_adequate": False}
            }
    
    async def _structured_evaluation(
        self,
        patient_context: Dict,
        guideline_context: Dict,
        treatment_analysis: Dict,
        clinical_note: str
    ) -> Dict[str, Any]:
        """Structured evaluation against each criterion"""
        
        # Import llm_service here
        from app.services.llm_service import llm_service
        
        # Build evaluation context
        eval_context = {
            "patient_summary": {
            "conditions": [c.get('display') for c in patient_context.get('conditions', [])[:3]],
            "treatment_summary": treatment_analysis.get('key_facts'),
            "treatments_tried": [t.get('name') for t in treatment_analysis.get('treatments', [])],
            "physical_exam": patient_context.get('observations', []),
            "imaging": [obs for obs in patient_context.get('observations', []) if 'mri' in str(obs).lower() or 'ct' in str(obs).lower()],
            "has_positive_slr": "straight leg raise" in clinical_note.lower(),
            "has_neurological_findings": any(term in clinical_note.lower() for term in ['weakness', 'decreased sensation', 'reflex']),
            "has_imaging": "mri" in clinical_note.lower() or "ct" in clinical_note.lower()
        },
            "requirements": {
                "criteria": guideline_context.get('coverage_criteria', []),
                "must_have": self._extract_must_haves(guideline_context)
            }
        }
        
        # Use focused LLM evaluation
        prompt = """Evaluate if the patient meets EACH coverage criterion. Be practical about medical documentation.

PATIENT SUMMARY:
{patient}

COVERAGE CRITERIA TO EVALUATE:
{criteria}

For EACH criterion, determine:
1. Is it met? (yes/no/partial)
2. What evidence supports this?
3. Confidence level (0-1)

REMEMBER:
- 3 months = 12 weeks (exceeds 6 week requirement)
- "Failed conservative management x 6 months including [list]" means everything in the list was tried
- If 2 modalities are required and 3 were tried, the requirement is MET

Return JSON:
{{
  "criteria_evaluation": [
    {{
      "criterion": "the exact criterion text",
      "met": true,
      "evidence": "specific evidence from patient data",
      "confidence": 0.9
    }}
  ],
  "overall_met": true,
  "final_decision": "approved",
  "confidence": 0.85
}}""".format(
            patient=json.dumps(eval_context['patient_summary'], indent=2),
            criteria=json.dumps(eval_context['requirements']['criteria'], indent=2)
        )
        
        result = await llm_service.query_with_context(prompt, {})
        return result
    
    def _extract_must_haves(self, guideline_context: Dict) -> List[str]:
        """Extract absolute requirements from guidelines"""
        must_haves = []
        
        for criterion in guideline_context.get('coverage_criteria', []):
            if any(word in criterion.lower() for word in ['must', 'required', 'mandatory']):
                must_haves.append(criterion)
        
        return must_haves
    
    def _build_final_decision(
        self,
        evaluation_result: Dict,
        patient_context: Dict,
        guideline_context: Dict,
        treatment_analysis: Dict
    ) -> PriorAuthDecision:
        """Build final decision with all supporting information"""
        
        # Extract decision
        decision_status = evaluation_result.get('final_decision', 'needs_more_info')
        
        # Validate decision
        if decision_status not in ['approved', 'denied', 'needs_more_info']:
            decision_status = 'needs_more_info'
        
        # Build reasoning
        reasoning = []
        matched_criteria = []
        unmatched_criteria = []
        
        for criterion_eval in evaluation_result.get('criteria_evaluation', []):
            criterion_text = criterion_eval.get('criterion', '')
            if criterion_eval.get('met'):
                matched_criteria.append(criterion_text)
                reasoning.append(f"✓ {criterion_text}: {criterion_eval.get('evidence', 'Met')}")
            else:
                unmatched_criteria.append(criterion_text)
                reasoning.append(f"✗ {criterion_text}: Not demonstrated")
        
        # Add treatment summary to reasoning
        key_facts = treatment_analysis.get('key_facts', {})
        if key_facts.get('duration_adequate'):
            reasoning.append(f"✓ Conservative treatment duration: {treatment_analysis.get('timeline', {}).get('total_duration_weeks', 0)} weeks")
        if key_facts.get('modality_count', 0) >= 2:
            reasoning.append(f"✓ Multiple modalities tried: {key_facts.get('modality_count', 0)}")
        
        # Build citations
        citations = self._build_citations(evaluation_result, patient_context, treatment_analysis)
        
        # Calculate confidence
        confidence = evaluation_result.get('confidence', 0.5)
        
        # Adjust confidence based on evidence strength
        if len(matched_criteria) >= len(guideline_context.get('coverage_criteria', [])) * 0.8:
            confidence = min(confidence * 1.1, 0.95)
        
        # Determine if additional documentation is needed
        additional_docs = None
        if decision_status == "needs_more_info":
            additional_docs = self._identify_missing_documentation(
                unmatched_criteria,
                guideline_context
            )
        
        return PriorAuthDecision(
            decision=decision_status,
            reasoning=reasoning,
            matched_criteria=matched_criteria,
            unmatched_criteria=unmatched_criteria,
            citations=citations,
            confidence_score=confidence,
            requires_additional_documentation=additional_docs
        )
    
    def _build_citations(
        self,
        evaluation_result: Dict,
        patient_context: Dict,
        treatment_analysis: Dict
    ) -> List[Citation]:
        """Build proper citations for the decision"""
        
        citations = []
        
        # Add citations from evaluation
        for criterion_eval in evaluation_result.get('criteria_evaluation', []):
            if criterion_eval.get('met') and criterion_eval.get('evidence'):
                citations.append(Citation(
                    claim=criterion_eval.get('criterion', ''),
                    source="Clinical Documentation",
                    source_section=self._identify_source_section(criterion_eval.get('evidence', ''))
                ))
        
        # Add treatment citations
        if treatment_analysis.get('treatments'):
            for treatment in treatment_analysis['treatments']:
                citations.append(Citation(
                    claim=f"{treatment.get('name')} for {treatment.get('duration_weeks')} weeks",
                    source="Treatment History",
                    source_section="Conservative Management"
                ))
        
        return citations
    
    def _identify_source_section(self, evidence: str) -> str:
        """Identify which section of the note the evidence came from"""
        
        section_keywords = {
            'History': ['history', 'hpi', 'present illness'],
            'Treatment': ['treatment', 'therapy', 'conservative', 'management'],
            'Assessment': ['assessment', 'plan', 'impression'],
            'Medications': ['medication', 'drug', 'prescription'],
            'Exam': ['exam', 'physical', 'examination']
        }
        
        evidence_lower = evidence.lower()
        for section, keywords in section_keywords.items():
            if any(keyword in evidence_lower for keyword in keywords):
                return section
        
        return "Clinical Note"
    
    def _identify_missing_documentation(
        self,
        unmatched_criteria: List[str],
        guideline_context: Dict
    ) -> List[str]:
        """Identify what documentation would help meet unmatched criteria"""
        
        missing_docs = []
        
        for criterion in unmatched_criteria:
            criterion_lower = criterion.lower()
            
            if 'imaging' in criterion_lower:
                missing_docs.append("Recent imaging results (MRI, CT, or X-ray)")
            elif 'therapy' in criterion_lower or 'conservative' in criterion_lower:
                missing_docs.append("Physical therapy notes with dates and progress")
            elif 'medication' in criterion_lower:
                missing_docs.append("Medication trial history with durations and outcomes")
            elif 'specialist' in criterion_lower:
                missing_docs.append("Specialist consultation notes")
        
        # Add any specific documentation requirements from guidelines
        missing_docs.extend(guideline_context.get('required_documentation', []))
        
        # Remove duplicates
        return list(set(missing_docs))
    
    def _add_audit_trail(self, decision: PriorAuthDecision, patient_context: Dict) -> PriorAuthDecision:
        """Add audit trail information to decision"""
        
        # Add metadata for audit
        # decision.evaluation_timestamp = datetime.now().isoformat()
        # decision.patient_id = patient_context.get('patient', {}).get('id', 'unknown')
        # decision.condition_count = len(patient_context.get('conditions', []))
        
        return decision

# Singleton instance
decision_engine = PriorAuthDecisionEngine()