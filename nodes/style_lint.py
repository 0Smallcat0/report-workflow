"""STYLE_LINT - Phase 2: T19 - Style and voice consistency checking."""
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def load_style_config(profile: str) -> dict:
    """Load style profile configuration."""
    config_dir = Path(__file__).parent.parent / "configs" / "style_profiles"
    profile_path = config_dir / f"{profile}.json"

    if profile_path.exists():
        try:
            with open(profile_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"[STYLE_LINT] failed to load style config {profile_path}: {exc}")

    # Fallback to hybrid
    hybrid_path = config_dir / "hybrid.json"
    if hybrid_path.exists():
        try:
            with open(hybrid_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"[STYLE_LINT] failed to load hybrid config {hybrid_path}: {exc}")

    return {}


def load_vocab() -> dict:
    """Load vocabulary configuration."""
    vocab_path = Path(__file__).parent.parent / "configs" / "style_vocab.json"
    if vocab_path.exists():
        try:
            with open(vocab_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"[STYLE_LINT] failed to load vocab {vocab_path}: {exc}")
    return {}


def load_banned_phrases() -> dict:
    """Load banned phrases configuration."""
    banned_path = Path(__file__).parent.parent / "configs" / "banned_phrases.json"
    if banned_path.exists():
        try:
            with open(banned_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(f"[STYLE_LINT] failed to load banned phrases {banned_path}: {exc}")
    return {}


# Voice consistency check
def check_passive_voice(text: str, max_percent: float = 30.0) -> list[dict]:
    """Check for excessive passive voice constructions."""
    issues = []
    
    # Pattern for passive voice: is/are/was/were/been/being + past participle
    passive_pattern = r'\b(is|are|was|were|been|being|be)\s+\w+ed\b'
    
    paragraphs = text.split("\n\n")
    for para_idx, para in enumerate(paragraphs):
        if not para.strip():
            continue
        
        words = para.split()
        if len(words) < 3:
            continue
        
        # Find passive constructions
        passives = re.findall(passive_pattern, para, re.IGNORECASE)
        
        # Estimate sentence count
        sentences = re.split(r'[.!?]+', para)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentence_count = max(len(sentences), 1)
        
        # Calculate passive percentage
        passive_percent = (len(passives) / sentence_count) * 100
        
        if passive_percent > max_percent:
            issues.append({
                "location": f"para_{para_idx}",
                "problem": f"Passive voice usage ({passive_percent:.0f}%) exceeds maximum ({max_percent}%)",
                "severity": "medium" if passive_percent < 50 else "high",
                "check": "voice"
            })
    
    return issues


def check_hedging(text: str, profile_config: dict) -> list[dict]:
    """Check hedging consistency."""
    issues = []
    
    hedges = profile_config.get("hedging_rules", {}).get("allowed_hedges", [])
    forbidden = profile_config.get("hedging_rules", {}).get("forbidden_superlatives", [])
    
    if not hedges and not forbidden:
        return issues
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    for sent_idx, sentence in enumerate(sentences):
        sentence_lower = sentence.lower()
        
        # Check for forbidden superlatives
        for phrase in forbidden:
            if phrase in sentence_lower:
                issues.append({
                    "location": f"sent_{sent_idx}",
                    "problem": f"Forbidden superlative: '{phrase}' in {profile_config.get('profile', 'unknown')} profile",
                    "severity": "high",
                    "check": "voice"
                })
        
        # Check for weak evidence without hedging
        weak_evidence_terms = ["anecdotal", "unverified", "unconfirmed", "preliminary"]
        strong_claim_terms = ["definitively", "conclusively", "absolutely"]
        
        has_weak_evidence = any(term in sentence_lower for term in weak_evidence_terms)
        has_strong_claim = any(term in sentence_lower for term in strong_claim_terms)
        has_hedge = any(hedge in sentence_lower for hedge in hedges)
        
        if has_weak_evidence and has_strong_claim and not has_hedge:
            issues.append({
                "location": f"sent_{sent_idx}",
                "problem": "Weak evidence with strong claim language without hedging",
                "severity": "medium",
                "check": "voice"
            })
    
    return issues


def check_impersonal(text: str, flag_list: list[str]) -> list[dict]:
    """Check for impersonal constructions."""
    issues = []
    
    for phrase in flag_list:
        if phrase.lower() in text.lower():
            issues.append({
                "location": "impersonal",
                "problem": f"Impersonal construction: '{phrase}'",
                "severity": "low",
                "check": "voice"
            })
    
    return issues


# Tone consistency check
def check_contractions(text: str, allowed: bool) -> list[dict]:
    """Check for contractions."""
    issues = []
    
    if allowed:
        return issues
    
    contractions = [
        "don't", "doesn't", "won't", "wouldn't", "couldn't", "shouldn't",
        "can't", "isn't", "aren't", "wasn't", "weren't", "haven't",
        "hasn't", "hadn't", "it's", "that's", "what's", "who's"
    ]
    
    for contraction in contractions:
        if contraction in text.lower():
            issues.append({
                "location": "contractions",
                "problem": f"Contraction found: '{contraction}'",
                "severity": "low",
                "check": "tone"
            })
    
    return issues


def check_colloquialisms(text: str) -> list[dict]:
    """Check for colloquialisms."""
    issues = []
    
    colloquial = [
        r'\bkinda\b', r'\bsorta\b', r'\bgotta\b', r'\bwanna\b',
        r'\blots of\b', r'\ba lot\b', r'\bkind of\b', r'\bsort of\b',
        r'\bpretty much\b', r'\bbasically\b', r'\bliterally\b'
    ]
    
    for pattern in colloquial:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            issues.append({
                "location": "colloquial",
                "problem": f"Colloquial expression: '{matches[0]}'",
                "severity": "medium",
                "check": "tone"
            })
    
    return issues


def check_rhetorical_questions(text: str) -> list[dict]:
    """Check for rhetorical questions."""
    issues = []
    
    # Pattern: starts with what/how/why/when/where/who/which + verb
    pattern = r'^(What|How|Why|When|Where|Who|Which)\s+\w+\s+\w+[?!]?'
    lines = text.split('\n')
    
    for line_idx, line in enumerate(lines):
        line = line.strip()
        if re.match(pattern, line, re.IGNORECASE):
            # Check if it's a genuine question or rhetorical
            if not line.endswith('?') or 'answer:' in line.lower():
                continue
            issues.append({
                "location": f"line_{line_idx}",
                "problem": "Rhetorical question detected",
                "severity": "low",
                "check": "tone"
            })
    
    return issues


# Editorial quality check
def check_wordiness(text: str, max_words: int = 20) -> list[dict]:
    """Check for overly wordy sentences."""
    issues = []
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    conjunction_pattern = r'\b(and|but|or|because|although|however|therefore|thus|while)\b'
    
    for sent_idx, sentence in enumerate(sentences):
        words = sentence.split()
        word_count = len(words)
        
        if word_count > max_words:
            # Count conjunctions
            conj_count = len(re.findall(conjunction_pattern, sentence, re.IGNORECASE))
            
            if conj_count >= 2:
                issues.append({
                    "location": f"sent_{sent_idx}",
                    "problem": f"Wordy sentence ({word_count} words) with multiple conjunctions ({conj_count})",
                    "severity": "low",
                    "check": "editorial"
                })
    
    return issues


def check_repetition(text: str, window: int = 3) -> list[dict]:
    """Check for same adjective/noun pair within N sentences."""
    issues = []
    
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Extract adjective+noun pairs
    def get_pairs(sentence):
        pattern = r'\b([A-Za-z]+)\s+([A-Za-z]+)\b'
        pairs = re.findall(pattern, sentence)
        return [f"{adj} {noun}" for adj, noun in pairs]
    
    all_pairs = [get_pairs(s) for s in sentences]
    
    for i in range(len(all_pairs)):
        check_end = min(i + window + 1, len(all_pairs))
        for j in range(i + 1, check_end):
            for pair in all_pairs[i]:
                if pair in all_pairs[j]:
                    issues.append({
                        "location": f"sent_{i}",
                        "problem": f"Repeated phrase within {window} sentences: '{pair}'",
                        "severity": "low",
                        "check": "editorial"
                    })
                    break
    
    return issues


def check_vague_quantifiers(text: str) -> list[dict]:
    """Check for vague quantifiers without supporting data."""
    issues = []
    
    vague_quantifiers = [
        r'\bmany\b', r'\bfew\b', r'\bseveral\b', r'\bsome\b',
        r'\balot\b', r'\bsignificant\b', r'\bimportant\b', r'\bconsiderable\b'
    ]
    
    # Pattern for data indicators (numbers, percentages, statistics)
    has_data_indicator = bool(re.search(r'\b\d+%|\d+\s+(?:people|participants|subjects|patients|cases|studies|trials)\b', text))
    
    for pattern in vague_quantifiers:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            if not has_data_indicator:
                issues.append({
                    "location": "vague_quantifiers",
                    "problem": f"Vague quantifier without data: '{matches[0]}'",
                    "severity": "low",
                    "check": "editorial"
                })
    
    return issues


def check_banned_phrases(text: str, profile: str) -> list[dict]:
    """Check against banned phrases list."""
    issues = []
    
    banned = load_banned_phrases()
    profile_banned = banned.get(profile, [])
    
    text_lower = text.lower()
    for phrase in profile_banned:
        if phrase.lower() in text_lower:
            issues.append({
                "location": "banned_phrases",
                "problem": f"Banned phrase: '{phrase}'",
                "severity": "medium",
                "check": "editorial"
            })
    
    return issues


def run_style_lint(
    merged_draft_path: str,
    blueprint_path: str,
    report_family: str,
    audience: str,
) -> dict:
    """T19: Run style lint checks on merged draft.
    
    Args:
        merged_draft_path: Path to merged_draft.md
        blueprint_path: Path to blueprint.json
        report_family: Report family (academic, work, hybrid)
        audience: Target audience
    
    Returns:
        dict with style check results
    """
    timestamp = datetime.now().isoformat()
    
    if not merged_draft_path or not Path(merged_draft_path).exists():
        return _empty_result(timestamp)

    try:
        with open(merged_draft_path) as f:
            text = f.read()
    except OSError as exc:
        logger.warning(f"[STYLE_LINT] failed to read merged draft {merged_draft_path}: {exc}")
        return _empty_result(timestamp)
    
    # Load configurations
    profile_config = load_style_config(report_family)
    vocab = load_vocab()
    
    all_issues = []
    
    # Layer 1: Voice Consistency
    voice_issues = []
    
    passive_max = profile_config.get("passive_voice", {}).get("max_percentage_per_paragraph", 30)
    voice_issues.extend(check_passive_voice(text, passive_max))
    voice_issues.extend(check_hedging(text, profile_config))
    
    impersonal_flag = profile_config.get("impersonal_constructions", {}).get("flag_list", [])
    voice_issues.extend(check_impersonal(text, impersonal_flag))
    
    all_issues.extend(voice_issues)
    
    # Layer 2: Tone Consistency
    tone_issues = []
    
    contractions_allowed = profile_config.get("contractions", {}).get("allowed", False)
    tone_issues.extend(check_contractions(text, contractions_allowed))
    tone_issues.extend(check_colloquialisms(text))
    tone_issues.extend(check_rhetorical_questions(text))
    
    all_issues.extend(tone_issues)
    
    # Layer 3: Editorial Quality
    editorial_issues = []
    
    max_sentence_words = profile_config.get("acceptable_sentence_length", {}).get("max", 25)
    editorial_issues.extend(check_wordiness(text, max_sentence_words))
    editorial_issues.extend(check_repetition(text, 3))
    editorial_issues.extend(check_vague_quantifiers(text))
    editorial_issues.extend(check_banned_phrases(text, report_family))
    
    all_issues.extend(editorial_issues)
    
    # Compute summary
    total_issues = len(all_issues)
    high_severity = sum(1 for i in all_issues if i.get("severity") == "high")
    medium_severity = sum(1 for i in all_issues if i.get("severity") == "medium")
    low_severity = sum(1 for i in all_issues if i.get("severity") == "low")
    
    # Style lint is always WARNING - never blocks
    return {
        "document": Path(merged_draft_path).name,
        "timestamp": timestamp,
        "gate": "style_lint",
        "status": "warning" if total_issues > 0 else "pass",
        "layers": {
            "voice": {
                "passed": len(voice_issues) == 0,
                "issues": voice_issues
            },
            "tone": {
                "passed": len(tone_issues) == 0,
                "issues": tone_issues
            },
            "editorial": {
                "passed": len(editorial_issues) == 0,
                "issues": editorial_issues
            }
        },
        "summary": {
            "total_issues": total_issues,
            "high_severity": high_severity,
            "medium_severity": medium_severity,
            "low_severity": low_severity,
            "gate_status": "warning"  # Always warning
        }
    }


def _empty_result(timestamp: str) -> dict:
    """Return empty result when input files are missing."""
    return {
        "document": "merged_draft.md",
        "timestamp": timestamp,
        "gate": "style_lint",
        "status": "pass",
        "layers": {
            "voice": {"passed": True, "issues": []},
            "tone": {"passed": True, "issues": []},
            "editorial": {"passed": True, "issues": []}
        },
        "summary": {
            "total_issues": 0,
            "high_severity": 0,
            "medium_severity": 0,
            "low_severity": 0,
            "gate_status": "warning"
        }
    }
