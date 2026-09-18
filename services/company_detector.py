"""
company_detector.py
Detects a human-readable company name from an uploaded filename or a
Screener URL slug. Falls back to a generic clean-up algorithm for
unknown companies so ANY CSV filename produces a sensible name.
"""

import os
import re

# Known company mappings (extend freely - case-insensitive keys)
KNOWN_COMPANIES = {
    "idbi": "IDBI Bank",
    "hdfc": "HDFC Bank",
    "sbi": "State Bank of India",
    "icici": "ICICI Bank",
    "tcs": "TCS",
    "reliance": "Reliance",
    "infosys": "Infosys",
    "wipro": "Wipro",
    "axis": "Axis Bank",
    "kotak": "Kotak Mahindra Bank",
    "amazon": "Amazon",
    "tesla": "Tesla",
    "apple": "Apple",
    "google": "Google",
    "microsoft": "Microsoft",
}


def _clean_generic_name(raw: str) -> str:
    """Turn an arbitrary filename/slug into a readable Title Case name."""
    name = raw

    # Remove file extension if present
    name = re.sub(r"\.csv$", "", name, flags=re.IGNORECASE)

    # Replace underscores / hyphens / dots with spaces
    name = re.sub(r"[_\-.]+", " ", name)

    # Insert space between camelCase boundaries (e.g. "ABCCompany" -> "ABC Company")
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)

    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name).strip()

    if not name:
        return "Unknown Company"

    # Title-case each word, but keep short all-caps acronyms (<=4 chars) as-is
    words = []
    for w in name.split(" "):
        if w.isupper() and len(w) <= 4:
            words.append(w)
        else:
            words.append(w.capitalize())

    return " ".join(words)


def detect_company_name(source_name: str) -> str:
    """
    Detect a company name from a filename (e.g. 'IDbi.csv') or a
    Screener slug (e.g. 'IDBI').

    Detection order:
      1. Exact / substring match against KNOWN_COMPANIES (case-insensitive)
      2. Generic clean-up of the filename into a readable name
    """
    if not source_name:
        return "Unknown Company"

    base = os.path.basename(source_name)
    base_no_ext = re.sub(r"\.csv$", "", base, flags=re.IGNORECASE)
    lower = base_no_ext.lower()

    # 1. Known company lookup (substring match so 'IDbi_2024' still matches 'idbi')
    for key, display_name in KNOWN_COMPANIES.items():
        if key in lower:
            return display_name

    # 2. Generic fallback
    return _clean_generic_name(base_no_ext)
