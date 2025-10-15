# app/models/clinical_note.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class Medication(BaseModel):
    name: str
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    duration: Optional[str] = None  # Added duration field

class Allergy(BaseModel):
    substance: str
    reaction: Optional[str] = None
    severity: Optional[str] = None

class LabResult(BaseModel):
    test_name: str
    value: str
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    date: Optional[str] = None

class DiagnosisCode(BaseModel):
    code: str
    system: str = "ICD-10"
    display: str

class ProcedureCode(BaseModel):
    code: str
    system: str = "CPT"
    display: str

class ConservativeTreatment(BaseModel):
    """Model for conservative treatment details"""
    modality: str
    details: Optional[str] = None
    duration: Optional[str] = None
    duration_weeks: Optional[int] = None
    sessions: Optional[int] = None
    outcome: Optional[str] = None

class ClinicalTimeline(BaseModel):
    """Model for clinical timeline information"""
    symptom_onset: Optional[str] = None
    conservative_treatment_start: Optional[str] = None
    conservative_treatment_duration: Optional[str] = None
    total_duration_weeks: Optional[int] = None

class StructuredClinicalNote(BaseModel):
    """Enhanced structured representation of a clinical note"""
    
    # Raw note
    raw_note: str
    
    # Patient identifiers
    patient_id: Optional[str] = None
    encounter_date: Optional[str] = None
    
    # Structured sections
    chief_complaint: Optional[str] = None
    history_present_illness: Optional[str] = None
    past_medical_history: Optional[List[str]] = None
    current_medications: Optional[List[Medication]] = None
    allergies: Optional[List[Allergy]] = None
    physical_exam: Optional[str] = None
    labs_imaging: Optional[List[LabResult]] = None
    assessment_plan: Optional[str] = None
    
    # Coded data
    diagnoses: Optional[List[DiagnosisCode]] = None
    procedures: Optional[List[ProcedureCode]] = None
    
    # NEW FIELDS for enhanced extraction
    symptom_duration: Optional[str] = None
    conservative_treatments: Optional[List[ConservativeTreatment]] = None
    clinical_timeline: Optional[ClinicalTimeline] = None
    confidence_scores: Optional[Dict[str, float]] = None
    
    # Metadata
    processed_at: datetime = Field(default_factory=datetime.now)
    processing_model: str = "claude-3-sonnet-20241022"

class ClinicalNoteRequest(BaseModel):
    """Request to process a clinical note"""
    note_text: str
    patient_id: Optional[str] = None
    encounter_date: Optional[str] = None

class ClinicalNoteResponse(BaseModel):
    """Response after processing a clinical note"""
    note_id: str
    structured_data: StructuredClinicalNote
    fhir_resources: Optional[dict] = None
    processing_time_ms: float
    extraction_confidence: Optional[Dict[str, float]] = None  # Added for confidence tracking