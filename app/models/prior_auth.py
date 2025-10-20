# app\models\prior_auth.py
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime


class GuidelineCriteria(BaseModel):
    """Coverage guideline criteria"""
    title: str
    coverage_criteria: List[str]
    exclusion_criteria: Optional[List[str]] = []
    required_documentation: Optional[List[str]] = []
    covered_icd10_codes: Optional[List[Dict[str, str]]] = []
    covered_cpt_codes: Optional[List[Dict[str, str]]] = []


class GuidelineExtractionRequest(BaseModel):
    """Request to extract criteria from guideline text"""
    guideline_text: str
    guideline_source: Optional[str] = None


class PriorAuthEvaluationRequest(BaseModel):
    """Request to evaluate prior authorization"""
    note_id: str
    guideline_url: Optional[str] = None
    guideline_text: Optional[str] = None
    guideline_criteria: Optional[GuidelineCriteria] = None


class Citation(BaseModel):
    """Citation linking decision to source data"""
    claim: str
    source: str
    source_section: Optional[str] = None
    fhir_reference: Optional[str] = None


class PriorAuthDecision(BaseModel):
    """Prior authorization decision"""
    decision: str  # "approved", "denied", "needs_more_info"
    reasoning: List[str]
    matched_criteria: List[str]
    unmatched_criteria: List[str]
    citations: List[Citation]
    confidence_score: float
    requires_additional_documentation: Optional[List[str]] = None


class PriorAuthEvaluationResponse(BaseModel):
    """Response from prior auth evaluation"""
    evaluation_id: str
    note_id: str
    patient_id: str
    decision: PriorAuthDecision
    guideline_used: Dict[str, Any]
    justification: str
    evaluated_at: datetime
    processing_time_ms: float