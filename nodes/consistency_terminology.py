"""CONSISTENCY_TERMINOLOGY - Terminology consistency checking."""
import re
from pathlib import Path
from collections import defaultdict
from typing import Optional


def extract_noun_phrases_simple(text: str) -> list[tuple[str, int]]:
    """Extract noun phrases using simple frequency analysis.
    
    Returns list of (phrase, paragraph_index) tuples.
    """
    # Split into paragraphs
    paragraphs = text.split("\n\n")
    
    noun_phrases = []
    
    # Simple pattern: capitalize words that appear multiple times
    # or look for common noun patterns (Adjective+Noun, Noun+Noun)
    
    # Split into sentences
    for para_idx, para in enumerate(paragraphs):
        # Find capitalized multi-word terms (potential proper nouns/key terms)
        # Pattern: 2-4 word sequences starting with capital letter
        pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b'
        matches = re.findall(pattern, para)
        for match in matches:
            if len(match.split()) >= 1:
                noun_phrases.append((match.strip(), para_idx))
    
    return noun_phrases


def terminology_consistency_checker(merged_draft_path: str) -> list[dict]:
    """Check terminology consistency within and across paragraphs."""
    issues = []
    
    if not Path(merged_draft_path).exists():
        return issues
    
    with open(merged_draft_path) as f:
        text = f.read()
    
    paragraphs = text.split("\n\n")
    
    # Extract noun phrases
    phrase_paragraphs = extract_noun_phrases_simple(text)
    
    # Group phrases by their normalized form (lowercase)
    phrase_groups = defaultdict(list)
    for phrase, para_idx in phrase_paragraphs:
        normalized = phrase.lower().strip()
        if len(normalized) > 2:  # Skip short phrases
            phrase_groups[normalized].append((phrase, para_idx))
    
    # Find phrases that appear in different forms
    for normalized, occurrences in phrase_groups.items():
        if len(occurrences) < 2:
            continue
        
        # Get all unique surface forms
        forms = set(phrase for phrase, _ in occurrences)
        
        if len(forms) > 1:
            # Different surface forms found
            for phrase, para_idx in occurrences:
                if phrase.lower().strip() != normalized:
                    # Find the dominant form
                    dominant = max(occurrences, key=lambda x: sum(1 for p, _ in occurrences if p == x[0]))
                    dominant_form = dominant[0]
                    
                    # Determine severity
                    same_para = sum(1 for _, p in occurrences if p == para_idx)
                    para_distance = [abs(p - para_idx) for _, p in occurrences if _ != phrase]
                    min_distance = min(para_distance) if para_distance else 0
                    
                    if same_para > 0:
                        severity = "high"
                    elif min_distance <= 3:
                        severity = "medium"
                    else:
                        severity = "low"
                    
                    issues.append({
                        "location": f"para_{para_idx}",
                        "problem": f"Terminology inconsistency: '{phrase}' vs '{dominant_form}' (different surface forms)",
                        "severity": severity,
                        "check": "terminology"
                    })
                    break
    
    # Check for same paragraph repetition
    for para_idx, para in enumerate(paragraphs):
        # Find repeated noun phrases in same paragraph
        words = re.findall(r'\b[A-Z][a-z]+\b', para)
        word_counts = defaultdict(int)
        for word in words:
            word_counts[word] += 1
        
        for word, count in word_counts.items():
            if count > 3:
                issues.append({
                    "location": f"para_{para_idx}",
                    "problem": f"Overused term in paragraph: '{word}' appears {count} times",
                    "severity": "low",
                    "check": "terminology"
                })
    
    return issues
