# app/services/nlp_fhir_mapper.py
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from app.services.llm_service import llm_service
import json

# Data Models

@dataclass
class QueryIntent:
    """Parsed intent from natural language query"""
    query_type: str  # medications, conditions, labs, procedures, etc.
    resource_types: List[str]  # FHIR resource types needed
    filters: Dict[str, Any]  # Filters to apply
    temporal_context: Optional[str]  # current, past, recent, specific date
    aggregation: Optional[str]  # count, list, summary
    original_query: str

@dataclass
class FHIRQuery:
    """Structured FHIR query ready for execution"""
    resource_type: str
    search_params: Dict[str, Any]
    include_params: Optional[List[str]] = None
    sort_params: Optional[List[str]] = None
    count_limit: Optional[int] = None


# Natural Language to FHIR Mapper

class NaturalLanguageFHIRMapper:
    """
    Core mapping engine that translates natural language to FHIR queries
    This implements Braman's MCP-FHIR mapping pattern
    """
    
    def __init__(self):
        # Terminology mappings (Braman's ontology mapping)
        self.concept_to_resource = {
            # Medications
            "medication": "MedicationRequest",
            "drug": "MedicationRequest", 
            "prescription": "MedicationRequest",
            "med": "MedicationRequest",
            "medicine": "MedicationRequest",
            
            # Conditions
            "diagnosis": "Condition",
            "diagnoses": "Condition",
            "condition": "Condition",
            "problem": "Condition",
            "disease": "Condition",
            "disorder": "Condition",
            
            # Labs & Observations
            "lab": "Observation",
            "labs": "Observation",
            "test": "Observation",
            "result": "Observation",
            "vital": "Observation",
            "vitals": "Observation",
            "blood pressure": "Observation",
            "glucose": "Observation",
            "hemoglobin": "Observation",
            
            # Procedures
            "procedure": "Procedure",
            "surgery": "Procedure",
            "operation": "Procedure",
            "injection": "Procedure",
            "therapy": "Procedure",
            
            # Allergies
            "allergy": "AllergyIntolerance",
            "allergies": "AllergyIntolerance",
            "reaction": "AllergyIntolerance",
            
            # Imaging
            "imaging": "ImagingStudy",
            "xray": "ImagingStudy",
            "x-ray": "ImagingStudy",
            "mri": "ImagingStudy",
            "ct": "ImagingStudy",
            "scan": "ImagingStudy",
            
            # Documents
            "note": "DocumentReference",
            "report": "DocumentReference",
            "document": "DocumentReference"
        }
        
        # Temporal mappings
        self.temporal_patterns = {
            "current": {"status": "active"},
            "active": {"status": "active"},
            "past": {"status": "completed|inactive"},
            "previous": {"status": "completed|inactive"},
            "recent": {"_date": "ge{30_days_ago}"},
            "last month": {"_date": "ge{30_days_ago}"},
            "last year": {"_date": "ge{365_days_ago}"},
            "today": {"_date": "eq{today}"},
            "yesterday": {"_date": "eq{yesterday}"}
        }
        
        # Anatomical/condition specific patterns
        self.anatomical_patterns = {
            "back": ["dorsalgia", "back pain", "lumbar", "spine"],
            "heart": ["cardiac", "coronary", "myocardial"],
            "lung": ["pulmonary", "respiratory", "pneumo"],
            "kidney": ["renal", "nephro"],
            "liver": ["hepatic", "hepato"]
        }
        
        # Query patterns for complex questions
        self.query_patterns = {
            "what.*taking": "list_current",
            "how many": "count",
            "when.*last": "most_recent",
            "any.*history": "check_existence",
            "all.*related": "get_related",
            "between.*and": "date_range"
        }
    
    async def parse_query(self, natural_query: str, patient_id: str = None) -> QueryIntent:
        """
        Parse natural language query into structured intent
        Uses both pattern matching and LLM understanding
        """
        query_lower = natural_query.lower()
        
        # Determine query type and resources needed
        resource_types = self._extract_resource_types(query_lower)
        query_type = self._determine_query_type(query_lower)
        temporal_context = self._extract_temporal_context(query_lower)
        filters = self._build_filters(query_lower, temporal_context)
        aggregation = self._determine_aggregation(query_lower)
        
        # If pattern matching isn't enough, use LLM
        if not resource_types or query_type == "complex":
            intent = await self._parse_with_llm(natural_query)
            return intent
        
        return QueryIntent(
            query_type=query_type,
            resource_types=resource_types,
            filters=filters,
            temporal_context=temporal_context,
            aggregation=aggregation,
            original_query=natural_query
        )
    
    def _extract_resource_types(self, query: str) -> List[str]:
        """Extract FHIR resource types from query"""
        resources = set()
        
        for concept, resource in self.concept_to_resource.items():
            if concept in query:
                resources.add(resource)
        
        # Check for body part references that might indicate conditions
        for body_part, terms in self.anatomical_patterns.items():
            if body_part in query:
                resources.add("Condition")
                # Also check for procedures related to that body part
                if any(word in query for word in ["surgery", "procedure", "injection"]):
                    resources.add("Procedure")
        
        return list(resources)
    
    def _determine_query_type(self, query: str) -> str:
        """Determine the type of query being asked"""
        
        # Simple resource queries
        if "medication" in query or "drug" in query:
            return "medications"
        elif "diagnos" in query or "condition" in query:
            return "conditions"
        elif "lab" in query or "test" in query:
            return "labs"
        elif "allerg" in query:
            return "allergies"
        elif "procedure" in query:
            return "procedures"
        
        # Complex pattern queries
        for pattern, qtype in self.query_patterns.items():
            if re.search(pattern, query):
                return qtype
        
        return "complex"
    
    def _extract_temporal_context(self, query: str) -> Optional[str]:
        """Extract temporal context from query"""
        
        for temporal_key in self.temporal_patterns.keys():
            if temporal_key in query:
                return temporal_key
        
        # Check for date patterns
        date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
        if re.search(date_pattern, query):
            return "specific_date"
        
        # Check for relative time
        if "ago" in query:
            return "relative_past"
        
        return None
    
    def _build_filters(self, query: str, temporal_context: str) -> Dict[str, Any]:
        """Build FHIR search filters"""
        filters = {}
        
        # Add temporal filters
        if temporal_context and temporal_context in self.temporal_patterns:
            filters.update(self.temporal_patterns[temporal_context])
        
        # Add status filters
        if "active" in query or "current" in query:
            filters["status"] = "active"
        elif "inactive" in query or "resolved" in query:
            filters["status"] = "inactive|resolved"
        
        # Add severity filters
        if "severe" in query:
            filters["severity"] = "severe"
        elif "mild" in query:
            filters["severity"] = "mild"
        
        return filters
    
    def _determine_aggregation(self, query: str) -> Optional[str]:
        """Determine if query needs aggregation"""
        
        if "how many" in query or "count" in query:
            return "count"
        elif "list" in query or "show all" in query:
            return "list"
        elif "summar" in query:
            return "summary"
        elif "latest" in query or "most recent" in query:
            return "most_recent"
        
        return None
    
    async def _parse_with_llm(self, query: str) -> QueryIntent:
        """
        Use LLM to understand complex queries
        This is where we leverage Claude's understanding
        """
        
        prompt = f"""Parse this healthcare query into structured components.
        
Query: "{query}"

Return ONLY valid JSON with this structure:
{{
    "query_type": "type of query",
    "resource_types": ["FHIR resource types needed"],
    "filters": {{"filter_name": "value"}},
    "temporal_context": "current|past|recent|null",
    "aggregation": "count|list|summary|null",
    "interpretation": "what the user is asking for"
}}

Examples:
- "What medications is the patient taking?" -> 
  {{"query_type": "medications", "resource_types": ["MedicationRequest"], "filters": {{"status": "active"}}, "temporal_context": "current", "aggregation": "list"}}

- "Any history of heart problems?" ->
  {{"query_type": "conditions", "resource_types": ["Condition"], "filters": {{"code": "heart|cardiac|coronary"}}, "temporal_context": "any", "aggregation": "check_existence"}}

Parse the query now:"""

        result = await llm_service.query_with_context(prompt, {"query": query})
        
        # Parse LLM response
        try:
            parsed = result if isinstance(result, dict) else json.loads(result.get('answer', '{}'))
            
            return QueryIntent(
                query_type=parsed.get("query_type", "complex"),
                resource_types=parsed.get("resource_types", []),
                filters=parsed.get("filters", {}),
                temporal_context=parsed.get("temporal_context"),
                aggregation=parsed.get("aggregation"),
                original_query=query
            )
        except:
            # Fallback to basic intent
            return QueryIntent(
                query_type="complex",
                resource_types=[],
                filters={},
                temporal_context=None,
                aggregation=None,
                original_query=query
            )
    
    def build_fhir_queries(self, intent: QueryIntent, patient_id: str) -> List[FHIRQuery]:
        """
        Convert QueryIntent into executable FHIR queries
        """
        queries = []
        
        for resource_type in intent.resource_types:
            # Base parameters
            params = {"patient": patient_id}
            
            # Add filters from intent
            params.update(intent.filters)
            
            # Handle temporal filters with date calculation
            params = self._process_temporal_filters(params)
            
            # Resource-specific parameters
            if resource_type == "Observation":
                # Determine if labs or vitals
                if "lab" in intent.original_query.lower():
                    params["category"] = "laboratory"
                elif "vital" in intent.original_query.lower():
                    params["category"] = "vital-signs"
            
            elif resource_type == "Condition":
                # Add verification status for active conditions
                if params.get("status") == "active":
                    params["verification-status"] = "confirmed"
            
            # Build query
            query = FHIRQuery(
                resource_type=resource_type,
                search_params=params,
                sort_params=["-date"] if intent.aggregation == "most_recent" else None,
                count_limit=1 if intent.aggregation == "most_recent" else None
            )
            
            queries.append(query)
        
        return queries
    
    def _process_temporal_filters(self, params: Dict) -> Dict:
        """Process temporal filters with actual date calculation"""
        
        if "_date" in params:
            date_filter = params["_date"]
            
            # Calculate actual dates
            today = datetime.now()
            
            if "{30_days_ago}" in date_filter:
                date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
                params["date"] = date_filter.replace("{30_days_ago}", date)
                del params["_date"]
            
            elif "{365_days_ago}" in date_filter:
                date = (today - timedelta(days=365)).strftime("%Y-%m-%d")
                params["date"] = date_filter.replace("{365_days_ago}", date)
                del params["_date"]
            
            elif "{today}" in date_filter:
                date = today.strftime("%Y-%m-%d")
                params["date"] = date_filter.replace("{today}", date)
                del params["_date"]
            
            elif "{yesterday}" in date_filter:
                date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
                params["date"] = date_filter.replace("{yesterday}", date)
                del params["_date"]
        
        return params

