# app/api/prior_auth.py
from fastapi import APIRouter, HTTPException
from typing import Dict, Optional
import time
import uuid
from datetime import datetime, timedelta

from app.models.a2a_models import DaVinciPASRequest
from app.models.prior_auth import (
    PriorAuthEvaluationRequest,
    PriorAuthEvaluationResponse,
    GuidelineExtractionRequest,
    GuidelineCriteria
)
from app.services.mcp_manager import mcp_manager
from app.services.decision_engine import decision_engine
from app.services.a2a_service import a2a_service
from app.api.clinical_notes import notes_storage
import json

router = APIRouter()

# Storage for evaluations
evaluations_storage: Dict[str, dict] = {}

# Keep all your existing endpoints exactly as they are
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

        print("\n" + "="*60)
        print("✅ PRIOR AUTH EVALUATION COMPLETED")
        print("="*60)
        print(f"📋 Evaluation ID: {evaluation_id}")
        print(f"📝 Note ID: {request.note_id}")
        print(f"🏥 Patient ID: {structured_data.get('patient_id') or 'unknown'}")
        print(f"📊 Decision: {decision.decision}")
        print(f"🎯 Confidence: {decision.confidence_score:.2%}")
        print("="*60)
        print("Use this Evaluation ID for A2A submission:")
        print(f"  {evaluation_id}")
        print("="*60 + "\n")
        
        response = PriorAuthEvaluationResponse(
            evaluation_id=evaluation_id,
            note_id=request.note_id,
            patient_id=structured_data.get('patient_id') or 'unknown',
            decision=decision,
            guideline_used=guideline_criteria,
            justification=justification,
            evaluated_at=structured_data.get('processed_at'),
            processing_time_ms=processing_time
        )
        
        # Store evaluation with additional data for A2A
        evaluation_data = response.dict()
        evaluation_data['structured_data'] = structured_data  # Add this for A2A
        evaluation_data['fhir_bundle'] = fhir_bundle  # Add this for A2A
        evaluations_storage[evaluation_id] = evaluation_data
        
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


# ============= NEW A2A ENDPOINTS START HERE =============

@router.post("/submit-a2a/{evaluation_id}")
async def submit_a2a_prior_auth(
    evaluation_id: str,
    payer: Optional[str] = "medicare",
    format: Optional[str] = "FHIR",
    urgency: Optional[str] = "routine"
):
    """
    Submit prior authorization to payer via A2A protocol (DaVinci PAS)
    
    Args:
        evaluation_id: ID from prior evaluation
        payer: Target payer (medicare, anthem, unitedhealthcare, etc.)
        format: Submission format (FHIR or X12)
        urgency: routine, urgent, or stat
    """
    
        # Create the PAS request object
    pas_request = DaVinciPASRequest(
        patient_id=evaluation.get('patient_id'),
        provider_npi="1234567890",
        payer_id=payer,
        service_date=datetime.now(),
        cpt_codes=["62323"],  # Extract from evaluation
        icd10_codes=["M54.16"],  # Extract from evaluation
        supporting_info={"decision": evaluation.get('decision')},
        urgency=urgency
    )

    if evaluation_id not in evaluations_storage:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    evaluation = evaluations_storage[evaluation_id]
    
    # Extract provider info (mock for demo - in production, get from auth context)
    provider_info = {
        "npi": "1234567890",
        "first_name": "Jane",
        "last_name": "Smith",
        "organization": "Boston Medical Center",
        "phone": "617-555-0100",
        "payer": payer
    }
    
    # Extract patient info from evaluation
    patient_info = {
        "id": evaluation.get('patient_id', 'unknown'),
        "mrn": "MRN-" + evaluation.get('patient_id', 'unknown'),
        "first_name": "John",
        "last_name": "Doe",
        "dob": "1960-01-01",
        "gender": "male"
    }

    
    # Submit via A2A service
    submission = await a2a_service.submit_to_payer(
        evaluation_id=evaluation_id,
        evaluation_data=evaluation,
        pas_request=pas_request
        # provider_info=provider_info,
        # patient_info=patient_info,
        # payer=payer,
        # format=format,
        # urgency=urgency
    )
    
    return {
        "submission_id": submission.submission_id,
        "transaction_id": submission.transaction_id,
        "status": submission.status,
        "tracking_number": submission.tracking_number,
        "payer_endpoint": submission.payer_endpoint,
        "format": submission.request_format,
        "expected_response": submission.expected_response_time,
        "preauth_reference": submission.preauth_reference,
        "message": f"Prior authorization successfully submitted to {payer} via {format} format",
        "details": {
            "patient_id": patient_info["id"],
            "provider_npi": provider_info["npi"],
            "urgency": urgency,
            "decision": evaluation.get('decision', {}).get('decision'),
            "confidence": evaluation.get('decision', {}).get('confidence_score')
        }
    }


