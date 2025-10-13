import requests
import json

BASE_URL = "http://localhost:8000/api/v1"

print("="*60)
print("PRIOR AUTHORIZATION COMPLETE WORKFLOW TEST")
print("="*60)

# Step 1: Process clinical note
print("\n1️⃣  Processing clinical note...")
with open("data/synthetic_notes/sample_note_1.txt", "r") as f:
    note_text = f.read()

response = requests.post(
    f"{BASE_URL}/clinical-notes/process",
    json={
        "note_text": note_text,
        "patient_id": "PT-12345",
        "encounter_date": "2025-01-15"
    }
)

if response.status_code != 200:
    print(f"❌ Failed to process note: {response.text}")
    exit(1)

note_result = response.json()
note_id = note_result['note_id']
print(f"✅ Note processed: {note_id}")

# Step 2: Extract guideline criteria
print("\n2️⃣  Extracting guideline criteria...")
with open("data/guidelines/lumbar_injection_guideline.txt", "r") as f:
    guideline_text = f.read()

response = requests.post(
    f"{BASE_URL}/prior-auth/extract-guideline",
    json={"guideline_text": guideline_text}
)

if response.status_code != 200:
    print(f"❌ Failed to extract guideline: {response.text}")
    exit(1)

guideline_criteria = response.json()
print(f"✅ Guideline extracted: {guideline_criteria['title']}")
print(f"   Coverage criteria: {len(guideline_criteria['coverage_criteria'])}")
print(f"   ICD-10 codes: {len(guideline_criteria.get('covered_icd10_codes', []))}")
print(f"   CPT codes: {len(guideline_criteria.get('covered_cpt_codes', []))}")

# Step 3: Evaluate prior authorization
print("\n3️⃣  Evaluating prior authorization...")
response = requests.post(
    f"{BASE_URL}/prior-auth/evaluate",
    json={
        "note_id": note_id,
        "guideline_criteria": guideline_criteria
    }
)

if response.status_code != 200:
    print(f"❌ Failed to evaluate: {response.text}")
    exit(1)

evaluation = response.json()
print(f"✅ Evaluation complete: {evaluation['evaluation_id']}")

# Display results
print("\n" + "="*60)
print("PRIOR AUTHORIZATION DECISION")
print("="*60)

decision = evaluation['decision']
print(f"\n🏥 DECISION: {decision['decision'].upper()}")
print(f"🎯 Confidence: {decision['confidence_score']:.2%}")

print(f"\n📋 Reasoning:")
for i, reason in enumerate(decision['reasoning'], 1):
    print(f"   {i}. {reason}")

print(f"\n✅ Matched Criteria ({len(decision['matched_criteria'])}):")
for criterion in decision['matched_criteria']:
    print(f"   • {criterion}")

if decision['unmatched_criteria']:
    print(f"\n❌ Unmatched Criteria ({len(decision['unmatched_criteria'])}):")
    for criterion in decision['unmatched_criteria']:
        print(f"   • {criterion}")

print(f"\n📎 Citations ({len(decision['citations'])}):")
for citation in decision['citations']:
    print(f"   • {citation['claim']}")
    print(f"     Source: {citation['source']}")

if decision.get('requires_additional_documentation'):
    print(f"\n📄 Required Documentation:")
    for doc in decision['requires_additional_documentation']:
        print(f"   • {doc}")

print("\n" + "="*60)
print("JUSTIFICATION")
print("="*60)
print(evaluation['justification'])

print("\n" + "="*60)
print(f"⏱️  Processing Time: {evaluation['processing_time_ms']:.2f}ms")
print("="*60)