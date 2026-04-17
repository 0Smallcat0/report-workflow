"""OPENALEX_ADAPTER - Retrieve literature from OpenAlex API."""
import json
import urllib.request
import urllib.parse
import urllib.error
import time
from typing import Optional


OPENALEX_API_BASE = "https://api.openalex.org"


def search_openalex(query: str, max_results: int = 10) -> list[dict]:
    """Search OpenAlex using their API.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to retrieve (default 10)
    
    Returns:
        List of result dicts with OpenAlex work metadata
    """
    results = []
    
    try:
        # OpenAlex uses "works" endpoint with filter syntax
        # Build search query
        search_params = urllib.parse.urlencode({
            "search": query,
            "per_page": min(max_results, 100),  # OpenAlex max is 100
            "sort": "relevance_score:desc"
        })
        
        url = f"{OPENALEX_API_BASE}/works?{search_params}"
        
        with urllib.request.urlopen(url, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        works = data.get("results", [])
        
        for work in works:
            try:
                # Extract authors
                authorships = work.get("authorships", [])
                author_list = []
                for auth in authorships:
                    author = auth.get("author", {})
                    if author:
                        author_list.append(author.get("display_name", ""))
                
                # Extract abstract
                abstract_inverted = work.get("abstract_inverted_index", {})
                abstract = ""
                if abstract_inverted:
                    # Reconstruct abstract from inverted index
                    word_positions = []
                    for word, positions in abstract_inverted.items():
                        for pos in positions:
                            word_positions.append((pos, word))
                    word_positions.sort(key=lambda x: x[0])
                    abstract = " ".join(word for _, word in word_positions)
                
                # Extract publication date
                publication_date = work.get("publication_date", "")
                if not publication_date and work.get("publication_year"):
                    publication_date = str(work.get("publication_year"))
                
                result = {
                    "source": "openalex",
                    "openalex_id": work.get("id", "").replace("https://openalex.org/", ""),
                    "title": work.get("display_name", ""),
                    "authors": author_list,
                    "pub_date": publication_date,
                    "journal": work.get("primary_location", {}).get("source", {}).get("display_name", ""),
                    "abstract": abstract,
                    "doi": work.get("doi", ""),
                    "url": work.get("id", ""),
                    "citation_count": work.get("cited_by_count", 0),
                    "publication_year": work.get("publication_year"),
                    "type": work.get("type", ""),
                    "open_access": work.get("open_access", {}).get("is_oa", False)
                }
                
                if result.get("title"):
                    results.append(result)
                    
            except Exception as e:
                print(f"[OpenAlex] Error parsing work: {e}")
                continue
        
        # Rate limiting - OpenAlex allows 10 requests per second
        time.sleep(0.1)
    
    except urllib.error.URLError as e:
        print(f"[OpenAlex] Network error: {e}")
    except Exception as e:
        print(f"[OpenAlex] Error: {e}")
    
    return results
