"""
Equipment Management

Manages user's astronomical equipment (eyepieces, filters, cameras) with
field of view calculations and usage tracking.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from celestron_nexstar.api.database.database import get_database
from celestron_nexstar.api.database.models import CameraModel, EyepieceModel, FilterModel
from celestron_nexstar.api.observation.optics import EyepieceSpecs, get_telescope_specs


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

__all__ = [
    "add_camera",
    "add_eyepiece",
    "add_filter",
    "calculate_fov",
    "delete_camera",
    "delete_eyepiece",
    "delete_filter",
    "get_cameras",
    "get_eyepieces",
    "get_filters",
    "update_camera",
    "update_eyepiece",
    "update_filter",
]


async def add_eyepiece(
    name: str,
    focal_length_mm: float,
    apparent_fov_deg: float = 50.0,
    barrel_size_mm: float | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    notes: str | None = None,
) -> int | None:
    """
    Add a new eyepiece to the catalog.

    Args:
        name: Eyepiece name
        focal_length_mm: Focal length in millimeters
        apparent_fov_deg: Apparent field of view in degrees (default: 50.0)
        barrel_size_mm: Barrel size in mm (1.25" = 31.75mm, 2" = 50.8mm)
        manufacturer: Manufacturer name
        model: Model number/name
        notes: Optional notes

    Returns:
        ID of created eyepiece, or None if creation failed
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            eyepiece = EyepieceModel(
                name=name,
                focal_length_mm=focal_length_mm,
                apparent_fov_deg=apparent_fov_deg,
                barrel_size_mm=barrel_size_mm,
                manufacturer=manufacturer,
                model=model,
                notes=notes,
            )
            session.add(eyepiece)
            await session.commit()
            await session.refresh(eyepiece)
            logger.info(f"Added eyepiece: {name}")
            return eyepiece.id
    except Exception as e:
        logger.error(f"Error adding eyepiece: {e}", exc_info=True)
        return None


async def get_eyepieces() -> list[dict[str, Any]]:
    """
    Get all eyepieces.

    Returns:
        List of eyepiece dictionaries
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            stmt = select(EyepieceModel).order_by(EyepieceModel.focal_length_mm)
            result = await session.execute(stmt)
            eyepieces = result.scalars().all()

            return [
                {
                    "id": ep.id,
                    "name": ep.name,
                    "focal_length_mm": ep.focal_length_mm,
                    "apparent_fov_deg": ep.apparent_fov_deg,
                    "barrel_size_mm": ep.barrel_size_mm,
                    "manufacturer": ep.manufacturer,
                    "model": ep.model,
                    "notes": ep.notes,
                    "usage_count": ep.usage_count,
                    "last_used_at": ep.last_used_at,
                    "created_at": ep.created_at,
                }
                for ep in eyepieces
            ]
    except Exception as e:
        logger.error(f"Error getting eyepieces: {e}", exc_info=True)
        return []


async def update_eyepiece(
    eyepiece_id: int,
    name: str | None = None,
    focal_length_mm: float | None = None,
    apparent_fov_deg: float | None = None,
    barrel_size_mm: float | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    notes: str | None = None,
) -> bool:
    """
    Update an existing eyepiece.

    Args:
        eyepiece_id: ID of eyepiece to update
        name: New name (if provided)
        focal_length_mm: New focal length (if provided)
        apparent_fov_deg: New apparent FOV (if provided)
        barrel_size_mm: New barrel size (if provided)
        manufacturer: New manufacturer (if provided)
        model: New model (if provided)
        notes: New notes (if provided)

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            stmt = select(EyepieceModel).where(EyepieceModel.id == eyepiece_id)
            result = await session.execute(stmt)
            eyepiece = result.scalar_one_or_none()

            if not eyepiece:
                logger.warning(f"Eyepiece {eyepiece_id} not found")
                return False

            if name is not None:
                eyepiece.name = name
            if focal_length_mm is not None:
                eyepiece.focal_length_mm = focal_length_mm
            if apparent_fov_deg is not None:
                eyepiece.apparent_fov_deg = apparent_fov_deg
            if barrel_size_mm is not None:
                eyepiece.barrel_size_mm = barrel_size_mm
            if manufacturer is not None:
                eyepiece.manufacturer = manufacturer
            if model is not None:
                eyepiece.model = model
            if notes is not None:
                eyepiece.notes = notes

            eyepiece.updated_at = datetime.now(UTC)
            await session.commit()
            logger.info(f"Updated eyepiece {eyepiece_id}")
            return True
    except Exception as e:
        logger.error(f"Error updating eyepiece: {e}", exc_info=True)
        return False