# Query Executor

class FHIRQueryExecutor:
    """
    Executes FHIR queries and formats results
    """
    
    def __init__(self, fhir_client=None):
        self.fhir_client = fhir_client  # Your existing FHIR client
        
    async def execute(self, queries: List[FHIRQuery]) -> Dict[str, Any]:
        """Execute FHIR queries and return formatted results"""
        
        results = {
            "total_results": 0,
            "resources": [],
            "summary": {}
        }
        
        for query in queries:
            # In production, this would call your actual FHIR server
            # For now, we'll simulate with stored data
            query_results = await self._execute_single_query(query)
            
            results["resources"].extend(query_results)
            results["total_results"] += len(query_results)
            
            # Group by resource type for summary
            if query.resource_type not in results["summary"]:
                results["summary"][query.resource_type] = []
            results["summary"][query.resource_type].extend(query_results)
        
        return results
    
    async def _execute_single_query(self, query: FHIRQuery) -> List[Dict]:
        """
        Execute a single FHIR query
        In production, this would call your FHIR server
        """
        
        # For now, search through stored notes (replace with actual FHIR client call)
        from app.api.clinical_notes import notes_storage
        
        results = []
        patient_id = query.search_params.get("patient")
        
        for note_id, note_data in notes_storage.items():
            if note_data['structured_data'].get('patient_id') == patient_id:
                # Extract relevant resources based on query type
                if query.resource_type == "MedicationRequest":
                    meds = note_data['structured_data'].get('current_medications', [])
                    results.extend(meds)
                
                elif query.resource_type == "Condition":
                    conditions = note_data['structured_data'].get('diagnoses', [])
                    results.extend(conditions)
                
                elif query.resource_type == "Procedure":
                    procedures = note_data['structured_data'].get('procedures', [])
                    results.extend(procedures)
                
                elif query.resource_type == "AllergyIntolerance":
                    allergies = note_data['structured_data'].get('allergies', [])
                    results.extend(allergies)
                
                elif query.resource_type == "Observation":
                    obs = note_data['structured_data'].get('labs_imaging', [])
                    results.extend(obs)
        
        # Apply any count limits
        if query.count_limit:
            results = results[:query.count_limit]
        
        return results

