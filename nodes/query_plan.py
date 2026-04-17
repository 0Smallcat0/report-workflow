"""QUERY_PLAN - Agent-assisted: constructs DB-specific queries from gap analysis."""
import json
import os
import anthropic
from pathlib import Path


ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")


QUERY_PLAN_PROMPT = """You are a research query planner. Your task is to construct 
database-specific search queries based on gap analysis results.

For each gap, create search queries for three databases:
1. PubMed (biomedical/medical literature)
2. arXiv (preprints in physics, math, CS, etc.)
3. OpenAlex (multi-disciplinary academic literature)

Guidelines:
- Use appropriate syntax for each database
- PubMed: MeSH terms, boolean operators (AND, OR, NOT)
- arXiv: keywords and category filters
- OpenAlex: work filters and concepts

Return a JSON object with the following structure:
{{
  "gap_queries": [
    {{
      "claim_id": "claim_1",
      "pubmed_query": "search terms for PubMed",
      "arxiv_query": "search terms for arXiv",
      "openalex_query": "search terms for OpenAlex"
    }}
  ]
}}

Return ONLY the JSON object, no additional text."""


def query_plan(gap_analysis: list[dict], report_spec: dict = None) -> list[dict]:
    """Construct database-specific queries from gap analysis.
    
    This is an AGENT-ASSISTED node that uses Claude to construct
    optimal search queries for each database.
    
    Args:
        gap_analysis: List of gap analysis dicts from gap_analysis
        report_spec: Optional report specification for context
    
    Returns:
        List of query plan dicts with database-specific queries
    """
    client = anthropic.Anthropic()
    
    if not gap_analysis:
        return []
    
    # Build context for query construction
    context = {
        "gaps": gap_analysis,
        "report_spec": report_spec or {}
    }
    
    user_prompt = f"""Based on the following gap analysis, construct database-specific search queries:

{json.dumps(context, indent=2)}

Create optimized search queries for:
1. PubMed (NCBI Entrez) - use MeSH terms and boolean operators
2. arXiv - use keywords and category filters
3. OpenAlex - use work filters and concepts

Return ONLY the JSON object."""
    
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=QUERY_PLAN_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        )
        
        response_text = response.content[0].text.strip()
        
        # Extract JSON
        if "```json" in response_text:
            start = response_text.find("```json") + 7
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        elif "```" in response_text:
            start = response_text.find("```") + 3
            end = response_text.find("```", start)
            response_text = response_text[start:end].strip()
        
        query_plan_data = json.loads(response_text)
        return query_plan_data.get("gap_queries", [])
        
    except Exception as e:
        # Fallback: generate simple queries without agent
        return _fallback_query_plan(gap_analysis)


def _fallback_query_plan(gap_analysis: list[dict]) -> list[dict]:
    """Fallback query plan when agent fails."""
    queries = []
    
    for gap in gap_analysis:
        claim_id = gap.get("claim_id", "")
        search_terms = gap.get("suggested_search_terms", [])
        
        if search_terms:
            term_str = " OR ".join(search_terms[:3])
        else:
            term_str = claim_id
        
        queries.append({
            "claim_id": claim_id,
            "pubmed_query": term_str,
            "arxiv_query": term_str,
            "openalex_query": term_str
        })
    
    return queries