async def delete_eyepiece(eyepiece_id: int) -> bool:
    """
    Delete an eyepiece.

    Args:
        eyepiece_id: ID of eyepiece to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            stmt = select(EyepieceModel).where(EyepieceModel.id == eyepiece_id)
            result = await session.execute(stmt)
            eyepiece = result.scalar_one_or_none()

            if not eyepiece:
                logger.warning(f"Eyepiece {eyepiece_id} not found")
                return False

            await session.delete(eyepiece)
            await session.commit()
            logger.info(f"Deleted eyepiece {eyepiece_id}")
            return True
    except Exception as e:
        logger.error(f"Error deleting eyepiece: {e}", exc_info=True)
        return False


async def add_filter(
    name: str,
    filter_type: str,
    barrel_size_mm: float | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    transmission_percent: float | None = None,
    notes: str | None = None,
) -> int | None:
    """
    Add a new filter to the catalog.

    Args:
        name: Filter name
        filter_type: Filter type (UHC, O-III, H-beta, color, etc.)
        barrel_size_mm: Barrel size in mm (1.25" = 31.75mm, 2" = 50.8mm)
        manufacturer: Manufacturer name
        model: Model number/name
        transmission_percent: Light transmission percentage
        notes: Optional notes

    Returns:
        ID of created filter, or None if creation failed
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            filter_obj = FilterModel(
                name=name,
                filter_type=filter_type,
                barrel_size_mm=barrel_size_mm,
                manufacturer=manufacturer,
                model=model,
                transmission_percent=transmission_percent,
                notes=notes,
            )
            session.add(filter_obj)
            await session.commit()
            await session.refresh(filter_obj)
            logger.info(f"Added filter: {name}")
            return filter_obj.id
    except Exception as e:
        logger.error(f"Error adding filter: {e}", exc_info=True)
        return None


async def get_filters() -> list[dict[str, Any]]:
    """
    Get all filters.

    Returns:
        List of filter dictionaries
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            stmt = select(FilterModel).order_by(FilterModel.name)
            result = await session.execute(stmt)
            filters = result.scalars().all()

            return [
                {
                    "id": f.id,
                    "name": f.name,
                    "filter_type": f.filter_type,
                    "barrel_size_mm": f.barrel_size_mm,
                    "manufacturer": f.manufacturer,
                    "model": f.model,
                    "transmission_percent": f.transmission_percent,
                    "notes": f.notes,
                    "usage_count": f.usage_count,
                    "last_used_at": f.last_used_at,
                    "created_at": f.created_at,
                }
                for f in filters
            ]
    except Exception as e:
        logger.error(f"Error getting filters: {e}", exc_info=True)
        return []


async def update_filter(
    filter_id: int,
    name: str | None = None,
    filter_type: str | None = None,
    barrel_size_mm: float | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    transmission_percent: float | None = None,
    notes: str | None = None,
) -> bool:
    """
    Update an existing filter.

    Args:
        filter_id: ID of filter to update
        name: New name (if provided)
        filter_type: New filter type (if provided)
        barrel_size_mm: New barrel size (if provided)
        manufacturer: New manufacturer (if provided)
        model: New model (if provided)
        transmission_percent: New transmission (if provided)
        notes: New notes (if provided)

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            stmt = select(FilterModel).where(FilterModel.id == filter_id)
            result = await session.execute(stmt)
            filter_obj = result.scalar_one_or_none()

            if not filter_obj:
                logger.warning(f"Filter {filter_id} not found")
                return False

            if name is not None:
                filter_obj.name = name
            if filter_type is not None:
                filter_obj.filter_type = filter_type
            if barrel_size_mm is not None:
                filter_obj.barrel_size_mm = barrel_size_mm
            if manufacturer is not None:
                filter_obj.manufacturer = manufacturer
            if model is not None:
                filter_obj.model = model
            if transmission_percent is not None:
                filter_obj.transmission_percent = transmission_percent
            if notes is not None:
                filter_obj.notes = notes

            filter_obj.updated_at = datetime.now(UTC)
            await session.commit()
            logger.info(f"Updated filter {filter_id}")
            return True
    except Exception as e:
        logger.error(f"Error updating filter: {e}", exc_info=True)
        return False


