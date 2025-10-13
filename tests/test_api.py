import requests
import json

# Read sample note
with open("data/synthetic_notes/sample_note_1.txt", "r") as f:
    note_text = f.read()

# API endpoint
url = "http://localhost:8000/api/v1/clinical-notes/process"

print("📝 Processing clinical note...")
print("-" * 50)

# Make request
response = requests.post(
    url,
    json={
        "note_text": note_text,
        "patient_id": "PT-12345",
        "encounter_date": "2025-01-15"
    }
)

# Print results
print(f"Status Code: {response.status_code}")
print("\n" + "=" * 50)

if response.status_code == 200:
    result = response.json()
    print("✅ Success!")
    print(f"\nNote ID: {result['note_id']}")
    print(f"Processing Time: {result['processing_time_ms']:.2f}ms")
    
    print("\n📊 Structured Data:")
    print("-" * 50)
    
    structured = result['structured_data']
    
    print(f"\n🏥 Chief Complaint:")
    print(f"  {structured.get('chief_complaint', 'N/A')}")
    
    print(f"\n💊 Medications:")
    for med in structured.get('current_medications', []):
        print(f"  - {med['name']} {med['dosage']} {med['frequency']}")
    
    print(f"\n🔬 Diagnoses:")
    for dx in structured.get('diagnoses', []):
        print(f"  - [{dx['code']}] {dx['display']}")
    
    print(f"\n⚕️ Procedures:")
    for proc in structured.get('procedures', []):
        print(f"  - [{proc['code']}] {proc['display']}")
    
    print("\n" + "=" * 50)
    print("\n📄 Full Response:")
    # print(json.dumps(result, indent=2))
    
else:
    print("❌ Error!")
    print(response.text)