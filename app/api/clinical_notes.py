from fastapi import APIRouter, HTTPException
from typing import Dict
import time
import uuid

from app.models.clinical_note import ClinicalNoteRequest, ClinicalNoteResponse
from app.services.llm_service import llm_service
from app.services.fhir_mapper import fhir_mapper

router = APIRouter()

# In-memory storage for demo (replace with DB later)
notes_storage: Dict[str, dict] = {}

@router.post("/process", response_model=ClinicalNoteResponse)
async def process_clinical_note(request: ClinicalNoteRequest):
    """
    Process an unstructured clinical note and extract structured data + FHIR resources
    """
    
    start_time = time.time()
    
    try:
        # Generate unique note ID
        note_id = str(uuid.uuid4())
        
        # Structure the note using LLM
        structured_data = await llm_service.structure_clinical_note(request.note_text)
        
        # Add patient info if provided
        if request.patient_id:
            structured_data.patient_id = request.patient_id
        if request.encounter_date:
            structured_data.encounter_date = request.encounter_date
        
        # Map to FHIR resources
        fhir_bundle = fhir_mapper.map_to_fhir_bundle(structured_data)
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000  # ms
        
        # Store in memory
        notes_storage[note_id] = {
            "structured_data": structured_data.dict(),
            "fhir_resources": fhir_bundle,
            "processed_at": structured_data.processed_at.isoformat()
        }
        
        return ClinicalNoteResponse(
            note_id=note_id,
            structured_data=structured_data,
            fhir_resources=fhir_bundle,
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing note: {str(e)}")

@router.get("/{note_id}")
async def get_clinical_note(note_id: str):
    """
    Retrieve a processed clinical note with FHIR resources
    """
    if note_id not in notes_storage:
        raise HTTPException(status_code=404, detail="Note not found")
    
    return notes_storage[note_id]

@router.get("/")
async def list_clinical_notes():
    """
    List all processed notes
    """
    return {
        "count": len(notes_storage),
        "notes": list(notes_storage.keys())
    }