from fastapi import APIRouter, HTTPException

router = APIRouter()

# Import storage from clinical_notes
from app.api.clinical_notes import notes_storage

@router.get("/patient/{patient_id}")
async def get_patient_fhir(patient_id: str):
    """Get FHIR resources for a specific patient"""
    
    patient_resources = []
    
    for note_id, note_data in notes_storage.items():
        if note_data['structured_data'].get('patient_id') == patient_id:
            patient_resources.append({
                "note_id": note_id,
                "fhir_bundle": note_data.get('fhir_resources'),
                "processed_at": note_data.get('processed_at')
            })
    
    if not patient_resources:
        raise HTTPException(status_code=404, detail=f"No resources found for patient {patient_id}")
    
    return {
        "patient_id": patient_id,
        "resource_count": len(patient_resources),
        "resources": patient_resources
    }

@router.get("/bundle/{note_id}")
async def get_fhir_bundle(note_id: str):
    """Get complete FHIR bundle for a clinical note"""
    
    if note_id not in notes_storage:
        raise HTTPException(status_code=404, detail="Note not found")
    
    return notes_storage[note_id].get('fhir_resources')