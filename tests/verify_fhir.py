import requests
import json

# Process a note
url = "http://localhost:8000/api/v1/clinical-notes/process"

with open("data/synthetic_notes/sample_note_1.txt", "r") as f:
    note_text = f.read()

response = requests.post(url, json={
    "note_text": note_text,
    "patient_id": "PT-12345",
    "encounter_date": "2025-01-15"
})

result = response.json()

print("="*60)
print("FHIR BUNDLE VERIFICATION")
print("="*60)

# Check if FHIR resources exist
if 'fhir_resources' not in result:
    print("❌ No FHIR resources in response")
    exit(1)

fhir_bundle = result['fhir_resources']

# Verify it's a bundle
if fhir_bundle.get('resourceType') != 'Bundle':
    print(f"❌ Not a Bundle. Got: {fhir_bundle.get('resourceType')}")
    exit(1)

print(f"✅ Resource Type: {fhir_bundle['resourceType']}")
print(f"✅ Bundle Type: {fhir_bundle['type']}")
print(f"✅ Total Entries: {fhir_bundle.get('total', len(fhir_bundle.get('entry', [])))}")

# Count resource types
resource_counts = {}
print("\n" + "="*60)
print("RESOURCES IN BUNDLE:")
print("="*60)

for entry in fhir_bundle.get('entry', []):
    resource = entry.get('resource', {})
    resource_type = resource.get('resourceType', 'Unknown')
    
    if resource_type not in resource_counts:
        resource_counts[resource_type] = 0
    resource_counts[resource_type] += 1

for resource_type, count in sorted(resource_counts.items()):
    print(f"  {resource_type}: {count}")

# Detailed verification
print("\n" + "="*60)
print("DETAILED VERIFICATION:")
print("="*60)

expected_resources = {
    'Patient': 1,
    'Condition': 'at least 1',
    'MedicationRequest': 'at least 1',
    'Observation': 'optional',
    'Procedure': 'optional',
    'AllergyIntolerance': 'optional'
}

for resource_type, expected in expected_resources.items():
    count = resource_counts.get(resource_type, 0)
    if expected == 'at least 1':
        if count >= 1:
            print(f"✅ {resource_type}: {count} found")
        else:
            print(f"⚠️  {resource_type}: None found (expected at least 1)")
    elif expected == 'optional':
        if count > 0:
            print(f"✅ {resource_type}: {count} found")
        else:
            print(f"ℹ️  {resource_type}: None (optional)")
    else:
        if count == expected:
            print(f"✅ {resource_type}: {count} found (expected {expected})")
        else:
            print(f"❌ {resource_type}: {count} found (expected {expected})")

# Check specific resources
print("\n" + "="*60)
print("SAMPLE RESOURCES:")
print("="*60)

for entry in fhir_bundle.get('entry', []):
    resource = entry.get('resource', {})
    resource_type = resource.get('resourceType')
    
    if resource_type == 'Patient':
        print(f"\n📋 Patient:")
        print(f"   ID: {resource.get('id')}")
        print(f"   Active: {resource.get('active')}")
    
    elif resource_type == 'Condition':
        print(f"\n🏥 Condition:")
        code = resource.get('code', {}).get('coding', [{}])[0]
        print(f"   Code: {code.get('code')} ({code.get('system')})")
        print(f"   Display: {code.get('display')}")
        print(f"   Status: {resource.get('clinicalStatus', {}).get('coding', [{}])[0].get('code')}")
    
    elif resource_type == 'MedicationRequest':
        print(f"\n💊 Medication:")
        med_concept = resource.get('medicationCodeableConcept', {})
        print(f"   Name: {med_concept.get('text')}")
        dosage = resource.get('dosageInstruction', [{}])[0]
        print(f"   Dosage: {dosage.get('text')}")
        print(f"   Status: {resource.get('status')}")
    
    elif resource_type == 'Procedure':
        print(f"\n⚕️  Procedure:")
        code = resource.get('code', {}).get('coding', [{}])[0]
        print(f"   Code: {code.get('code')} ({code.get('system')})")
        print(f"   Display: {code.get('display')}")
        print(f"   Status: {resource.get('status')}")

# Check for ICD-10 and CPT codes
print("\n" + "="*60)
print("MEDICAL CODES EXTRACTED:")
print("="*60)

icd10_codes = []
cpt_codes = []

for entry in fhir_bundle.get('entry', []):
    resource = entry.get('resource', {})
    
    if resource.get('resourceType') == 'Condition':
        code_obj = resource.get('code', {}).get('coding', [{}])[0]
        if 'icd-10' in code_obj.get('system', '').lower():
            icd10_codes.append(f"{code_obj.get('code')} - {code_obj.get('display')}")
    
    if resource.get('resourceType') == 'Procedure':
        code_obj = resource.get('code', {}).get('coding', [{}])[0]
        if 'cpt' in code_obj.get('system', '').lower():
            cpt_codes.append(f"{code_obj.get('code')} - {code_obj.get('display')}")

print(f"\n🔍 ICD-10 Codes ({len(icd10_codes)}):")
for code in icd10_codes:
    print(f"   • {code}")

print(f"\n🔍 CPT Codes ({len(cpt_codes)}):")
for code in cpt_codes:
    print(f"   • {code}")

# Overall assessment
print("\n" + "="*60)
print("OVERALL ASSESSMENT:")
print("="*60)

issues = []

if fhir_bundle.get('resourceType') != 'Bundle':
    issues.append("Not a valid FHIR Bundle")

if not fhir_bundle.get('entry'):
    issues.append("Bundle has no entries")

if resource_counts.get('Patient', 0) != 1:
    issues.append("Should have exactly 1 Patient resource")

if resource_counts.get('Condition', 0) == 0:
    issues.append("Should have at least 1 Condition resource")

if resource_counts.get('MedicationRequest', 0) == 0:
    issues.append("Should have at least 1 MedicationRequest resource")

if len(icd10_codes) == 0:
    issues.append("No ICD-10 codes found")

if len(cpt_codes) == 0:
    issues.append("No CPT codes found")

if issues:
    print("⚠️  Issues found:")
    for issue in issues:
        print(f"   • {issue}")
else:
    print("✅ ALL CHECKS PASSED!")
    print("   • Valid FHIR Bundle structure")
    print("   • All expected resources present")
    print("   • Medical codes properly extracted")
    print("   • Ready for prior authorization evaluation")

print("="*60)