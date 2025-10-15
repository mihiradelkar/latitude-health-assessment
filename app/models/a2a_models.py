from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

class A2AStatus(str, Enum):
    SUBMITTED = "submitted"
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"
    ERROR = "error"

class DaVinciPASRequest(BaseModel):
    """DaVinci PAS compliant prior auth request"""
    patient_id: str
    provider_npi: str
    payer_id: str
    service_date: datetime
    cpt_codes: List[str]
    icd10_codes: List[str]
    supporting_info: Dict[str, Any]
    urgency: str = "routine"
    
class X12_278_Request(BaseModel):
    """X12 278 format request for compatibility"""
    transaction_set_id: str = "278"
    authorization_type: str = "HS"  # Health Services
    certification_type: str = "I"   # Initial
    service_type: str = "1"         # Medical Care
    
class A2ASubmission(BaseModel):
    """Track A2A submission"""
    submission_id: str
    transaction_id: str
    evaluation_id: str
    status: A2AStatus
    submitted_at: datetime
    payer_endpoint: str
    request_format: str  # "FHIR" or "X12"
    fhir_bundle: Optional[Dict[str, Any]]
    x12_payload: Optional[str]
    tracking_number: str
    expected_response_time: str
    response_received: Optional[Dict[str, Any]] = None
    
class A2AResponse(BaseModel):
    """Payer response via A2A"""
    response_id: str
    submission_id: str
    decision: str
    reference_number: str
    valid_from: datetime
    valid_to: datetime
    authorized_units: Optional[int]
    notes: Optional[str]