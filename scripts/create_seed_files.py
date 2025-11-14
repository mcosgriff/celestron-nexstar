#!/usr/bin/env python3
"""
Script to extract static data from Python files and create JSON seed files.

This script reads the static data structures from Python modules and converts
them to JSON format for database seeding.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import models and data
from celestron_nexstar.api.constellations import PROMINENT_CONSTELLATIONS, FAMOUS_ASTERISMS
from celestron_nexstar.api.meteor_showers import METEOR_SHOWERS
from celestron_nexstar.api.space_events import SPACE_EVENTS_2025


def create_constellations_json():
    """Create constellations.json from PROMINENT_CONSTELLATIONS."""
    constellations = []
    for c in PROMINENT_CONSTELLATIONS:
        # Calculate boundaries (simplified - use center +/- area estimate)
        area_deg = c.area_sq_deg
        ra_span = (area_deg ** 0.5) / 15.0  # Approximate RA span in hours
        dec_span = (area_deg ** 0.5)  # Approximate Dec span in degrees

        constellations.append({
            "name": c.name,
            "abbreviation": c.abbreviation,
            "common_name": None,
            "ra_hours": c.ra_hours,
            "dec_degrees": c.dec_degrees,
            "ra_min_hours": max(0, c.ra_hours - ra_span / 2),
            "ra_max_hours": min(24, c.ra_hours + ra_span / 2),
            "dec_min_degrees": max(-90, c.dec_degrees - dec_span / 2),
            "dec_max_degrees": min(90, c.dec_degrees + dec_span / 2),
            "area_sq_deg": c.area_sq_deg,
            "brightest_star": c.brightest_star,
            "mythology": None,
            "season": c.season,
        })
    return constellations


def create_asterisms_json():
    """Create asterisms.json from FAMOUS_ASTERISMS."""
    asterisms = []
    for a in FAMOUS_ASTERISMS:
        asterisms.append({
            "name": a.name,
            "alt_names": ",".join(a.alt_names) if a.alt_names else None,
            "ra_hours": a.ra_hours,
            "dec_degrees": a.dec_degrees,
            "size_degrees": a.size_degrees,
            "parent_constellation": a.parent_constellation,
            "description": a.description,
            "stars": ",".join(a.member_stars) if a.member_stars else None,
            "season": a.season,
        })
    return asterisms


def create_meteor_showers_json():
    """Create meteor_showers.json from METEOR_SHOWERS."""
    showers = []
    for s in METEOR_SHOWERS:
        showers.append({
            "name": s.name,
            "code": None,
            "start_month": s.activity_start_month,
            "start_day": s.activity_start_day,
            "end_month": s.activity_end_month,
            "end_day": s.activity_end_day,
            "peak_month": s.peak_month,
            "peak_day": s.peak_day,
            "radiant_ra_hours": s.radiant_ra_hours,
            "radiant_dec_degrees": s.radiant_dec_degrees,
            "radiant_constellation": None,
            "zhr_peak": s.zhr_peak,
            "velocity_km_s": float(s.velocity_km_s),
            "parent_comet": s.parent_comet,
            "best_time": None,  # Extract from description if needed
            "notes": s.description,
        })
    return showers


def create_dark_sky_sites_json():
    """Update dark_sky_sites.json with geohashes if missing."""
    from celestron_nexstar.api.database_seeder import get_seed_data_path
    from celestron_nexstar.api.geohash_utils import encode

    # Load existing JSON file (source of truth)
    seed_dir = get_seed_data_path()
    json_path = seed_dir / "dark_sky_sites.json"

    if not json_path.exists():
        print(f"Warning: {json_path} does not exist. Cannot update geohashes.")
        return []

    with open(json_path, encoding="utf-8") as f:
        sites = json.load(f)

    # Update geohashes if missing
    for site in sites:
        if not site.get("geohash"):
            # Calculate geohash for spatial indexing (precision 9 for ~5m accuracy)
            site["geohash"] = encode(site["latitude"], site["longitude"], precision=9)

    return sites


def create_space_events_json():
    """Create space_events.json from SPACE_EVENTS_2025."""
    events = []
    for event in SPACE_EVENTS_2025:
        req = event.viewing_requirements
        events.append({
            "name": event.name,
            "event_type": event.event_type.value if hasattr(event.event_type, "value") else str(event.event_type),
            "date": event.date.isoformat(),
            "description": event.description,
            "min_latitude": req.min_latitude,
            "max_latitude": req.max_latitude,
            "min_longitude": req.min_longitude,
            "max_longitude": req.max_longitude,
            "dark_sky_required": req.dark_sky_required,
            "min_bortle_class": req.min_bortle_class,
            "equipment_needed": req.equipment_needed,
            "viewing_notes": req.notes,
            "source": event.source,
            "url": event.url,
        })
    return events


def main():
    """Create all seed JSON files."""
    seed_dir = Path(__file__).parent.parent / "src" / "celestron_nexstar" / "cli" / "data" / "seed"
    seed_dir.mkdir(parents=True, exist_ok=True)

    print("Creating seed JSON files...")

    # Create each JSON file
    files = {
        "constellations.json": create_constellations_json,
        "asterisms.json": create_asterisms_json,
        "meteor_showers.json": create_meteor_showers_json,
        "dark_sky_sites.json": create_dark_sky_sites_json,
        "space_events.json": create_space_events_json,
    }

    for filename, create_func in files.items():
        try:
            data = create_func()
            filepath = seed_dir / filename
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"  ✓ Created {filename} ({len(data)} records)")
        except Exception as e:
            print(f"  ✗ Failed to create {filename}: {e}")
            import traceback
            traceback.print_exc()

    print("\nDone!")


if __name__ == "__main__":
    main()
