import requests
import json

# Read sample note
with open("data/synthetic_notes/sample_note_1.txt", "r") as f:
    note_text = f.read()

# API endpoint
url = "http://localhost:8000/api/v1/clinical-notes/process"

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
print("Status Code:", response.status_code)
print("\nResponse:")
print(json.dumps(response.json(), indent=2))