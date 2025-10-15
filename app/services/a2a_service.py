from typing import Dict, Any, List, Optional
import uuid
import json
from datetime import datetime, timedelta
import logging
from app.models.a2a_models import A2ASubmission, A2AStatus, DaVinciPASRequest

logger = logging.getLogger(__name__)

class A2AService:
    """Service for A2A prior authorization submissions"""
    
    def __init__(self):
        self.payer_endpoints = {
            "medicare": "https://medicare.gov/davinci-pas/v1/claim",
            "anthem": "https://anthem.com/pas/api/v1",
            "unitedhealthcare": "https://uhc.com/prior-auth/v1",
            "default": "https://payer.example.com/pas/v1"
        }
        
        # Track submissions (in production, use database)
        self.submissions = {}
        
    def create_davinci_pas_bundle(
        self,
        evaluation_data: Dict[str, Any],
        provider_info: Dict[str, Any],
        patient_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create DaVinci PAS compliant FHIR Bundle"""
        
        bundle_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # Extract decision details
        decision = evaluation_data.get('decision', {})
        
        # Create the FHIR Bundle following DaVinci PAS IG
        bundle = {
            "resourceType": "Bundle",
            "id": bundle_id,
            "type": "collection",
            "timestamp": timestamp,
            "entry": []
        }
        
        # 1. Patient Resource
        patient = {
            "resourceType": "Patient",
            "id": patient_info.get('id', str(uuid.uuid4())),
            "identifier": [{
                "system": "http://example.org/patient-id",
                "value": patient_info.get('mrn', 'unknown')
            }],
            "name": [{
                "family": patient_info.get('last_name', 'Doe'),
                "given": [patient_info.get('first_name', 'John')]
            }],
            "birthDate": patient_info.get('dob', '1960-01-01'),
            "gender": patient_info.get('gender', 'unknown')
        }
        bundle["entry"].append({"resource": patient})
        
        # 2. Practitioner Resource
        practitioner = {
            "resourceType": "Practitioner",
            "id": str(uuid.uuid4()),
            "identifier": [{
                "system": "http://hl7.org/fhir/sid/us-npi",
                "value": provider_info.get('npi', '1234567890')
            }],
            "name": [{
                "family": provider_info.get('last_name', 'Smith'),
                "given": [provider_info.get('first_name', 'Jane')],
                "prefix": ["Dr."]
            }]
        }
        bundle["entry"].append({"resource": practitioner})
        
        # 3. Coverage Resource (Insurance)
        coverage = {
            "resourceType": "Coverage",
            "id": str(uuid.uuid4()),
            "status": "active",
            "beneficiary": {
                "reference": f"Patient/{patient['id']}"
            },
            "payor": [{
                "display": provider_info.get('payer', 'Medicare')
            }],
            "class": [{
                "type": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/coverage-class",
                        "code": "plan"
                    }]
                },
                "value": "Medicare Part B"
            }]
        }
        bundle["entry"].append({"resource": coverage})
        
        # 4. Claim Resource (Prior Auth Request)
        claim = {
            "resourceType": "Claim",
            "id": str(uuid.uuid4()),
            "status": "active",
            "type": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                    "code": "professional"
                }]
            },
            "use": "preauthorization",
            "patient": {
                "reference": f"Patient/{patient['id']}"
            },
            "created": timestamp,
            "provider": {
                "reference": f"Practitioner/{practitioner['id']}"
            },
            "priority": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/processpriority",
                    "code": "normal"
                }]
            },
            "insurance": [{
                "sequence": 1,
                "focal": True,
                "coverage": {
                    "reference": f"Coverage/{coverage['id']}"
                }
            }],
            "diagnosis": self._build_diagnosis_list(evaluation_data),
            "item": self._build_service_items(evaluation_data),
            "supportingInfo": self._build_supporting_info(evaluation_data, decision)
        }
        bundle["entry"].append({"resource": claim})
        
        # 5. Add ClaimResponse if we're simulating response
        if decision.get('decision') == 'approved':
            claim_response = self._create_claim_response(claim, decision)
            bundle["entry"].append({"resource": claim_response})
        
        logger.info(f"Created DaVinci PAS bundle with {len(bundle['entry'])} resources")
        return bundle
    
    def _build_diagnosis_list(self, evaluation_data: Dict) -> List[Dict]:
        """Build diagnosis list for claim"""
        diagnoses = []
        structured_data = evaluation_data.get('structured_data', {})
        
        for idx, diag in enumerate(structured_data.get('diagnoses', []), 1):
            diagnoses.append({
                "sequence": idx,
                "diagnosisCodeableConcept": {
                    "coding": [{
                        "system": "http://hl7.org/fhir/sid/icd-10-cm",
                        "code": diag.get('code', 'M54.5'),
                        "display": diag.get('display', 'Low back pain')
                    }]
                }
            })
        
        return diagnoses
    
    def _build_service_items(self, evaluation_data: Dict) -> List[Dict]:
        """Build service items for claim"""
        items = []
        structured_data = evaluation_data.get('structured_data', {})
        
        for idx, proc in enumerate(structured_data.get('procedures', []), 1):
            items.append({
                "sequence": idx,
                "productOrService": {
                    "coding": [{
                        "system": "http://www.ama-assn.org/go/cpt",
                        "code": proc.get('code', '62323'),
                        "display": proc.get('display', 'Epidural injection')
                    }]
                },
                "servicedDate": datetime.now().date().isoformat()
            })
        
        # If no procedures, add a default
        if not items:
            items.append({
                "sequence": 1,
                "productOrService": {
                    "coding": [{
                        "system": "http://www.ama-assn.org/go/cpt",
                        "code": "62323",
                        "display": "Lumbar epidural injection"
                    }]
                },
                "servicedDate": datetime.now().date().isoformat()
            })
        
        return items
    
    def _build_supporting_info(self, evaluation_data: Dict, decision: Dict) -> List[Dict]:
        """Build supporting information for claim"""
        supporting_info = []
        
        # Add clinical documentation
        supporting_info.append({
            "sequence": 1,
            "category": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/claiminformationcategory",
                    "code": "info",
                    "display": "Information"
                }]
            },
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "11506-3",
                    "display": "Progress note"
                }]
            },
            "valueString": decision.get('justification', 'Clinical documentation supports medical necessity')
        })
        
        # Add treatment history
        if 'matched_criteria' in decision:
            supporting_info.append({
                "sequence": 2,
                "category": {
                    "coding": [{
                        "code": "treatment-history"
                    }]
                },
                "valueString": f"Matched criteria: {', '.join(decision['matched_criteria'][:3])}"
            })
        
        return supporting_info
    
    def _create_claim_response(self, claim: Dict, decision: Dict) -> Dict:
        """Create ClaimResponse for approved requests"""
        return {
            "resourceType": "ClaimResponse",
            "id": str(uuid.uuid4()),
            "status": "active",
            "type": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                    "code": "professional"
                }]
            },
            "use": "preauthorization",
            "patient": claim["patient"],
            "created": datetime.now().isoformat(),
            "insurer": {
                "display": "Payer Organization"
            },
            "outcome": "complete",
            "disposition": f"Prior authorization approved with {decision.get('confidence_score', 0.85):.0%} confidence",
            "preAuthRef": f"PA{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "preAuthPeriod": {
                "start": datetime.now().date().isoformat(),
                "end": (datetime.now() + timedelta(days=90)).date().isoformat()
            },
            "item": [{
                "itemSequence": 1,
                "adjudication": [{
                    "category": {
                        "coding": [{
                            "code": "benefit"
                        }]
                    },
                    "reason": {
                        "coding": [{
                            "system": "http://terminology.hl7.org/CodeSystem/adjudication-reason",
                            "code": "ar001",
                            "display": "Meets medical necessity"
                        }]
                    }
                }]
            }]
        }
    
    def create_x12_278_request(self, evaluation_data: Dict) -> str:
        """Create X12 278 format request for legacy systems"""
        
        # X12 278 Health Care Services Review Request
        segments = []
        
        # ISA - Interchange Control Header
        segments.append("ISA*00*          *00*          *ZZ*PROVIDER       *ZZ*PAYER          *241015*1200*^*00501*000000001*0*P*:")
        
        # GS - Functional Group Header
        segments.append("GS*HI*PROVIDER*PAYER*20241015*1200*1*X*005010X217")
        
        # ST - Transaction Set Header
        segments.append("ST*278*0001*005010X217")
        
        # BHT - Beginning of Hierarchical Transaction
        segments.append("BHT*0007*13*" + str(uuid.uuid4())[:10] + "*20241015*1200")
        
        # Loop 2000A - Utilization Management Organization
        segments.append("HL*1**20*1")
        segments.append("NM1*X3*2*PAYER ORGANIZATION*****PI*87654321")
        
        # Loop 2000B - Requester
        segments.append("HL*2*1*21*1")
        segments.append("NM1*1P*2*PROVIDER CLINIC*****XX*1234567890")
        
        # Loop 2000C - Subscriber
        segments.append("HL*3*2*22*0")
        segments.append("NM1*IL*1*DOE*JOHN****MI*123456789")
        
        # Loop 2000E - Service
        segments.append("HL*4*3*EV*1")
        segments.append("UM*SC*I*1***Y")  # Service Certification, Initial, Medical Care
        
        # HCR - Health Care Services Review
        segments.append("HCR*A1*C1")  # Certified in Total, Approved
        
        # SE - Transaction Set Trailer
        segments.append("SE*15*0001")
        
        # GE - Functional Group Trailer
        segments.append("GE*1*1")
        
        # IEA - Interchange Control Trailer
        segments.append("IEA*1*000000001")
        
        return "~".join(segments)
    
    async def submit_to_payer(
        self,
        evaluation_id: str,
        evaluation_data: Dict[str, Any],
        pas_request: DaVinciPASRequest  # Use the model here
    ) -> A2ASubmission:
        """Submit prior auth to payer via A2A"""
        
        # Then use pas_request fields
        endpoint = self.payer_endpoints.get(pas_request.payer_id.lower(), self.payer_endpoints["default"])
        
        # Use pas_request data in bundle creation
        provider_info = {
            "npi": pas_request.provider_npi,
            "payer": pas_request.payer_id
        }
        patient_info = {
            "id": pas_request.patient_id
        }

        # Create request based on format
        if format == "FHIR":
            bundle = self.create_davinci_pas_bundle(
                evaluation_data,
                provider_info,
                patient_info
            )
            # Add urgency to bundle
            if bundle["entry"]:
                for entry in bundle["entry"]:
                    if entry["resource"]["resourceType"] == "Claim":
                        entry["resource"]["priority"] = {
                            "coding": [{
                                "system": "http://terminology.hl7.org/CodeSystem/processpriority",
                                "code": urgency
                            }]
                        }
            payload = bundle
            x12_payload = None
        else:
            x12_payload = self.create_x12_278_request(evaluation_data)
            payload = None

        # Create submission record
        submission = A2ASubmission(
            submission_id=submission_id,
            transaction_id=transaction_id,
            evaluation_id=evaluation_id,
            status=A2AStatus.SUBMITTED,
            submitted_at=datetime.now(),
            payer_endpoint=endpoint,
            request_format=format,
            fhir_bundle=payload,
            x12_payload=x12_payload,
            tracking_number=preauth_ref,
            preauth_reference=preauth_ref,  # Add this field to model
            expected_response_time="2-4 hours" if urgency == "routine" else "30 minutes",
            urgency=urgency  # Add this field to model
        )

        # Store submission
        self.submissions[submission_id] = submission

        # Set initial status based on decision
        decision = evaluation_data.get('decision', {}).get('decision')
        if decision == 'approved':
            submission.status = A2AStatus.PENDING  # Will change to APPROVED after "processing"
        elif decision == 'denied':
            submission.status = A2AStatus.DENIED
        else:
            submission.status = A2AStatus.PENDING

        logger.info(f"Submitted prior auth {submission_id} to {endpoint} with urgency: {urgency}")
        return submission

    # Add these helper methods to a2a_service.py:

    def get_all_submissions(self) -> List[Dict]:
        """Get all submissions for history"""
        return [s.dict() for s in self.submissions.values()]

    async def simulate_payer_response(
        self,
        submission_id: str,
        decision: str
    ) -> Dict[str, Any]:
        """Simulate payer response for demo"""

        if submission_id not in self.submissions:
            return {"error": "Submission not found"}

        submission = self.submissions[submission_id]

        # Update status based on decision
        if decision == "approved":
            submission.status = A2AStatus.APPROVED
            submission.response_received = {
                "decision": "approved",
                "reference_number": f"REF{datetime.now().strftime('%Y%m%d%H%M%S')}",
                "valid_from": datetime.now().isoformat(),
                "valid_to": (datetime.now() + timedelta(days=90)).isoformat(),
                "authorized_units": 3,
                "notes": "Approved for 3 treatments over 90 days"
            }
        elif decision == "denied":
            submission.status = A2AStatus.DENIED
            submission.response_received = {
                "decision": "denied",
                "reason": "Does not meet medical necessity criteria",
                "appeal_rights": "You may appeal this decision within 30 days"
            }
        else:
            submission.status = A2AStatus.PENDING
            submission.response_received = {
                "decision": "pending",
                "reason": "Additional information required",
                "requested_info": ["Recent imaging results", "Specialist consultation"]
            }

        return submission.dict()
    
    async def check_submission_status(self, submission_id: str) -> Dict[str, Any]:
        """Check status of A2A submission"""
        
        if submission_id not in self.submissions:
            return {"error": "Submission not found"}
        
        submission = self.submissions[submission_id]
        
        # Simulate status updates
        time_diff = datetime.now() - submission.submitted_at
        if time_diff.total_seconds() > 10:
            # After 10 seconds, mark as processed
            if submission.status == A2AStatus.SUBMITTED:
                submission.status = A2AStatus.APPROVED
                submission.response_received = {
                    "decision": "approved",
                    "reference_number": f"REF{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    "valid_from": datetime.now().isoformat(),
                    "valid_to": (datetime.now() + timedelta(days=90)).isoformat()
                }
        
        return submission.dict()

# Singleton instance
a2a_service = A2AService()