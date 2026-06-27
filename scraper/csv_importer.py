"""
CSV lead importer — accepts uploaded CSV files and converts rows to Lead records.
Expected columns (case-insensitive, flexible mapping):
  name, phone, email, company, address, health_interest, notes, source
"""
import logging
import io
from typing import List, Dict, Tuple

logger = logging.getLogger(__name__)

# Flexible column name aliases
COLUMN_MAP = {
    "name": ["name", "full name", "fullname", "contact", "contact name", "first name", "firstname"],
    "phone": ["phone", "phone number", "mobile", "cell", "telephone", "tel"],
    "email": ["email", "email address", "e-mail", "mail"],
    "company": ["company", "business", "organization", "org", "business name"],
    "address": ["address", "location", "street", "city", "full address"],
    "health_interest": ["health interest", "interest", "interests", "product interest", "health focus"],
    "notes": ["notes", "note", "comments", "comment", "remarks"],
    "source": ["source", "lead source", "origin"],
}


def import_csv(file_content: bytes, default_campaign_id: int = None) -> Tuple[List[Dict], List[str]]:
    """
    Parse CSV bytes and return (leads, errors).
    leads: list of dicts ready for Lead model creation
    errors: list of rows that couldn't be parsed
    """
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas not installed")
        return [], ["pandas not installed"]

    errors = []
    leads = []

    try:
        df = pd.read_csv(io.BytesIO(file_content), dtype=str).fillna("")
    except Exception as e:
        return [], [f"Could not parse CSV: {e}"]

    # Build column mapping (normalize headers)
    col_mapping = {}
    normalized_cols = {c.lower().strip(): c for c in df.columns}

    for field, aliases in COLUMN_MAP.items():
        for alias in aliases:
            if alias in normalized_cols:
                col_mapping[field] = normalized_cols[alias]
                break

    if "name" not in col_mapping:
        return [], ["CSV must have a 'name' column"]

    for idx, row in df.iterrows():
        try:
            name = row.get(col_mapping["name"], "").strip()
            if not name:
                errors.append(f"Row {idx + 2}: empty name — skipped")
                continue

            lead = {
                "name": name,
                "phone": row.get(col_mapping.get("phone", ""), "").strip(),
                "email": row.get(col_mapping.get("email", ""), "").strip(),
                "company": row.get(col_mapping.get("company", ""), "").strip() or name,
                "address": row.get(col_mapping.get("address", ""), "").strip(),
                "health_interest": row.get(col_mapping.get("health_interest", ""), "").strip(),
                "notes": row.get(col_mapping.get("notes", ""), "").strip(),
                "source": row.get(col_mapping.get("source", ""), "csv").strip() or "csv",
                "status": "new",
                "campaign_id": default_campaign_id,
            }

            if not lead["phone"]:
                errors.append(f"Row {idx + 2}: '{name}' skipped — no phone number")
                continue

            leads.append(lead)
        except Exception as e:
            errors.append(f"Row {idx + 2}: {e}")

    logger.info(f"CSV import: {len(leads)} leads parsed, {len(errors)} errors")
    return leads, errors
