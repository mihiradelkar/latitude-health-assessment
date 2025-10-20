# app\api\prior_auth.py
from fastapi import APIRouter, HTTPException
from typing import Dict
import time
import uuid

from app.models.prior_auth import (
    PriorAuthEvaluationRequest,
    PriorAuthEvaluationResponse,
    GuidelineExtractionRequest,
    GuidelineCriteria
)
from app.services.mcp_manager import mcp_manager
from app.services.decision_engine import decision_engine
from app.api.clinical_notes import notes_storage
import json

router = APIRouter()

# Storage for evaluations
evaluations_storage: Dict[str, dict] = {}

@router.post("/extract-guideline", response_model=GuidelineCriteria)
async def extract_guideline_criteria(request: GuidelineExtractionRequest):
    """
    Extract structured criteria from guideline text using LLM
    """
    try:
        criteria = await mcp_manager.extract_guideline_criteria(request.guideline_text)
        # Save criteria as a JSON object in a file
        with open("extracted_guideline_criteria.json", "w") as f:
            json.dump(criteria, f, indent=2)
        return GuidelineCriteria(**criteria)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting guideline: {str(e)}")


@router.post("/evaluate", response_model=PriorAuthEvaluationResponse)
async def evaluate_prior_authorization(request: PriorAuthEvaluationRequest):
    """
    Evaluate prior authorization based on patient data and coverage guidelines
    """
    start_time = time.time()
    
    try:
        # Get clinical note data
        if request.note_id not in notes_storage:
            raise HTTPException(status_code=404, detail="Clinical note not found")
        
        note_data = notes_storage[request.note_id]
        fhir_bundle = note_data.get('fhir_resources')
        structured_data = note_data.get('structured_data')
        clinical_note = structured_data.get('raw_note', '')
        
        # Get or extract guideline criteria
        if request.guideline_criteria:
            guideline_criteria = request.guideline_criteria.dict()
        elif request.guideline_text:
            guideline_criteria = await mcp_manager.extract_guideline_criteria(request.guideline_text)
        else:
            raise HTTPException(
                status_code=400, 
                detail="Must provide either guideline_criteria or guideline_text"
            )
        
        # Evaluate using decision engine
        decision = await decision_engine.evaluate(
            fhir_bundle,
            guideline_criteria,
            clinical_note
        )
        
        # Generate justification
        patient_context = mcp_manager.build_patient_context(fhir_bundle)
        guideline_context = mcp_manager.build_guideline_context(guideline_criteria)
        
        justification = mcp_manager.generate_prior_auth_justification(
            decision.dict(),
            patient_context,
            guideline_context
        )
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000
        
        # Create evaluation record
        evaluation_id = str(uuid.uuid4())
        
        response = PriorAuthEvaluationResponse(
            evaluation_id=evaluation_id,
            note_id=request.note_id,
            patient_id=structured_data.get('patient_id', 'unknown'),
            decision=decision,
            guideline_used=guideline_criteria,
            justification=justification,
            evaluated_at=structured_data.get('processed_at'),
            processing_time_ms=processing_time
        )
        
        # Store evaluation
        evaluations_storage[evaluation_id] = response.dict()
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error evaluating prior auth: {str(e)}")


@router.get("/{evaluation_id}")
async def get_prior_auth_evaluation(evaluation_id: str):
    """
    Retrieve a prior authorization evaluation
    """
    if evaluation_id not in evaluations_storage:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    return evaluations_storage[evaluation_id]


@router.get("/")
async def list_prior_auth_evaluations():
    """
    List all prior authorization evaluations
    """
    return {
        "count": len(evaluations_storage),
        "evaluations": list(evaluations_storage.keys())
    }