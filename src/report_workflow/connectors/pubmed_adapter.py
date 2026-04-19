"""PUBMED_ADAPTER - Retrieve literature from NCBI PubMed via Entrez API."""
import json
import urllib.request
import urllib.parse
import urllib.error
import time
from typing import Optional


PUBMED_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def search_pubmed(query: str, max_results: int = 10) -> list[dict]:
    """Search PubMed using NCBI Entrez API.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to retrieve (default 10)
    
    Returns:
        List of result dicts with PubMed metadata
    """
    results = []
    
    try:
        # Step 1: Search for PMIDs
        search_params = urllib.parse.urlencode({
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance"
        })
        
        search_url = f"{PUBMED_EUTILS_BASE}/esearch.fcgi?{search_params}"
        
        with urllib.request.urlopen(search_url, timeout=30) as response:
            search_data = json.loads(response.read().decode("utf-8"))
        
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        
        if not id_list:
            return []
        
        # Step 2: Fetch article details for each PMID
        # Batch fetch in groups of 100 (Entrez limit)
        batch_size = 100
        for i in range(0, len(id_list), batch_size):
            batch_ids = id_list[i:i + batch_size]
            
            # Fetch summary for batch
            summary_params = urllib.parse.urlencode({
                "db": "pubmed",
                "id": ",".join(batch_ids),
                "retmode": "json"
            })
            
            summary_url = f"{PUBMED_EUTILS_BASE}/esummary.fcgi?{summary_params}"
            
            try:
                with urllib.request.urlopen(summary_url, timeout=30) as response:
                    summary_data = json.loads(response.read().decode("utf-8"))
                
                # Parse results
                result_uids = summary_data.get("result", {})
                for uid in batch_ids:
                    if uid == "undefined":
                        continue
                    
                    article_data = result_uids.get(uid, {})
                    if not article_data or uid == "0":
                        continue
                    
                    # Extract authors
                    authors = article_data.get("authors", [])
                    author_list = [a.get("name", "") for a in authors if a.get("name")]
                    
                    result = {
                        "source": "pubmed",
                        "pmid": uid,
                        "title": article_data.get("title", ""),
                        "authors": author_list,
                        "pub_date": article_data.get("pubdate", ""),
                        "journal": article_data.get("source", ""),
                        "abstract": article_data.get("abstract", ""),
                        "doi": article_data.get("elocationid", "").replace("doi: ", ""),
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/"
                    }
                    
                    if result.get("title"):
                        results.append(result)
                
            except Exception as e:
                print(f"[PubMed] Error fetching batch: {e}")
            
            # Rate limiting - Entrez requires 1 request per second
            time.sleep(0.34)  # Slightly more than 3 per second limit
    
    except urllib.error.URLError as e:
        print(f"[PubMed] Network error: {e}")
    except Exception as e:
        print(f"[PubMed] Error: {e}")
    
    return results
