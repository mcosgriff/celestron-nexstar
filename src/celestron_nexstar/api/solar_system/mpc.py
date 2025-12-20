"""
MPC comet element fetching and parsing utilities.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import aiohttp


MPC_COMET_URL = "https://minorplanetcenter.net/iau/Ephemerides/Comets/Soft00Cmt.txt"


async def fetch_mpc_comets_async(max_magnitude: float = 12.0, limit: int | None = None) -> list[dict[str, Any]]:
    """Fetch comet orbital elements from MPC asynchronously."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(MPC_COMET_URL, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    return []
                text = await response.text()
                parsed = parse_mpc_comet_data(text, max_magnitude=max_magnitude)
                if limit and len(parsed) > limit:
                    return parsed[:limit]
                return parsed
        except Exception:
            return []


def fetch_mpc_comets(max_magnitude: float = 12.0, limit: int | None = None) -> list[dict[str, Any]]:
    """Fetch comet orbital elements from MPC (synchronous wrapper)."""
    return asyncio.run(fetch_mpc_comets_async(max_magnitude=max_magnitude, limit=limit))


def parse_mpc_comet_data(text: str, max_magnitude: float = 12.0) -> list[dict[str, Any]]:
    """
    Parse MPC comet data format.

    Format documentation: https://minorplanetcenter.net/iau/info/CometOrbitFormat.html
    """
    comets: list[dict[str, Any]] = []
    lines = text.strip().split("\n")

    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue

        try:
            parts = line.split()
            if len(parts) < 12:
                continue

            q = float(parts[4])  # Perihelion distance in AU
            e = float(parts[5])  # Eccentricity
            inclination_deg = float(parts[6])
            arg_peri_deg = float(parts[7])
            ascending_node_deg = float(parts[8])
            t_yyyymmdd = parts[9]  # Time of perihelion as YYYYMMDD
            absolute_magnitude_h = float(parts[10])  # Absolute magnitude H
            slope_g = float(parts[11]) if len(parts) > 11 else None

            if len(t_yyyymmdd) == 8:
                t_year = int(t_yyyymmdd[:4])
                t_month = int(t_yyyymmdd[4:6])
                t_day = int(t_yyyymmdd[6:8])
            else:
                t_year = int(parts[1])
                t_month = int(parts[2])
                t_day = int(float(parts[3]))

            perihelion_dt = datetime(t_year, t_month, t_day, tzinfo=UTC)

            if len(parts) > 12:
                full_name_parts = parts[12:-1] if len(parts) > 13 else parts[12:]
                designation = " ".join(full_name_parts)
            else:
                designation = parts[0]

            peak_magnitude = absolute_magnitude_h + 5.0  # rough estimate
            if peak_magnitude > max_magnitude:
                continue

            is_periodic = e < 1.0
            period_years = None
            semi_major_axis_au = None
            if is_periodic:
                semi_major_axis_au = q / (1 - e) if (1 - e) != 0 else None
                if semi_major_axis_au:
                    period_years = (semi_major_axis_au**3) ** 0.5

            name = designation

            comet = {
                "name": name,
                "designation": designation,
                "perihelion_date": perihelion_dt.isoformat(),
                "perihelion_time": perihelion_dt.isoformat(),
                "perihelion_distance_au": q,
                "eccentricity": e,
                "inclination_deg": inclination_deg,
                "arg_perihelion_deg": arg_peri_deg,
                "ascending_node_deg": ascending_node_deg,
                "semi_major_axis_au": semi_major_axis_au,
                "absolute_magnitude_h": absolute_magnitude_h,
                "slope_g": slope_g,
                "peak_magnitude": peak_magnitude,
                "peak_date": perihelion_dt.isoformat(),
                "is_periodic": is_periodic,
                "period_years": period_years,
                "notes": f"Orbital data from MPC. Eccentricity: {e:.3f}",
                "source": "MPC Soft00Cmt",
            }

            comets.append(comet)
        except (ValueError, IndexError):
            continue

    return comets
