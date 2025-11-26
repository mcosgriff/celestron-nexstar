"""
Space Weather Data from NOAA SWPC

Provides space weather conditions including NOAA scales (R, S, G),
solar activity, geomagnetic conditions, and alerts.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import aiohttp


logger = logging.getLogger(__name__)

# Simple in-memory cache for API responses
_cache: dict[str, tuple[datetime, dict[str, Any] | list[Any] | float | None]] = {}
_CACHE_TTL_SECONDS = 1800  # 30 minutes


__all__ = [
    "NOAAScale",
    "OvationAuroraForecast",
    "SpaceWeatherConditions",
    "get_goes_xray_data",
    "get_ovation_aurora_forecast",
    "get_radio_flux_107",
    "get_solar_wind_data",
    "get_space_weather_conditions",
]


@dataclass
class NOAAScale:
    """NOAA Space Weather Scale value."""

    level: int  # 0-5 (0 = no activity, 1-5 = minor to extreme)
    scale_type: str  # "R", "S", or "G"
    description: str | None = None

    @property
    def display_name(self) -> str:
        """Get display name for the scale."""
        if self.level == 0:
            return "None"
        # Only known scale types (R, S, G) use level names
        if self.scale_type not in ("R", "S", "G"):
            return f"Level {self.level}"
        # All scales (R, S, G) use the same level names
        level_names = {1: "Minor", 2: "Moderate", 3: "Strong", 4: "Severe", 5: "Extreme"}
        return level_names.get(self.level, f"Level {self.level}")

    @property
    def color_code(self) -> str:
        """Get color code for display."""
        match self.level:
            case 0:
                return "green"
            case level if level <= 2:
                return "yellow"
            case level if level <= 3:
                return "red"
            case _:
                return "bold red"


@dataclass
class SpaceWeatherConditions:
    """Current space weather conditions from NOAA SWPC."""

    # NOAA Scales
    r_scale: NOAAScale | None = None  # Radio blackout scale (R1-R5)
    s_scale: NOAAScale | None = None  # Solar radiation scale (S1-S5)
    g_scale: NOAAScale | None = None  # Geomagnetic scale (G1-G5)

    # Geomagnetic
    kp_index: float | None = None
    ap_index: float | None = None

    # Solar Wind
    solar_wind_speed: float | None = None  # km/s
    solar_wind_bt: float | None = None  # nT (total magnetic field)
    solar_wind_bz: float | None = None  # nT (north-south component)
    solar_wind_density: float | None = None  # particles/cm³

    # Solar Activity
    radio_flux_107: float | None = None  # 10.7cm radio flux in sfu
    xray_flux: float | None = None  # X-ray flux in W/m²
    xray_class: str | None = None  # X-ray class (A, B, C, M, X)

    # Alerts and Warnings
    alerts: list[str] | None = None
    last_updated: datetime | None = None

    def __post_init__(self) -> None:
        """Initialize alerts list if None."""
        if self.alerts is None:
            object.__setattr__(self, "alerts", [])


def _get_from_cache(key: str) -> dict[str, Any] | list[Any] | float | None:
    """Get cached response if still valid."""
    if key in _cache:
        timestamp, data = _cache[key]
        if datetime.now(UTC) - timestamp < timedelta(seconds=_CACHE_TTL_SECONDS):
            return data
        # Cache expired, remove it
        del _cache[key]
    return None


def _set_cache(key: str, data: dict[str, Any] | list[Any] | float | None) -> None:
    """Store response in cache."""
    _cache[key] = (datetime.now(UTC), data)


def _parse_noaa_scale(scale_str: str | None, scale_type: str) -> NOAAScale | None:
    """Parse NOAA scale string (e.g., 'G1', 'R3') into NOAAScale object."""
    if not scale_str:
        return None

    try:
        # Extract level (1-5) from string like "G1", "R3", etc.
        scale_str = scale_str.strip().upper()
        if scale_str.startswith(scale_type):
            level_str = scale_str[1:]
            level = int(level_str)
            if 0 <= level <= 5:
                return NOAAScale(level=level, scale_type=scale_type)
    except (ValueError, IndexError, AttributeError):
        pass

    return None


async def get_solar_wind_data() -> dict[str, float | None]:
    """
    Fetch current solar wind data from NOAA SWPC.

    Fetches plasma and magnetic field data concurrently for better performance.

    Returns:
        Dictionary with solar_wind_speed, solar_wind_bt, solar_wind_bz, solar_wind_density
    """
    import asyncio

    cache_key = "solar_wind_data"
    cached = _get_from_cache(cache_key)
    if cached is not None and isinstance(cached, dict):
        return cached

    try:
        async with aiohttp.ClientSession() as session:
            # Fetch plasma and magnetic field data concurrently
            plasma_url = "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json"
            mag_url = "https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json"

            plasma_task = session.get(plasma_url, timeout=aiohttp.ClientTimeout(total=10))
            mag_task = session.get(mag_url, timeout=aiohttp.ClientTimeout(total=10))

            plasma_response, mag_response = await asyncio.gather(plasma_task, mag_task)

            # Process plasma data
            density = None
            speed = None
            async with plasma_response:
                plasma_response.raise_for_status()
                data = await plasma_response.json()

                if data and len(data) >= 2:
                    # Format: First row is header, subsequent rows are data
                    # Header: ["time_tag", "density", "speed", "temperature"]
                    # Get the most recent entry (last row)
                    latest_row = data[-1]
                    try:
                        density = float(latest_row[1]) if latest_row[1] else None
                        speed = float(latest_row[2]) if latest_row[2] else None
                    except (IndexError, ValueError, TypeError):
                        density = None
                        speed = None

            # Process magnetic field data
            bt = None
            bz = None
            async with mag_response:
                if mag_response.status == 200:
                    mag_data = await mag_response.json()
                    if mag_data and len(mag_data) >= 2:
                        # Header: ["time_tag", "bt", "bz", "phi", "theta"]
                        latest_mag = mag_data[-1]
                        try:
                            bt = float(latest_mag[1]) if latest_mag[1] else None
                            bz = float(latest_mag[2]) if latest_mag[2] else None
                        except (IndexError, ValueError, TypeError):
                            bt = None
                            bz = None

            result = {
                "solar_wind_speed": speed,
                "solar_wind_bt": bt,
                "solar_wind_bz": bz,
                "solar_wind_density": density,
            }
            _set_cache(cache_key, result)
            return result
    except (aiohttp.ClientError, ValueError, TypeError, KeyError, IndexError, TimeoutError) as e:
        # aiohttp.ClientError: HTTP/network errors
        # ValueError: invalid JSON or data format
        # TypeError: wrong data types
        # KeyError: missing keys in response
        # IndexError: missing array indices
        # TimeoutError: request timeout
        logger.debug(f"Error fetching solar wind data: {e}")
        return {}


async def get_goes_xray_data() -> dict[str, float | str | None]:
    """
    Fetch GOES X-ray flux data from NOAA SWPC.

    Returns:
        Dictionary with xray_flux, xray_class
    """
    cache_key = "goes_xray_data"
    cached = _get_from_cache(cache_key)
    if cached is not None and isinstance(cached, dict):
        return cached

    try:
        async with aiohttp.ClientSession() as session:
            # GOES XRS report
            url = "https://services.swpc.noaa.gov/json/goes/goes-xrs-report.json"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                data = await response.json()

            if not data:
                return {}

            # Find the most recent entry using max() with key function
            def get_entry_time(entry: dict[str, object]) -> datetime | None:
                """Extract datetime from entry, or return None if invalid."""
                time_str = entry.get("time_tag")
                if not time_str:
                    return None
                with contextlib.suppress(ValueError, AttributeError):
                    if isinstance(time_str, str):
                        return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                return None

            # Filter entries with valid timestamps and get the latest
            entries_with_times = [
                (entry, time)
                for entry in data
                if isinstance(entry, dict) and (time := get_entry_time(entry)) is not None
            ]
            latest_pair = max(entries_with_times, key=lambda x: x[1], default=None)
            latest = latest_pair[0] if latest_pair else None

            if latest:
                flux = latest.get("flux")
                xray_class = latest.get("class")

                # Convert flux to float if it's a string
                xray_flux = None
                if flux:
                    with contextlib.suppress(ValueError, TypeError):
                        xray_flux = float(flux)

                xray_class_str = str(xray_class) if xray_class else None

                result = {
                    "xray_flux": xray_flux,
                    "xray_class": xray_class_str,
                }
                _set_cache(cache_key, result)
                return result

            return {}
    except (aiohttp.ClientError, ValueError, TypeError, KeyError, IndexError, TimeoutError) as e:
        # aiohttp.ClientError: HTTP/network errors
        # ValueError: invalid JSON or data format
        # TypeError: wrong data types
        # KeyError: missing keys in response
        # IndexError: missing array indices
        # TimeoutError: request timeout
        logger.debug(f"Error fetching GOES X-ray data: {e}")
        return {}


async def get_radio_flux_107() -> float | None:
    """
    Fetch 10.7cm radio flux from NOAA SWPC.

    The 10.7cm radio flux (F10.7) is a measure of solar activity at 2800 MHz.
    It's a good indicator of overall solar activity and correlates with sunspot numbers.

    Returns:
        10.7cm radio flux in sfu (solar flux units), or None if unavailable
    """
    cache_key = "radio_flux_107"
    cached = _get_from_cache(cache_key)
    if cached is not None and isinstance(cached, (int, float)):
        return float(cached)

    try:
        async with aiohttp.ClientSession() as session:
            # Try the GOES XRS report which sometimes includes radio flux
            # Alternative: Use daily solar data endpoint if available
            url = "https://services.swpc.noaa.gov/json/goes/goes-xrs-report.json"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                data = await response.json()

            if not data:
                return None

            # Look for radio flux in the data
            # The structure may vary, so we'll try multiple approaches
            field_names = ("flux_107", "f107", "radio_flux")
            for entry in data:
                if isinstance(entry, dict):
                    # Try common field names
                    flux_107 = next((entry.get(field) for field in field_names if entry.get(field)), None)
                    if flux_107:
                        with contextlib.suppress(ValueError, TypeError):
                            result = float(flux_107)
                            _set_cache(cache_key, result)
                            return result

            # Try alternative endpoint for daily solar flux
            # NOAA provides daily solar flux data
            try:
                flux_url = "https://services.swpc.noaa.gov/json/radio_flux/daily_flux.json"
                async with session.get(flux_url, timeout=aiohttp.ClientTimeout(total=10)) as flux_response:
                    if flux_response.status == 200:
                        flux_data = await flux_response.json()
                        if flux_data and isinstance(flux_data, list):
                            # Get the most recent entry
                            def get_flux_entry_time(entry: dict[str, object]) -> datetime | None:
                                """Extract datetime from flux entry."""
                                time_str = entry.get("time_tag") or entry.get("date") or entry.get("time")
                                if not time_str:
                                    return None
                                with contextlib.suppress(ValueError, AttributeError):
                                    if isinstance(time_str, str):
                                        return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                                return None

                            # Filter entries with valid timestamps and get the latest
                            entries_with_times = [
                                (entry, time)
                                for entry in flux_data
                                if isinstance(entry, dict) and (time := get_flux_entry_time(entry)) is not None
                            ]
                            latest_entry_pair = max(entries_with_times, key=lambda x: x[1], default=None)
                            latest_entry = latest_entry_pair[0] if latest_entry_pair else None
                            if latest_entry:
                                flux_value = (
                                    latest_entry.get("flux") or latest_entry.get("f107") or latest_entry.get("flux_107")
                                )
                                if flux_value:
                                    with contextlib.suppress(ValueError, TypeError):
                                        result = float(flux_value)
                                        _set_cache(cache_key, result)
                                        return result
            except (KeyError, IndexError, AttributeError):
                # KeyError: missing keys in response
                # IndexError: missing array indices
                # AttributeError: missing attributes
                pass

            # If not found, return None
            return None
    except (aiohttp.ClientError, ValueError, TypeError, TimeoutError) as e:
        # aiohttp.ClientError: HTTP/network errors
        # ValueError: invalid JSON or data format
        # TypeError: wrong data types
        # TimeoutError: request timeout
        logger.debug(f"Error fetching 10.7cm radio flux: {e}")
        return None


async def get_proton_flux_data() -> dict[str, float | None]:
    """
    Fetch proton flux data from NOAA SWPC for S-scale calculation.

    S-scale is based on proton flux measurements:
    - S1: >= 10 pfu (proton flux units) at >10 MeV
    - S2: >= 100 pfu at >10 MeV
    - S3: >= 1000 pfu at >10 MeV
    - S4: >= 10000 pfu at >10 MeV
    - S5: >= 100000 pfu at >10 MeV

    Returns:
        Dictionary with proton_flux_10mev (proton flux at >10 MeV in pfu)
    """
    cache_key = "proton_flux_data"
    cached = _get_from_cache(cache_key)
    if cached is not None and isinstance(cached, dict):
        return cached

    try:
        async with aiohttp.ClientSession() as session:
            # Try GOES proton flux endpoint
            # Common endpoint: goes-proton-flux or similar
            # Note: Exact endpoint may need verification
            url = "https://services.swpc.noaa.gov/json/goes/goes-proton-flux.json"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    # Try alternative endpoint format
                    url = "https://services.swpc.noaa.gov/products/goes/goes-proton-flux.json"
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as alt_response:
                        response = alt_response

                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list):
                        # Find the most recent entry
                        def get_proton_entry_time(entry: dict[str, object]) -> datetime | None:
                            """Extract datetime from proton flux entry."""
                            time_str = entry.get("time_tag") or entry.get("time")
                            if not time_str:
                                return None
                            with contextlib.suppress(ValueError, AttributeError):
                                if isinstance(time_str, str):
                                    return datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                            return None

                        # Filter entries with valid timestamps and get the latest
                        entries_with_times = [
                            (entry, time)
                            for entry in data
                            if isinstance(entry, dict) and (time := get_proton_entry_time(entry)) is not None
                        ]
                        latest_pair = max(entries_with_times, key=lambda x: x[1], default=None)
                        latest = latest_pair[0] if latest_pair else None

                        if latest:
                            # Look for >10 MeV proton flux
                            flux_10mev = latest.get("flux_10mev") or latest.get("p10") or latest.get("proton_flux")
                            if flux_10mev:
                                with contextlib.suppress(ValueError, TypeError):
                                    result: dict[str, float | None] = {"proton_flux_10mev": float(flux_10mev)}
                                    _set_cache(cache_key, result)
                                    return result

            return {}
    except (aiohttp.ClientError, ValueError, TypeError, KeyError, IndexError, TimeoutError) as e:
        # aiohttp.ClientError: HTTP/network errors
        # ValueError: invalid JSON or data format
        # TypeError: wrong data types
        # KeyError: missing keys in response
        # IndexError: missing array indices
        # TimeoutError: request timeout
        logger.debug(f"Error fetching proton flux data: {e}")
        return {}


async def get_kp_ap_data() -> dict[str, float | None]:
    """
    Fetch current Kp and Ap indices from NOAA SWPC.

    Returns:
        Dictionary with kp_index, ap_index
    """
    cache_key = "kp_ap_data"
    cached = _get_from_cache(cache_key)
    if cached is not None and isinstance(cached, dict):
        return cached

    try:
        async with aiohttp.ClientSession() as session:
            # Kp forecast includes current observed values
            url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                data = await response.json()

            if not data or len(data) < 2:
                return {}

            # Find the most recent observed value
            def get_kp_entry_time(row: list[object]) -> datetime | None:
                """Extract datetime from Kp data row if it's observed."""
                if len(row) < 3:
                    return None
                try:
                    observed = str(row[2]).lower() if row[2] else ""
                    if observed == "observed":
                        time_str = str(row[0])
                        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                except (ValueError, IndexError, TypeError, AttributeError):
                    pass
                return None

            # Filter rows with valid timestamps and get the latest
            rows_with_times = [
                (row, time) for row in data[1:] if len(row) >= 3 and (time := get_kp_entry_time(row)) is not None
            ]
            if rows_with_times:
                latest_row_pair = max(rows_with_times, key=lambda x: x[1])
                latest_row = latest_row_pair[0]
                try:
                    latest_kp = float(latest_row[1])
                    result: dict[str, float | None] = {"kp_index": latest_kp}
                    _set_cache(cache_key, result)
                    return result
                except (ValueError, IndexError, TypeError):
                    pass

            return {"kp_index": None}
    except (aiohttp.ClientError, KeyError, TimeoutError) as e:
        # aiohttp.ClientError: HTTP/network errors
        # KeyError: missing keys in response
        # TimeoutError: request timeout
        logger.debug(f"Error fetching Kp/Ap data: {e}")
        return {}


