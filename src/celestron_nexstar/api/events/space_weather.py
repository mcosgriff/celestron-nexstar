"""
Space Weather Data from NOAA SWPC

Provides space weather conditions including NOAA scales (R, S, G),
solar activity, geomagnetic conditions, and alerts.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests_cache
from requests.adapters import HTTPAdapter  # type: ignore[import-untyped]
from urllib3.util.retry import Retry  # type: ignore[import-not-found]


logger = logging.getLogger(__name__)


__all__ = [
    "NOAAScale",
    "SpaceWeatherConditions",
    "get_goes_xray_data",
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
        scale_names = {
            "R": {1: "Minor", 2: "Moderate", 3: "Strong", 4: "Severe", 5: "Extreme"},
            "S": {1: "Minor", 2: "Moderate", 3: "Strong", 4: "Severe", 5: "Extreme"},
            "G": {1: "Minor", 2: "Moderate", 3: "Strong", 4: "Severe", 5: "Extreme"},
        }
        return scale_names.get(self.scale_type, {}).get(self.level, f"Level {self.level}")

    @property
    def color_code(self) -> str:
        """Get color code for display."""
        if self.level == 0:
            return "green"
        elif self.level <= 2:
            return "yellow"
        elif self.level <= 3:
            return "red"
        else:
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


def _get_cached_session() -> requests_cache.CachedSession:
    """Get a cached HTTP session for NOAA SWPC API calls."""
    cache_dir = Path.home() / ".cache" / "celestron-nexstar"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_session = requests_cache.CachedSession(
        str(cache_dir / "space_weather_cache"),
        expire_after=1800,  # 30 minutes
    )

    # Add retry strategy
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.2,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    cache_session.mount("https://", adapter)

    return cache_session


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


def get_solar_wind_data() -> dict[str, float | None]:
    """
    Fetch current solar wind data from NOAA SWPC.

    Returns:
        Dictionary with solar_wind_speed, solar_wind_bt, solar_wind_bz, solar_wind_density
    """
    try:
        session = _get_cached_session()

        # Try 7-day plasma data (most recent)
        url = "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json"
        response = session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data or len(data) < 2:
            return {}

        # Format: First row is header, subsequent rows are data
        # Header: ["time_tag", "density", "speed", "temperature"]
        # Get the most recent entry (last row)
        latest_row = data[-1]
        if len(latest_row) >= 4:
            density = float(latest_row[1]) if latest_row[1] else None
            speed = float(latest_row[2]) if latest_row[2] else None
            # temperature = float(latest_row[3]) if latest_row[3] else None
        else:
            density = None
            speed = None

        # Get magnetic field data
        mag_url = "https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json"
        mag_response = session.get(mag_url, timeout=10)
        bt = None
        bz = None

        if mag_response.status_code == 200:
            mag_data = mag_response.json()
            if mag_data and len(mag_data) >= 2:
                # Header: ["time_tag", "bt", "bz", "phi", "theta"]
                latest_mag = mag_data[-1]
                if len(latest_mag) >= 3:
                    bt = float(latest_mag[1]) if latest_mag[1] else None
                    bz = float(latest_mag[2]) if latest_mag[2] else None

        return {
            "solar_wind_speed": speed,
            "solar_wind_bt": bt,
            "solar_wind_bz": bz,
            "solar_wind_density": density,
        }
    except Exception as e:
        logger.debug(f"Error fetching solar wind data: {e}")
        return {}


def get_goes_xray_data() -> dict[str, float | str | None]:
    """
    Fetch GOES X-ray flux data from NOAA SWPC.

    Returns:
        Dictionary with xray_flux, xray_class
    """
    try:
        session = _get_cached_session()

        # GOES XRS report
        url = "https://services.swpc.noaa.gov/json/goes/goes-xrs-report.json"
        response = session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data:
            return {}

        # Find the most recent entry
        latest = None
        latest_time = None

        for entry in data:
            if isinstance(entry, dict):
                time_str = entry.get("time_tag")
                if time_str:
                    try:
                        # Parse time (format varies, try common formats)
                        entry_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                        if latest_time is None or entry_time > latest_time:
                            latest_time = entry_time
                            latest = entry
                    except (ValueError, AttributeError):
                        continue

        if latest:
            flux = latest.get("flux")
            xray_class = latest.get("class")

            # Convert flux to float if it's a string
            xray_flux = None
            if flux:
                with contextlib.suppress(ValueError, TypeError):
                    xray_flux = float(flux)

            xray_class_str: str | None = None
            if xray_class:
                xray_class_str = str(xray_class)

            return {
                "xray_flux": xray_flux,
                "xray_class": xray_class_str,
            }

        return {}
    except Exception as e:
        logger.debug(f"Error fetching GOES X-ray data: {e}")
        return {}


def get_kp_ap_data() -> dict[str, float | None]:
    """
    Fetch current Kp and Ap indices from NOAA SWPC.

    Returns:
        Dictionary with kp_index, ap_index
    """
    try:
        session = _get_cached_session()

        # Kp forecast includes current observed values
        url = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
        response = session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data or len(data) < 2:
            return {}

        # Find the most recent observed value
        latest_kp = None
        latest_time = None

        for row in data[1:]:  # Skip header
            if len(row) >= 3:
                try:
                    time_str = row[0]
                    kp_str = row[1]
                    observed = row[2] if len(row) > 2 else None

                    if observed and observed.lower() == "observed":
                        entry_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                        if latest_time is None or entry_time > latest_time:
                            latest_time = entry_time
                            latest_kp = float(kp_str)
                except (ValueError, IndexError, TypeError):
                    continue

        return {"kp_index": latest_kp}
    except Exception as e:
        logger.debug(f"Error fetching Kp/Ap data: {e}")
        return {}


def get_space_weather_conditions() -> SpaceWeatherConditions:
    """
    Fetch current space weather conditions from NOAA SWPC.

    Returns:
        SpaceWeatherConditions object with current data
    """
    conditions = SpaceWeatherConditions(last_updated=datetime.now(UTC))

    # Fetch solar wind data
    solar_wind = get_solar_wind_data()
    conditions.solar_wind_speed = solar_wind.get("solar_wind_speed")
    conditions.solar_wind_bt = solar_wind.get("solar_wind_bt")
    conditions.solar_wind_bz = solar_wind.get("solar_wind_bz")
    conditions.solar_wind_density = solar_wind.get("solar_wind_density")

    # Fetch X-ray data
    xray_data = get_goes_xray_data()
    xray_flux_val = xray_data.get("xray_flux")
    xray_class_val = xray_data.get("xray_class")
    if isinstance(xray_flux_val, float):
        conditions.xray_flux = xray_flux_val
    if isinstance(xray_class_val, str):
        conditions.xray_class = xray_class_val

    # Fetch Kp index
    kp_data = get_kp_ap_data()
    conditions.kp_index = kp_data.get("kp_index")

    # Determine NOAA scales from Kp index and X-ray class
    # G-scale from Kp: G1 (Kp=5), G2 (Kp=6), G3 (Kp=7), G4 (Kp=8), G5 (Kp=9)
    if conditions.kp_index is not None:
        kp = conditions.kp_index
        if kp >= 9:
            conditions.g_scale = NOAAScale(level=5, scale_type="G", description="Extreme geomagnetic storm")
        elif kp >= 8:
            conditions.g_scale = NOAAScale(level=4, scale_type="G", description="Severe geomagnetic storm")
        elif kp >= 7:
            conditions.g_scale = NOAAScale(level=3, scale_type="G", description="Strong geomagnetic storm")
        elif kp >= 6:
            conditions.g_scale = NOAAScale(level=2, scale_type="G", description="Moderate geomagnetic storm")
        elif kp >= 5:
            conditions.g_scale = NOAAScale(level=1, scale_type="G", description="Minor geomagnetic storm")
        else:
            conditions.g_scale = NOAAScale(level=0, scale_type="G", description="Quiet conditions")

    # R-scale from X-ray class: R1 (M1), R2 (M5), R3 (X1), R4 (X10), R5 (X20)
    if conditions.xray_class:
        xray_class = conditions.xray_class.upper()
        if xray_class.startswith("X"):
            try:
                x_value = float(xray_class[1:])
                if x_value >= 20:
                    conditions.r_scale = NOAAScale(level=5, scale_type="R", description="Extreme radio blackout")
                elif x_value >= 10:
                    conditions.r_scale = NOAAScale(level=4, scale_type="R", description="Severe radio blackout")
                elif x_value >= 1:
                    conditions.r_scale = NOAAScale(level=3, scale_type="R", description="Strong radio blackout")
            except ValueError:
                pass
        elif xray_class.startswith("M"):
            try:
                m_value = float(xray_class[1:])
                if m_value >= 5:
                    conditions.r_scale = NOAAScale(level=2, scale_type="R", description="Moderate radio blackout")
                elif m_value >= 1:
                    conditions.r_scale = NOAAScale(level=1, scale_type="R", description="Minor radio blackout")
            except ValueError:
                pass

    # Generate alerts based on conditions
    # Ensure alerts list is initialized
    alerts_list: list[str] = conditions.alerts if conditions.alerts is not None else []
    if conditions.alerts is None:
        object.__setattr__(conditions, "alerts", alerts_list)

    if conditions.g_scale and conditions.g_scale.level >= 3:
        alerts_list.append(f"G{conditions.g_scale.level} geomagnetic storm - Enhanced aurora possible")
    if conditions.r_scale and conditions.r_scale.level >= 3:
        alerts_list.append(f"R{conditions.r_scale.level} radio blackout - GPS/communications may be affected")
    if conditions.solar_wind_speed and conditions.solar_wind_speed > 600:
        alerts_list.append("High solar wind speed detected")

    return conditions
