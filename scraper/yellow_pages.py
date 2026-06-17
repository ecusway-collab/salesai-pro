"""
Business directory scrapers — Yellow Pages + OpenStreetMap (Overpass API).
OpenStreetMap is completely free, no API key, no rate limits.
Yellow Pages is a secondary option with realistic browser simulation.
"""
import logging
import time
import re
from typing import List, Dict

logger = logging.getLogger(__name__)


def scrape_yellow_pages(query: str, location: str, max_results: int = 50) -> List[Dict]:
    """Try Yellow Pages first, fall back to OpenStreetMap on failure."""
    results = _scrape_yp(query, location, max_results)
    if results:
        return results
    logger.info("Yellow Pages unavailable — using OpenStreetMap (free, no key needed)")
    return scrape_openstreetmap(query, location, max_results)


def _scrape_yp(query: str, location: str, max_results: int) -> List[Dict]:
    """Scrape Yellow Pages with realistic browser headers."""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Referer": "https://www.google.com/",
    })

    leads = []
    page = 1

    while len(leads) < max_results:
        url = (
            f"https://www.yellowpages.com/search"
            f"?search_terms={query.replace(' ', '+')}"
            f"&geo_location_terms={location.replace(' ', '+')}"
            f"&page={page}"
        )
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code in (403, 429):
                logger.warning(f"Yellow Pages blocked (HTTP {resp.status_code})")
                return leads

            soup = BeautifulSoup(resp.text, "lxml")
            items = soup.find_all("div", {"class": "result"})
            if not items:
                break

            for item in items:
                if len(leads) >= max_results:
                    break
                lead = _parse_yp_result(item, query, location)
                if lead:
                    leads.append(lead)

            if not soup.find("a", {"class": "next ajax-page"}):
                break
            page += 1
            time.sleep(2)

        except Exception as e:
            logger.warning(f"Yellow Pages error: {e}")
            break

    logger.info(f"Yellow Pages: {len(leads)} leads for '{query}' in {location}")
    return leads


def _parse_yp_result(item, query: str, location: str) -> Dict | None:
    try:
        name_el = item.find("a", {"class": "business-name"})
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        phone_el = item.find("div", {"class": "phones phone primary"})
        phone = _clean_phone(phone_el.get_text(strip=True)) if phone_el else ""
        street_el = item.find("div", {"class": "street-address"})
        locality_el = item.find("div", {"class": "locality"})
        addr = ", ".join(filter(None, [
            street_el.get_text(strip=True) if street_el else "",
            locality_el.get_text(strip=True) if locality_el else location,
        ]))
        cats_el = item.find("div", {"class": "categories"})
        cats = cats_el.get_text(strip=True) if cats_el else ""
        return {
            "name": name, "phone": phone, "email": "", "company": name,
            "address": addr, "source": "yellow_pages",
            "notes": f"Yellow Pages: '{query}' in {location}. {cats}",
            "health_interest": _infer_interest(cats + " " + name),
        }
    except Exception:
        return None


