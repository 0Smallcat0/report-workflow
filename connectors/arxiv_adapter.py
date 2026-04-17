"""ARXIV_ADAPTER - Retrieve preprints from arXiv API."""
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
import time
from typing import Optional


ARXIV_API_BASE = "https://export.arxiv.org/api/query"


def search_arxiv(query: str, max_results: int = 10) -> list[dict]:
    """Search arXiv using the arXiv API.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to retrieve (default 10)
    
    Returns:
        List of result dicts with arXiv preprint metadata
    """
    results = []
    
    try:
        # Build query parameters
        params = urllib.parse.urlencode({
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending"
        })
        
        url = f"{ARXIV_API_BASE}?{params}"
        
        with urllib.request.urlopen(url, timeout=60) as response:
            xml_content = response.read().decode("utf-8")
        
        # Parse XML response
        root = ET.fromstring(xml_content)
        
        # Define namespace map
        namespaces = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom"
        }
        
        # Find all entries
        for entry in root.findall("atom:entry", namespaces):
            try:
                # Extract basic info
                title = entry.find("atom:title", namespaces)
                summary = entry.find("atom:summary", namespaces)
                author_elements = entry.findall("atom:author/atom:name", namespaces)
                published = entry.find("atom:published", namespaces)
                updated = entry.find("atom:updated", namespaces)
                link_element = entry.find("atom:id", namespaces)
                
                # Extract arXiv-specific fields
                arxiv_ns = {"arxiv": "http://arxiv.org/schemas/atom"}
                comments = entry.find("arxiv:comment", arxiv_ns)
                journal_ref = entry.find("arxiv:journal_ref", arxiv_ns)
                doi_element = entry.find("arxiv:doi", arxiv_ns)
                categories = entry.findall("arxiv:category", arxiv_ns)
                
                # Get primary category
                primary_category = entry.find("arxiv:primary_category", arxiv_ns)
                primary_cat = primary_category.get("term") if primary_category is not None else ""
                
                result = {
                    "source": "arxiv",
                    "arxiv_id": link_element.text.split("/")[-1] if link_element is not None else "",
                    "title": title.text.strip() if title is not None else "",
                    "authors": [a.text for a in author_elements if a.text],
                    "abstract": summary.text.strip() if summary is not None else "",
                    "pub_date": published.text[:10] if published is not None else "",
                    "updated": updated.text[:10] if updated is not None else "",
                    "comments": comments.text if comments is not None else "",
                    "journal_ref": journal_ref.text if journal_ref is not None else "",
                    "doi": doi_element.text if doi_element is not None else "",
                    "categories": [c.get("term") for c in categories],
                    "primary_category": primary_cat,
                    "url": link_element.text if link_element is not None else ""
                }
                
                if result.get("title"):
                    results.append(result)
                    
            except Exception as e:
                print(f"[arXiv] Error parsing entry: {e}")
                continue
        
        # Rate limiting - arXiv requests 1 request per 3 seconds
        time.sleep(3.1)
    
    except urllib.error.URLError as e:
        print(f"[arXiv] Network error: {e}")
    except Exception as e:
        print(f"[arXiv] Error: {e}")
    
    return results
