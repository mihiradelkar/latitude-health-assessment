import requests

BASE_URL = "http://localhost:8000/api/v1"

def test_upload_image():
    """Test uploading an image file"""
    
    # You need to have a test image - create one or use an existing file
    test_file_path = "test_clinical_note.jpg"  # Replace with your test file
    
    with open(test_file_path, 'rb') as f:
        files = {'file': (test_file_path, f, 'image/jpeg')}
        data = {
            'patient_id': 'PT-OCR-TEST',
            'encounter_date': '2025-01-15'
        }
        
        print(f"Uploading {test_file_path}...")
        response = requests.post(
            f"{BASE_URL}/clinical-notes/upload",
            files=files,
            data=data
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Success!")
            print(f"Note ID: {result['note_id']}")
            print(f"Processing Time: {result['processing_time_ms']:.0f}ms")
            print(f"\nExtracted Diagnoses: {len(result['structured_data']['diagnoses'])}")
            print(f"Extracted Medications: {len(result['structured_data']['current_medications'])}")
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)

if __name__ == "__main__":
    test_upload_image()