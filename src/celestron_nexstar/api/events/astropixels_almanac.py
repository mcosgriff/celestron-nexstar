"""
AstroPixels Almanac Parser

Parses astronomical events from the AstroPixels Sky Event Almanac.
Fetches and caches events from https://astropixels.com/almanac/
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import aiohttp
from bs4 import BeautifulSoup


if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


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

    if "full moon" in event_lower or "new moon" in event_lower or "quarter" in event_lower:
        return "moon_phase"
    elif "meteor" in event_lower or "shower" in event_lower:
        return "meteor_shower"
    elif "lunar eclipse" in event_lower or ("eclipse" in event_lower and "lunar" in event_lower):
        return "lunar_eclipse"
    elif "solar eclipse" in event_lower or ("eclipse" in event_lower and "solar" in event_lower):
        return "solar_eclipse"
    elif "eclipse" in event_lower:
        # Default to lunar if not specified
        return "lunar_eclipse"
    elif "solstice" in event_lower:
        return "solstice"
    elif "equinox" in event_lower:
        return "equinox"
    elif "apogee" in event_lower or "perigee" in event_lower:
        return "moon_position"
    elif "conjunction" in event_lower:
        return "conjunction"
    elif "opposition" in event_lower:
        return "planetary_opposition"
    elif "elongation" in event_lower:
        return "planetary_elongation"
    elif any(
        planet in event_lower for planet in ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"]
    ):
        return "planetary_opposition"  # Default for planetary events
    else:
        return "other"


async def fetch_and_parse_almanac(year: int, timezone: str = "MST") -> list[AstroPixelsEvent]:
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
        async with (
            aiohttp.ClientSession() as session,
            session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response,
        ):
            if response.status != 200:
                logger.error(f"Failed to fetch almanac: HTTP {response.status}")
                return events

            html = await response.text()
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
                pre_text = pre_block.get_text()
                lines = pre_text.split("\n")

                logger.debug(f"Parsing pre block with {len(lines)} lines")

                # Skip header lines
                current_month = None
                lines_processed = 0
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    # Skip header lines
                    if (
                        line.lower().startswith("date")
                        or line.lower().startswith("(h:m)")
                        or "sky event" in line.lower()
                    ):
                        continue

                    # Parse line format: "Jan 03  08:24  Venus 1.4°N of Moon"
                    # Or: "    03  08     Quadrantid Meteor Shower" (continued from previous month)
                    # Pattern: Optional month abbreviation, day, time, event

                    # Check if line starts with month abbreviation
                    month_match = re.match(r"^([A-Z][a-z]{2})\s+(\d{1,2})", line)
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
                        # Extract time and event from rest of line
                        rest = line[month_match.end() :].strip()
                    else:
                        # Line continues from previous month (starts with spaces and day)
                        # Match lines like "    04  16:14  FULL MOON" or "    04  04:06  Moon at Perigee"
                        # The line might have leading spaces, then day, then spaces, then time/event
                        day_match = re.match(r"^\s+(\d{1,2})\s+(.+)", line)
                        if day_match and current_month:
                            day = int(day_match.group(1))
                            rest = day_match.group(2).strip()  # Get everything after day
                        else:
                            # Try without leading spaces (in case line was already stripped)
                            day_match = re.match(r"^(\d{1,2})\s+(.+)", line)
                            if day_match and current_month:
                                day = int(day_match.group(1))
                                rest = day_match.group(2).strip()
                            else:
                                continue

                    # Parse time and event from rest of line
                    # Format: "08:24  Event" or "08     Event" (hours only) or just "Event" (no time)
                    # The time might have multiple spaces before the event
                    # Try to match time with colon first (e.g., "16:14  FULL MOON")
                    time_match = re.match(r"(\d{1,2}):(\d{2})\s+(.+)", rest)
                    if time_match:
                        hour_str, minute_str, event_text = time_match.groups()
                        hour = int(hour_str)
                        minute = int(minute_str)
                        event_name = event_text.strip()
                    else:
                        # Try to match time without colon (hours only, e.g., "08     Event")
                        hour_match = re.match(r"(\d{1,2})\s+(.+)", rest)
                        if hour_match:
                            hour_str, event_text = hour_match.groups()
                            hour = int(hour_str)
                            minute = 0
                            event_name = event_text.strip()
                        else:
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

            # Count December events
            december_count = sum(1 for e in events if e.local_date and e.local_date.month == 12)
            if december_count > 0:
                logger.info(f"Found {december_count} events in December")

            logger.info(f"Parsed {len(events)} events from AstroPixels almanac for {year}")

    except TimeoutError:
        logger.error(f"Timeout fetching almanac from {url}")
    except Exception as e:
        logger.error(f"Error fetching/parsing almanac: {e}", exc_info=True)

    return events


async def cache_astropixels_events(
    db_session: AsyncSession, year: int, timezone: str = "MST", force_refresh: bool = False
) -> int:
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

        count = await db_session.scalar(
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
    events = await fetch_and_parse_almanac(year, timezone)

    if not events:
        logger.warning(f"No events found for {year}")
        return 0

    # Delete existing events for this year if forcing refresh
    if force_refresh:
        await db_session.execute(
            delete(SpaceEventModel).where(
                SpaceEventModel.source == "AstroPixels",
                SpaceEventModel.date >= datetime(year, 1, 1, tzinfo=UTC),
                SpaceEventModel.date < datetime(year + 1, 1, 1, tzinfo=UTC),
            )
        )

    # Store events
    added = 0
    skipped = 0
    for event in events:
        # Check if event already exists
        existing = await db_session.scalar(
            select(SpaceEventModel)
            .where(
                SpaceEventModel.source == "AstroPixels",
                SpaceEventModel.name == event.event_name,
                SpaceEventModel.date == event.date,
            )
            .limit(1)
        )

        if not existing:
            db_event = SpaceEventModel(
                name=event.event_name,
                event_type=event.event_type,
                date=event.date,
                description=event.description,
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
            skipped += 1
            # Debug logging for skipped FULL MOON events
            if "FULL MOON" in event.event_name.upper() or "full moon" in event.event_name.lower():
                logger.debug(
                    f"Skipping duplicate FULL MOON: {event.event_name}, date={event.date}, "
                    f"existing_date={existing.date if existing else None}"
                )

    await db_session.commit()
    logger.info(f"Cached {added} AstroPixels events for {year} (skipped {skipped} duplicates)")

    return added


async def get_cached_astropixels_events(
    db_session: AsyncSession, start_date: datetime, end_date: datetime, timezone_offset: int | None = None
) -> list[AstroPixelsEvent]:
    """
    Get cached AstroPixels events from database.

    Args:
        db_session: Database session
        start_date: Start date
        end_date: End date
        timezone_offset: Timezone offset in hours (e.g., -7 for MST) to reconstruct local_date

    Returns:
        List of events
    """
    from sqlalchemy import and_, select

    from celestron_nexstar.api.database.models import SpaceEventModel

    result = await db_session.execute(
        select(SpaceEventModel)
        .where(
            and_(
                SpaceEventModel.source == "AstroPixels",
                SpaceEventModel.date >= start_date,
                SpaceEventModel.date <= end_date,
            )
        )
        .order_by(SpaceEventModel.date)
    )

    models = result.scalars().all()

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

        events.append(
            AstroPixelsEvent(
                date=model.date,
                event_name=model.name,
                event_type=model.event_type,
                description=model.description,
                local_date=local_date,  # Reconstructed local date if timezone_offset provided
            )
        )

    return events