# Natural Language Response Generator

class NaturalLanguageResponder:
    """
    Generates natural language responses from FHIR query results
    """
    
    async def generate_response(
        self, 
        query: str, 
        results: Dict[str, Any],
        intent: QueryIntent
    ) -> str:
        """
        Generate a natural language response from query results
        """
        
        if results["total_results"] == 0:
            return f"I couldn't find any {intent.query_type} for this patient."
        
        # Generate response based on aggregation type
        if intent.aggregation == "count":
            return f"The patient has {results['total_results']} {intent.query_type} recorded."
        
        elif intent.aggregation == "check_existence":
            return f"Yes, the patient has a history of {intent.query_type}."
        
        elif intent.aggregation == "most_recent":
            most_recent = results["resources"][0] if results["resources"] else None
            if most_recent:
                return f"The most recent {intent.query_type}: {self._format_resource(most_recent)}"
            return f"No recent {intent.query_type} found."
        
        else:
            # List response
            response = f"Found {results['total_results']} {intent.query_type}:\n\n"
            
            for resource_type, items in results["summary"].items():
                if items:
                    response += f"{resource_type}:\n"
                    for item in items[:5]:  # Limit to 5 items for readability
                        response += f"  • {self._format_resource(item)}\n"
            
            if results["total_results"] > 5:
                response += f"\n... and {results['total_results'] - 5} more"
            
            return response
    
    def _format_resource(self, resource: Dict) -> str:
        """Format a resource for display"""
        
        # Medication
        if "name" in resource and "dosage" in resource:
            return f"{resource['name']} - {resource.get('dosage', 'N/A')} {resource.get('frequency', '')}"
        
        # Condition/Diagnosis
        elif "code" in resource and "display" in resource:
            return f"{resource['display']} ({resource['code']})"
        
        # Observation/Lab
        elif "test_name" in resource:
            return f"{resource['test_name']}: {resource.get('value', 'N/A')} {resource.get('unit', '')}"
        
        # Allergy
        elif "substance" in resource:
            return f"{resource['substance']} - {resource.get('reaction', 'N/A')}"
        
        # Generic
        else:
            return str(resource)