async def get_space_weather_conditions() -> SpaceWeatherConditions:
    """
    Fetch current space weather conditions from NOAA SWPC.

    All API calls are made concurrently for improved performance.

    Returns:
        SpaceWeatherConditions object with current data
    """
    import asyncio

    conditions = SpaceWeatherConditions(last_updated=datetime.now(UTC))

    # Fetch all data concurrently using asyncio.gather() for better performance
    solar_wind, xray_data, kp_data, radio_flux, proton_data = await asyncio.gather(
        get_solar_wind_data(),
        get_goes_xray_data(),
        get_kp_ap_data(),
        get_radio_flux_107(),
        get_proton_flux_data(),
        return_exceptions=True,  # Continue even if one request fails
    )

    # Process solar wind data (handle exception)
    if not isinstance(solar_wind, Exception) and isinstance(solar_wind, dict):
        conditions.solar_wind_speed = solar_wind.get("solar_wind_speed")
        conditions.solar_wind_bt = solar_wind.get("solar_wind_bt")
        conditions.solar_wind_bz = solar_wind.get("solar_wind_bz")
        conditions.solar_wind_density = solar_wind.get("solar_wind_density")

    # Process X-ray data (handle exception)
    if not isinstance(xray_data, Exception) and isinstance(xray_data, dict):
        xray_flux_val = xray_data.get("xray_flux")
        xray_class_val = xray_data.get("xray_class")
        if isinstance(xray_flux_val, float):
            conditions.xray_flux = xray_flux_val
        if isinstance(xray_class_val, str):
            conditions.xray_class = xray_class_val

    # Process Kp index (handle exception)
    if not isinstance(kp_data, Exception) and isinstance(kp_data, dict):
        conditions.kp_index = kp_data.get("kp_index")

    # Process radio flux (handle exception)
    if not isinstance(radio_flux, Exception) and isinstance(radio_flux, (int, float)):
        conditions.radio_flux_107 = float(radio_flux)

    # Process proton flux (handle exception)
    proton_flux_10mev = None
    if not isinstance(proton_data, Exception) and isinstance(proton_data, dict):
        proton_flux_10mev = proton_data.get("proton_flux_10mev")

    # Determine NOAA scales from Kp index, X-ray class, and proton flux
    # G-scale from Kp: G1 (Kp=5), G2 (Kp=6), G3 (Kp=7), G4 (Kp=8), G5 (Kp=9)
    if conditions.kp_index is not None:
        kp = conditions.kp_index
        g_scale_levels = [
            (9, 5, "Extreme geomagnetic storm"),
            (8, 4, "Severe geomagnetic storm"),
            (7, 3, "Strong geomagnetic storm"),
            (6, 2, "Moderate geomagnetic storm"),
            (5, 1, "Minor geomagnetic storm"),
        ]
        level, description = next(
            ((lev, desc) for threshold, lev, desc in g_scale_levels if kp >= threshold),
            (0, "Quiet conditions"),
        )
        conditions.g_scale = NOAAScale(level=level, scale_type="G", description=description)

    # R-scale from X-ray class: R1 (M1), R2 (M5), R3 (X1), R4 (X10), R5 (X20)
    if conditions.xray_class:
        xray_class = conditions.xray_class.upper()
        with contextlib.suppress(ValueError):
            match xray_class:
                case class_str if class_str.startswith("X"):
                    x_value = float(class_str[1:])
                    r_scale_levels = [
                        (20, 5, "Extreme radio blackout"),
                        (10, 4, "Severe radio blackout"),
                        (1, 3, "Strong radio blackout"),
                    ]
                    result = next(
                        ((lev, desc) for threshold, lev, desc in r_scale_levels if x_value >= threshold),
                        None,
                    )
                    if result is not None:
                        level, description = result
                        conditions.r_scale = NOAAScale(level=level, scale_type="R", description=description)
                case class_str if class_str.startswith("M"):
                    m_value = float(class_str[1:])
                    r_scale_levels = [
                        (5, 2, "Moderate radio blackout"),
                        (1, 1, "Minor radio blackout"),
                    ]
                    result = next(
                        ((lev, desc) for threshold, lev, desc in r_scale_levels if m_value >= threshold),
                        None,
                    )
                    if result is not None:
                        level, description = result
                        conditions.r_scale = NOAAScale(level=level, scale_type="R", description=description)
                case _:
                    pass

    # S-scale from proton flux: S1 (>=10 pfu), S2 (>=100), S3 (>=1000), S4 (>=10000), S5 (>=100000)
    if proton_flux_10mev is not None:
        flux = proton_flux_10mev
        s_scale_levels = [
            (100000, 5, "Extreme solar radiation storm"),
            (10000, 4, "Severe solar radiation storm"),
            (1000, 3, "Strong solar radiation storm"),
            (100, 2, "Moderate solar radiation storm"),
            (10, 1, "Minor solar radiation storm"),
        ]
        level, description = next(
            ((lev, desc) for threshold, lev, desc in s_scale_levels if flux >= threshold),
            (0, "No solar radiation storm"),
        )
        conditions.s_scale = NOAAScale(level=level, scale_type="S", description=description)

    # Generate alerts based on conditions
    # Ensure alerts list is initialized
    if conditions.alerts is None:
        object.__setattr__(conditions, "alerts", [])
    alerts_list = conditions.alerts
    assert alerts_list is not None  # Type narrowing for mypy

    if conditions.g_scale and conditions.g_scale.level >= 3:
        alerts_list.append(f"G{conditions.g_scale.level} geomagnetic storm - Enhanced aurora possible")
    if conditions.r_scale and conditions.r_scale.level >= 3:
        alerts_list.append(f"R{conditions.r_scale.level} radio blackout - GPS/communications may be affected")
    if conditions.solar_wind_speed and conditions.solar_wind_speed > 600:
        alerts_list.append("High solar wind speed detected")
    if conditions.s_scale and conditions.s_scale.level >= 3:
        alerts_list.append(f"S{conditions.s_scale.level} solar radiation storm - High-energy particles detected")

    return conditions