async def delete_filter(filter_id: int) -> bool:
    """
    Delete a filter.

    Args:
        filter_id: ID of filter to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            stmt = select(FilterModel).where(FilterModel.id == filter_id)
            result = await session.execute(stmt)
            filter_obj = result.scalar_one_or_none()

            if not filter_obj:
                logger.warning(f"Filter {filter_id} not found")
                return False

            await session.delete(filter_obj)
            await session.commit()
            logger.info(f"Deleted filter {filter_id}")
            return True
    except Exception as e:
        logger.error(f"Error deleting filter: {e}", exc_info=True)
        return False


async def add_camera(
    name: str,
    sensor_width_mm: float,
    sensor_height_mm: float,
    pixel_width_um: float | None = None,
    pixel_height_um: float | None = None,
    resolution_width: int | None = None,
    resolution_height: int | None = None,
    camera_type: str = "DSLR",
    manufacturer: str | None = None,
    model: str | None = None,
    notes: str | None = None,
) -> int | None:
    """
    Add a new camera to the catalog.

    Args:
        name: Camera name
        sensor_width_mm: Sensor width in millimeters
        sensor_height_mm: Sensor height in millimeters
        pixel_width_um: Pixel width in micrometers
        pixel_height_um: Pixel height in micrometers
        resolution_width: Resolution width in pixels
        resolution_height: Resolution height in pixels
        camera_type: Camera type (DSLR, CCD, CMOS, etc.)
        manufacturer: Manufacturer name
        model: Model number/name
        notes: Optional notes

    Returns:
        ID of created camera, or None if creation failed
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            camera = CameraModel(
                name=name,
                sensor_width_mm=sensor_width_mm,
                sensor_height_mm=sensor_height_mm,
                pixel_width_um=pixel_width_um,
                pixel_height_um=pixel_height_um,
                resolution_width=resolution_width,
                resolution_height=resolution_height,
                camera_type=camera_type,
                manufacturer=manufacturer,
                model=model,
                notes=notes,
            )
            session.add(camera)
            await session.commit()
            await session.refresh(camera)
            logger.info(f"Added camera: {name}")
            return camera.id
    except Exception as e:
        logger.error(f"Error adding camera: {e}", exc_info=True)
        return None


async def get_cameras() -> list[dict[str, Any]]:
    """
    Get all cameras.

    Returns:
        List of camera dictionaries
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            stmt = select(CameraModel).order_by(CameraModel.name)
            result = await session.execute(stmt)
            cameras = result.scalars().all()

            return [
                {
                    "id": cam.id,
                    "name": cam.name,
                    "sensor_width_mm": cam.sensor_width_mm,
                    "sensor_height_mm": cam.sensor_height_mm,
                    "pixel_width_um": cam.pixel_width_um,
                    "pixel_height_um": cam.pixel_height_um,
                    "resolution_width": cam.resolution_width,
                    "resolution_height": cam.resolution_height,
                    "camera_type": cam.camera_type,
                    "manufacturer": cam.manufacturer,
                    "model": cam.model,
                    "notes": cam.notes,
                    "usage_count": cam.usage_count,
                    "last_used_at": cam.last_used_at,
                    "created_at": cam.created_at,
                }
                for cam in cameras
            ]
    except Exception as e:
        logger.error(f"Error getting cameras: {e}", exc_info=True)
        return []


async def update_camera(
    camera_id: int,
    name: str | None = None,
    sensor_width_mm: float | None = None,
    sensor_height_mm: float | None = None,
    pixel_width_um: float | None = None,
    pixel_height_um: float | None = None,
    resolution_width: int | None = None,
    resolution_height: int | None = None,
    camera_type: str | None = None,
    manufacturer: str | None = None,
    model: str | None = None,
    notes: str | None = None,
) -> bool:
    """
    Update an existing camera.

    Args:
        camera_id: ID of camera to update
        name: New name (if provided)
        sensor_width_mm: New sensor width (if provided)
        sensor_height_mm: New sensor height (if provided)
        pixel_width_um: New pixel width (if provided)
        pixel_height_um: New pixel height (if provided)
        resolution_width: New resolution width (if provided)
        resolution_height: New resolution height (if provided)
        camera_type: New camera type (if provided)
        manufacturer: New manufacturer (if provided)
        model: New model (if provided)
        notes: New notes (if provided)

    Returns:
        True if updated successfully, False otherwise
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            stmt = select(CameraModel).where(CameraModel.id == camera_id)
            result = await session.execute(stmt)
            camera = result.scalar_one_or_none()

            if not camera:
                logger.warning(f"Camera {camera_id} not found")
                return False

            if name is not None:
                camera.name = name
            if sensor_width_mm is not None:
                camera.sensor_width_mm = sensor_width_mm
            if sensor_height_mm is not None:
                camera.sensor_height_mm = sensor_height_mm
            if pixel_width_um is not None:
                camera.pixel_width_um = pixel_width_um
            if pixel_height_um is not None:
                camera.pixel_height_um = pixel_height_um
            if resolution_width is not None:
                camera.resolution_width = resolution_width
            if resolution_height is not None:
                camera.resolution_height = resolution_height
            if camera_type is not None:
                camera.camera_type = camera_type
            if manufacturer is not None:
                camera.manufacturer = manufacturer
            if model is not None:
                camera.model = model
            if notes is not None:
                camera.notes = notes

            camera.updated_at = datetime.now(UTC)
            await session.commit()
            logger.info(f"Updated camera {camera_id}")
            return True
    except Exception as e:
        logger.error(f"Error updating camera: {e}", exc_info=True)
        return False


