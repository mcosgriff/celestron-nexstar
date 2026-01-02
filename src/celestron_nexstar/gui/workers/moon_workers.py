"""
Moon Calendar Worker Threads

QThread workers for async moon data calculations to prevent UI blocking.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal

from celestron_nexstar.api.astronomy.solar_system import get_moon_info
from celestron_nexstar.api.core.enums import MoonPhase


if TYPE_CHECKING:
    from celestron_nexstar.api.location.observer import ObserverLocation


logger = logging.getLogger(__name__)

# Supermoon threshold: Full moon within 90% of minimum perigee distance
PERIGEE_DISTANCE_KM = 356500  # Approximate minimum distance to Moon
SUPERMOON_THRESHOLD_KM = PERIGEE_DISTANCE_KM * 1.10  # 392,150 km


@dataclass
class MoonDayData:
    """Moon information for a single day."""

    date: datetime
    phase_name: MoonPhase
    illumination: float  # 0.0 to 1.0
    moonrise_time: datetime | None
    moonset_time: datetime | None
    distance_km: float  # Earth-Moon distance for supermoon detection
    is_major_phase: bool  # True if New/Quarter/Full phase occurs this day
    traditional_name: str | None  # Full moon name (if applicable)


@dataclass
class MoonPhaseEvent:
    """Major moon phase event for timeline."""

    date: datetime
    phase: MoonPhase
    illumination: float
    distance_km: float
    traditional_name: str | None
    is_supermoon: bool
    is_blue_moon: bool
    eclipse_type: str | None  # "lunar_total", "lunar_partial", etc.


class MoonDataWorker(QThread):
    """
    Worker thread to calculate moon data for entire month.

    Calculates moon phases, distances, and special events without blocking UI.
    """

    data_ready = Signal(dict, list)  # type: ignore[type-arg,misc]  # dict[str, MoonDayData], list[MoonPhaseEvent]
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Error message
    progress_updated = Signal(int, int)  # type: ignore[type-arg,misc]  # current, total

    def __init__(
        self,
        year: int,
        month: int,
        location: ObserverLocation,
        months_ahead: int = 6,
    ) -> None:
        """
        Initialize the moon data worker.

        Args:
            year: Year to calculate
            month: Month to calculate (1-12)
            location: Observer location for calculations
            months_ahead: Number of months ahead to calculate for phase timeline
        """
        super().__init__()
        self.year = year
        self.month = month
        self.location = location
        self.months_ahead = months_ahead
        self._traditional_names: dict | None = None
        self._previous_phase: MoonPhase | None = None

    def run(self) -> None:
        """Calculate moon data for month in background thread."""
        try:
            logger.debug(f"Calculating moon data for {self.year}-{self.month:02d}")

            # Load traditional moon names
            self._load_traditional_names()

            # Calculate moon data for all days in month
            moon_data: dict[str, MoonDayData] = {}
            phase_events: list[MoonPhaseEvent] = []

            # Get days in month
            start_date = datetime(self.year, self.month, 1, tzinfo=UTC)
            if self.month == 12:
                end_date = datetime(self.year + 1, 1, 1, tzinfo=UTC)
            else:
                end_date = datetime(self.year, self.month + 1, 1, tzinfo=UTC)

            total_days = (end_date - start_date).days

            # Calculate for each day at noon local time
            current_date = start_date
            day_count = 0

            while current_date < end_date:
                day_count += 1

                # Get moon info for this day (at noon)
                moon_info = get_moon_info(
                    self.location.latitude,
                    self.location.longitude,
                    current_date.replace(hour=12),
                    self.location.elevation,
                )

                if moon_info:
                    # Calculate distance
                    distance = self._calculate_moon_distance(current_date.replace(hour=12))

                    # Check if major phase transition
                    is_major = self._is_major_phase_transition(moon_info.phase_name)

                    # Get traditional name (for full moons with major phase)
                    traditional_name = None
                    if is_major and moon_info.phase_name == MoonPhase.FULL_MOON:
                        traditional_name = self._get_traditional_name(current_date)

                    # Create day data
                    day_data = MoonDayData(
                        date=current_date,
                        phase_name=moon_info.phase_name,
                        illumination=moon_info.illumination,
                        moonrise_time=moon_info.moonrise_time,
                        moonset_time=moon_info.moonset_time,
                        distance_km=distance,
                        is_major_phase=is_major,
                        traditional_name=traditional_name,
                    )

                    moon_data[current_date.strftime("%Y-%m-%d")] = day_data

                    # Add to phase events if major phase
                    if is_major:
                        phase_event = MoonPhaseEvent(
                            date=current_date,
                            phase=moon_info.phase_name,
                            illumination=moon_info.illumination,
                            distance_km=distance,
                            traditional_name=traditional_name,
                            is_supermoon=False,  # Will be set later
                            is_blue_moon=False,  # Will be set later
                            eclipse_type=None,  # Will be set later
                        )
                        phase_events.append(phase_event)

                # Update progress
                self.progress_updated.emit(day_count, total_days)

                current_date += timedelta(days=1)

            # Extend phase events for timeline (next N months)
            self._extend_phase_events(phase_events, end_date)

            # Detect special events
            self._detect_special_events(phase_events)

            # Emit results
            logger.debug(f"Calculated {len(moon_data)} days, {len(phase_events)} phase events")
            self.data_ready.emit(moon_data, phase_events)

        except Exception as e:
            logger.exception("Error calculating moon data")
            self.error_occurred.emit(str(e))

    def _calculate_moon_distance(self, dt: datetime) -> float:
        """
        Calculate Earth-Moon distance in km using Skyfield.

        Args:
            dt: Datetime to calculate distance for

        Returns:
            Distance in kilometers
        """
        try:
            from skyfield.api import Topos

            from celestron_nexstar.api.ephemeris.skyfield_utils import (
                get_skyfield_ephemeris,
                get_skyfield_timescale,
            )

            # Get Skyfield objects
            ts = get_skyfield_timescale()
            eph = get_skyfield_ephemeris("de421.bsp")

            earth = eph["earth"]
            moon = eph["moon"]

            # Create observer at location
            observer = earth + Topos(
                latitude_degrees=self.location.latitude,
                longitude_degrees=self.location.longitude,
                elevation_m=self.location.elevation * 0.3048,  # Convert feet to meters
            )

            # Get time
            t = ts.from_datetime(dt)

            # Calculate distance
            moon_astrometric = observer.at(t).observe(moon)
            distance_au = moon_astrometric.distance().au
            distance_km = distance_au * 149597870.7  # AU to km conversion

            return distance_km

        except Exception as e:
            logger.warning(f"Error calculating moon distance: {e}")
            # Return average moon distance if calculation fails
            return 384400.0  # Average Earth-Moon distance in km

    def _is_major_phase_transition(self, current_phase: MoonPhase) -> bool:
        """
        Check if this is a major phase transition day.

        Major phases are: New Moon, First Quarter, Full Moon, Last Quarter

        Args:
            current_phase: Current moon phase

        Returns:
            True if this is a major phase transition
        """
        major_phases = {
            MoonPhase.NEW_MOON,
            MoonPhase.FIRST_QUARTER,
            MoonPhase.FULL_MOON,
            MoonPhase.LAST_QUARTER,
        }

        # Check if current phase is major and different from previous
        is_major = current_phase in major_phases
        is_transition = current_phase != self._previous_phase

        # Update previous phase for next iteration
        self._previous_phase = current_phase

        return is_major and is_transition

    def _load_traditional_names(self) -> None:
        """Load traditional moon names from JSON file."""
        try:
            # Find the JSON file
            json_path = Path(__file__).parent.parent.parent / "data" / "seed" / "traditional_moon_names.json"

            with open(json_path) as f:
                self._traditional_names = json.load(f)

            logger.debug("Loaded traditional moon names")

        except Exception as e:
            logger.warning(f"Error loading traditional moon names: {e}")
            self._traditional_names = {"month_names": {}, "special_names": {}}

    def _get_traditional_name(self, date: datetime) -> str:
        """
        Get traditional full moon name for date.

        Handles special cases like Harvest Moon and Hunter's Moon.

        Args:
            date: Date to get name for

        Returns:
            Traditional name or empty string if none
        """
        if not self._traditional_names:
            return ""

        month = date.month

        # Check for special cases first (Harvest Moon, Hunter's Moon handled in post-processing)
        # For now, just return month-based name
        month_data = self._traditional_names.get("month_names", {}).get(str(month))
        if month_data:
            return month_data.get("primary", "")

        return ""

    def _extend_phase_events(self, phase_events: list[MoonPhaseEvent], start_date: datetime) -> None:
        """
        Extend phase events timeline for next N months.

        Args:
            phase_events: List of phase events to extend
            start_date: Starting date for extension
        """
        # Calculate additional months
        end_date = start_date + timedelta(days=30 * self.months_ahead)

        current_date = start_date

        while current_date < end_date:
            # Get moon info
            moon_info = get_moon_info(
                self.location.latitude,
                self.location.longitude,
                current_date.replace(hour=12),
                self.location.elevation,
            )

            if moon_info:
                # Check if major phase transition
                is_major = self._is_major_phase_transition(moon_info.phase_name)

                if is_major:
                    distance = self._calculate_moon_distance(current_date.replace(hour=12))

                    # Get traditional name for full moons
                    traditional_name = None
                    if moon_info.phase_name == MoonPhase.FULL_MOON:
                        traditional_name = self._get_traditional_name(current_date)

                    phase_event = MoonPhaseEvent(
                        date=current_date,
                        phase=moon_info.phase_name,
                        illumination=moon_info.illumination,
                        distance_km=distance,
                        traditional_name=traditional_name,
                        is_supermoon=False,
                        is_blue_moon=False,
                        eclipse_type=None,
                    )
                    phase_events.append(phase_event)

            current_date += timedelta(days=1)

    def _detect_special_events(self, phase_events: list[MoonPhaseEvent]) -> None:
        """
        Detect and mark special events (supermoons, blue moons).

        Args:
            phase_events: List of phase events to check
        """
        # Detect supermoons
        for event in phase_events:
            if event.phase == MoonPhase.FULL_MOON:
                event.is_supermoon = event.distance_km <= SUPERMOON_THRESHOLD_KM

        # Detect blue moons (monthly: 2nd full moon in calendar month)
        from collections import defaultdict

        full_moons_by_month: dict[str, list[MoonPhaseEvent]] = defaultdict(list)

        for event in phase_events:
            if event.phase == MoonPhase.FULL_MOON:
                month_key = event.date.strftime("%Y-%m")
                full_moons_by_month[month_key].append(event)

        # Mark 2nd full moon in each month as blue moon
        for month_events in full_moons_by_month.values():
            if len(month_events) >= 2:
                # Second full moon is blue moon
                month_events[1].is_blue_moon = True
                # Override traditional name with "Blue Moon"
                month_events[1].traditional_name = "Blue Moon"

        logger.debug(
            f"Detected {sum(1 for e in phase_events if e.is_supermoon)} supermoons, "
            f"{sum(1 for e in phase_events if e.is_blue_moon)} blue moons"
        )
