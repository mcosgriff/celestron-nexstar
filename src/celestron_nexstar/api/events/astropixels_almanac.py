"""
AstroPixels Almanac Parser

Parses astronomical events from the AstroPixels Sky Event Almanac.
Fetches and caches events from https://astropixels.com/almanac/
"""

from __future__ import annotations

import html as html_module
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import requests
from bs4 import BeautifulSoup


if TYPE_CHECKING:
    from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

__all__ = [
    "AstroPixelsEvent",
    "cache_astropixels_events",
    "fetch_and_parse_almanac",
    "get_cached_astropixels_events",
]


@dataclass
class AstroPixelsEvent:
    """An astronomical event from AstroPixels almanac."""

    date: datetime  # UTC datetime
    event_name: str
    event_type: str  # "moon_phase", "meteor_shower", "lunar_eclipse", "solar_eclipse", "planetary_opposition", "solstice", "equinox", etc.
    description: str
    time_str: str | None = None  # Original time string from almanac
    local_date: datetime | None = None  # Original local date (before UTC conversion) for calendar grouping


# Map timezone abbreviations to UTC offsets
TIMEZONE_OFFSETS = {
    "EST": -5,  # Eastern Standard Time
    "CST": -6,  # Central Standard Time
    "MST": -7,  # Mountain Standard Time
    "PST": -8,  # Pacific Standard Time
    "AKST": -9,  # Alaskan Standard Time
    "HST": -10,  # Hawaiian Standard Time
    "AST": -4,  # Atlantic Standard Time
    "ART": -3,  # Argentina Time
}


def _parse_time_string(time_str: str, date: datetime, tz_offset: int) -> datetime:
    """
    Parse time string from almanac (e.g., "12:34" or "12:34 AM") and convert to UTC.

    Args:
        time_str: Time string from almanac
        date: Date for the event
        tz_offset: Timezone offset in hours from UTC

    Returns:
        datetime in UTC
    """
    time_str = time_str.strip()

    # Handle "hh:mm" format
    if re.match(r"^\d{1,2}:\d{2}$", time_str):
        hour, minute = map(int, time_str.split(":"))
        # Assume 24-hour format if hour > 12, otherwise assume PM if not specified
        dt = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # Handle "hh:mm AM/PM" format
    am_pm_match = re.match(r"^(\d{1,2}:\d{2})\s*(AM|PM)$", time_str, re.IGNORECASE)
    if am_pm_match:
        time_part, am_pm = am_pm_match.groups()
        hour, minute = map(int, time_part.split(":"))
        if am_pm.upper() == "PM" and hour != 12:
            hour += 12
        elif am_pm.upper() == "AM" and hour == 12:
            hour = 0
        dt = date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    else:
        # No time specified, use noon
        dt = date.replace(hour=12, minute=0, second=0, microsecond=0)

    # Convert from local timezone to UTC
    dt_local = dt.replace(tzinfo=None)  # Assume local time
    # Apply timezone offset
    dt_utc = dt_local - timedelta(hours=tz_offset)
    return dt_utc.replace(tzinfo=UTC)


