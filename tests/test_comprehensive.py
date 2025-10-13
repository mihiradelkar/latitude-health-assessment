import requests
import json
import time
from typing import Dict, List
import sys

BASE_URL = "http://localhost:8000/api/v1"

class TestCase:
    def __init__(self, name: str, note_file: str, guideline_file: str, expected_decision: str):
        self.name = name
        self.note_file = note_file
        self.guideline_file = guideline_file
        self.expected_decision = expected_decision
        self.result = None
        self.passed = None
        self.error = None

class TestSuite:
    def __init__(self):
        self.test_cases: List[TestCase] = []
        self.results = []
    
    def add_test_case(self, test_case: TestCase):
        self.test_cases.append(test_case)
    
    def run_all_tests(self):
        print("="*80)
        print("COMPREHENSIVE PRIOR AUTHORIZATION TEST SUITE")
        print("="*80)
        print(f"\nTotal Test Cases: {len(self.test_cases)}\n")
        
        passed = 0
        failed = 0
        
        for i, test_case in enumerate(self.test_cases, 1):
            print(f"\n{'='*80}")
            print(f"Test Case {i}/{len(self.test_cases)}: {test_case.name}")
            print(f"{'='*80}")
            
            try:
                result = self.run_test_case(test_case)
                test_case.result = result
                
                # Check if decision matches expected
                actual_decision = result['decision']['decision'].lower()
                expected = test_case.expected_decision.lower()
                
                if actual_decision == expected:
                    test_case.passed = True
                    passed += 1
                    print(f"\n✅ TEST PASSED")
                else:
                    test_case.passed = False
                    failed += 1
                    print(f"\n❌ TEST FAILED")
                    print(f"   Expected: {expected}")
                    print(f"   Got: {actual_decision}")
                
                # Print summary
                print(f"\n📊 Results:")
                print(f"   Decision: {result['decision']['decision']}")
                print(f"   Confidence: {result['decision']['confidence_score']:.2%}")
                print(f"   Matched Criteria: {len(result['decision']['matched_criteria'])}")
                print(f"   Reasoning Points: {len(result['decision']['reasoning'])}")
                
            except Exception as e:
                test_case.passed = False
                test_case.error = str(e)
                failed += 1
                print(f"\n❌ TEST ERROR: {str(e)}")
        
        # Final summary
        print(f"\n{'='*80}")
        print("FINAL RESULTS")
        print(f"{'='*80}")
        print(f"✅ Passed: {passed}/{len(self.test_cases)}")
        print(f"❌ Failed: {failed}/{len(self.test_cases)}")
        print(f"📊 Success Rate: {(passed/len(self.test_cases)*100):.1f}%")
        print(f"{'='*80}\n")
        
        return passed, failed
    
    def run_test_case(self, test_case: TestCase) -> Dict:
        """Run a single test case"""
        
        # Step 1: Read files
        print("\n1️⃣  Reading clinical note...")
        with open(test_case.note_file, 'r') as f:
            note_text = f.read()
        print(f"   ✅ Loaded note ({len(note_text)} characters)")
        
        print("\n2️⃣  Reading guideline...")
        with open(test_case.guideline_file, 'r') as f:
            guideline_text = f.read()
        print(f"   ✅ Loaded guideline ({len(guideline_text)} characters)")
        
        # Step 2: Process note
        print("\n3️⃣  Processing clinical note...")
        response = requests.post(
            f"{BASE_URL}/clinical-notes/process",
            json={
                "note_text": note_text,
                "patient_id": f"TEST-{int(time.time())}",
                "encounter_date": "2025-01-20"
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to process note: {response.text}")
        
        note_result = response.json()
        note_id = note_result['note_id']
        print(f"   ✅ Note processed: {note_id}")
        print(f"   📊 Extracted: {len(note_result['structured_data'].get('diagnoses', []))} diagnoses, "
              f"{len(note_result['structured_data'].get('procedures', []))} procedures")
        
        # Step 3: Extract guideline
        print("\n4️⃣  Extracting guideline criteria...")
        response = requests.post(
            f"{BASE_URL}/prior-auth/extract-guideline",
            json={"guideline_text": guideline_text}
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to extract guideline: {response.text}")
        
        guideline_criteria = response.json()
        print(f"   ✅ Guideline extracted: {guideline_criteria.get('title', 'N/A')}")
        print(f"   📋 {len(guideline_criteria.get('coverage_criteria', []))} coverage criteria")
        
        # Step 4: Evaluate
        print("\n5️⃣  Evaluating prior authorization...")
        response = requests.post(
            f"{BASE_URL}/prior-auth/evaluate",
            json={
                "note_id": note_id,
                "guideline_criteria": guideline_criteria
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to evaluate: {response.text}")
        
        evaluation = response.json()
        print(f"   ✅ Evaluation complete: {evaluation['evaluation_id']}")
        
        return evaluation


# Define test cases
def create_test_suite():
    suite = TestSuite()
    
    # Test Case 1: Should be APPROVED
    suite.add_test_case(TestCase(
        name="Knee Arthroscopy - All Criteria Met",
        note_file="data/synthetic_notes/test_cases/case_approved.txt",
        guideline_file="data/guidelines/test_policies/knee_arthroscopy_policy.txt",
        expected_decision="approved"
    ))
    
    # Test Case 2: Should be DENIED
    suite.add_test_case(TestCase(
        name="Acute Back Pain - Insufficient Conservative Therapy",
        note_file="data/synthetic_notes/test_cases/case_denied_insufficient.txt",
        guideline_file="data/guidelines/lumbar_injection_guideline.txt",
        expected_decision="denied"
    ))
    
    # Test Case 3: Should be NEEDS_MORE_INFO
    suite.add_test_case(TestCase(
        name="Cardiac Cath - Missing Diagnostic Workup",
        note_file="data/synthetic_notes/test_cases/case_needs_info.txt",
        guideline_file="data/guidelines/test_policies/cardiac_cath_policy.txt",
        expected_decision="needs_more_info"
    ))
    
    # Test Case 4: Original lumbar case
    suite.add_test_case(TestCase(
        name="Lumbar Epidural - Original Case",
        note_file="data/synthetic_notes/sample_note_1.txt",
        guideline_file="data/guidelines/lumbar_injection_guideline.txt",
        expected_decision="denied"
    ))
    
    return suite


if __name__ == "__main__":
    print("\n🧪 Starting Comprehensive Test Suite...\n")
    
    # Check if API is running
    try:
        response = requests.get(f"{BASE_URL.replace('/api/v1', '')}/health")
        if response.status_code != 200:
            print("❌ API is not running. Please start the API first:")
            print("   uvicorn app.main:app --reload --port 8000")
            sys.exit(1)
        print("✅ API is running\n")
    except:
        print("❌ Cannot connect to API. Please start the API first:")
        print("   uvicorn app.main:app --reload --port 8000")
        sys.exit(1)
    
    # Create and run test suite
    suite = create_test_suite()
    passed, failed = suite.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)