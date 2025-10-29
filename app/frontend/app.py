# app\frontend\app.py
import streamlit as st
import requests
import json
from datetime import datetime

st.set_page_config(page_title="Prior Auth AI System", page_icon="🏥", layout="wide")

BASE_URL = "http://localhost:8000/api/v1"

st.title("🏥 AI-Powered Prior Authorization System")
st.markdown("**Latitude Health Assessment** - Clinical Note Processing + FHIR + MCP + LLM")

# Sidebar
with st.sidebar:
    st.header("System Info")
    st.info("""
    This system demonstrates:
    - Clinical note structuring with LLM
    - PDF/Image upload with OCR
    - FHIR resource mapping
    - Model Context Protocol (MCP)
    - Prior authorization evaluation
    - A2A workflow simulation
    """)
    
    # Health check
    try:
        response = requests.get(f"{BASE_URL.replace('/api/v1', '')}/health")
        if response.status_code == 200:
            st.success("✅ API Connected")
        else:
            st.error("❌ API Error")
    except:
        st.error("❌ API Not Running")

# Main tabs - Added Upload tab
tab1, tab1_5, tab2, tab3, tab4 = st.tabs([
    "Process Clinical Note",
    "Upload Document (OCR)",
    "Extract Guidelines", 
    "Evaluate Prior Auth",
    "View Results"
])