def _parse_date_from_row(row_text: str, year: int) -> datetime | None:
    """
    Parse date from table row text.

    Args:
        row_text: Text from table row
        year: Year for the events

    Returns:
        datetime or None if parsing fails
    """
    # Look for date patterns like "Jan 1", "January 1", "1/1", "Jan. 1", etc.
    date_patterns = [
        r"(\w+\.?)\s+(\d{1,2})",  # "Jan 1" or "Jan. 1" or "January 1"
        r"(\d{1,2})/(\d{1,2})",  # "1/1"
        r"(\d{1,2})-(\d{1,2})",  # "1-1" (alternative format)
    ]

    month_names = {
        "jan": 1,
        "january": 1,
        "jan.": 1,
        "feb": 2,
        "february": 2,
        "feb.": 2,
        "mar": 3,
        "march": 3,
        "mar.": 3,
        "apr": 4,
        "april": 4,
        "apr.": 4,
        "may": 5,
        "may.": 5,
        "jun": 6,
        "june": 6,
        "jun.": 6,
        "jul": 7,
        "july": 7,
        "jul.": 7,
        "aug": 8,
        "august": 8,
        "aug.": 8,
        "sep": 9,
        "september": 9,
        "sep.": 9,
        "sept": 9,
        "sept.": 9,
        "oct": 10,
        "october": 10,
        "oct.": 10,
        "nov": 11,
        "november": 11,
        "nov.": 11,
        "dec": 12,
        "december": 12,
        "dec.": 12,
    }

    # Clean up the text - remove extra whitespace
    row_text = re.sub(r"\s+", " ", row_text.strip())

    for pattern in date_patterns:
        match = re.search(pattern, row_text, re.IGNORECASE)
        if match:
            if "/" in match.group(0) or "-" in match.group(0):
                # "1/1" or "1-1" format
                try:
                    month, day = map(int, match.groups())
                except ValueError:
                    continue
            else:
                # "Jan 1" format
                groups = match.groups()
                if len(groups) < 2:
                    continue
                month_str = str(groups[0]).strip().rstrip(".")
                day_str = str(groups[1]).strip()
                month_num = month_names.get(month_str.lower())
                if month_num is None:
                    continue
                month = month_num
                try:
                    day = int(day_str)
                except ValueError:
                    continue

            try:
                return datetime(year, month, day, tzinfo=UTC)
            except ValueError:
                continue

    return None


def _classify_event_type(event_name: str) -> str:
    """Classify event type based on event name."""
    event_lower = event_name.lower()

    # Moon phases
    if "full moon" in event_lower or "new moon" in event_lower or "quarter" in event_lower:
        return "moon_phase"

    # Meteor showers
    elif "meteor" in event_lower or "shower" in event_lower:
        return "meteor_shower"

    # Eclipses
    elif "lunar eclipse" in event_lower or ("eclipse" in event_lower and "lunar" in event_lower):
        return "lunar_eclipse"
    elif "solar eclipse" in event_lower or ("eclipse" in event_lower and "solar" in event_lower):
        return "solar_eclipse"

    # Solstices and equinoxes
    elif "solstice" in event_lower:
        return "solstice"
    elif "equinox" in event_lower:
        return "equinox"

    # Moon positions
    elif "perigee" in event_lower:
        return "moon_perigee"
    elif "apogee" in event_lower:
        return "moon_apogee"

    # Planetary positions
    elif "perihelion" in event_lower:
        return "planetary_perihelion"
    elif "aphelion" in event_lower:
        return "planetary_aphelion"
    elif "inferior conjunction" in event_lower:
        return "planetary_inferior_conjunction"
    elif "superior conjunction" in event_lower:
        return "planetary_superior_conjunction"
    elif "greatest elongation" in event_lower or "elongation" in event_lower:
        return "planetary_elongation"
    elif "opposition" in event_lower:
        return "planetary_opposition"

    # Conjunctions (general)
    elif "conjunction" in event_lower:
        return "conjunction"

    # Occultations
    elif "occn" in event_lower or "occultation" in event_lower or "occults" in event_lower:
        return "occultation"

    # Moon nodes
    elif "ascending node" in event_lower:
        return "moon_ascending_node"
    elif "descending node" in event_lower:
        return "moon_descending_node"

    # Star positions (Pleiades, Aldebaran, Pollux, Regulus, Spica, Antares)
    # Check for star names in the event (e.g., "Pleiades 0.8°S of Moon" or "Pollux 2.9°N of Moon")
    elif any(star in event_lower for star in ["pleiades", "aldebaran", "pollux", "regulus", "spica", "antares"]):
        return "star_position"

    # Planetary conjunctions with Moon or other objects
    # Patterns like "Jupiter 3.7°S of Moon", "Venus 1.4°N of Moon", "Mars 0.2°S of Moon"
    # These are conjunctions, not just planetary positions
    elif any(
        planet in event_lower for planet in ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"]
    ):
        # Check if it's a conjunction pattern (e.g., "Jupiter X°S of Moon" or "Venus X°N of Moon")
        if "of moon" in event_lower or "of sun" in event_lower or "°n of" in event_lower or "°s of" in event_lower:
            return "conjunction"
        # Otherwise, it's a general planetary event
        else:
            return "planetary_opposition"  # Default for planetary events

    else:
        return "other"


