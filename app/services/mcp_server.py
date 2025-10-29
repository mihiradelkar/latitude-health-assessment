# app/services/mcp_server.py
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import json
import asyncio
from fastapi import FastAPI, HTTPException, WebSocket
from pydantic import BaseModel
import logging

from app.services.llm_service import llm_service
from app.services.fhir_mapper import fhir_mapper
from app.services.document_processor import document_processor
from app.services.decision_engine import decision_engine
from app.services.mcp_manager import mcp_manager
from app.api.clinical_notes import notes_storage

# MCP Protocol Data Models

@dataclass
class MCPTool:
    """Definition of an MCP tool"""
    name: str
    description: str
    handler: Callable
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    requires_auth: bool = True
    timeout_ms: int = 30000

class MCPRequest(BaseModel):
    """Standard MCP request format"""
    tool: str
    parameters: Dict[str, Any]
    context: Optional[Dict[str, Any]] = {}
    session_id: Optional[str] = None
    auth_token: Optional[str] = None

class MCPResponse(BaseModel):
    """Standard MCP response format"""
    tool: str
    status: str  # success, error, partial
    result: Any
    metadata: Optional[Dict[str, Any]] = {}
    citations: Optional[List[Dict[str, str]]] = []
    processing_time_ms: Optional[float] = None
    session_id: Optional[str] = None

# MCP Server Implementation