# Tab 1: Process Clinical Note (existing code)
with tab1:
    st.header("Step 1A: Process Clinical Note (Text)")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        clinical_note = st.text_area(
            "Enter Clinical Note",
            height=400,
            value="""PATIENT: John Doe
DATE: 2025-01-15

CHIEF COMPLAINT:
Lower back pain radiating to left leg.

HISTORY OF PRESENT ILLNESS:
58-year-old male with chronic lower back pain for past 18 months, now with new onset of radiating pain down left leg for past 6 weeks. Pain is sharp, rated 8/10, worse with sitting and standing. Conservative treatment including physical therapy for 3 months and NSAIDs have provided minimal relief. Patient reports numbness in left foot.

PAST MEDICAL HISTORY:
- Type 2 Diabetes Mellitus (E11.9)
- Hypertension (I10)
- Lumbar disc degeneration (M51.36)

CURRENT MEDICATIONS:
- Metformin 1000mg PO BID
- Lisinopril 20mg PO daily
- Ibuprofen 600mg PO TID PRN

PHYSICAL EXAMINATION:
Vitals: BP 138/88, HR 76
Musculoskeletal: Tenderness over L4-L5 region. Positive straight leg raise on left at 45 degrees. Decreased sensation in L5 distribution on left foot.

LABS AND IMAGING:
- HbA1c: 7.2% (reference: <7.0%)
- MRI Lumbar Spine (01/10/2025): Moderate L4-L5 disc herniation with nerve root impingement

ASSESSMENT AND PLAN:
1. Lumbar radiculopathy secondary to L4-L5 disc herniation (M51.16)
   - Recommend epidural steroid injection

PROCEDURES REQUESTED:
- Lumbar epidural steroid injection (CPT 62323)"""
        )
    
    with col2:
        st.subheader("Patient Info")
        patient_id = st.text_input("Patient ID", value="PT-12345")
        encounter_date = st.date_input("Encounter Date", value=datetime(2025, 1, 15))
    
    if st.button("🔄 Process Note", type="primary", key="process_text"):
        with st.spinner("Processing clinical note with LLM..."):
            try:
                response = requests.post(
                    f"{BASE_URL}/clinical-notes/process",
                    json={
                        "note_text": clinical_note,
                        "patient_id": patient_id,
                        "encounter_date": str(encounter_date)
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    st.session_state['note_result'] = result
                    st.session_state['note_id'] = result['note_id']
                    
                    st.success(f"✅ Note processed! ID: {result['note_id']}")
                    
                    # Show structured data
                    structured = result['structured_data']
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Diagnoses", len(structured.get('diagnoses', [])))
                    with col2:
                        st.metric("Medications", len(structured.get('current_medications', [])))
                    with col3:
                        st.metric("Procedures", len(structured.get('procedures', [])))
                    
                    with st.expander("📊 View Structured Data"):
                        st.json(structured)
                    
                    with st.expander("🔗 View FHIR Resources"):
                        st.json(result.get('fhir_resources'))
                    
                else:
                    st.error(f"Error: {response.text}")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# Tab 1.5: Upload Document with OCR (NEW)
with tab1_5:
    st.header("Step 1B: Upload Document (PDF/Image)")
    
    st.info("📄 Upload a PDF or image of a clinical note. The system will use OCR to extract text and then process it.")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=['pdf', 'jpg', 'jpeg', 'png', 'bmp', 'tiff'],
            help="Supported formats: PDF, JPG, PNG, BMP, TIFF (Max 10MB)"
        )
        
        if uploaded_file is not None:
            st.success(f"✅ File loaded: {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
            
            # Show preview for images
            if uploaded_file.type.startswith('image'):
                st.image(uploaded_file, caption="Uploaded Image", use_column_width=True)
    
    with col2:
        st.subheader("Patient Info")
        patient_id_upload = st.text_input("Patient ID", value="PT-UPLOAD", key="patient_id_upload")
        encounter_date_upload = st.date_input("Encounter Date", value=datetime(2025, 1, 15), key="encounter_date_upload")
    
    if st.button("🔄 Process Document with OCR", type="primary", disabled=uploaded_file is None):
        with st.spinner("Processing document with OCR... This may take a minute..."):
            try:
                # Prepare form data
                files = {'file': (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                data = {
                    'patient_id': patient_id_upload,
                    'encounter_date': str(encounter_date_upload)
                }
                
                # Upload and process
                response = requests.post(
                    f"{BASE_URL}/clinical-notes/upload",
                    files=files,
                    data=data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    st.session_state['note_result'] = result
                    st.session_state['note_id'] = result['note_id']
                    
                    st.success(f"✅ Document processed! ID: {result['note_id']}")
                    
                    # Show OCR metadata if available
                    note_data = requests.get(f"{BASE_URL}/clinical-notes/{result['note_id']}").json()
                    if 'ocr_metadata' in note_data:
                        ocr_meta = note_data['ocr_metadata']
                        st.subheader("📊 OCR Processing Info")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Method", ocr_meta.get('processing_method', 'N/A'))
                        with col2:
                            st.metric("Characters", ocr_meta.get('character_count', 0))
                        with col3:
                            st.metric("Words", ocr_meta.get('word_count', 0))
                        with col4:
                            if 'ocr_confidence' in ocr_meta:
                                st.metric("OCR Confidence", f"{ocr_meta['ocr_confidence']:.1f}%")
                            elif 'total_pages' in ocr_meta:
                                st.metric("Pages", ocr_meta['total_pages'])
                    
                    # Show structured data
                    structured = result['structured_data']
                    
                    st.subheader("📋 Extracted Medical Data")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Diagnoses", len(structured.get('diagnoses', [])))
                    with col2:
                        st.metric("Medications", len(structured.get('current_medications', [])))
                    with col3:
                        st.metric("Procedures", len(structured.get('procedures', [])))
                    
                    with st.expander("📊 View Structured Data"):
                        st.json(structured)
                    
                    with st.expander("🔗 View FHIR Resources"):
                        st.json(result.get('fhir_resources'))
                    
                    with st.expander("📄 View Extracted Text"):
                        st.text_area("OCR Extracted Text", value=structured.get('raw_note', ''), height=300)
                    
                else:
                    st.error(f"Error: {response.text}")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# Tab 2: Extract Guidelines
with tab2:
    st.header("Step 2: Extract Coverage Guidelines")
    
    guideline_text = st.text_area(
        "Enter Coverage Guideline/Policy",
        height=400,
        value="""COVERAGE GUIDELINE: Lumbar Epidural Steroid Injections

COVERAGE CRITERIA:
1. Patient must have documented radicular pain radiating below the knee for at least 6 weeks
2. Diagnosis of herniated disc confirmed by MRI or CT scan within past 6 months
3. Failed conservative treatment including:
   - Physical therapy for minimum of 4 weeks
   - Trial of NSAIDs or other anti-inflammatory medications
   - Activity modification
4. Pain level of 5/10 or greater on validated pain scale

COVERED ICD-10 CODES:
- M51.16: Intervertebral disc disorders with radiculopathy, lumbar region
- M54.16: Radiculopathy, lumbar region

COVERED CPT CODES:
- 62323: Lumbar or sacral epidural injection

REQUIRED DOCUMENTATION:
1. Clinical notes documenting duration of symptoms
2. MRI or CT scan results
3. Documentation of failed conservative treatments
4. Pain assessment score"""
    )
    
    if st.button("📋 Extract Criteria", type="primary"):
        with st.spinner("Extracting guideline criteria with LLM..."):
            try:
                response = requests.post(
                    f"{BASE_URL}/prior-auth/extract-guideline",
                    json={"guideline_text": guideline_text}
                )
                
                if response.status_code == 200:
                    criteria = response.json()
                    st.session_state['guideline_criteria'] = criteria
                    
                    st.success(f"✅ Guideline extracted: {criteria.get('title', 'Untitled')}")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Coverage Criteria", len(criteria.get('coverage_criteria', [])))
                    with col2:
                        st.metric("ICD-10 Codes", len(criteria.get('covered_icd10_codes', [])))
                    with col3:
                        st.metric("CPT Codes", len(criteria.get('covered_cpt_codes', [])))
                    
                    with st.expander("📋 View Extracted Criteria"):
                        st.json(criteria)
                else:
                    st.error(f"Error: {response.text}")
            except Exception as e:
                st.error(f"Error: {str(e)}")

# Tab 3: Evaluate Prior Auth
with tab3:
    st.header("Step 3: Evaluate Prior Authorization")
    
    if 'note_id' not in st.session_state:
        st.warning("⚠️ Please process a clinical note first (Step 1)")
    elif 'guideline_criteria' not in st.session_state:
        st.warning("⚠️ Please extract guideline criteria first (Step 2)")
    else:
        st.info(f"Note ID: {st.session_state['note_id']}")
        st.info(f"Guideline: {st.session_state['guideline_criteria'].get('title', 'N/A')}")
        
        if st.button("⚖️ Evaluate Prior Authorization", type="primary"):
            with st.spinner("Evaluating with MCP + LLM decision engine..."):
                try:
                    response = requests.post(
                        f"{BASE_URL}/prior-auth/evaluate",
                        json={
                            "note_id": st.session_state['note_id'],
                            "guideline_criteria": st.session_state['guideline_criteria']
                        }
                    )
                    
                    if response.status_code == 200:
                        evaluation = response.json()
                        st.session_state['evaluation'] = evaluation
                        
                        decision = evaluation['decision']
                        
                        # Decision banner
                        decision_status = decision['decision'].upper()
                        if decision_status == "APPROVED":
                            st.success(f"✅ DECISION: {decision_status}")
                        elif decision_status == "DENIED":
                            st.error(f"❌ DECISION: {decision_status}")
                        else:
                            st.warning(f"⚠️ DECISION: {decision_status}")
                        
                        # Metrics
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Confidence", f"{decision['confidence_score']:.0%}")
                        with col2:
                            st.metric("Matched Criteria", len(decision['matched_criteria']))
                        with col3:
                            st.metric("Citations", len(decision['citations']))
                        
                        # Reasoning
                        st.subheader("📋 Reasoning")
                        for i, reason in enumerate(decision['reasoning'], 1):
                            st.markdown(f"{i}. {reason}")
                        
                        # Matched/Unmatched
                        col1, col2 = st.columns(2)
                        with col1:
                            with st.expander(f"✅ Matched Criteria ({len(decision['matched_criteria'])})"):
                                for criterion in decision['matched_criteria']:
                                    st.markdown(f"• {criterion}")
                        
                        with col2:
                            if decision['unmatched_criteria']:
                                with st.expander(f"❌ Unmatched Criteria ({len(decision['unmatched_criteria'])})"):
                                    for criterion in decision['unmatched_criteria']:
                                        st.markdown(f"• {criterion}")
                        
                        # Citations
                        with st.expander(f"📎 Citations ({len(decision['citations'])})"):
                            for citation in decision['citations']:
                                st.markdown(f"**{citation['claim']}**")
                                st.markdown(f"*Source: {citation['source']}*")
                                st.markdown("---")
                        
                        # Full justification
                        with st.expander("📄 Full Justification"):
                            st.text(evaluation['justification'])
                        
                    else:
                        st.error(f"Error: {response.text}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

# Tab 4: View Results
with tab4:
    st.header("Results Summary")
    
    if 'evaluation' in st.session_state:
        evaluation = st.session_state['evaluation']
        
        st.download_button(
            label="📥 Download Full Results (JSON)",
            data=json.dumps(evaluation, indent=2),
            file_name=f"prior_auth_{evaluation['evaluation_id']}.json",
            mime="application/json"
        )
        
        st.json(evaluation)
    else:
        st.info("Complete the prior authorization evaluation to view results here.")

# Footer
st.markdown("---")
st.markdown("**Latitude Health Assessment** | Built with FastAPI, Claude API, FHIR, and Streamlit")