@router.get("/a2a-status/{submission_id}")
async def check_a2a_status(submission_id: str):
    """
    Check status of A2A submission
    
    Returns current status and any payer response
    """
    
    status = await a2a_service.check_submission_status(submission_id)
    
    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])
    
    return status


@router.get("/a2a-bundle/{evaluation_id}")
async def get_davinci_pas_bundle(evaluation_id: str):
    """
    Get the DaVinci PAS compliant FHIR Bundle for an evaluation
    
    This shows what will be submitted to the payer
    """
    
    if evaluation_id not in evaluations_storage:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    evaluation = evaluations_storage[evaluation_id]
    
    # Generate the bundle
    bundle = a2a_service.create_davinci_pas_bundle(
        evaluation_data=evaluation,
        provider_info={
            "npi": "1234567890",
            "first_name": "Jane",
            "last_name": "Smith",
            "payer": "Medicare"
        },
        patient_info={
            "id": evaluation.get('patient_id', 'unknown'),
            "first_name": "John",
            "last_name": "Doe"
        }
    )
    
    return {
        "bundle": bundle,
        "resource_count": len(bundle.get("entry", [])),
        "bundle_id": bundle.get("id"),
        "compliance": "DaVinci PAS IG v2.0.1"
    }


@router.get("/x12-278/{evaluation_id}")
async def get_x12_278_format(evaluation_id: str):
    """
    Get X12 278 format for legacy payer systems
    
    Some payers still require X12 EDI format
    """
    
    if evaluation_id not in evaluations_storage:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    
    evaluation = evaluations_storage[evaluation_id]
    x12_message = a2a_service.create_x12_278_request(evaluation)
    
    # Parse segments for display
    segments = x12_message.split("~")
    
    return {
        "format": "X12_278",
        "version": "005010X217",
        "message": x12_message,
        "segments": segments,
        "segment_count": len(segments),
        "transaction_set": "278 - Health Care Services Review",
        "usage": "For legacy payers not supporting FHIR"
    }


@router.get("/a2a-history")
async def get_a2a_submission_history():
    """
    Get history of all A2A submissions
    """
    
    submissions = a2a_service.get_all_submissions()
    
    return {
        "total_submissions": len(submissions),
        "submissions": submissions,
        "stats": {
            "approved": sum(1 for s in submissions if s.get("status") == "approved"),
            "denied": sum(1 for s in submissions if s.get("status") == "denied"),
            "pending": sum(1 for s in submissions if s.get("status") == "pending")
        }
    }


@router.post("/a2a-simulate-response/{submission_id}")
async def simulate_payer_response(
    submission_id: str,
    decision: str = "approved",
    delay_seconds: int = 0
):
    """
    Simulate a payer response for demo purposes
    
    In production, this would be a webhook from the payer
    """
    
    if delay_seconds > 0:
        time.sleep(delay_seconds)
    
    response = await a2a_service.simulate_payer_response(
        submission_id=submission_id,
        decision=decision
    )
    
    if "error" in response:
        raise HTTPException(status_code=404, detail=response["error"])
    
    return response