@dataclass
class OvationAuroraForecast:
    """Ovation aurora forecast data point from NOAA SWPC."""

    timestamp: datetime
    latitude: float
    longitude: float
    probability: float  # Aurora intensity (0-15 scale) - normalized to 0.0-1.0 for display
    forecast_type: str  # "forecast" or "observed"


async def get_ovation_aurora_forecast() -> list[OvationAuroraForecast] | None:
    """
    Fetch Ovation aurora forecast from NOAA SWPC.

    The Ovation model provides 30-minute aurora probability forecasts
    on a latitude/longitude grid.

    Returns:
        List of OvationAuroraForecast objects, or None if unavailable
    """
    cache_key = "ovation_aurora_forecast"
    cached = _get_from_cache(cache_key)
    if cached is not None and isinstance(cached, list):
        return cached

    try:
        async with aiohttp.ClientSession() as session:
            url = "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                response.raise_for_status()
                data = await response.json()

            if not data:
                return None

            forecasts: list[OvationAuroraForecast] = []

        # The Ovation data structure can vary
        # Common formats:
        # 1. Array of objects with coordinates and probability
        # 2. Grid data with lat/lon arrays and probability matrix
        # 3. GeoJSON format

        match data:
            case list():
                for entry in data:
                    match entry:
                        case dict():
                            try:
                                # Try to extract timestamp
                                time_str = entry.get("time_tag") or entry.get("time") or entry.get("timestamp")
                                timestamp = datetime.now(UTC)
                                if time_str:
                                    with contextlib.suppress(ValueError, AttributeError):
                                        timestamp = datetime.fromisoformat(time_str.replace("Z", "+00:00"))

                                # Extract coordinates and probability
                                lat = entry.get("latitude") or entry.get("lat")
                                lon = entry.get("longitude") or entry.get("lon") or entry.get("lng")
                                prob = (
                                    entry.get("probability")
                                    or entry.get("prob")
                                    or entry.get("intensity")
                                    or entry.get("value")
                                )

                                if lat is not None and lon is not None and prob is not None:
                                    forecasts.append(
                                        OvationAuroraForecast(
                                            timestamp=timestamp,
                                            latitude=float(lat),
                                            longitude=float(lon),
                                            probability=float(prob),
                                            forecast_type=entry.get("type", "forecast"),
                                        )
                                    )
                            except (ValueError, TypeError, KeyError):
                                continue
                        case _:
                            continue

            case dict() as data_dict:
                # Handle GeoJSON MultiPoint format: {"type": "MultiPoint", "coordinates": [[lon, lat, value], ...]}
                coordinates = data_dict.get("coordinates") or data_dict.get("coords")

                match coordinates:
                    case list() if coordinates:
                        time_str = data_dict.get("time_tag") or data_dict.get("time") or data_dict.get("timestamp")
                        timestamp = datetime.now(UTC)
                        if time_str:
                            with contextlib.suppress(ValueError, AttributeError):
                                timestamp = datetime.fromisoformat(time_str.replace("Z", "+00:00"))

                        # GeoJSON MultiPoint format: coordinates is array of [longitude, latitude, probability]
                        for coord in coordinates:
                            match coord:
                                case (list() | tuple()) as coord_seq if len(coord_seq) >= 3:
                                    try:
                                        lon, lat, intensity = (
                                            float(coord_seq[0]),
                                            float(coord_seq[1]),
                                            float(coord_seq[2]),
                                        )
                                        # Normalize to 0.0-1.0 for consistency (Ovation uses 0-15 scale)
                                        prob = intensity / 15.0 if intensity > 0 else 0.0
                                        forecasts.append(
                                            OvationAuroraForecast(
                                                timestamp=timestamp,
                                                latitude=lat,
                                                longitude=lon,
                                                probability=prob,
                                                forecast_type=data_dict.get("type", "forecast"),
                                            )
                                        )
                                    except (ValueError, TypeError, IndexError):
                                        continue
                                case _:
                                    continue
                    case _:
                        pass

            case _:
                pass

        result = forecasts if forecasts else None
        if result:
            _set_cache(cache_key, result)
        return result
    except (aiohttp.ClientError, ValueError, TypeError, KeyError, IndexError, TimeoutError) as e:
        # aiohttp.ClientError: HTTP/network errors
        # ValueError: invalid JSON or data format
        # TypeError: wrong data types
        # KeyError: missing keys in response
        # IndexError: missing array indices
        # TimeoutError: request timeout
        logger.debug(f"Error fetching Ovation aurora forecast: {e}")
        return None
