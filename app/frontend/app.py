# frontend/app.py (updated with proper null checks)
import streamlit as st
import requests
import json
from datetime import datetime
import pandas as pd
from typing import Dict, Any, Optional
import time

# Configuration
API_BASE_URL = "http://localhost:8000/api/v1"

# Page config
st.set_page_config(
    page_title="Prior Auth AI System",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
    }
    .warning-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        color: #856404;
    }
    .metric-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #dee2e6;
    }
    .confidence-high { color: #28a745; font-weight: bold; }
    .confidence-medium { color: #ffc107; font-weight: bold; }
    .confidence-low { color: #dc3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Session state initialization
if 'processed_note' not in st.session_state:
    st.session_state.processed_note = None
if 'evaluation_result' not in st.session_state:
    st.session_state.evaluation_result = None
if 'current_note_id' not in st.session_state:
    st.session_state.current_note_id = None

def get_confidence_class(score: float) -> str:
    """Get CSS class based on confidence score"""
    if score >= 0.85:
        return "confidence-high"
    elif score >= 0.60:
        return "confidence-medium"
    else:
        return "confidence-low"

def display_confidence_badge(score: float):
    """Display confidence score with color coding"""
    css_class = get_confidence_class(score)
    percentage = f"{score:.0%}"
    return f'<span class="{css_class}">{percentage}</span>'

# Sample clinical notes
SAMPLE_NOTES = {
    "Low Back Pain - Clear Approval": """PATIENT: John Smith
MRN: 123456
DATE: 2024-01-15

CHIEF COMPLAINT:
Severe low back pain with radiculopathy x 6 months

HISTORY OF PRESENT ILLNESS:
Mr. Smith is a 45-year-old male presenting with persistent low back pain radiating to the right leg for the past 6 months. Pain is 8/10, worse with standing and walking. Failed conservative management x 6 months including:
- Physical therapy (24 sessions over 12 weeks) - minimal improvement
- NSAIDs (ibuprofen 800mg TID x 3 months) - temporary relief only  
- Muscle relaxants (cyclobenzaprine 10mg TID x 2 months) - no significant benefit
- Activity modification and home exercises - compliant but ineffective
- Epidural steroid injection 3 months ago - provided 2 weeks of relief only

PAST MEDICAL HISTORY:
- Type 2 Diabetes (controlled, A1c 6.8%)
- Hypertension (controlled on lisinopril)

PHYSICAL EXAM:
Positive straight leg raise on right at 30 degrees
Decreased sensation L5 distribution
Strength 4/5 right ankle dorsiflexion

IMAGING:
MRI lumbar spine (2 weeks ago): Large disc herniation L4-L5 with nerve root compression

ASSESSMENT/PLAN:
Failed comprehensive conservative management. Requesting approval for:
- CPT 62323: Lumbar epidural injection under fluoroscopy
- ICD-10: M54.16 (Radiculopathy, lumbar region)""",

    "Knee Pain - Missing Documentation": """PATIENT: Sarah Johnson
MRN: 789012

CHIEF COMPLAINT:
Right knee pain

HISTORY OF PRESENT ILLNESS:
55-year-old female with knee pain for several months. Tried some medications.

ASSESSMENT:
Knee arthritis
Requesting MRI knee

PLAN:
MRI right knee
ICD-10: M17.11""",

    "Urgent Case - Red Flags": """PATIENT: Michael Chen
MRN: 456789
DATE: 2024-01-20

CHIEF COMPLAINT:
Severe back pain with progressive leg weakness

HISTORY OF PRESENT ILLNESS:
62-year-old male presenting with acute on chronic back pain, now with rapidly progressive bilateral leg weakness over past 48 hours. Also reports new onset bowel incontinence and saddle anesthesia. Unable to ambulate.

PAST MEDICAL HISTORY:
- Prostate cancer (in remission)
- Chronic back pain

PHYSICAL EXAM:
- Bilateral lower extremity weakness 2/5
- Absent ankle reflexes bilaterally
- Decreased perianal sensation
- Positive Babinski bilaterally

IMAGING:
MRI STAT ordered - suspected cauda equina syndrome

ASSESSMENT:
Cauda equina syndrome - URGENT
Need immediate MRI and likely surgical decompression

ICD-10: G83.4 (Cauda equina syndrome)
CPT: 72148 (MRI lumbar spine without contrast)"""
}

SAMPLE_GUIDELINES = {
    "Epidural Injection": """Coverage Criteria for Lumbar Epidural Steroid Injection (CPT 62323):

The patient must meet ALL of the following criteria:

1. Clinical diagnosis of radiculopathy with corresponding ICD-10 codes (M54.16, M54.17)

2. Failed conservative treatment for at least 6 weeks including at least TWO of the following:
   - Physical therapy (minimum 6 sessions)
   - NSAIDs or other oral medications
   - Activity modification
   - Home exercise program

3. Clinical findings consistent with nerve root compression:
   - Positive straight leg raise test
   - Neurological deficits (weakness, sensory loss, or reflex changes)

4. Imaging (MRI or CT) confirming anatomical abnormality correlating with clinical symptoms

EXCLUSIONS:
- Cauda equina syndrome (requires urgent surgery)
- Progressive neurological deficit
- Spinal infection
- Coagulopathy""",

    "MRI Knee": """Coverage Criteria for MRI Knee (CPT 73721):

The patient must meet the following:

1. Failed conservative treatment for at least 4 weeks including:
   - Rest, ice, compression, elevation (RICE)
   - NSAIDs or analgesics
   - Physical therapy or home exercises

2. ONE of the following indications:
   - Suspected meniscal tear with mechanical symptoms
   - Suspected ligament injury
   - Osteochondral defect
   - Failure to respond to conservative treatment

REQUIRED DOCUMENTATION:
- Duration and type of conservative treatment
- Physical examination findings
- X-ray results (if available)"""
}

def main():
    st.title("🏥 Healthcare Prior Authorization AI System")
    st.markdown("### AI-Powered Clinical Decision Support")
    
    # Sidebar with proper null checks
    with st.sidebar:
        st.header("📊 System Status")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("API Status", "✅ Connected")
        with col2:
            st.metric("Model", "Claude")
        
        st.markdown("---")
        
        st.header("📈 Statistics")
        
        # Check if processed_note exists and has data
        if st.session_state.processed_note is not None:
            # Try to get extraction confidence
            extraction_confidence = None
            if isinstance(st.session_state.processed_note, dict):
                # Check for extraction_confidence in the response
                if 'extraction_confidence' in st.session_state.processed_note:
                    extraction_confidence = st.session_state.processed_note['extraction_confidence']
                # Or check in structured_data
                elif 'structured_data' in st.session_state.processed_note:
                    structured_data = st.session_state.processed_note['structured_data']
                    if isinstance(structured_data, dict) and 'confidence_scores' in structured_data:
                        extraction_confidence = structured_data['confidence_scores']
            
            if extraction_confidence and isinstance(extraction_confidence, dict):
                confidence = extraction_confidence.get('overall', 0)
                st.metric("Extraction Confidence", f"{confidence:.0%}")
            else:
                st.metric("Extraction Confidence", "N/A")
        
        # Check if evaluation_result exists and has data
        if st.session_state.evaluation_result is not None:
            if isinstance(st.session_state.evaluation_result, dict):
                decision = st.session_state.evaluation_result.get('decision', {})
                if isinstance(decision, dict):
                    decision_conf = decision.get('confidence_score', 0)
                    st.metric("Decision Confidence", f"{decision_conf:.0%}")
                else:
                    st.metric("Decision Confidence", "N/A")
    
    # Main content tabs
    tabs = st.tabs(["📝 Clinical Note", "🔍 Evaluation", "📊 Analysis", "📋 Guidelines"])
    
    # Tab 1: Clinical Note Input
    with tabs[0]:
        st.header("Step 1: Input Clinical Note")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            input_method = st.radio(
                "Choose input method:",
                ["Use Sample Note", "Paste Custom Note", "Upload File"],
                horizontal=True
            )
            
            note_text = ""
            
            if input_method == "Use Sample Note":
                selected_sample = st.selectbox(
                    "Select sample scenario:",
                    list(SAMPLE_NOTES.keys())
                )
                note_text = st.text_area(
                    "Clinical Note:",
                    value=SAMPLE_NOTES[selected_sample],
                    height=400
                )
                
            elif input_method == "Paste Custom Note":
                note_text = st.text_area(
                    "Paste your clinical note here:",
                    height=400,
                    placeholder="Enter clinical note..."
                )
                
            else:  # Upload File
                uploaded_file = st.file_uploader(
                    "Upload clinical note",
                    type=['txt', 'pdf'],
                    help="Upload a text or PDF file"
                )
                if uploaded_file:
                    try:
                        note_text = uploaded_file.read().decode('utf-8')
                        st.text_area("Uploaded Note:", value=note_text, height=400)
                    except:
                        st.error("Error reading file. Please ensure it's a valid text file.")
                        note_text = ""
        
        with col2:
            st.info("""
            **Required Elements:**
            - Chief Complaint
            - History (HPI)
            - Treatment History
            - Physical Exam
            - Assessment/Plan
            
            **For Best Results:**
            - Include treatment durations
            - List all therapies tried
            - Add relevant diagnoses
            - Include ICD/CPT codes
            """)
        
        if st.button("🔄 Process Note", type="primary", disabled=not note_text):
            with st.spinner("Processing clinical note..."):
                try:
                    # Call API to process note
                    response = requests.post(
                        f"{API_BASE_URL}/clinical-notes/process",
                        json={"note_text": note_text}
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.session_state.processed_note = result
                        st.session_state.current_note_id = result.get('note_id')
                        st.success(f"✅ Note processed successfully! (ID: {result.get('note_id', 'N/A')[:8]}...)")
                        
                        # Display extraction results
                        with st.expander("📋 Extracted Information", expanded=True):
                            structured = result.get('structured_data', {})
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown("**Chief Complaint:**")
                                st.write(structured.get('chief_complaint', 'Not found'))
                                
                                st.markdown("**Diagnoses:**")
                                diagnoses = structured.get('diagnoses', [])
                                if diagnoses:
                                    for dx in diagnoses:
                                        if isinstance(dx, dict):
                                            st.write(f"- {dx.get('display', 'N/A')} ({dx.get('code', 'N/A')})")
                                        else:
                                            st.write(f"- {dx}")
                                else:
                                    st.write("No diagnoses extracted")
                            
                            with col2:
                                st.markdown("**Medications:**")
                                medications = structured.get('current_medications', [])
                                if medications:
                                    for med in medications:
                                        if isinstance(med, dict):
                                            st.write(f"- {med.get('name', 'N/A')} {med.get('dosage', '')}")
                                        else:
                                            st.write(f"- {med}")
                                else:
                                    st.write("No medications extracted")
                                
                                st.markdown("**Conservative Treatments:**")
                                treatments = structured.get('conservative_treatments', [])
                                if treatments:
                                    for tx in treatments:
                                        if isinstance(tx, dict):
                                            st.write(f"- {tx.get('modality', 'N/A')}: {tx.get('duration', 'N/A')}")
                                        else:
                                            st.write(f"- {tx}")
                                else:
                                    st.write("No treatments extracted")
                    else:
                        st.error(f"Error: {response.text}")
                        
                except Exception as e:
                    st.error(f"Error processing note: {str(e)}")
    
    # Tab 2: Prior Auth Evaluation
    with tabs[1]:
        st.header("Step 2: Prior Authorization Evaluation")
        
        if not st.session_state.current_note_id:
            st.warning("⚠️ Please process a clinical note first")
        else:
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Guideline selection
                guideline_method = st.radio(
                    "Guideline source:",
                    ["Use Sample Guideline", "Paste Custom Guideline"],
                    horizontal=True
                )
                
                guideline_text = ""
                
                if guideline_method == "Use Sample Guideline":
                    selected_guideline = st.selectbox(
                        "Select guideline:",
                        list(SAMPLE_GUIDELINES.keys())
                    )
                    guideline_text = st.text_area(
                        "Coverage Guideline:",
                        value=SAMPLE_GUIDELINES[selected_guideline],
                        height=300
                    )
                else:
                    guideline_text = st.text_area(
                        "Paste coverage guideline:",
                        height=300,
                        placeholder="Enter coverage criteria..."
                    )
            
            with col2:
                st.info("""
                **Evaluation Process:**
                1. Extract guideline criteria
                2. Match patient data
                3. Check requirements
                4. Generate decision
                
                **Decision Types:**
                - ✅ Approved
                - ❌ Denied  
                - ⚠️ Need More Info
                """)
            
            if st.button("🎯 Evaluate Prior Auth", type="primary", disabled=not guideline_text):
                with st.spinner("Evaluating prior authorization..."):
                    try:
                        # Call API to evaluate
                        response = requests.post(
                            f"{API_BASE_URL}/prior-auth/evaluate",
                            json={
                                "note_id": st.session_state.current_note_id,
                                "guideline_text": guideline_text
                            }
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            st.session_state.evaluation_result = result
                            
                            # Display decision
                            decision = result.get('decision', {})
                            decision_type = decision.get('decision', 'unknown')
                            confidence = decision.get('confidence_score', 0)
                            
                            # Color-coded decision box
                            if decision_type == "approved":
                                st.markdown(
                                    f'<div class="success-box">✅ APPROVED - Confidence: {display_confidence_badge(confidence)}</div>',
                                    unsafe_allow_html=True
                                )
                            elif decision_type == "denied":
                                st.markdown(
                                    f'<div class="error-box">❌ DENIED - Confidence: {display_confidence_badge(confidence)}</div>',
                                    unsafe_allow_html=True
                                )
                            else:
                                st.markdown(
                                    f'<div class="warning-box">⚠️ NEEDS MORE INFO - Confidence: {display_confidence_badge(confidence)}</div>',
                                    unsafe_allow_html=True
                                )
                            
                            # Show reasoning
                            with st.expander("📝 Decision Reasoning", expanded=True):
                                reasoning = decision.get('reasoning', [])
                                if reasoning:
                                    for reason in reasoning:
                                        st.write(reason)
                                else:
                                    st.write("No reasoning provided")
                            
                            # Show matched/unmatched criteria
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown("**✅ Matched Criteria:**")
                                matched = decision.get('matched_criteria', [])
                                if matched:
                                    for criterion in matched:
                                        st.write(f"- {criterion}")
                                else:
                                    st.write("No criteria matched")
                            
                            with col2:
                                st.markdown("**❌ Unmatched Criteria:**")
                                unmatched = decision.get('unmatched_criteria', [])
                                if unmatched:
                                    for criterion in unmatched:
                                        st.write(f"- {criterion}")
                                else:
                                    st.write("All criteria matched")
                            
                            # Show required documentation if needed
                            required_docs = decision.get('requires_additional_documentation')
                            if required_docs:
                                st.markdown("**📄 Additional Documentation Required:**")
                                for doc in required_docs:
                                    st.write(f"- {doc}")
                        else:
                            st.error(f"Error: {response.text}")
                            
                    except Exception as e:
                        st.error(f"Error evaluating: {str(e)}")
    
    # Tab 3: Analysis
    with tabs[2]:
        st.header("📊 Decision Analysis")
        
        if st.session_state.evaluation_result:
            result = st.session_state.evaluation_result
            decision = result.get('decision', {})
            
            # Confidence metrics
            st.subheader("Confidence Analysis")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                conf_score = decision.get('confidence_score', 0)
                st.metric(
                    "Overall Confidence",
                    f"{conf_score:.0%}",
                    delta=None
                )
                
                # Confidence level indicator
                if conf_score >= 0.85:
                    st.success("✅ High Confidence - Auto-processable")
                elif conf_score >= 0.60:
                    st.warning("⚠️ Medium Confidence - Quick review needed")
                else:
                    st.error("❌ Low Confidence - Full review required")
            
            with col2:
                matched = len(decision.get('matched_criteria', []))
                unmatched = len(decision.get('unmatched_criteria', []))
                total = matched + unmatched
                match_rate = matched / total if total > 0 else 0
                st.metric(
                    "Criteria Match Rate",
                    f"{match_rate:.0%}",
                    delta=f"{matched}/{total} criteria"
                )
            
            with col3:
                processing_time = result.get('processing_time_ms', 0) / 1000
                st.metric(
                    "Processing Time",
                    f"{processing_time:.1f}s",
                    delta="Fast" if processing_time < 5 else "Normal"
                )
            
            # Citations
            st.subheader("📚 Evidence & Citations")
            citations = decision.get('citations', [])
            if citations:
                for i, citation in enumerate(citations, 1):
                    with st.expander(f"Citation {i}: {citation.get('claim', '')[:50]}..."):
                        st.write(f"**Claim:** {citation.get('claim', 'N/A')}")
                        st.write(f"**Source:** {citation.get('source', 'N/A')}")
                        if citation.get('source_section'):
                            st.write(f"**Section:** {citation.get('source_section')}")
            else:
                st.info("No citations available")
            
            # Justification
            st.subheader("📋 Full Justification")
            justification_text = result.get('justification', 'No justification provided')
            st.text_area("", value=justification_text, height=300, disabled=True)
            
        else:
            st.info("👆 Complete an evaluation to see analysis")
    
    # Tab 4: Guidelines
    with tabs[3]:
        st.header("📋 Coverage Guidelines")
        
        st.markdown("""
        ### Available Sample Guidelines
        
        These sample guidelines demonstrate different coverage scenarios:
        """)
        
        for title, content in SAMPLE_GUIDELINES.items():
            with st.expander(f"📄 {title}"):
                st.text(content)
                if st.button(f"Copy {title}", key=f"copy_{title}"):
                    st.info("Guideline copied! Go to Evaluation tab to use it.")
        
        st.markdown("""
        ### Creating Custom Guidelines
        
        When writing custom guidelines, include:
        - **Coverage criteria** - What must be met
        - **Duration requirements** - Minimum treatment periods  
        - **Required modalities** - Types of treatments needed
        - **Documentation requirements** - What must be documented
        - **ICD-10/CPT codes** - Covered diagnoses and procedures
        - **Exclusion criteria** - What would cause denial
        """)

if __name__ == "__main__":
    main()