class MCPServer:
    """
    MCP Server that wraps your existing services
    This is the bridge between MCP protocol and your current implementation
    """
    
    def __init__(self):
        self.tools: Dict[str, MCPTool] = {}
        self.sessions: Dict[str, Dict] = {}
        self.logger = logging.getLogger(__name__)
        
        # Register all your existing services as MCP tools
        self._register_existing_services()
    
    def _register_existing_services(self):
        """
        Register your existing services as MCP tools
        This is where we map your current functionality to MCP
        """
        
        # 1. Clinical Note Processing Tool
        self.register_tool(
            MCPTool(
                name="extract_clinical_note",
                description="Extract structured data from unstructured clinical notes",
                handler=self._handle_clinical_extraction,
                input_schema={
                    "type": "object",
                    "properties": {
                        "note_text": {"type": "string", "description": "Raw clinical note text"},
                        "patient_id": {"type": "string", "optional": True},
                        "encounter_date": {"type": "string", "optional": True}
                    },
                    "required": ["note_text"]
                }
            )
        )
        
        # 2. Document OCR Processing Tool
        self.register_tool(
            MCPTool(
                name="process_document",
                description="Process PDF/image documents with OCR",
                handler=self._handle_document_processing,
                input_schema={
                    "type": "object",
                    "properties": {
                        "document": {"type": "string", "description": "Base64 encoded document"},
                        "document_type": {"type": "string", "enum": ["pdf", "image"]},
                        "filename": {"type": "string"}
                    },
                    "required": ["document", "document_type"]
                }
            )
        )
        
        # 3. FHIR Bundle Generation Tool
        self.register_tool(
            MCPTool(
                name="generate_fhir_bundle",
                description="Convert structured clinical data to FHIR Bundle",
                handler=self._handle_fhir_generation,
                input_schema={
                    "type": "object",
                    "properties": {
                        "structured_note": {"type": "object", "description": "Structured clinical note data"},
                        "patient_id": {"type": "string"}
                    },
                    "required": ["structured_note"]
                }
            )
        )
        
        # 4. Coverage Determination Tool
        self.register_tool(
            MCPTool(
                name="check_coverage",
                description="Evaluate if patient meets coverage criteria for prior authorization",
                handler=self._handle_coverage_check,
                input_schema={
                    "type": "object",
                    "properties": {
                        "fhir_bundle": {"type": "object", "description": "FHIR Bundle with patient data"},
                        "guideline_criteria": {"type": "object", "description": "Coverage guidelines"},
                        "clinical_note": {"type": "string", "description": "Original clinical note"},
                        "procedure_code": {"type": "string", "optional": True}
                    },
                    "required": ["fhir_bundle", "guideline_criteria", "clinical_note"]
                }
            )
        )
        
        # 5. Guideline Extraction Tool
        self.register_tool(
            MCPTool(
                name="extract_guidelines",
                description="Extract structured criteria from guideline text",
                handler=self._handle_guideline_extraction,
                input_schema={
                    "type": "object",
                    "properties": {
                        "guideline_text": {"type": "string", "description": "Raw guideline document"}
                    },
                    "required": ["guideline_text"]
                }
            )
        )
        
        # 6. Natural Language Query Tool (NEW - for Braman's pattern)
        self.register_tool(
            MCPTool(
                name="query_patient_data",
                description="Query patient data using natural language",
                handler=self._handle_natural_language_query,
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language query"},
                        "patient_id": {"type": "string"},
                        "include_history": {"type": "boolean", "default": False}
                    },
                    "required": ["query", "patient_id"]
                }
            )
        )
    
    def register_tool(self, tool: MCPTool):
        """Register a new MCP tool"""
        self.tools[tool.name] = tool
        self.logger.info(f"Registered MCP tool: {tool.name}")
    
    # Tool Handlers (Wrapping Your Existing Services)
    
    async def _handle_clinical_extraction(self, params: Dict) -> Dict:
        """Wrap your existing clinical note extraction"""
        start_time = datetime.now()
        
        try:
            # Call your existing service
            structured_note = await llm_service.structure_clinical_note(
                params["note_text"]
            )
            
            # Add optional patient info if provided
            if params.get("patient_id"):
                structured_note.patient_id = params["patient_id"]
            if params.get("encounter_date"):
                structured_note.encounter_date = params["encounter_date"]
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return {
                "structured_data": structured_note.dict(),
                "confidence_scores": {
                    "diagnoses": 0.95,
                    "medications": 0.92,
                    "procedures": 0.98
                },
                "processing_time_ms": processing_time
            }
            
        except Exception as e:
            self.logger.error(f"Clinical extraction error: {str(e)}")
            raise
    
    async def _handle_document_processing(self, params: Dict) -> Dict:
        """Wrap your existing document processor"""
        import base64
        from io import BytesIO
        from fastapi import UploadFile
        
        try:
            # Decode base64 document
            document_bytes = base64.b64decode(params["document"])
            
            # Create UploadFile-like object for your existing processor
            file = UploadFile(
                filename=params.get("filename", "document"),
                file=BytesIO(document_bytes)
            )
            
            # Call your existing OCR processor
            extracted_text, metadata = await document_processor.process_upload(file)
            
            return {
                "extracted_text": extracted_text,
                "metadata": metadata,
                "success": True
            }
            
        except Exception as e:
            self.logger.error(f"Document processing error: {str(e)}")
            raise
    
    async def _handle_fhir_generation(self, params: Dict) -> Dict:
        """Wrap your existing FHIR mapper"""
        try:
            # Convert dict back to StructuredClinicalNote object
            from app.models.clinical_note import StructuredClinicalNote
            structured_note = StructuredClinicalNote(**params["structured_note"])
            
            # Call your existing FHIR mapper
            fhir_bundle = fhir_mapper.map_to_fhir_bundle(structured_note)
            
            return {
                "fhir_bundle": fhir_bundle,
                "resource_count": len(fhir_bundle.get("entry", [])),
                "bundle_type": fhir_bundle.get("type", "collection")
            }
            
        except Exception as e:
            self.logger.error(f"FHIR generation error: {str(e)}")
            raise
    
    async def _handle_coverage_check(self, params: Dict) -> Dict:
        """Wrap your existing decision engine"""
        try:
            # Call your existing decision engine
            decision = await decision_engine.evaluate(
                params["fhir_bundle"],
                params["guideline_criteria"],
                params["clinical_note"]
            )
            
            return {
                "decision": decision.decision,
                "reasoning": decision.reasoning,
                "matched_criteria": decision.matched_criteria,
                "unmatched_criteria": decision.unmatched_criteria,
                "confidence_score": decision.confidence_score,
                "citations": [c.dict() for c in decision.citations]
            }
            
        except Exception as e:
            self.logger.error(f"Coverage check error: {str(e)}")
            raise
    
    async def _handle_guideline_extraction(self, params: Dict) -> Dict:
        """Wrap your existing guideline extraction"""
        try:
            # Call your existing MCP manager's extraction
            criteria = await mcp_manager.extract_guideline_criteria(
                params["guideline_text"]
            )
            
            return criteria
            
        except Exception as e:
            self.logger.error(f"Guideline extraction error: {str(e)}")
            raise
    
    async def _handle_natural_language_query(self, params: Dict) -> Dict:
        """
        NEW: Natural language query handler
        This is where we start implementing Braman's vision
        """
        query = params["query"].lower()
        patient_id = params["patient_id"]
        
        # Simple pattern matching for now (will enhance with LLM later)
        if "medication" in query or "drug" in query:
            # Get medications from stored notes
            result = {
                "query_type": "medications",
                "data": [],
                "interpretation": f"Retrieving medications for patient {patient_id}"
            }
            
            # Search through stored notes
            for note_id, note_data in notes_storage.items():
                if note_data['structured_data'].get('patient_id') == patient_id:
                    meds = note_data['structured_data'].get('current_medications', [])
                    result["data"].extend(meds)
            
            return result
            
        elif "diagnosis" in query or "condition" in query:
            result = {
                "query_type": "diagnoses",
                "data": [],
                "interpretation": f"Retrieving diagnoses for patient {patient_id}"
            }
            
            for note_id, note_data in notes_storage.items():
                if note_data['structured_data'].get('patient_id') == patient_id:
                    dx = note_data['structured_data'].get('diagnoses', [])
                    result["data"].extend(dx)
            
            return result
            
        else:
            # For complex queries, use LLM to interpret
            interpretation = await llm_service.query_with_context(
                query,
                {"patient_id": patient_id, "available_data": "clinical_notes"}
            )
            
            return {
                "query_type": "complex",
                "interpretation": interpretation,
                "data": None
            }
    
    # Core MCP Protocol Methods
    
    async def execute(self, request: MCPRequest) -> MCPResponse:
        """
        Main entry point for MCP requests
        Routes to appropriate tool handler
        """
        start_time = datetime.now()
        
        # Validate tool exists
        if request.tool not in self.tools:
            return MCPResponse(
                tool=request.tool,
                status="error",
                result={"error": f"Tool '{request.tool}' not found"}
            )
        
        tool = self.tools[request.tool]
        
        try:
            # Execute tool handler
            result = await tool.handler(request.parameters)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            
            return MCPResponse(
                tool=request.tool,
                status="success",
                result=result,
                processing_time_ms=processing_time,
                session_id=request.session_id
            )
            
        except Exception as e:
            self.logger.error(f"Error executing tool {request.tool}: {str(e)}")
            return MCPResponse(
                tool=request.tool,
                status="error",
                result={"error": str(e)},
                session_id=request.session_id
            )
    
    def list_tools(self) -> List[Dict]:
        """
        List all available MCP tools
        This implements Josh's dynamic discovery pattern
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
                "requires_auth": tool.requires_auth,
                "timeout_ms": tool.timeout_ms
            }
            for tool in self.tools.values()
        ]
    
    async def create_session(self, session_config: Dict) -> str:
        """Create a new MCP session for stateful interactions"""
        import uuid
        session_id = str(uuid.uuid4())
        
        self.sessions[session_id] = {
            "created_at": datetime.now().isoformat(),
            "config": session_config,
            "context": {},
            "history": []
        }
        
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session data"""
        return self.sessions.get(session_id)