def fetch_and_parse_almanac(year: int, timezone: str = "MST") -> list[AstroPixelsEvent]:
    """
    Fetch and parse AstroPixels almanac for a given year and timezone.

    Args:
        year: Year to fetch (e.g., 2025)
        timezone: Timezone abbreviation (EST, CST, MST, PST, etc.)

    Returns:
        List of parsed events
    """
    tz_offset = TIMEZONE_OFFSETS.get(timezone.upper(), -7)  # Default to MST

    # Construct URL
    url = f"https://astropixels.com/almanac/almanac21/almanac{year}{timezone.lower()}.html"

    events: list[AstroPixelsEvent] = []

    try:
        # Set headers to avoid HTTP 406 errors
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            logger.error(f"Failed to fetch almanac: HTTP {response.status_code} for {url}")
            return events

        html = response.text
        # Sanitize broken numeric character refs like "&#176E" -> "&#176;E" to avoid parser errors
        html = re.sub(r"&#176([A-Za-z])", r"&#176;\1", html)
        soup = BeautifulSoup(html, "html.parser")

        # Find the main table with events
        # The almanac table has class "datatab" and contains <pre> tags with the data
        main_table = soup.find("table", class_="datatab")
        if not main_table:
            # Fallback: try to find any table with pre tags
            tables = soup.find_all("table")
            for table in tables:
                pre_tags = table.find_all("pre")
                if pre_tags:
                    main_table = table
                    logger.debug("Found table with <pre> tags")
                    break

        if not main_table:
            logger.warning(
                "Could not find almanac table (looking for table with class 'datatab' or containing <pre> tags)"
            )
            return events

        logger.info("Found almanac table with pre-formatted data")

        # Parse the <pre> tags inside table cells
        # The data is in pre-formatted text blocks, one per table cell (column)
        pre_tags = main_table.find_all("pre")

        if not pre_tags:
            logger.warning("No <pre> tags found in almanac table")
            return events

        logger.info(f"Found {len(pre_tags)} pre-formatted data blocks")

        # Parse each pre block (each represents a time period, e.g., Jan-Jun, Jul-Dec)
        for pre_block in pre_tags:
            # Get text and decode HTML entities to preserve special characters like °
            # Use get_text with separator to preserve line structure
            pre_text = pre_block.get_text(separator="\n", strip=False)
            # Decode HTML entities if any (BeautifulSoup should handle this, but ensure UTF-8)
            pre_text = html_module.unescape(pre_text)
            lines = pre_text.split("\n")

            logger.debug(f"Parsing pre block with {len(lines)} lines")

            # Skip header lines
            current_month = None
            lines_processed = 0
            skipped_lines = []  # Track skipped lines for debugging
            for line in lines:
                original_line = line  # Keep original for debugging (before stripping)
                # Don't strip yet - we need leading spaces for continuation lines
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                # Use original_line for parsing, but line_stripped for checks
                line = original_line

                # Skip header lines (use stripped version for checks)
                if (
                    line_stripped.lower().startswith("date")
                    or line_stripped.lower().startswith("(h:m)")
                    or "sky event" in line_stripped.lower()
                ):
                    continue

                # Parse line format: "Jan 03  08:24  Venus 1.4°N of Moon"
                # Or: "    03  08     Quadrantid Meteor Shower" (continued from previous month)
                # Pattern: Optional month abbreviation, day, time, event

                # Check if line starts with month abbreviation (use stripped version)
                month_match = re.match(r"^([A-Z][a-z]{2})\s+(\d{1,2})", line_stripped)
                if month_match:
                    month_str, day_str = month_match.groups()
                    # Update current month
                    month_names = {
                        "jan": 1,
                        "feb": 2,
                        "mar": 3,
                        "apr": 4,
                        "may": 5,
                        "jun": 6,
                        "jul": 7,
                        "aug": 8,
                        "sep": 9,
                        "oct": 10,
                        "nov": 11,
                        "dec": 12,
                    }
                    current_month = month_names.get(month_str.lower())
                    if not current_month:
                        continue
                    day = int(day_str)
                    # Extract time and event from rest of line (use original line to preserve spacing)
                    # Find the position in original line
                    month_pos = line.find(month_str + " " + day_str)
                    if month_pos >= 0:
                        rest = line[month_pos + month_match.end() :].strip()
                    else:
                        # Fallback to stripped version
                        rest = line_stripped[month_match.end() :].strip()
                else:
                    # Line continues from previous month (starts with spaces and day)
                    # Match lines like "    04  16:14  FULL MOON" or "    04  04:06  Moon at Perigee"
                    # The line might have leading spaces, then day, then spaces, then time/event
                    # Try with leading spaces first (most common case)
                    # Use original_line here since line might have been stripped
                    day_match = re.match(r"^\s+(\d{1,2})\s+(.+)", original_line)
                    if day_match and current_month:
                        day = int(day_match.group(1))
                        rest = day_match.group(2).strip()  # Get everything after day
                    else:
                        # Try without leading spaces (in case line was already stripped)
                        day_match = re.match(r"^(\d{1,2})\s+(.+)", line_stripped)
                        if day_match and current_month:
                            day = int(day_match.group(1))
                            rest = day_match.group(2).strip()
                        else:
                            # If we can't parse and don't have a current_month, skip
                            if current_month is None:
                                skipped_lines.append(f"No current_month: {original_line[:100]}")
                                continue
                            # If we have a current_month but can't parse, log it for debugging
                            skipped_lines.append(
                                f"Could not parse (current_month={current_month}): {original_line[:100]}"
                            )
                            logger.debug(
                                f"Could not parse line (no month match, current_month={current_month}): {original_line[:100]}"
                            )
                            continue

                # Parse time and event from rest of line
                # Format: "08:24  Event" or "08     Event" (hours only) or just "Event" (no time)
                # The time might have multiple spaces before the event
                # Try to match time with colon first (e.g., "16:14  FULL MOON")
                # Use \s+ to match one or more spaces between time and event
                time_match = re.match(r"(\d{1,2}):(\d{2})\s+(.+)", rest)
                if time_match:
                    hour_str, minute_str, event_text = time_match.groups()
                    hour = int(hour_str)
                    minute = int(minute_str)
                    event_name = event_text.strip()
                else:
                    # Try to match time without colon (hours only, e.g., "08     Event")
                    # Match one or more spaces between hour and event
                    hour_match = re.match(r"(\d{1,2})\s+(.+)", rest)
                    if hour_match:
                        hour_str, event_text = hour_match.groups()
                        hour = int(hour_str)
                        minute = 0
                        event_name = event_text.strip()
                    else:
                        # No time, just event - but check if rest starts with a number (might be a time)
                        # If rest is just whitespace or empty, skip
                        if not rest or not rest.strip():
                            logger.debug(f"Skipping line with empty event text: {line[:100]}")
                            continue
                        # No time, just event
                        event_name = rest.strip()
                        hour = 12  # Default to noon
                        minute = 0

                if not event_name:
                    continue

                # Skip if event name looks like it's just whitespace or a number
                if not event_name or event_name.isdigit():
                    continue

                # Create datetime in local timezone first
                try:
                    # Create datetime in the almanac's timezone (timezone-naive, represents local time)
                    event_date_local = datetime(year, current_month, day, hour, minute, tzinfo=None)
                    # Convert to UTC for storage, but keep local date for calendar grouping
                    event_date_utc = event_date_local - timedelta(hours=tz_offset)
                    event_date_utc = event_date_utc.replace(tzinfo=UTC)
                except ValueError:
                    logger.debug(f"Invalid date: {year}-{current_month}-{day}")
                    continue

                event_type = _classify_event_type(event_name)
                time_str = f"{hour:02d}:{minute:02d}" if minute > 0 else f"{hour:02d}"

                # Debug logging for FULL MOON events
                if "FULL MOON" in event_name.upper() or "full moon" in event_name.lower():
                    logger.debug(
                        f"Parsed FULL MOON: {event_name}, date_local={event_date_local}, "
                        f"date_utc={event_date_utc}, type={event_type}"
                    )

                event = AstroPixelsEvent(
                    date=event_date_utc,  # Store in UTC
                    event_name=event_name,
                    event_type=event_type,
                    description=event_name,
                    time_str=time_str,
                    local_date=event_date_local,  # Keep original local date for calendar grouping
                )

                events.append(event)
                lines_processed += 1

                # Debug logging for December events
                if current_month == 12:
                    logger.debug(f"December event: {day:02d} {hour:02d}:{minute:02d} - {event_name}")

            logger.debug(f"Processed {lines_processed} events from this pre block")

        logger.info(f"Parsed {len(events)} events from pre-formatted data")

        # Count December events and log them
        december_events_list = [e for e in events if e.local_date and e.local_date.month == 12]
        december_count = len(december_events_list)
        if december_count > 0:
            logger.info(f"Found {december_count} events in December")
            # Log all December events for debugging
            for e in sorted(december_events_list, key=lambda x: x.local_date.day if x.local_date else 0):
                if e.local_date:
                    logger.debug(f"  Dec {e.local_date.day:02d} {e.event_name}")

        logger.info(f"Parsed {len(events)} events from AstroPixels almanac for {year}")

    except TimeoutError:
        logger.error(f"Timeout fetching almanac from {url}")
    except Exception as e:
        logger.error(f"Error fetching/parsing almanac: {e}", exc_info=True)

    return events


