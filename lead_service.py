"""
Sarah — Lead extraction service.

Analyses the call transcript and summary produced by call_service to
extract structured lead information using:

  * Regex patterns for phone numbers and names
  * Keyword scanning for trade services and urgency levels
  * Layered fallbacks so partial data is always returned

Extracted fields
----------------
caller_name  – Customer's first (and optionally last) name
phone        – Best available phone number (E.164 or raw digits)
suburb       – Suburb / locality mentioned during the call
service      – Canonical trade service label  (e.g. "Plumbing - Blocked Drain")
urgency      – emergency | urgent | standard | unknown
summary      – Best available human-readable summary
"""

import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Service keyword map
# Key   → substring to search for (case-insensitive)
# Value → canonical service label
# Ordered from most-specific to least-specific so the first match wins.
# --------------------------------------------------------------------------- #
_SERVICE_MAP: Dict[str, str] = {
    # ── Plumbing ────────────────────────────────────────────────────────────
    "burst pipe":        "Plumbing - Burst Pipe",
    "burst":             "Plumbing - Burst Pipe",
    "no hot water":      "Plumbing - No Hot Water",
    "hot water":         "Plumbing - Hot Water System",
    "blocked drain":     "Plumbing - Blocked Drain",
    "blocked toilet":    "Plumbing - Blocked Toilet",
    "blocked":           "Plumbing - Blockage",
    "leaking tap":       "Plumbing - Leaking Tap",
    "dripping tap":      "Plumbing - Leaking Tap",
    "faucet":            "Plumbing - Leaking Tap",
    "leak":              "Plumbing - Leak",
    "pipe":              "Plumbing - Pipe Repair",
    "drain":             "Plumbing - Drain",
    "toilet":            "Plumbing - Toilet",
    "tap":               "Plumbing - Tap",
    "sewage":            "Plumbing - Sewage",
    "sewer":             "Plumbing - Sewage",
    "flooding":          "Plumbing - Flooding",
    "flood":             "Plumbing - Flooding",
    # ── Gas ─────────────────────────────────────────────────────────────────
    "gas leak":          "Gas Fitting - Gas Leak",
    "gas":               "Gas Fitting",
    # ── Electrical ──────────────────────────────────────────────────────────
    "switchboard":       "Electrical - Switchboard",
    "circuit breaker":   "Electrical - Circuit Breaker",
    "circuit":           "Electrical - Circuit",
    "power point":       "Electrical - Power Point",
    "outlet":            "Electrical - Power Point",
    "wiring":            "Electrical - Wiring",
    "electrician":       "Electrical",
    "electrical":        "Electrical",
    # ── HVAC ────────────────────────────────────────────────────────────────
    "air conditioning":  "HVAC - Air Conditioning",
    "air con":           "HVAC - Air Conditioning",
    "aircon":            "HVAC - Air Conditioning",
    "heating":           "HVAC - Heating",
    "hvac":              "HVAC",
    # ── General ─────────────────────────────────────────────────────────────
    "roof":              "Roofing",
    "gutter":            "Guttering",
    "paint":             "Painting",
    "tiling":            "Tiling",
    "tile":              "Tiling",
    "renovation":        "Renovation",
    "inspection":        "Inspection",
    "quote":             "Quote Request",
    "install":           "Installation",
    "maintenance":       "Maintenance",
    "repair":            "General Repair",
}

# --------------------------------------------------------------------------- #
# Urgency keyword map
# --------------------------------------------------------------------------- #
_URGENCY_MAP: Dict[str, str] = {
    # emergency tier
    "emergency":      "emergency",
    "flooding":       "emergency",
    "flood":          "emergency",
    "burst pipe":     "emergency",
    "no hot water":   "emergency",
    "gas leak":       "emergency",
    "sparking":       "emergency",
    "on fire":        "emergency",
    # urgent tier
    "urgent":         "urgent",
    "urgently":       "urgent",
    "asap":           "urgent",
    "as soon as":     "urgent",
    "right away":     "urgent",
    "today":          "urgent",
    "tonight":        "urgent",
    "this morning":   "urgent",
    "this afternoon": "urgent",
    "this evening":   "urgent",
    # standard tier
    "tomorrow":       "standard",
    "next week":      "standard",
    "this week":      "standard",
    "when you can":   "standard",
    "no rush":        "standard",
    "whenever":       "standard",
    "quote":          "standard",
    "just a quote":   "standard",
}

# --------------------------------------------------------------------------- #
# Regex patterns
# --------------------------------------------------------------------------- #

# Phone numbers — AU mobile, AU landline, generic international
_RE_PHONE = re.compile(
    r"""
    (?:\+61|0061|0)     # country/trunk prefix
    [\s\-\.]?
    (?:4\d{2}|[2378]\d) # mobile 04xx or landline area
    [\s\-\.]?
    \d{3,4}
    [\s\-\.]?
    \d{3,4}
    |
    \+\d{7,15}          # generic E.164
    """,
    re.VERBOSE,
)

