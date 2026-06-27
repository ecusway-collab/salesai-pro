"""
Yelp Fusion API scraper — free tier, returns real phone numbers.
Get a free API key at https://www.yelp.com/developers/v3/manage_app
"""
import logging
import requests
from typing import List, Dict

logger = logging.getLogger(__name__)

YELP_URL = "https://api.yelp.com/v3/businesses/search"


def scrape_yelp(query: str, location: str, max_results: int = 50, api_key: str = "") -> List[Dict]:
    if not api_key:
        return []

    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    leads = []
    offset = 0

    while len(leads) < max_results:
        params = {
            "term": query,
            "location": location,
            "limit": min(50, max_results - len(leads)),
            "offset": offset,
        }
        try:
            resp = requests.get(YELP_URL, headers=headers, params=params, timeout=15)
            if not resp.ok:
                logger.error(f"Yelp API error {resp.status_code}: {resp.text[:200]}")
                break
            data = resp.json()
            businesses = data.get("businesses", [])
            if not businesses:
                break

            for biz in businesses:
                loc = biz.get("location", {})
                address = ", ".join(
                    p for p in [
                        loc.get("address1", ""),
                        loc.get("city", ""),
                        loc.get("state", ""),
                    ] if p
                )
                cats = ", ".join(c.get("title", "") for c in biz.get("categories", []))
                leads.append({
                    "name":           biz.get("name", ""),
                    "phone":          biz.get("phone", ""),
                    "email":          "",
                    "company":        biz.get("name", ""),
                    "address":        address or location,
                    "source":         "yelp",
                    "notes":          f"Yelp: '{query}' in {location}. Rating: {biz.get('rating','N/A')}. {cats}",
                    "health_interest": _infer_interest(cats + " " + biz.get("name", "")),
                })

            offset += len(businesses)
            if offset >= data.get("total", 0) or len(businesses) < 50:
                break

        except Exception as e:
            logger.error(f"Yelp scraper error: {e}")
            break

    logger.info(f"Yelp: {len(leads)} results for '{query}' in {location}")
    return leads


def _infer_interest(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["gym", "fitness", "crossfit", "sport", "trainer"]):
        return "V-NRGY energy, V-NITRO performance, VITALPRO protein"
    if any(k in t for k in ["yoga", "meditation", "pilates", "mindful"]):
        return "V-DAILY wellness, adaptogens"
    if any(k in t for k in ["chiropractic", "chiropractor"]):
        return "V-OMEGA 3 joint health, anti-inflammatory"
    if any(k in t for k in ["naturopath", "holistic", "alternative"]):
        return "full product line, V-GLUTATION PLUS"
    if any(k in t for k in ["health food", "organic", "supplement", "vitamin", "nutrition"]):
        return "full product line, V-DAILY, VITALPRO"
    if any(k in t for k in ["spa", "beauty", "salon", "skin", "collagen"]):
        return "VITALAGE COLLAGEN, V-GLUTATION PLUS"
    if any(k in t for k in ["massage", "physio", "therapy", "acupuncture"]):
        return "V-OMEGA 3, muscle recovery, herbal"
    if any(k in t for k in ["coach", "wellness", "health"]):
        return "V-DAILY, VITALPRO, personalized nutrition"
    return "V-DAILY general wellness, VITALPRO nutrition"