def cache_astropixels_events(db_session: Session, year: int, timezone: str = "MST", force_refresh: bool = False) -> int:
    """
    Fetch and cache AstroPixels events in the database.

    Args:
        db_session: Database session
        year: Year to fetch
        timezone: Timezone abbreviation
        force_refresh: Force refresh even if events already exist

    Returns:
        Number of events cached
    """
    from sqlalchemy import delete, select

    from celestron_nexstar.api.database.models import SpaceEventModel

    # Check if events already exist
    if not force_refresh:
        from sqlalchemy import func

        count = db_session.scalar(
            select(func.count(SpaceEventModel.id)).where(
                SpaceEventModel.source == "AstroPixels",
                SpaceEventModel.date >= datetime(year, 1, 1, tzinfo=UTC),
                SpaceEventModel.date < datetime(year + 1, 1, 1, tzinfo=UTC),
            )
        )
        if count and count > 0:
            logger.info(f"AstroPixels events for {year} already cached ({count} events)")
            return count

    # Fetch events
    events = fetch_and_parse_almanac(year, timezone)

    if not events:
        logger.warning(f"No events found for {year}")
        return 0

    # Delete existing events for this year if forcing refresh
    if force_refresh:
        db_session.execute(
            delete(SpaceEventModel).where(
                SpaceEventModel.source == "AstroPixels",
                SpaceEventModel.date >= datetime(year, 1, 1, tzinfo=UTC),
                SpaceEventModel.date < datetime(year + 1, 1, 1, tzinfo=UTC),
            )
        )
        db_session.commit()  # Commit the delete before adding new events
        logger.info(f"Deleted existing AstroPixels events for {year} (force_refresh=True)")

    # Store events
    added = 0
    skipped = 0
    updated = 0
    for event in events:
        # Check if event already exists (by name and date)
        existing = db_session.scalar(
            select(SpaceEventModel)
            .where(
                SpaceEventModel.source == "AstroPixels",
                SpaceEventModel.name == event.event_name,
                SpaceEventModel.date == event.date,
            )
            .limit(1)
        )

        if not existing:
            # Ensure text is properly encoded (UTF-8) to preserve special characters
            event_name = event.event_name.encode("utf-8", errors="replace").decode("utf-8")
            event_description = event.description.encode("utf-8", errors="replace").decode("utf-8")

            db_event = SpaceEventModel(
                name=event_name,
                event_type=event.event_type,
                date=event.date,
                description=event_description,
                source="AstroPixels",
                url=f"https://astropixels.com/almanac/almanac21/almanac{year}{timezone.lower()}.html",
            )
            db_session.add(db_event)
            added += 1

            # Debug logging for FULL MOON events
            if "FULL MOON" in event.event_name.upper() or "full moon" in event.event_name.lower():
                logger.debug(
                    f"Caching FULL MOON: {event.event_name}, date={event.date}, "
                    f"local_date={event.local_date}, type={event.event_type}"
                )
        else:
            # Update existing event's event_type in case classification changed
            if existing.event_type != event.event_type:
                existing.event_type = event.event_type
                existing.description = event.description.encode("utf-8", errors="replace").decode("utf-8")
                updated += 1
            else:
                skipped += 1
            # Debug logging for skipped FULL MOON events
            if "FULL MOON" in event.event_name.upper() or "full moon" in event.event_name.lower():
                logger.debug(
                    f"Skipping duplicate FULL MOON: {event.event_name}, date={event.date}, "
                    f"existing_date={existing.date if existing else None}"
                )

    db_session.commit()
    logger.info(f"Cached {added} new AstroPixels events for {year} (updated {updated}, skipped {skipped} duplicates)")

    return added + updated