# Name patterns — "My name is X", "I'm X", "This is X", "It's X"
_RE_NAME = re.compile(
    r"""
    (?:
        my\s+name\s+is  |
        i['']?m         |
        this\s+is       |
        it['']?s        |
        name['']?s?\s+  |
        caller[:\s]+    |
        speaking\s+with |
        call\s+for      |
        calling\s+for
    )
    \s+
    ([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)   # Firstname [Lastname]
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Suburb — "in [Suburb]", "at [Suburb]", "from [Suburb]"
# Matches title-case words (1-3 words) that follow a preposition
_RE_SUBURB = re.compile(
    r"""
    (?:in|at|from|located\s+in|based\s+in|near|around)
    \s+
    ([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,2})  # 1-3 capitalised words
    """,
    re.VERBOSE,
)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def extract_lead(call_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract structured lead fields from parsed call data.

    Args:
        call_data: Dict returned by ``call_service.parse_call_payload``.
                   Uses the ``transcript``, ``summary``, and
                   ``caller_phone`` keys.

    Returns:
        Dict with keys:
            caller_name (str | None)
            phone       (str | None)
            suburb      (str | None)
            service     (str | None)
            urgency     (str)           always set, default "unknown"
            summary     (str)           best available summary
    """
    transcript: str   = (call_data.get("transcript") or "").strip()
    summary: str      = (call_data.get("summary") or "").strip()
    caller_phone: str = (call_data.get("caller_phone") or "").strip()

    # Combined search text — transcript has more detail, summary is cleaner
    full_text = f"{transcript}\n{summary}"

    caller_name = _extract_name(full_text)
    phone       = _extract_phone(full_text) or (caller_phone or None)
    suburb      = _extract_suburb(full_text)
    service     = _extract_service(full_text)
    urgency     = _extract_urgency(full_text)

    # Use the Vapi summary if present; otherwise build one from transcript
    best_summary = summary or _build_summary(transcript)

    result = {
        "caller_name": caller_name,
        "phone":       phone,
        "suburb":      suburb,
        "service":     service,
        "urgency":     urgency,
        "summary":     best_summary,
    }

    logger.info(
        "Lead extracted — name=%s  phone=%s  suburb=%s  service=%s  urgency=%s",
        caller_name, phone, suburb, service, urgency,
    )
    return result


# --------------------------------------------------------------------------- #
# Private extraction helpers
# --------------------------------------------------------------------------- #

def _extract_name(text: str) -> Optional[str]:
    """
    Extract the caller's name using introduction-phrase patterns.

    Args:
        text: Combined transcript + summary text.

    Returns:
        Extracted name string, or None if not found.
    """
    match = _RE_NAME.search(text)
    if match:
        name = match.group(1).strip()
        logger.debug("Name extracted: %s", name)
        return name
    return None


def _extract_phone(text: str) -> Optional[str]:
    """
    Extract the first phone number found in *text*.

    Strips non-digit characters and normalises to a clean string.

    Args:
        text: Combined transcript + summary text.

    Returns:
        Cleaned phone string, or None if not found.
    """
    match = _RE_PHONE.search(text)
    if match:
        raw = match.group(0)
        # Collapse whitespace/dashes/dots into a single clean string
        cleaned = re.sub(r"[\s\-\.]", "", raw)
        logger.debug("Phone extracted: %s", cleaned)
        return cleaned
    return None


def _extract_suburb(text: str) -> Optional[str]:
    """
    Extract a suburb / locality from positional preposition patterns.

    Args:
        text: Combined transcript + summary text.

    Returns:
        Suburb string, or None if not found.
    """
    # Try the regex pattern first
    match = _RE_SUBURB.search(text)
    if match:
        suburb = match.group(1).strip()
        logger.debug("Suburb extracted (regex): %s", suburb)
        return suburb

    # Fallback: look for "suburb" or "area" keyword
    suburb_kw = re.search(
        r"(?:suburb|area|location)[:\s]+([A-Z][a-zA-Z ]+?)(?:[,\.\n]|$)",
        text,
        re.IGNORECASE,
    )
    if suburb_kw:
        suburb = suburb_kw.group(1).strip()
        logger.debug("Suburb extracted (keyword): %s", suburb)
        return suburb

    return None


def _extract_service(text: str) -> Optional[str]:
    """
    Determine the trade service requested by scanning for keywords.

    Uses the ordered ``_SERVICE_MAP``; the first match wins.

    Args:
        text: Combined transcript + summary text.

    Returns:
        Canonical service label, or None if no keyword matched.
    """
    lower = text.lower()
    for keyword, label in _SERVICE_MAP.items():
        if keyword in lower:
            logger.debug("Service matched: %s → %s", keyword, label)
            return label
    return None


def _extract_urgency(text: str) -> str:
    """
    Determine the urgency level by scanning for keywords.

    Uses the ordered ``_URGENCY_MAP``; the first (highest-priority) match
    wins.  Tiers: emergency > urgent > standard > unknown.

    Args:
        text: Combined transcript + summary text.

    Returns:
        One of: "emergency", "urgent", "standard", "unknown".
    """
    lower = text.lower()

    # Walk the map in insertion order (most critical first)
    for keyword, tier in _URGENCY_MAP.items():
        if keyword in lower:
            logger.debug("Urgency matched: %s → %s", keyword, tier)
            return tier

    return "unknown"


def _build_summary(transcript: str, max_chars: int = 300) -> str:
    """
    Build a short summary from the transcript when Vapi didn't provide one.

    Takes the first ``max_chars`` characters and appends an ellipsis.

    Args:
        transcript: Full call transcript.
        max_chars:  Maximum characters to include.

    Returns:
        Truncated transcript string, or empty string if transcript is empty.
    """
    if not transcript:
        return ""
    snippet = transcript[:max_chars].strip()
    if len(transcript) > max_chars:
        snippet += " …"
    return snippet