# Main Natural Language Query Interface

class NaturalLanguageQueryInterface:
    """
    Main interface for natural language FHIR queries
    This is what gets integrated into your MCP server
    """
    
    def __init__(self):
        self.mapper = NaturalLanguageFHIRMapper()
        self.executor = FHIRQueryExecutor()
        self.responder = NaturalLanguageResponder()
    
    async def query(self, natural_query: str, patient_id: str) -> Dict[str, Any]:
        """
        Main query method - takes natural language, returns structured response
        """
        
        # Step 1: Parse the natural language query
        intent = await self.mapper.parse_query(natural_query, patient_id)
        
        # Step 2: Build FHIR queries
        fhir_queries = self.mapper.build_fhir_queries(intent, patient_id)
        
        # Step 3: Execute queries
        results = await self.executor.execute(fhir_queries)
        
        # Step 4: Generate natural language response
        nl_response = await self.responder.generate_response(
            natural_query, 
            results, 
            intent
        )
        
        return {
            "query": natural_query,
            "intent": {
                "type": intent.query_type,
                "resources": intent.resource_types,
                "temporal": intent.temporal_context,
                "aggregation": intent.aggregation
            },
            "fhir_queries": [
                {
                    "resource": q.resource_type,
                    "params": q.search_params
                }
                for q in fhir_queries
            ],
            "results": results,
            "response": nl_response,
            "patient_id": patient_id
        }

# Singleton instance
nl_query_interface = NaturalLanguageQueryInterface()