def get_cached_astropixels_events(
    db_session: Session, start_date: datetime, end_date: datetime, timezone_offset: int | None = None
) -> list[AstroPixelsEvent]:
    """
    Get cached AstroPixels events from database.

    Args:
        db_session: Database session
        start_date: Start date (in UTC)
        end_date: End date (in UTC)
        timezone_offset: Timezone offset in hours (e.g., -7 for MST) to reconstruct local_date

    Returns:
        List of events
    """
    from sqlalchemy import and_, select

    from celestron_nexstar.api.database.models import SpaceEventModel

    # Adjust query range to account for timezone offset
    # Events stored in UTC might correspond to dates in local timezone that are
    # outside the UTC date range. For example, Dec 31 23:00 MST = Jan 1 06:00 UTC.
    # So we need to expand the query range by the timezone offset to capture all events.
    query_start = start_date
    query_end = end_date

    if timezone_offset is not None:
        # If timezone_offset is negative (e.g., -7 for MST), events late in the day
        # in local time will be on the next day in UTC. So we need to extend the
        # end_date by the absolute value of the offset.
        # Similarly, events early in the day might be on the previous day in UTC.
        offset_hours = abs(timezone_offset)
        query_start = start_date - timedelta(hours=offset_hours)
        query_end = end_date + timedelta(hours=offset_hours)

    result = db_session.execute(
        select(SpaceEventModel)
        .where(
            and_(
                SpaceEventModel.source == "AstroPixels",
                SpaceEventModel.date >= query_start,
                SpaceEventModel.date <= query_end,
            )
        )
        .order_by(SpaceEventModel.date)
    )

    models = result.scalars().all()

    logger.debug(
        f"Retrieved {len(models)} events from database (query range: {query_start} to {query_end}, "
        f"original range: {start_date} to {end_date}, tz_offset: {timezone_offset})"
    )

    events = []
    for model in models:
        # Try to reconstruct local_date from stored UTC date
        # Add back the timezone offset to get the approximate local date
        local_date = None
        if timezone_offset is not None:
            try:
                # Convert UTC to local by adding the offset
                local_date_naive = model.date.replace(tzinfo=None) + timedelta(hours=timezone_offset)
                # Create a timezone-naive datetime for the local date
                local_date = datetime(
                    local_date_naive.year,
                    local_date_naive.month,
                    local_date_naive.day,
                    local_date_naive.hour,
                    local_date_naive.minute,
                    tzinfo=None,
                )
            except Exception:
                # If reconstruction fails, use None (will fall back to UTC date)
                local_date = None

        # Don't filter here - return all events from the expanded query
        # The calendar dialog will handle filtering based on the actual date range needed
        # This ensures we don't accidentally filter out valid events due to timezone conversion issues
        events.append(
            AstroPixelsEvent(
                date=model.date,
                event_name=model.name,
                event_type=model.event_type,
                description=model.description,
                local_date=local_date,  # Reconstructed local date if timezone_offset provided
            )
        )

    logger.debug(f"Returning {len(events)} events (all events from expanded query range)")
    return events
