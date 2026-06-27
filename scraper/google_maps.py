"""
Google Maps Places scraper.
Uses the new Places API (Text Search) via direct HTTP — no legacy API needed.
Falls back to Yellow Pages web scraping if no API key is configured.
"""
import logging
import re
import time
import requests
from typing import List, Dict
from config import settings

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_SKIP_DOMAINS = {"sentry.io", "wix.com", "example.com", "google.com", "schema.org",
                 "wordpress.com", "cloudflare.com", "w3.org", "mozilla.org"}


def _extract_email_from_website(url: str) -> str:
    """Visit a business website and extract the first contact email found."""
    if not url:
        return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; SalesBot/1.0)"}
        pages = [url, url.rstrip("/") + "/contact", url.rstrip("/") + "/about"]
        for page in pages:
            try:
                r = requests.get(page, headers=headers, timeout=6, allow_redirects=True)
                if r.ok:
                    emails = _EMAIL_RE.findall(r.text)
                    for email in emails:
                        domain = email.split("@")[-1].lower()
                        if domain not in _SKIP_DOMAINS and not email.endswith(".png") and not email.endswith(".jpg"):
                            return email.lower()
            except Exception:
                continue
    except Exception:
        pass
    return ""

logger = logging.getLogger(__name__)

NEW_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"


def scrape_google_maps(query: str, location: str, max_results: int = 50) -> List[Dict]:
    """
    Search Google Maps for businesses matching query in location.
    Returns a list of lead dicts ready for database import.
    """
    if settings.GOOGLE_MAPS_API_KEY:
        return _scrape_new_api(query, location, max_results)
    else:
        logger.warning("No Google Maps API key — using Yelp/YP/OSM fallback chain")
        return _fallback(query, location, max_results)


def _scrape_new_api(query: str, location: str, max_results: int) -> List[Dict]:
    """Use the new Google Places API (Text Search) — works with any modern API key."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": settings.GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": (
            "places.displayName,"
            "places.formattedAddress,"
            "places.nationalPhoneNumber,"
            "places.websiteUri,"
            "places.types,"
            "places.rating,"
            "nextPageToken"
        ),
    }

    leads = []
    next_page_token = None
    search_text = f"{query} in {location}"

    while len(leads) < max_results:
        body = {
            "textQuery": search_text,
            "maxResultCount": min(20, max_results - len(leads)),  # API max is 20 per page
        }
        if next_page_token:
            body["pageToken"] = next_page_token

        try:
            resp = requests.post(NEW_PLACES_URL, json=body, headers=headers, timeout=15)
            data = resp.json()

            if not resp.ok:
                error = data.get("error", {})
                logger.error(f"Google Places API error: {error.get('message', resp.text)}")
                return _fallback(query, location, max_results)


            places = data.get("places", [])
            if not places:
                break

            for place in places:
                name = place.get("displayName", {}).get("text", "")
                if not name:
                    continue
                website = place.get("websiteUri", "")
                email = _extract_email_from_website(website)
                lead = {
                    "name": name,
                    "phone": place.get("nationalPhoneNumber", ""),
                    "email": email,
                    "company": name,
                    "address": place.get("formattedAddress", ""),
                    "website": website,
                    "source": "google_maps",
                    "notes": (
                        f"Google Maps: '{query}' in {location}. "
                        f"Rating: {place.get('rating', 'N/A')}. "
                        f"Website: {website or 'N/A'}"
                    ),
                    "health_interest": _infer_health_interest(
                        place.get("types", []), name
                    ),
                }
                leads.append(lead)
                time.sleep(0.5)  # polite delay between website visits

            next_page_token = data.get("nextPageToken")
            if not next_page_token or len(leads) >= max_results:
                break

            time.sleep(1)  # brief pause between pages

        except requests.exceptions.Timeout:
            logger.error("Google Places API timed out")
            break
        except Exception as e:
            logger.error(f"Google Places API error: {e}")
            break

    logger.info(f"Google Maps: found {len(leads)} leads for '{query}' in {location}")
    return leads


def _fallback(query: str, location: str, max_results: int) -> list:
    """Ordered fallback: Yelp (API, reliable) → Yellow Pages → OpenStreetMap."""
    # Try Yelp first — proper API, not blocked by cloud IPs
    try:
        from config import settings as _s
        from scraper.yelp import scrape_yelp
        yelp_key = _s.YELP_API_KEY
        if yelp_key:
            results = scrape_yelp(query, location, max_results, api_key=yelp_key)
            if results:
                logger.info(f"Yelp fallback returned {len(results)} results")
                return results
    except Exception as e:
        logger.warning(f"Yelp fallback failed: {e}")

    # Try Yellow Pages (works locally, often blocked from cloud IPs)
    try:
        from scraper.yellow_pages import scrape_yellow_pages
        results = scrape_yellow_pages(query, location, max_results)
        if results:
            return results
    except Exception as e:
        logger.warning(f"Yellow Pages fallback failed: {e}")

    # Last resort — OpenStreetMap (sparse phone data)
    try:
        from scraper.yellow_pages import scrape_openstreetmap
        return scrape_openstreetmap(query, location, max_results)
    except Exception as e:
        logger.warning(f"OSM fallback failed: {e}")
        return []


def _infer_health_interest(types: list, name: str) -> str:
    """Guess a lead's health interest from their business type and name."""
    name_lower = name.lower()
    type_str = " ".join(types).lower()
    combined = name_lower + " " + type_str

    mappings = [
        (["gym", "fitness", "crossfit", "weightlift"], "V-NRGY energy, V-NITRO performance, VITALPRO protein"),
        (["yoga", "meditation", "pilates", "mindful"], "adaptogens, V-DAILY, essential wellness"),
        (["chiropractic", "chiropractor"], "V-OMEGA 3 joint health, anti-inflammatory"),
        (["naturopath", "naturopathic", "holistic"], "full product line, herbal, V-GLUTATION PLUS"),
        (["health_food", "organic", "natural_food", "grocery"], "full product line, V-DAILY, VITALPRO"),
        (["spa", "beauty", "salon", "skin"], "VITALAGE COLLAGEN, V-GLUTATION PLUS skincare"),
        (["massage", "physical_therapy", "physio"], "V-OMEGA 3, muscle recovery, essential oils"),
        (["nutrition", "dietitian", "diet"], "VITALPRO, weight management, V-TEDETOX"),
        (["acupuncture", "tcm"], "herbal remedies, V-ORGANEX detox"),
        (["doctor", "clinic", "medical"], "V-DAILY, V-OMEGA 3, immune support"),
    ]
    for keywords, interest in mappings:
        if any(k in combined for k in keywords):
            return interest
    return "V-DAILY general wellness, VITALPRO nutrition"


# Suggested search queries for Vital Health Global prospects
SUGGESTED_QUERIES = [
    "health food stores",
    "gyms and fitness centers",
    "yoga studios",
    "chiropractors",
    "naturopathic doctors",
    "wellness centers",
    "massage therapy",
    "holistic health practitioners",
    "nutrition counselors",
    "organic grocery stores",
    "vitamin and supplement stores",
    "physical therapy clinics",
    "personal trainers",
    "pilates studios",
    "acupuncture clinics",
    "day spas",
    "crossfit gyms",
    "health coaches",
]
