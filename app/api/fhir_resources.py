from fastapi import APIRouter

router = APIRouter()

@router.get("/patient/{patient_id}")
async def get_patient_fhir():
    """Get patient FHIR resources (to be implemented)"""
    return {"message": "FHIR resources - coming soon"}