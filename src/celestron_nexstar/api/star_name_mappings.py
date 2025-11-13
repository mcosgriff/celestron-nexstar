"""
Star Name Mappings Module

Fetches and provides mappings from catalog numbers (e.g., HR numbers) to common star names.
This allows users to search for stars by their common names even though they're
stored in the database as catalog numbers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path

import aiohttp
from sqlalchemy.orm import Session

from .database_seeder import load_seed_json
from .models import StarNameMappingModel


logger = logging.getLogger(__name__)

# SIMBAD API base URL
SIMBAD_BASE_URL = "http://simbad.u-strasbg.fr/simbad/sim-id"
# VizieR catalog URL for HD-DM-GC-HR-HIP-Bayer-Flamsteed Cross Index
# This is a comprehensive cross-reference catalog
VIZIER_CATALOG_URL = "https://cdsarc.cds.unistra.fr/viz-bin/nph-Cat/txt?V/50"


async def _fetch_from_simbad(hr_numbers: list[int]) -> dict[int, tuple[str | None, str | None]]:
    """
    Fetch common names and Bayer designations from SIMBAD for a list of HR numbers.

    Args:
        hr_numbers: List of HR catalog numbers

    Returns:
        Dictionary mapping HR number to (common_name, bayer_designation) tuple
    """
    results: dict[int, tuple[str | None, str | None]] = {}

    try:
        async with aiohttp.ClientSession() as session:
            # SIMBAD allows batch queries using catalog identifiers
            # Format: query "HR 1708" or "HR 2491" etc.
            # We'll query in batches to avoid overwhelming the server
            batch_size = 10  # SIMBAD recommends small batches

            for i in range(0, len(hr_numbers), batch_size):
                batch = hr_numbers[i : i + batch_size]
                # Build query: "HR 1708|HR 2491|..."
                query_ids = "|".join(f"HR {hr}" for hr in batch)

                try:
                    params = {
                        "Ident": query_ids,
                        "output.format": "VOTable",  # VOTable is more structured
                    }

                    async with session.get(
                        SIMBAD_BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)
                    ) as response:
                        if response.status == 200:
                            # Parse VOTable response
                            # This is simplified - full VOTable parsing would be more robust
                            text = await response.text()
                            # Extract common names and Bayer designations from VOTable
                            # This is a simplified parser - may need refinement
                            for hr in batch:
                                # Look for common name patterns in the response
                                # SIMBAD returns names in various formats
                                pattern = rf"HR\s+{hr}.*?<TD>([^<]+)</TD>"
                                matches = re.findall(pattern, text, re.DOTALL)
                                if matches:
                                    # First match is usually the primary name
                                    name = matches[0].strip()
                                    # Check if it's a common name (not HR number itself)
                                    if name and not name.startswith("HR"):
                                        results[hr] = (name, None)  # Bayer designation parsing would go here
                        else:
                            logger.warning(f"SIMBAD query failed with status {response.status}")

                    # Be polite to SIMBAD server
                    await asyncio.sleep(0.5)  # Rate limiting

                except Exception as e:
                    logger.warning(f"Failed to query SIMBAD for batch {batch}: {e}")
                    continue

    except Exception as e:
        logger.warning(f"Failed to fetch from SIMBAD: {e}")

    return results


async def _fetch_from_yale_bsc() -> dict[int, tuple[str | None, str | None]]:
    """
    Extract common names from Yale Bright Star Catalog JSON if available.

    Returns:
        Dictionary mapping HR number to (common_name, bayer_designation) tuple
    """
    results: dict[int, tuple[str | None, str | None]] = {}

    try:
        # Check if Yale BSC JSON is already downloaded
        cache_path = Path("/tmp") / "yale_bsc.json"
        if not cache_path.exists():
            # Try to download it
            from ..cli.data_import import download_yale_bsc

            try:
                download_yale_bsc(cache_path)
            except Exception as e:
                logger.debug(f"Could not download Yale BSC: {e}")
                return results

        # Parse the JSON
        with open(cache_path, encoding="utf-8") as f:
            stars_data = json.load(f)

        # Extract common names if present in the data
        # The format may vary, so we check common field names
        for star in stars_data:
            hr_number = star.get("harvard_ref_#")
            if not hr_number:
                continue

            # Check for common name fields (field names may vary)
            common_name = None
            bayer = None

            # Common field names in various BSC formats
            for name_field in ["name", "proper_name", "common_name", "Name", "ProperName"]:
                value = star.get(name_field)
                if value:
                    value_str = str(value).strip()
                    if value_str and not value_str.startswith("HR"):
                        common_name = value_str
                        break

            # Check for Bayer designation
            for bayer_field in ["bayer", "Bayer", "bayer_designation", "Designation"]:
                value = star.get(bayer_field)
                if value:
                    bayer = str(value).strip()
                    break

            if common_name or bayer:
                results[hr_number] = (common_name, bayer)

    except Exception as e:
        logger.debug(f"Could not extract names from Yale BSC: {e}")

    return results


async def fetch_star_name_mappings(hr_numbers: list[int] | None = None) -> dict[int, tuple[str | None, str | None]]:
    """
    Fetch star name mappings from external sources.

    Tries multiple sources in order:
    1. Yale BSC JSON (if available)
    2. SIMBAD API (for specific HR numbers)

    Args:
        hr_numbers: Optional list of HR numbers to fetch. If None, tries to fetch
                    all available mappings from Yale BSC.

    Returns:
        Dictionary mapping HR number to (common_name, bayer_designation) tuple
    """
    results: dict[int, tuple[str | None, str | None]] = {}

    # First, try Yale BSC (fastest, most reliable)
    logger.info("Fetching star name mappings from Yale BSC...")
    yale_results = await _fetch_from_yale_bsc()
    results.update(yale_results)
    logger.info(f"Found {len(yale_results)} mappings in Yale BSC")

    # If specific HR numbers requested and not all found, try SIMBAD
    if hr_numbers:
        missing = [hr for hr in hr_numbers if hr not in results]
        if missing:
            logger.info(f"Fetching {len(missing)} missing mappings from SIMBAD...")
            simbad_results = await _fetch_from_simbad(missing)
            results.update(simbad_results)
            logger.info(f"Found {len(simbad_results)} additional mappings from SIMBAD")

    return results


def populate_star_name_mappings_database(
    db_session: Session, hr_numbers: list[int] | None = None, force_refresh: bool = False
) -> None:
    """
    Populate database with star name mappings.

    Uses seed data from JSON files as the primary source.
    Optionally enhances with additional mappings from external APIs/catalogs if available.
    This ensures star common names are always available even without internet connectivity.

    Args:
        db_session: SQLAlchemy database session
        hr_numbers: Optional list of HR numbers to fetch from external sources. If None, fetches all available.
        force_refresh: If True, re-populate even if data exists
    """
    from .database_seeder import seed_star_name_mappings

    logger.info("Populating star name mappings database...")

    # Seed from JSON file (primary source)
    seed_star_name_mappings(db_session, force=force_refresh)

    # Try to enhance with external sources (optional enhancement)
    try:
        logger.info("Attempting to fetch additional mappings from external sources...")
        # Run async function - this is a sync entry point, so asyncio.run() is safe
        external_mappings = asyncio.run(fetch_star_name_mappings(hr_numbers))
        if external_mappings:
            # Add any new mappings from external sources
            added = 0
            for hr_number, (common_name, bayer_designation) in external_mappings.items():
                # Check if already exists
                existing = (
                    db_session.query(StarNameMappingModel).filter(StarNameMappingModel.hr_number == hr_number).first()
                )
                if not existing:
                    model = StarNameMappingModel(
                        hr_number=hr_number,
                        common_name=common_name.strip() if common_name else "",
                        bayer_designation=bayer_designation.strip() if bayer_designation else None,
                    )
                    db_session.add(model)
                    added += 1
            if added > 0:
                db_session.commit()
                logger.info(f"Enhanced with {added} additional mappings from external sources")
            else:
                logger.info("External sources returned no additional mappings")
    except Exception as e:
        logger.warning(f"Could not fetch additional mappings from external sources: {e}")
        logger.info("Continuing with seed data only")


def _get_comprehensive_star_mappings() -> dict[int, tuple[str | None, str | None]]:
    """
    Comprehensive static mappings for commonly searched stars.

    This is the PRIMARY source for star name mappings. It includes all stars
    with IAU-approved proper names and commonly used names for bright stars.
    Source: IAU Working Group on Star Names, Bright Star Catalogue, and common usage.

    Loads data from seed JSON file instead of hardcoded dictionary.
    """
    try:
        # Load from seed data JSON file
        data = load_seed_json("star_name_mappings.json")

        # Convert JSON format to internal format
        # JSON format: [{"hr_number": int, "common_name": str, "bayer_designation": str}]
        # Internal format: {hr_number: (common_name, bayer_designation)}
        mappings: dict[int, tuple[str | None, str | None]] = {}
        for item in data:
            hr_number = item["hr_number"]
            common_name = item.get("common_name") or None
            bayer_designation = item.get("bayer_designation") or None
            mappings[hr_number] = (common_name, bayer_designation)

        return mappings
    except Exception as e:
        logger.error(f"Failed to load star name mappings from seed data: {e}")
        logger.warning("Falling back to empty mappings - star name search may be limited")
        return {}


def get_common_name_by_hr(db_session: Session, hr_number: int) -> str | None:
    """
    Get common name for a given HR number.

    Args:
        db_session: SQLAlchemy database session
        hr_number: HR catalog number

    Returns:
        Common name if found, None otherwise
    """
    mapping = db_session.query(StarNameMappingModel).filter(StarNameMappingModel.hr_number == hr_number).first()
    if mapping and mapping.common_name and mapping.common_name.strip():
        return mapping.common_name.strip()
    return None
