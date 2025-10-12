from datetime import datetime
from typing import List, Dict, Any
import uuid

from app.models.clinical_note import StructuredClinicalNote


class FHIRMapper:
    """Maps structured clinical data to FHIR resources"""
    
    def __init__(self):
        self.base_url = "http://example.org/fhir"
    
    def map_to_fhir_bundle(self, structured_note: StructuredClinicalNote) -> Dict[str, Any]:
        """
        Convert structured clinical note to FHIR Bundle containing all resources
        """
        
        patient_id = structured_note.patient_id or f"patient-{uuid.uuid4()}"
        encounter_id = f"encounter-{uuid.uuid4()}"
        
        # Create all resources
        entries = []
        
        # Add patient
        patient = self._create_patient(patient_id)
        entries.append({
            "fullUrl": f"{self.base_url}/Patient/{patient_id}",
            "resource": patient
        })
        
        # Add conditions
        conditions = self._create_conditions(structured_note, patient_id)
        for condition in conditions:
            entries.append({
                "fullUrl": f"{self.base_url}/Condition/{condition['id']}",
                "resource": condition
            })
        
        # Add medications
        medications = self._create_medication_requests(structured_note, patient_id)
        for med in medications:
            entries.append({
                "fullUrl": f"{self.base_url}/MedicationRequest/{med['id']}",
                "resource": med
            })
        
        # Add observations
        observations = self._create_observations(structured_note, patient_id, encounter_id)
        for obs in observations:
            entries.append({
                "fullUrl": f"{self.base_url}/Observation/{obs['id']}",
                "resource": obs
            })
        
        # Add procedures
        procedures = self._create_procedures(structured_note, patient_id)
        for proc in procedures:
            entries.append({
                "fullUrl": f"{self.base_url}/Procedure/{proc['id']}",
                "resource": proc
            })
        
        # Add allergies
        allergies = self._create_allergies(structured_note, patient_id)
        for allergy in allergies:
            entries.append({
                "fullUrl": f"{self.base_url}/AllergyIntolerance/{allergy['id']}",
                "resource": allergy
            })
        
        # Create bundle
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "timestamp": datetime.now().isoformat(),
            "entry": entries,
            "total": len(entries)
        }
        
        return bundle
    
    def _create_patient(self, patient_id: str) -> Dict[str, Any]:
        """Create FHIR Patient resource"""
        return {
            "resourceType": "Patient",
            "id": patient_id,
            "identifier": [{
                "system": "http://example.org/patient-ids",
                "value": patient_id
            }],
            "active": True
        }
    
    def _create_conditions(self, note: StructuredClinicalNote, patient_id: str) -> List[Dict[str, Any]]:
        """Create FHIR Condition resources from diagnoses"""
        conditions = []
        
        if not note.diagnoses:
            return conditions
        
        for dx in note.diagnoses:
            condition = {
                "resourceType": "Condition",
                "id": f"condition-{uuid.uuid4()}",
                "clinicalStatus": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "active",
                        "display": "Active"
                    }]
                },
                "verificationStatus": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
                        "code": "confirmed",
                        "display": "Confirmed"
                    }]
                },
                "code": {
                    "coding": [{
                        "system": "http://hl7.org/fhir/sid/icd-10-cm",
                        "code": dx.code,
                        "display": dx.display
                    }],
                    "text": dx.display
                },
                "subject": {
                    "reference": f"Patient/{patient_id}"
                },
                "recordedDate": note.encounter_date or datetime.now().date().isoformat()
            }
            conditions.append(condition)
        
        return conditions
    
    def _create_medication_requests(self, note: StructuredClinicalNote, patient_id: str) -> List[Dict[str, Any]]:
        """Create FHIR MedicationRequest resources"""
        medications = []
        
        if not note.current_medications:
            return medications
        
        for med in note.current_medications:
            # Build dosage instruction
            dosage_parts = []
            if med.dosage:
                dosage_parts.append(med.dosage)
            if med.frequency:
                dosage_parts.append(med.frequency)
            dosage_text = " ".join(dosage_parts) if dosage_parts else "As directed"
            
            med_request = {
                "resourceType": "MedicationRequest",
                "id": f"medicationrequest-{uuid.uuid4()}",
                "status": "active",
                "intent": "order",
                "medicationCodeableConcept": {
                    "text": med.name
                },
                "subject": {
                    "reference": f"Patient/{patient_id}"
                },
                "dosageInstruction": [{
                    "text": dosage_text,
                    "route": {
                        "text": med.route
                    } if med.route else None
                }]
            }
            medications.append(med_request)
        
        return medications
    
    def _create_observations(self, note: StructuredClinicalNote, patient_id: str, encounter_id: str) -> List[Dict[str, Any]]:
        """Create FHIR Observation resources from labs/imaging"""
        observations = []
        
        if not note.labs_imaging:
            return observations
        
        for lab in note.labs_imaging:
            value_string = lab.value
            if lab.unit:
                value_string = f"{lab.value} {lab.unit}"
            
            observation = {
                "resourceType": "Observation",
                "id": f"observation-{uuid.uuid4()}",
                "status": "final",
                "code": {
                    "text": lab.test_name
                },
                "subject": {
                    "reference": f"Patient/{patient_id}"
                },
                "encounter": {
                    "reference": f"Encounter/{encounter_id}"
                },
                "valueString": value_string
            }
            
            if lab.reference_range:
                observation["referenceRange"] = [{
                    "text": lab.reference_range
                }]
            
            observations.append(observation)
        
        return observations
    
    def _create_procedures(self, note: StructuredClinicalNote, patient_id: str) -> List[Dict[str, Any]]:
        """Create FHIR Procedure resources"""
        procedures = []
        
        if not note.procedures:
            return procedures
        
        for proc in note.procedures:
            procedure = {
                "resourceType": "Procedure",
                "id": f"procedure-{uuid.uuid4()}",
                "status": "preparation",  # These are planned/requested procedures
                "code": {
                    "coding": [{
                        "system": "http://www.ama-assn.org/go/cpt",
                        "code": proc.code,
                        "display": proc.display
                    }],
                    "text": proc.display
                },
                "subject": {
                    "reference": f"Patient/{patient_id}"
                },
                "performedDateTime": note.encounter_date or datetime.now().date().isoformat()
            }
            procedures.append(procedure)
        
        return procedures
    
    def _create_allergies(self, note: StructuredClinicalNote, patient_id: str) -> List[Dict[str, Any]]:
        """Create FHIR AllergyIntolerance resources"""
        allergies = []
        
        if not note.allergies:
            return allergies
        
        for allergy in note.allergies:
            # Map severity
            severity = "mild"
            if allergy.severity:
                severity_lower = allergy.severity.lower()
                if severity_lower in ["mild", "moderate", "severe"]:
                    severity = severity_lower
            
            allergy_resource = {
                "resourceType": "AllergyIntolerance",
                "id": f"allergyintolerance-{uuid.uuid4()}",
                "clinicalStatus": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
                        "code": "active",
                        "display": "Active"
                    }]
                },
                "verificationStatus": {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
                        "code": "confirmed",
                        "display": "Confirmed"
                    }]
                },
                "code": {
                    "text": allergy.substance
                },
                "patient": {
                    "reference": f"Patient/{patient_id}"
                }
            }
            
            if allergy.reaction:
                allergy_resource["reaction"] = [{
                    "substance": {
                        "text": allergy.substance
                    },
                    "manifestation": [{
                        "text": allergy.reaction
                    }],
                    "severity": severity
                }]
            
            allergies.append(allergy_resource)
        
        return allergies


# Singleton instance
fhir_mapper = FHIRMapper()