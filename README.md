# Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```



# AI-Powered Prior Authorization System
**Latitude Health - Senior Engineer Assessment**

## Overview
This system demonstrates an end-to-end AI-powered prior authorization workflow using:
- **LLM (Claude Sonnet 4.5)** for clinical note structuring and decision support
- **FHIR R4** for standardized healthcare data representation
- **Model Context Protocol (MCP)** for structured AI reasoning
- **FastAPI** for API-first architecture
- **A2A Workflow** simulation for automated prior authorization

## Quick Start

### Prerequisites

- Python 3.10+
- Anthropic API key

### Installation

```bash
# Clone repository
git clone <your-repo-url>
cd latitude-health-assessment

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
echo "ANTHROPIC_API_KEY=your_key_here" > .env
```

### Run the Application
```bash
# Start API server
uvicorn app.main:app --reload --port 8000
# In another terminal, run Streamlit UI (optional)
streamlit run demo_app.py
```

### Test the System

```bash
# Run comprehensive tests
python tests/test_comprehensive_v2.py
# Run individual test
python test_prior_auth.py
```

## Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    Clinical Note (Unstructured)             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              LLM Structuring (Claude Sonnet 4.5)            │
│  • Extract diagnoses (ICD-10), procedures (CPT)             │
│  • Parse medications, allergies, labs                       │
│  • Structure into JSON                                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    FHIR Resource Mapping                    │
│  • Patient, Condition, MedicationRequest                    │
│  • Observation, Procedure, AllergyIntolerance               │
│  • Bundle with all resources                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│          Model Context Protocol (MCP) Manager               │
│  • Build patient context from FHIR                          │
│  • Build guideline context                                  │
│  • Orchestrate LLM reasoning                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               Coverage Guideline Extraction                 │
│  • LLM extracts criteria from policy text                   │
│  • Structure coverage rules, ICD-10/CPT codes               │
│  • Identify exclusions and requirements                     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Prior Auth Decision Engine                     │
│  • Compare patient data vs. guidelines                      │
│  • LLM evaluates medical necessity                          │
│  • Generate decision with citations                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│            Decision: Approved / Denied / More Info          │
│  • Detailed reasoning                                       │
│  • Citations to source data                                 │
│  • Confidence score                                         │
└─────────────────────────────────────────────────────────────┘
```
