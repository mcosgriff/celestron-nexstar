"""
Database Statistics Functions

Functions for aggregating and retrieving database statistics.
These functions are designed to be reusable across CLI, GUI, and other interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Row, func, select, text

from celestron_nexstar.api.database.models import (
    LightPollutionGridModel,
    TLEModel,
    get_db_session,
)


@dataclass
class LightPollutionStats:
    """Statistics for light pollution data."""

    table_exists: bool
    total_count: int | None
    sqm_min: float | None
    sqm_max: float | None
    region_counts: list[Row[tuple[str | None, int]]] | None


@dataclass
class TLEStats:
    """Statistics for TLE (satellite) data."""

    table_exists: bool
    total_count: int | None
    unique_satellites: int | None
    group_counts: list[Row[tuple[str | None, int]]] | None
    last_fetched: datetime | None
    oldest_epoch: datetime | None
    newest_epoch: datetime | None


async def get_light_pollution_stats() -> LightPollutionStats:
    """
    Get statistics for light pollution grid data.

    Returns:
        LightPollutionStats with aggregated statistics
    """
    async with get_db_session() as db_session:
        # Check if table exists
        table_check = await db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='light_pollution_grid'")
        )
        table_exists = table_check.fetchone() is not None

        if not table_exists:
            return LightPollutionStats(
                table_exists=False,
                total_count=None,
                sqm_min=None,
                sqm_max=None,
                region_counts=None,
            )

        # Get total count
        total_count_result = await db_session.scalar(select(func.count(LightPollutionGridModel.id)))
        total_count = total_count_result or 0

        if total_count == 0:
            return LightPollutionStats(
                table_exists=True,
                total_count=0,
                sqm_min=None,
                sqm_max=None,
                region_counts=None,
            )

        # Get SQM range
        sqm_result = await db_session.execute(
            select(
                func.min(LightPollutionGridModel.sqm_value),
                func.max(LightPollutionGridModel.sqm_value),
            )
        )
        sqm_range = sqm_result.fetchone()
        if sqm_range is not None:
            sqm_min = sqm_range[0] if sqm_range[0] is not None else None
            sqm_max = sqm_range[1] if sqm_range[1] is not None else None
        else:
            sqm_min = None
            sqm_max = None

        # Get coverage by region
        region_result = await db_session.execute(
            select(
                LightPollutionGridModel.region,
                func.count(LightPollutionGridModel.id),
            )
            .where(LightPollutionGridModel.region.isnot(None))
            .group_by(LightPollutionGridModel.region)
            .order_by(LightPollutionGridModel.region)
        )
        region_counts = list(region_result.fetchall())

        return LightPollutionStats(
            table_exists=True,
            total_count=total_count,
            sqm_min=sqm_min,
            sqm_max=sqm_max,
            region_counts=region_counts,
        )


async def get_tle_stats() -> TLEStats:
    """
    Get statistics for TLE (satellite orbital elements) data.

    Returns:
        TLEStats with aggregated statistics
    """
    async with get_db_session() as db_session:
        # Check if table exists
        table_check = await db_session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='tle_data'")
        )
        table_exists = table_check.fetchone() is not None

        if not table_exists:
            return TLEStats(
                table_exists=False,
                total_count=None,
                unique_satellites=None,
                group_counts=None,
                last_fetched=None,
                oldest_epoch=None,
                newest_epoch=None,
            )

        total_tle_result = await db_session.scalar(select(func.count(TLEModel.norad_id)))
        total_tle_count = total_tle_result or 0

        if total_tle_count == 0:
            return TLEStats(
                table_exists=True,
                total_count=0,
                unique_satellites=0,
                group_counts=None,
                last_fetched=None,
                oldest_epoch=None,
                newest_epoch=None,
            )

        # Get counts by group
        group_result = await db_session.execute(
            select(
                TLEModel.satellite_group,
                func.count(TLEModel.norad_id),
            )
            .where(TLEModel.satellite_group.isnot(None))
            .group_by(TLEModel.satellite_group)
            .order_by(TLEModel.satellite_group)
        )
        group_counts = list(group_result.fetchall())

        # Get unique satellite count
        unique_result = await db_session.scalar(select(func.count(func.distinct(TLEModel.norad_id))))
        unique_satellites = unique_result or 0

        # Get last fetched time
        last_fetched_result = await db_session.scalar(
            select(func.max(TLEModel.fetched_at)).where(TLEModel.fetched_at.isnot(None))
        )
        last_fetched = last_fetched_result

        # Get oldest and newest TLE epoch (to show data freshness)
        oldest_result = await db_session.scalar(select(func.min(TLEModel.epoch)).where(TLEModel.epoch.isnot(None)))
        oldest_epoch = oldest_result
        newest_result = await db_session.scalar(select(func.max(TLEModel.epoch)).where(TLEModel.epoch.isnot(None)))
        newest_epoch = newest_result

        return TLEStats(
            table_exists=True,
            total_count=total_tle_count,
            unique_satellites=unique_satellites,
            group_counts=group_counts,
            last_fetched=last_fetched,
            oldest_epoch=oldest_epoch,
            newest_epoch=newest_epoch,
        )
