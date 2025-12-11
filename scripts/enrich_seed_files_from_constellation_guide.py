#!/usr/bin/env python3
"""
Enrich constellation and asterism seed files with data from Wikipedia.

This script:
1. Uses Wikipedia API to fetch detailed information
2. Removes fields that are already in GeoJSON files (position, geometry, etc.)
3. Enriches seed files with descriptions, mythology, cultural info, etc.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

try:
    import requests
    from bs4 import BeautifulSoup

    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False
    logger.warning("requests or beautifulsoup4 not available. Scraping will be disabled.")

# Wikipedia API endpoint
WIKIPEDIA_API_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"

# Headers for Wikipedia API (they're friendly to bots, but still good practice)
HEADERS = {
    "User-Agent": "CelestronNexStar/1.0 (https://github.com/yourusername/celestron-nexstar; contact@example.com)",
    "Accept": "application/json",
}

# Fields that come from GeoJSON files (should be removed from seed files)
# These are imported from constellations.min.geojson and constellations.bounds.min.geojson
# Note: We keep "name" in seed files for human readability and scraping, even though it's in GeoJSON
CONSTELLATION_GEOJSON_FIELDS = {
    # "name",  # Keep name for scraping and readability
    "abbreviation",  # 3-letter IAU code
    "ra_hours",  # Center RA
    "dec_degrees",  # Center Dec
    "ra_min_hours",  # Calculated from geometry
    "ra_max_hours",  # Calculated from geometry
    "dec_min_degrees",  # Calculated from geometry
    "dec_max_degrees",  # Calculated from geometry
    "area_sq_deg",  # From GeoJSON properties
    "season",  # May be in GeoJSON properties
    # Note: mythology might be in GeoJSON, but we'll keep it in seed if present
    # brightest_star is now a foreign key, not a string - keep magnitude in seed
}

# Fields that come from GeoJSON files (should be removed from seed files)
# These are imported from asterisms.min.geojson
# Note: We keep "name" in seed files for human readability and scraping, even though it's in GeoJSON
ASTERISM_GEOJSON_FIELDS = {
    # "name",  # Keep name for scraping and readability
    "ra_hours",  # Center RA
    "dec_degrees",  # Center Dec
    "size_degrees",  # Angular size
    "parent_constellation",  # Which constellation it's in
    "season",  # May be in GeoJSON properties
    # Note: stars list might be in GeoJSON, but we'll keep it in seed for explicit lists
}


def normalize_wikipedia_title(name: str) -> str:
    """Normalize constellation/asterism name for Wikipedia title."""
    # Wikipedia titles are case-sensitive and use underscores
    name = name.strip()
    # Remove "Constellation" suffix if present
    name = re.sub(r"\s+constellation$", "", name, flags=re.IGNORECASE)
    # Replace spaces with underscores (Wikipedia format)
    name = name.replace(" ", "_")
    return name


def get_wikipedia_api_url(title: str) -> str:
    """Get the Wikipedia API URL for a page."""
    normalized = normalize_wikipedia_title(title)
    # URL encode the title
    encoded = quote(normalized, safe="")
    return f"{WIKIPEDIA_API_URL}{encoded}"


def fetch_wikipedia_summary(title: str, session: requests.Session | None = None) -> dict[str, Any] | None:
    """Fetch Wikipedia page summary using the REST API.
    
    Args:
        title: Wikipedia page title
        session: Optional requests session for maintaining connection
    """
    url = get_wikipedia_api_url(title)
    try:
        logger.info(f"Fetching Wikipedia: {title}")
        if session:
            response = session.get(url, headers=HEADERS, timeout=10)
        else:
            response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch Wikipedia page for '{title}': {e}")
        return None


def fetch_wikipedia_html(title: str, session: requests.Session | None = None) -> BeautifulSoup | None:
    """Fetch full Wikipedia page HTML for parsing detailed content.
    
    Args:
        title: Wikipedia page title
        session: Optional requests session for maintaining connection
    """
    normalized = normalize_wikipedia_title(title)
    encoded = quote(normalized, safe="")
    url = f"https://en.wikipedia.org/api/rest_v1/page/html/{encoded}"
    try:
        if session:
            response = session.get(url, headers=HEADERS, timeout=10)
        else:
            response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch Wikipedia HTML for '{title}': {e}")
        return None


def extract_star_list_from_wikipedia(soup: BeautifulSoup) -> list[str]:
    """Extract list of star names from Wikipedia page.
    
    Looks for:
    - Tables with star information (most reliable)
    - Infobox data
    """
    stars: list[str] = []
    
    if not soup:
        return stars
    
    # Common star name patterns (proper names, typically capitalized)
    valid_star_name_pattern = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?$")
    
    # Look for tables with star data (often labeled "Stars" or "Notable stars")
    # Skip infobox tables (they have general info, not star lists)
    tables = soup.find_all("table", class_=re.compile("wikitable"))
    for table in tables:
        # Skip infobox tables entirely
        if "infobox" in table.get("class", []):
            continue
            
        # Check if table is about stars (must have "star" in caption)
        caption = table.find("caption")
        caption_text = ""
        if caption:
            caption_text = caption.get_text().lower()
        
        # Only process tables that are explicitly about stars
        # Must have "star" or "brightest" in caption, not just in headers
        if not ("star" in caption_text or "brightest" in caption_text):
            continue
        
        # Extract star names from table rows
        rows = table.find_all("tr")
        for row in rows[1:]:  # Skip header
            cells = row.find_all(["td", "th"])
            if cells:
                # First cell often contains star name
                star_cell = cells[0]
                # Get text from links first (more reliable), then fall back to cell text
                link = star_cell.find("a")
                if link:
                    star_name = link.get_text(strip=True)
                else:
                    star_name = star_cell.get_text(strip=True)
                
                # Clean up common prefixes/suffixes and Greek letters
                star_name = re.sub(r"^[αβγδεζηθικλμνξοπρστυφχψω]\s*", "", star_name, flags=re.IGNORECASE)
                star_name = re.sub(r"\s*\([^)]*\)$", "", star_name)  # Remove parenthetical notes
                star_name = re.sub(r"^\d+\s*", "", star_name)  # Remove leading numbers
                star_name = star_name.strip()
                
                # Validate it looks like a star name
                if star_name and valid_star_name_pattern.match(star_name) and len(star_name) < 30:
                    # Filter out common false positives and generic words
                    false_positives = {
                        "abbreviation", "genitive", "pronunciation", "symbolism", "declination", 
                        "quadrant", "area", "bayer", "bordering", "constellations", "borderingconstellations",
                        "proper", "name", "designation", "magnitude", "distance", 
                        "spectral", "type", "constellation", "night", "known", "as",
                        "and", "is", "the", "or", "in", "of", "to", "for", "with",
                        "luminous", "hot", "bright", "star", "stars", "first",
                        "second", "third", "fourth", "fifth", "right", "ascension",
                        "coordinates", "visible", "latitude", "between", "degrees"
                    }
                    star_lower = star_name.lower()
                    # Also check if it's a single common word that's not a star name
                    if (star_lower not in false_positives and 
                        not any(star_lower.startswith(fp) for fp in false_positives) and
                        len(star_name.split()) <= 2):  # Max 2 words for star names
                        stars.append(star_name)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_stars = []
    for star in stars:
        star_lower = star.lower()
        if star_lower not in seen:
            seen.add(star_lower)
            unique_stars.append(star)
    
    return unique_stars


def clean_html_text(html: str) -> str:
    """Remove HTML tags from text."""
    if not html:
        return ""
    # Simple HTML tag removal using regex (for basic cases)
    text = re.sub(r"<[^>]+>", "", html)
    # Decode HTML entities
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'")
    return text.strip()


def scrape_constellation_info(constellation_name: str, session: requests.Session | None = None) -> dict[str, Any]:
    """Fetch information about a constellation from Wikipedia."""
    # Try with "constellation" suffix first
    title = f"{constellation_name} (constellation)"
    data = fetch_wikipedia_summary(title, session=session)
    if not data or data.get("type") == "disambiguation":
        # Fallback to just the name
        title = constellation_name
        data = fetch_wikipedia_summary(title, session=session)
    
    if not data:
        return {}

    info: dict[str, Any] = {}

    # Extract description from extract or extract_html
    extract = data.get("extract", "")
    extract_html = data.get("extract_html", "")
    
    if extract:
        # Use plain text extract (first paragraph or two)
        info["description"] = extract[:500]  # Limit length
    
    # Get full Wikipedia URL
    content_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
    if content_url:
        info["wikipedia_url"] = content_url

    # Try to extract mythology from extract (basic keyword search)
    if extract:
        # Look for mythology-related keywords
        mythology_keywords = ["mythology", "myth", "legend", "story", "ancient", "greek", "roman"]
        extract_lower = extract.lower()
        for keyword in mythology_keywords:
            if keyword in extract_lower:
                # Try to extract a sentence or two around the keyword
                idx = extract_lower.find(keyword)
                if idx > 0:
                    # Get context around the keyword
                    start = max(0, idx - 200)
                    end = min(len(extract), idx + 500)
                    mythology_text = extract[start:end].strip()
                    if len(mythology_text) > 100:
                        info["mythology"] = mythology_text
                        break

    # Extract star list from full HTML page
    if SCRAPING_AVAILABLE:
        soup = fetch_wikipedia_html(title, session=session)
        if soup:
            stars = extract_star_list_from_wikipedia(soup)
            if stars:
                # Limit to reasonable number of stars (brightest/most notable)
                info["stars"] = ",".join(stars[:20])  # Top 20 stars

    return info


def scrape_asterism_info(asterism_name: str, session: requests.Session | None = None) -> dict[str, Any]:
    """Fetch information about an asterism from Wikipedia."""
    data = fetch_wikipedia_summary(asterism_name, session=session)
    
    if not data:
        return {}

    info: dict[str, Any] = {}

    # Extract description from extract
    extract = data.get("extract", "")
    
    if extract:
        # Use plain text extract (first paragraph or two)
        info["description"] = extract[:500]  # Limit length
    
    # Get full Wikipedia URL
    content_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
    if content_url:
        info["wikipedia_url"] = content_url

    # Try to extract cultural/guidepost/historical info from extract (basic keyword search)
    if extract:
        extract_lower = extract.lower()
        
        # Cultural info
        cultural_keywords = ["cultural", "culture", "tradition", "known as", "called"]
        for keyword in cultural_keywords:
            if keyword in extract_lower:
                idx = extract_lower.find(keyword)
                if idx > 0:
                    start = max(0, idx - 100)
                    end = min(len(extract), idx + 400)
                    cultural_text = extract[start:end].strip()
                    if len(cultural_text) > 50:
                        info["cultural_info"] = cultural_text
                        break
        
        # Guidepost/navigation info
        guidepost_keywords = ["guidepost", "navigation", "finding", "locate", "points to", "used to find"]
        for keyword in guidepost_keywords:
            if keyword in extract_lower:
                idx = extract_lower.find(keyword)
                if idx > 0:
                    start = max(0, idx - 100)
                    end = min(len(extract), idx + 400)
                    guidepost_text = extract[start:end].strip()
                    if len(guidepost_text) > 50:
                        info["guidepost_info"] = guidepost_text
                        break
        
        # Historical notes
        historical_keywords = ["history", "historical", "ancient", "mentioned", "first"]
        for keyword in historical_keywords:
            if keyword in extract_lower:
                idx = extract_lower.find(keyword)
                if idx > 0:
                    start = max(0, idx - 100)
                    end = min(len(extract), idx + 400)
                    historical_text = extract[start:end].strip()
                    if len(historical_text) > 50:
                        info["historical_notes"] = historical_text
                        break
        
        # Shape description
        shape_keywords = ["shape", "appearance", "looks like", "forms", "pattern"]
        for keyword in shape_keywords:
            if keyword in extract_lower:
                idx = extract_lower.find(keyword)
                if idx > 0:
                    start = max(0, idx - 100)
                    end = min(len(extract), idx + 300)
                    shape_text = extract[start:end].strip()
                    if len(shape_text) > 50:
                        info["shape_description"] = shape_text
                        break

    # Extract/update star list from full HTML page if not already present
    if SCRAPING_AVAILABLE:
        soup = fetch_wikipedia_html(asterism_name, session=session)
        if soup:
            stars = extract_star_list_from_wikipedia(soup)
            if stars:
                # Only update if we found stars and don't already have a good list
                if "stars" not in info or not info.get("stars"):
                    info["stars"] = ",".join(stars[:15])  # Top 15 stars for asterisms

    return info


def clean_seed_file(data: list[dict[str, Any]], geojson_fields: set[str]) -> list[dict[str, Any]]:
    """Remove fields that are already in GeoJSON files."""
    cleaned = []
    for item in data:
        cleaned_item = {k: v for k, v in item.items() if k not in geojson_fields}
        cleaned.append(cleaned_item)
    return cleaned


def enrich_constellations(
    constellations: list[dict[str, Any]], output_path: Path, scrape: bool = True
) -> None:
    """Enrich constellation seed file with data from Wikipedia."""
    logger.info(f"Processing {len(constellations)} constellations...")

    if scrape and not SCRAPING_AVAILABLE:
        logger.warning("Scraping requested but dependencies not available. Skipping scraping.")
        scrape = False

    # Use a session for connection pooling (Wikipedia API is friendly to bots)
    session = requests.Session() if scrape and SCRAPING_AVAILABLE else None

    enriched = []
    for idx, const in enumerate(constellations, 1):
        name = const.get("name", "")
        logger.info(f"[{idx}/{len(constellations)}] Processing {name}...")

        # Start with cleaned data (remove GeoJSON fields, but keep 'name' for scraping)
        enriched_const = clean_seed_file([const], CONSTELLATION_GEOJSON_FIELDS)[0]

        if scrape and SCRAPING_AVAILABLE:
            # Scrape additional info
            scraped_info = scrape_constellation_info(name, session=session)
            # Merge scraped info, but don't overwrite existing non-empty values
            # Exception: always update 'stars' field if we got better data from Wikipedia
            for key, value in scraped_info.items():
                if key == "stars" and value:
                    # Always update stars field if we got data from Wikipedia
                    enriched_const[key] = value
                elif key not in enriched_const or not enriched_const.get(key):
                    enriched_const[key] = value

            # Be polite - rate limit (Wikipedia allows reasonable use, but still be respectful)
            time.sleep(0.5)  # Wikipedia API is more permissive

        enriched.append(enriched_const)
    
    if session:
        session.close()

    # Write enriched data
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    logger.info(f"Wrote enriched constellations to {output_path}")


def enrich_asterisms(asterisms: list[dict[str, Any]], output_path: Path, scrape: bool = True) -> None:
    """Enrich asterism seed file with data from Wikipedia."""
    logger.info(f"Processing {len(asterisms)} asterisms...")

    if scrape and not SCRAPING_AVAILABLE:
        logger.warning("Scraping requested but dependencies not available. Skipping scraping.")
        scrape = False

    # Use a session for connection pooling (Wikipedia API is friendly to bots)
    session = requests.Session() if scrape and SCRAPING_AVAILABLE else None

    enriched = []
    for idx, asterism in enumerate(asterisms, 1):
        name = asterism.get("name", "")
        logger.info(f"[{idx}/{len(asterisms)}] Processing {name}...")

        # Start with cleaned data (remove GeoJSON fields, but keep 'name' for scraping)
        enriched_asterism = clean_seed_file([asterism], ASTERISM_GEOJSON_FIELDS)[0]

        if scrape and SCRAPING_AVAILABLE:
            # Scrape additional info
            scraped_info = scrape_asterism_info(name, session=session)
            # Merge scraped info, but don't overwrite existing non-empty values
            # Exception: always update 'stars' field if we got better data from Wikipedia
            for key, value in scraped_info.items():
                if key == "stars" and value:
                    # Always update stars field if we got data from Wikipedia
                    enriched_asterism[key] = value
                elif key not in enriched_asterism or not enriched_asterism.get(key):
                    enriched_asterism[key] = value

            # Be polite - rate limit (Wikipedia allows reasonable use, but still be respectful)
            time.sleep(0.5)  # Wikipedia API is more permissive

        enriched.append(enriched_asterism)
    
    if session:
        session.close()

    # Write enriched data
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    logger.info(f"Wrote enriched asterisms to {output_path}")


def main() -> None:
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Enrich seed files from constellation-guide.com")
    parser.add_argument(
        "--no-scrape",
        action="store_true",
        help="Only clean existing files (remove GeoJSON fields), don't scrape new data",
    )
    parser.add_argument(
        "--constellations-only",
        action="store_true",
        help="Only process constellations",
    )
    parser.add_argument(
        "--asterisms-only",
        action="store_true",
        help="Only process asterisms",
    )

    args = parser.parse_args()

    # Find seed files
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    seed_dir = project_root / "src" / "celestron_nexstar" / "cli" / "data" / "seed"

    constellations_path = seed_dir / "constellations.json"
    asterisms_path = seed_dir / "asterisms.json"

    # Process constellations
    if not args.asterisms_only:
        if constellations_path.exists():
            with open(constellations_path, encoding="utf-8") as f:
                constellations = json.load(f)

            enrich_constellations(
                constellations,
                constellations_path,
                scrape=not args.no_scrape,
            )
        else:
            logger.warning(f"Constellations file not found: {constellations_path}")

    # Process asterisms
    if not args.constellations_only:
        if asterisms_path.exists():
            with open(asterisms_path, encoding="utf-8") as f:
                asterisms = json.load(f)

            enrich_asterisms(
                asterisms,
                asterisms_path,
                scrape=not args.no_scrape,
            )
        else:
            logger.warning(f"Asterisms file not found: {asterisms_path}")


if __name__ == "__main__":
    main()