def scrape_openstreetmap(query: str, location: str, max_results: int = 50) -> List[Dict]:
    """
    Scrape using Nominatim (OpenStreetMap) + Overpass API.
    100% free, no API key needed, no rate limiting issues.
    """
    try:
        import requests
    except ImportError:
        return []

    # Step 1: geocode the location to lat/lon
    try:
        geo_resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "json", "limit": 1},
            headers={"User-Agent": "VitalHealthGlobal-SalesAI/1.0"},
            timeout=10,
        )
        geo_data = geo_resp.json()
        if not geo_data:
            logger.error(f"Could not geocode location: {location}")
            return []
        lat = float(geo_data[0]["lat"])
        lon = float(geo_data[0]["lon"])
        # search radius ~25km
        bbox_delta = 0.25
        bbox = f"{lat-bbox_delta},{lon-bbox_delta},{lat+bbox_delta},{lon+bbox_delta}"
    except Exception as e:
        logger.error(f"Geocoding failed: {e}")
        return []

    # Step 2: map query to OSM tags
    osm_tags = _query_to_osm_tags(query)

    # Step 3: Overpass API query
    leads = []
    for tag in osm_tags:
        if len(leads) >= max_results:
            break
        overpass_query = f"""
[out:json][timeout:25];
(
  node[{tag}]({bbox});
  way[{tag}]({bbox});
);
out body;
"""
        try:
            resp = requests.post(
                "https://overpass-api.de/api/interpreter",
                data={"data": overpass_query},
                headers={"User-Agent": "VitalHealthGlobal-SalesAI/1.0"},
                timeout=30,
            )
            elements = resp.json().get("elements", [])

            for el in elements:
                if len(leads) >= max_results:
                    break
                tags = el.get("tags", {})
                name = tags.get("name", "")
                if not name:
                    continue
                phone = _clean_phone(tags.get("phone", tags.get("contact:phone", "")))
                addr_parts = [
                    tags.get("addr:housenumber", ""),
                    tags.get("addr:street", ""),
                    tags.get("addr:city", location),
                    tags.get("addr:state", ""),
                ]
                address = " ".join(filter(None, addr_parts)) or location
                website = tags.get("website", tags.get("contact:website", ""))
                leads.append({
                    "name": name,
                    "phone": phone,
                    "email": tags.get("email", tags.get("contact:email", "")),
                    "company": name,
                    "address": address,
                    "source": "openstreetmap",
                    "notes": (
                        f"OpenStreetMap: '{query}' in {location}. "
                        f"Website: {website or 'N/A'}"
                    ),
                    "health_interest": _infer_interest(
                        tags.get("amenity", "") + " " +
                        tags.get("leisure", "") + " " + name
                    ),
                })
            time.sleep(1)  # OSM rate limit courtesy

        except Exception as e:
            logger.warning(f"Overpass API error for tag '{tag}': {e}")

    logger.info(f"OpenStreetMap: {len(leads)} leads for '{query}' in {location}")
    return leads


def _query_to_osm_tags(query: str) -> List[str]:
    """Map a search query to OpenStreetMap tags."""
    q = query.lower()
    mappings = {
        "gym": ['"leisure"="fitness_centre"', '"leisure"="sports_centre"'],
        "fitness": ['"leisure"="fitness_centre"', '"sport"="fitness"'],
        "yoga": ['"leisure"="yoga"', '"amenity"="yoga_studio"'],
        "health food": ['"shop"="health_food"', '"shop"="organic"'],
        "supplement": ['"shop"="health_food"', '"shop"="nutrition"'],
        "vitamin": ['"shop"="health_food"'],
        "chiropractor": ['"healthcare"="chiropractor"'],
        "naturopath": ['"healthcare"="naturopath"', '"healthcare"="alternative"'],
        "massage": ['"amenity"="massage"', '"healthcare"="physiotherapist"'],
        "spa": ['"leisure"="spa"', '"amenity"="beauty"'],
        "wellness": ['"leisure"="fitness_centre"', '"healthcare"="alternative"'],
        "nutrition": ['"shop"="health_food"', '"amenity"="dietitian"'],
        "pilates": ['"leisure"="fitness_centre"', '"sport"="pilates"'],
        "acupuncture": ['"healthcare"="acupuncturist"'],
        "personal trainer": ['"leisure"="fitness_centre"'],
        "organic": ['"shop"="organic"', '"shop"="health_food"'],
    }
    for keyword, tags in mappings.items():
        if keyword in q:
            return tags
    return ['"shop"="health_food"', '"leisure"="fitness_centre"']


def _clean_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    return phone


def _infer_interest(text: str) -> str:
    text = text.lower()
    mappings = [
        (["gym", "fitness", "crossfit", "weightlift", "sport"], "V-NRGY energy, V-NITRO performance, VITALPRO protein"),
        (["yoga", "meditation", "pilates", "mindful"], "V-DAILY wellness, adaptogens"),
        (["chiropractic", "chiropractor"], "V-OMEGA 3 joint health, anti-inflammatory"),
        (["naturopath", "holistic", "alternative"], "full product line, V-GLUTATION PLUS"),
        (["health_food", "organic", "nutrition", "supplement", "vitamin"], "full product line, V-DAILY, VITALPRO"),
        (["spa", "beauty", "salon", "skin"], "VITALAGE COLLAGEN, V-GLUTATION PLUS"),
        (["massage", "physio", "therapy"], "V-OMEGA 3, muscle recovery"),
        (["acupuncture", "tcm"], "V-ORGANEX detox, herbal"),
    ]
    for keywords, interest in mappings:
        if any(k in text for k in keywords):
            return interest
    return "V-DAILY general wellness, VITALPRO nutrition"
