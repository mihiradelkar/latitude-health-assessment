# app/services/decision_engine.py
from typing import Dict, Any, List
from app.services.mcp_manager import mcp_manager
from app.models.prior_auth import PriorAuthDecision, Citation
import json


class PriorAuthDecisionEngine:
    """
    Decision engine for prior authorization evaluation
    Combines patient data, FHIR resources, and coverage guidelines
    """
    
    def __init__(self):
        self.mcp = mcp_manager
    
    async def evaluate(
        self,
        fhir_bundle: Dict[str, Any],
        guideline_criteria: Dict[str, Any],
        clinical_note: str
    ) -> PriorAuthDecision:
        """
        Evaluate if patient meets coverage criteria for prior authorization
        """
        
        # Build contexts using MCP
        patient_context = self.mcp.build_patient_context(fhir_bundle)
        guideline_context = self.mcp.build_guideline_context(guideline_criteria)
        
        # Get LLM evaluation with context
        llm_result = await self.mcp.evaluate_coverage(
            patient_context,
            guideline_context,
            clinical_note
        )

        # Save LLM result as a text file
        with open("llm_result.json", "w") as f:
            json.dump(llm_result, f, indent=2)
        
        # Parse LLM response into structured decision
        decision = self._parse_llm_decision(llm_result, patient_context, guideline_context)
        
        return decision
    
    def _parse_llm_decision(
        self,
        llm_result: Dict[str, Any],
        patient_context: Dict[str, Any],
        guideline_context: Dict[str, Any]
    ) -> PriorAuthDecision:
        """
        Parse LLM output into structured PriorAuthDecision
        """
        
        # Use the explicit final_decision field from LLM
        decision_status = llm_result.get('final_decision', 'needs_more_info')
        
        # Validate decision is one of the allowed values
        valid_decisions = {'approved', 'denied', 'needs_more_info'}
        if decision_status not in valid_decisions:
            print(f"⚠️  Warning: Invalid decision '{decision_status}', defaulting to needs_more_info")
            decision_status = 'needs_more_info'
        
        print(f"📋 Decision from LLM: {decision_status}")
        
        # Extract matched and unmatched criteria from reasoning
        matched_criteria = []
        unmatched_criteria = []
        
        reasoning_text = ' '.join(llm_result.get('reasoning', [])).lower()
        
        for criterion in guideline_context.get('coverage_criteria', []):
            criterion_lower = criterion.lower()
            
            # Extract key words from criterion (skip common words)
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
            criterion_keywords = [
                word for word in criterion_lower.split() 
                if len(word) > 3 and word not in stop_words
            ][:5]  # First 5 meaningful words
            
            # Check if this criterion is mentioned in reasoning
            criterion_mentioned = any(
                keyword in reasoning_text 
                for keyword in criterion_keywords
            )
            
            if criterion_mentioned:
                # Check if mentioned as met or unmet
                # Look for positive indicators near the criterion keywords
                criterion_context = []
                for keyword in criterion_keywords:
                    if keyword in reasoning_text:
                        idx = reasoning_text.find(keyword)
                        # Get surrounding context (100 chars before and after)
                        start = max(0, idx - 100)
                        end = min(len(reasoning_text), idx + 100)
                        criterion_context.append(reasoning_text[start:end])
                
                context_str = ' '.join(criterion_context)
                
                # Positive indicators
                if any(phrase in context_str for phrase in [
                    'met', 'meets', 'satisfied', 'documented', 'confirmed',
                    'present', 'completed', 'achieved', 'requirement met',
                    'criteria met', 'successfully'
                ]):
                    matched_criteria.append(criterion)
                # Negative indicators
                elif any(phrase in context_str for phrase in [
                    'not met', 'unmet', 'missing', 'absent', 'insufficient',
                    'not documented', 'lacks', 'does not meet', 'failed to',
                    'not present', 'unclear', 'incomplete'
                ]):
                    unmatched_criteria.append(criterion)
                else:
                    # Ambiguous - default to unmatched
                    unmatched_criteria.append(criterion)
            else:
                # Not mentioned - assume unmatched
                unmatched_criteria.append(criterion)
        
        # Build citations
        citations = []
        for citation_data in llm_result.get('citations', []):
            citations.append(Citation(
                claim=citation_data.get('claim', ''),
                source=citation_data.get('source', ''),
                source_section=None,
                fhir_reference=None
            ))
    
        # Determine required documentation
        required_docs = []
        if decision_status in ["denied", "needs_more_info"]:
            required_docs = guideline_context.get('required_documentation', [])

        return PriorAuthDecision(
            decision=decision_status,
            reasoning=llm_result.get('reasoning', []),
            matched_criteria=matched_criteria,
            unmatched_criteria=unmatched_criteria,
            citations=citations,
            confidence_score=llm_result.get('confidence', 0.0),
            requires_additional_documentation=required_docs if required_docs else None
        )

# Singleton instance
decision_engine = PriorAuthDecisionEngine()