async def delete_camera(camera_id: int) -> bool:
    """
    Delete a camera.

    Args:
        camera_id: ID of camera to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    try:
        db = get_database()
        async with db._AsyncSession() as session:
            from sqlalchemy import select

            stmt = select(CameraModel).where(CameraModel.id == camera_id)
            result = await session.execute(stmt)
            camera = result.scalar_one_or_none()

            if not camera:
                logger.warning(f"Camera {camera_id} not found")
                return False

            await session.delete(camera)
            await session.commit()
            logger.info(f"Deleted camera {camera_id}")
            return True
    except Exception as e:
        logger.error(f"Error deleting camera: {e}", exc_info=True)
        return False


def calculate_fov(
    telescope_model: str | None = None,
    eyepiece_focal_length_mm: float | None = None,
    eyepiece_apparent_fov_deg: float = 50.0,
) -> dict[str, float | None]:
    """
    Calculate field of view for a telescope and eyepiece combination.

    Args:
        telescope_model: Telescope model (e.g., "nexstar_6se")
        eyepiece_focal_length_mm: Eyepiece focal length in mm
        eyepiece_apparent_fov_deg: Eyepiece apparent field of view in degrees

    Returns:
        Dictionary with magnification, exit_pupil_mm, true_fov_deg, true_fov_arcmin
    """
    try:
        if not telescope_model or not eyepiece_focal_length_mm:
            return {
                "magnification": None,
                "exit_pupil_mm": None,
                "true_fov_deg": None,
                "true_fov_arcmin": None,
            }

        # Convert string to TelescopeModel enum if needed
        from celestron_nexstar.api.observation.optics import TelescopeModel

        telescope_model_enum: TelescopeModel | None = None
        if telescope_model:
            try:
                telescope_model_enum = TelescopeModel(telescope_model)
            except (ValueError, TypeError):
                # Invalid telescope model string
                telescope_model_enum = None

        if telescope_model_enum is None:
            return {
                "magnification": None,
                "exit_pupil_mm": None,
                "true_fov_deg": None,
                "true_fov_arcmin": None,
            }

        telescope = get_telescope_specs(telescope_model_enum)
        eyepiece = EyepieceSpecs(focal_length_mm=eyepiece_focal_length_mm, apparent_fov_deg=eyepiece_apparent_fov_deg)

        magnification = eyepiece.magnification(telescope)
        exit_pupil = eyepiece.exit_pupil_mm(telescope)
        true_fov_deg = eyepiece.true_fov_deg(telescope)
        true_fov_arcmin = eyepiece.true_fov_arcmin(telescope)

        return {
            "magnification": magnification,
            "exit_pupil_mm": exit_pupil,
            "true_fov_deg": true_fov_deg,
            "true_fov_arcmin": true_fov_arcmin,
        }
    except Exception as e:
        logger.error(f"Error calculating FOV: {e}", exc_info=True)
        return {
            "magnification": None,
            "exit_pupil_mm": None,
            "true_fov_deg": None,
            "true_fov_arcmin": None,
        }
