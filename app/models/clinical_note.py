from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class Medication(BaseModel):
    name: str
    dosage: str
    frequency: str
    route: Optional[str] = None

class Allergy(BaseModel):
    substance: str
    reaction: str
    severity: Optional[str] = None

class LabResult(BaseModel):
    test_name: str
    value: str
    unit: str
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

class StructuredClinicalNote(BaseModel):
    """Structured representation of a clinical note"""
    
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
    
    # Metadata
    processed_at: datetime = Field(default_factory=datetime.now)
    processing_model: str = "claude-sonnet-4-5-20250929"

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