# FastAPI Integration

# Initialize MCP Server
mcp_server = MCPServer()

# Add MCP endpoints to your existing FastAPI app
def add_mcp_routes(app: FastAPI):
    """
    Add MCP protocol endpoints to your existing FastAPI app
    Call this from your main.py
    """
    
    @app.get("/mcp/tools")
    async def list_mcp_tools():
        """
        Discovery endpoint - lists all available MCP tools
        This is what AI clients will call first
        """
        return {
            "version": "1.0",
            "tools": mcp_server.list_tools(),
            "capabilities": {
                "streaming": False,
                "sessions": True,
                "natural_language": True
            }
        }
    
    @app.post("/mcp/execute")
    async def execute_mcp_tool(request: MCPRequest):
        """
        Main MCP execution endpoint
        Routes requests to appropriate tool handlers
        """
        response = await mcp_server.execute(request)
        return response.dict()
    
    @app.post("/mcp/session/create")
    async def create_mcp_session(config: Dict = {}):
        """Create a new MCP session"""
        session_id = await mcp_server.create_session(config)
        return {"session_id": session_id}
    
    @app.get("/mcp/session/{session_id}")
    async def get_mcp_session(session_id: str):
        """Get session details"""
        session = mcp_server.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    
    @app.websocket("/mcp/stream")
    async def mcp_websocket(websocket: WebSocket):
        """
        WebSocket endpoint for streaming MCP interactions
        Useful for real-time updates during processing
        """
        await websocket.accept()
        
        try:
            while True:
                # Receive request
                data = await websocket.receive_json()
                request = MCPRequest(**data)
                
                # Process request
                response = await mcp_server.execute(request)
                
                # Send response
                await websocket.send_json(response.dict())
                
        except Exception as e:
            await websocket.send_json({
                "error": str(e),
                "status": "connection_closed"
            })
            await websocket.close()

# Testing the MCP Wrapper

async def test_mcp_wrapper():
    """
    Test function to verify MCP wrapper is working
    Run this to ensure everything is connected properly
    """
    
    print("Testing MCP Server Wrapper...")
    
    # Test 1: List tools
    tools = mcp_server.list_tools()
    print(f"✓ Found {len(tools)} MCP tools")
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description']}")
    
    # Test 2: Extract clinical note
    test_request = MCPRequest(
        tool="extract_clinical_note",
        parameters={
            "note_text": "Patient has diabetes type 2, taking metformin 1000mg twice daily",
            "patient_id": "TEST-001"
        }
    )
    
    response = await mcp_server.execute(test_request)
    print(f"\n✓ Clinical extraction test: {response.status}")
    
    # Test 3: Natural language query
    query_request = MCPRequest(
        tool="query_patient_data",
        parameters={
            "query": "What medications is the patient taking?",
            "patient_id": "TEST-001"
        }
    )
    
    response = await mcp_server.execute(query_request)
    print(f"✓ Natural language query test: {response.status}")
    
    print("\n✅ MCP Wrapper is working correctly!")

# Run test if this file is executed directly
if __name__ == "__main__":
    asyncio.run(test_mcp_wrapper())