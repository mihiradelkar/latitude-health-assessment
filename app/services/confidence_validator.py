from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class ConfidenceLevel(Enum):
    """Confidence levels for routing decisions"""
    HIGH = "high"           # >0.85 - Auto-process
    MEDIUM = "medium"       # 0.60-0.85 - Quick review
    LOW = "low"            # <0.60 - Full review
    CRITICAL = "critical"  # Red flags or urgent

@dataclass
class ValidationResult:
    """Result of confidence validation"""
    confidence_level: ConfidenceLevel
    confidence_score: float
    requires_human_review: bool
    review_reasons: List[str]
    risk_factors: List[str]
    recommendations: List[str]

class ConfidenceValidator:
    """
    Validates prior auth decisions and determines confidence levels
    """
    
    def __init__(self):
        self.thresholds = {
            'auto_approve': 0.85,
            'quick_review': 0.60,
            'full_review': 0.40
        }
        
        self.risk_indicators = {
            'high_risk': [
                'experimental', 'investigational', 'off-label',
                'high-cost', 'opioid', 'controlled substance'
            ],
            'medium_risk': [
                'specialist required', 'second opinion',
                'alternative available', 'elective'
            ],
            'low_risk': [
                'routine', 'standard care', 'first-line',
                'guideline-recommended'
            ]
        }
    
    def validate_decision(
        self,
        decision: Dict[str, Any],
        patient_context: Dict[str, Any],
        treatment_analysis: Dict[str, Any],
        extraction_confidence: Dict[str, float]
    ) -> ValidationResult:
        """
        Comprehensive validation of a prior auth decision
        """
        
        # Calculate composite confidence score
        composite_score = self._calculate_composite_confidence(
            decision,
            extraction_confidence,
            treatment_analysis
        )
        
        # Identify risk factors
        risk_factors = self._identify_risk_factors(
            decision,
            patient_context,
            treatment_analysis
        )
        
        # Determine confidence level
        confidence_level = self._determine_confidence_level(
            composite_score,
            risk_factors,
            patient_context
        )
        
        # Check if human review is required
        requires_review, review_reasons = self._check_human_review_required(
            confidence_level,
            decision,
            risk_factors,
            patient_context
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            confidence_level,
            decision,
            risk_factors
        )
        
        return ValidationResult(
            confidence_level=confidence_level,
            confidence_score=composite_score,
            requires_human_review=requires_review,
            review_reasons=review_reasons,
            risk_factors=risk_factors,
            recommendations=recommendations
        )
    
    def _calculate_composite_confidence(
        self,
        decision: Dict,
        extraction_confidence: Dict,
        treatment_analysis: Dict
    ) -> float:
        """Calculate weighted composite confidence score"""
        
        weights = {
            'decision_confidence': 0.40,
            'extraction_quality': 0.30,
            'treatment_clarity': 0.20,
            'criteria_match': 0.10
        }
        
        scores = {}
        
        # Decision confidence from LLM
        scores['decision_confidence'] = decision.get('confidence_score', 0.5)
        
        # Extraction quality
        extraction_scores = extraction_confidence.values()
        scores['extraction_quality'] = sum(extraction_scores) / len(extraction_scores) if extraction_scores else 0.5
        
        # Treatment clarity
        key_facts = treatment_analysis.get('key_facts', {})
        treatment_score = 0.0
        if key_facts.get('duration_adequate'):
            treatment_score += 0.33
        if key_facts.get('modality_count', 0) >= 2:
            treatment_score += 0.33
        if key_facts.get('treatment_failed'):
            treatment_score += 0.34
        scores['treatment_clarity'] = treatment_score
        
        # Criteria match rate
        total_criteria = len(decision.get('matched_criteria', [])) + len(decision.get('unmatched_criteria', []))
        if total_criteria > 0:
            scores['criteria_match'] = len(decision.get('matched_criteria', [])) / total_criteria
        else:
            scores['criteria_match'] = 0.0
        
        # Calculate weighted average
        composite = sum(scores[key] * weights[key] for key in weights)
        
        logger.info(f"Confidence scores: {scores}")
        logger.info(f"Composite confidence: {composite:.2f}")
        
        return composite
    
    def _identify_risk_factors(
        self,
        decision: Dict,
        patient_context: Dict,
        treatment_analysis: Dict
    ) -> List[str]:
        """Identify risk factors that might affect the decision"""
        
        risk_factors = []
        
        # Check for high-risk conditions
        for condition in patient_context.get('conditions', []):
            condition_text = (condition.get('display', '') or '').lower()
            for risk_term in self.risk_indicators['high_risk']:
                if risk_term in condition_text:
                    risk_factors.append(f"High-risk condition: {condition.get('display')}")
                    break
        
        # Check for red flags
        if patient_context.get('key_indicators', {}).get('has_red_flags'):
            risk_factors.append("Red flag conditions present")
        
        # Check for incomplete documentation
        if decision.get('decision') == 'needs_more_info':
            risk_factors.append("Incomplete documentation")
        
        # Check for treatment duration issues
        timeline = treatment_analysis.get('timeline', {})
        if timeline.get('total_duration_weeks', 0) < 6:
            risk_factors.append("Conservative treatment duration less than 6 weeks")
        
        # Check for conflicting information
        if self._has_conflicting_information(decision):
            risk_factors.append("Conflicting information in clinical documentation")
        
        return risk_factors
    
    def _has_conflicting_information(self, decision: Dict) -> bool:
        """Check if there's conflicting information in the decision"""
        
        # Look for contradictions in reasoning
        reasoning_text = ' '.join(decision.get('reasoning', [])).lower()
        
        conflict_patterns = [
            ('meets', 'does not meet'),
            ('adequate', 'inadequate'),
            ('sufficient', 'insufficient'),
            ('failed', 'successful')
        ]
        
        for positive, negative in conflict_patterns:
            if positive in reasoning_text and negative in reasoning_text:
                return True
        
        return False
    
    def _determine_confidence_level(
        self,
        composite_score: float,
        risk_factors: List[str],
        patient_context: Dict
    ) -> ConfidenceLevel:
        """Determine the confidence level based on score and risk"""
        
        # Check for critical conditions first
        if patient_context.get('key_indicators', {}).get('has_red_flags'):
            for flag in patient_context.get('red_flags', []):
                if self._is_critical_condition(flag):
                    return ConfidenceLevel.CRITICAL
        
        # Adjust for risk factors
        adjusted_score = composite_score
        if len(risk_factors) > 2:
            adjusted_score *= 0.8  # Reduce confidence for multiple risks
        
        # Determine level based on adjusted score
        if adjusted_score >= self.thresholds['auto_approve']:
            return ConfidenceLevel.HIGH
        elif adjusted_score >= self.thresholds['quick_review']:
            return ConfidenceLevel.MEDIUM
        else:
            return ConfidenceLevel.LOW
    
    def _is_critical_condition(self, condition: Dict) -> bool:
        """Check if condition requires urgent attention"""
        critical_terms = [
            'cauda equina', 'paralysis', 'cancer', 'tumor',
            'emergency', 'urgent', 'acute', 'unstable'
        ]
        
        display = (condition.get('display', '') or '').lower()
        return any(term in display for term in critical_terms)
    
    def _check_human_review_required(
        self,
        confidence_level: ConfidenceLevel,
        decision: Dict,
        risk_factors: List[str],
        patient_context: Dict
    ) -> Tuple[bool, List[str]]:
        """Determine if human review is required and why"""
        
        requires_review = False
        review_reasons = []
        
        # Always review low confidence
        if confidence_level == ConfidenceLevel.LOW:
            requires_review = True
            review_reasons.append("Low confidence score")
        
        # Review critical cases
        if confidence_level == ConfidenceLevel.CRITICAL:
            requires_review = True
            review_reasons.append("Critical medical condition")
        
        # Review denials
        if decision.get('decision') == 'denied':
            requires_review = True
            review_reasons.append("Denial requires review")
        
        # Review high-risk cases
        if len(risk_factors) >= 3:
            requires_review = True
            review_reasons.append(f"Multiple risk factors ({len(risk_factors)})")
        
        # Review cases with missing documentation
        if decision.get('requires_additional_documentation'):
            requires_review = True
            review_reasons.append("Additional documentation needed")
        
        # Review conflicting decisions
        if decision.get('decision') == 'needs_more_info' and confidence_level == ConfidenceLevel.HIGH:
            requires_review = True
            review_reasons.append("Conflicting confidence indicators")
        
        return requires_review, review_reasons
    
    def _generate_recommendations(
        self,
        confidence_level: ConfidenceLevel,
        decision: Dict,
        risk_factors: List[str]
    ) -> List[str]:
        """Generate recommendations based on validation"""
        
        recommendations = []
        
        if confidence_level == ConfidenceLevel.HIGH:
            recommendations.append("Auto-approve with standard documentation")
            
        elif confidence_level == ConfidenceLevel.MEDIUM:
            recommendations.append("Quick clinical review recommended")
            if decision.get('requires_additional_documentation'):
                recommendations.append("Request additional documentation before final decision")
                
        elif confidence_level == ConfidenceLevel.LOW:
            recommendations.append("Full clinical review required")
            recommendations.append("Consider peer-to-peer discussion")
            
        elif confidence_level == ConfidenceLevel.CRITICAL:
            recommendations.append("Expedited review required")
            recommendations.append("Consider immediate approval with retrospective review")
        
        # Add specific recommendations based on risk factors
        if "Conservative treatment duration less than 6 weeks" in risk_factors:
            recommendations.append("Verify treatment timeline with provider")
        
        if "Incomplete documentation" in risk_factors:
            recommendations.append("Request complete clinical notes")
        
        if "Conflicting information" in risk_factors:
            recommendations.append("Clarify discrepancies with provider")
        
        return recommendations
    
    def generate_confidence_report(self, validation_result: ValidationResult) -> str:
        """Generate human-readable confidence report"""
        
        report = []
        report.append("=" * 60)
        report.append("CONFIDENCE VALIDATION REPORT")
        report.append("=" * 60)
        
        report.append(f"\nConfidence Level: {validation_result.confidence_level.value.upper()}")
        report.append(f"Confidence Score: {validation_result.confidence_score:.1%}")
        report.append(f"Human Review Required: {'Yes' if validation_result.requires_human_review else 'No'}")
        
        if validation_result.review_reasons:
            report.append("\nReview Required Because:")
            for reason in validation_result.review_reasons:
                report.append(f"  • {reason}")
        
        if validation_result.risk_factors:
            report.append("\nRisk Factors Identified:")
            for risk in validation_result.risk_factors:
                report.append(f"  • {risk}")
        
        if validation_result.recommendations:
            report.append("\nRecommendations:")
            for rec in validation_result.recommendations:
                report.append(f"  • {rec}")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)

# Singleton instance
confidence_validator = ConfidenceValidator()