"""
Main application window for telescope control.
"""

from __future__ import annotations

import contextlib
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPoint, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QActionGroup, QCursor, QFontMetrics, QGuiApplication, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QProgressDialog,
    QSizeGrip,
    QSizePolicy,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.core import format_local_time, get_local_timezone
from celestron_nexstar.api.core.enums import CelestialObjectType
from celestron_nexstar.api.location.observer import get_observer_location
from celestron_nexstar.gui.dialogs.gps_info_dialog import GPSInfoDialog
from celestron_nexstar.gui.dialogs.moon_info_dialog import MoonInfoDialog
from celestron_nexstar.gui.dialogs.time_info_dialog import TimeInfoDialog
from celestron_nexstar.gui.dialogs.weather_info_dialog import WeatherInfoDialog
from celestron_nexstar.gui.themes import FusionTheme, ThemeMode
from celestron_nexstar.gui.utils.table_utils import autosize_table_columns
from celestron_nexstar.gui.widgets.collapsible_log_panel import CollapsibleLogPanel
from celestron_nexstar.gui.widgets.debug_log_panel import DebugLogPanel
from celestron_nexstar.gui.workers.telescope_workers import (
    DisconnectThread,
    GetLocationThread,
    GetPositionRADecThread,
)


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope
    from celestron_nexstar.api.observation.observation_planner import RecommendedObject

logger = logging.getLogger(__name__)


class VisibilityCountThread(QThread):
    """Worker thread to count visible stars for constellations/asterisms in the background."""

    count_ready = Signal(str, int)  # type: ignore[type-arg,misc]  # Emits (name, count) for each item
    counts_complete = Signal()  # type: ignore[type-arg,misc]  # Emits when all counts are done

    def __init__(
        self,
        constellation_names: list[str],
        is_asterism: bool = False,
        asterism_objects: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the visibility count thread."""
        super().__init__()
        self.constellation_names = constellation_names
        self.is_asterism = is_asterism
        self.asterism_objects = asterism_objects or {}

    def run(self) -> None:
        """Count visible stars in background thread."""
        try:
            # Check if thread should stop
            if self.isInterruptionRequested():
                return

            from celestron_nexstar.api.core.enums import SkyBrightness
            from celestron_nexstar.api.core.exceptions import DatabaseError
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner
            from celestron_nexstar.api.observation.optics import get_current_configuration
            from celestron_nexstar.api.observation.visibility import assess_visibility

            # Get conditions
            location = get_observer_location()
            config = get_current_configuration()
            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()

            def _count_all_stars() -> None:
                db = get_database()

                # Get sky brightness from light pollution (single call outside the pool)
                try:
                    with db._get_session() as session:
                        light_pollution = get_light_pollution_data(session, location.latitude, location.longitude)
                    bortle_to_sky_brightness = {
                        1: SkyBrightness.EXCELLENT,
                        2: SkyBrightness.EXCELLENT,
                        3: SkyBrightness.GOOD,
                        4: SkyBrightness.FAIR,
                        5: SkyBrightness.FAIR,
                        6: SkyBrightness.POOR,
                        7: SkyBrightness.URBAN,
                        8: SkyBrightness.URBAN,
                        9: SkyBrightness.URBAN,
                    }
                    sky_brightness = bortle_to_sky_brightness.get(
                        light_pollution.bortle_class.value, SkyBrightness.FAIR
                    )
                except DatabaseError:
                    # Light pollution data not available, use default
                    logger.warning("Light pollution data not available, using default sky brightness")
                    sky_brightness = SkyBrightness.FAIR

                # Use a small pool to avoid starving other UI/DB work
                max_workers = max(2, min(4, (os.cpu_count() or 4)))

                if self.is_asterism:

                    def _count_asterism(name: str) -> tuple[str, int]:
                        if self.isInterruptionRequested():
                            return name, 0
                        asterism = self.asterism_objects.get(name)
                        if not asterism or not asterism.member_stars:
                            return name, 0
                        visible_count = 0
                        for star_name in asterism.member_stars:
                            star = db.get_by_name(star_name.strip())
                            if not star:
                                continue
                            try:
                                vis_info = assess_visibility(
                                    star,
                                    config=config,
                                    sky_brightness=sky_brightness,
                                    min_altitude_deg=20.0,
                                    observer_lat=location.latitude,
                                    observer_lon=location.longitude,
                                    dt=conditions.timestamp,
                                )
                                visibility_prob_result = planner._calculate_visibility_probability(
                                    star, conditions, vis_info
                                )
                                visibility_probability = (
                                    visibility_prob_result[0]
                                    if isinstance(visibility_prob_result, tuple)
                                    else visibility_prob_result
                                )
                                if visibility_probability > 0:
                                    visible_count += 1
                            except Exception:
                                continue
                        return name, visible_count

                    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="vis-asterism") as executor:
                        futures = {executor.submit(_count_asterism, name): name for name in self.constellation_names}
                        for future in as_completed(futures):
                            if self.isInterruptionRequested():
                                break
                            try:
                                name, count = future.result()
                                self.count_ready.emit(name, count)
                            except Exception:
                                continue
                else:

                    def _count_constellation(name: str) -> tuple[str, int]:
                        if self.isInterruptionRequested():
                            return name, 0
                        stars = db.filter_objects(object_type="star", constellation=name, limit=50)
                        visible_count = 0
                        for star in stars:
                            try:
                                vis_info = assess_visibility(
                                    star,
                                    config=config,
                                    sky_brightness=sky_brightness,
                                    min_altitude_deg=20.0,
                                    observer_lat=location.latitude,
                                    observer_lon=location.longitude,
                                    dt=conditions.timestamp,
                                )
                                visibility_prob_result = planner._calculate_visibility_probability(
                                    star, conditions, vis_info
                                )
                                visibility_probability = (
                                    visibility_prob_result[0]
                                    if isinstance(visibility_prob_result, tuple)
                                    else visibility_prob_result
                                )
                                if visibility_probability > 0:
                                    visible_count += 1
                            except Exception:
                                continue
                        return name, visible_count

                    with ThreadPoolExecutor(
                        max_workers=max_workers, thread_name_prefix="vis-constellation"
                    ) as executor:
                        futures = {
                            executor.submit(_count_constellation, name): name for name in self.constellation_names
                        }
                        for future in as_completed(futures):
                            if self.isInterruptionRequested():
                                break
                            try:
                                name, count = future.result()
                                self.count_ready.emit(name, count)
                            except Exception:
                                continue

            print(f"DEBUG: VisibilityCountThread starting count for {len(self.constellation_names)} items")
            _count_all_stars()
            print("DEBUG: VisibilityCountThread completed all counts")
            logger.info("VisibilityCountThread completed all counts")
            # Emit completion signal
            self.counts_complete.emit()
            print("DEBUG: VisibilityCountThread completion signal emitted")
        except Exception as e:
            logger.error(f"Error counting visible stars: {e}", exc_info=True)
            print(f"DEBUG: VisibilityCountThread error: {e}")
            # On error, just emit completion signal (individual errors are handled in the loop)
            self.counts_complete.emit()


class ObjectsLoaderThread(QThread):
    """Worker thread to load objects data in the background."""

    data_loaded = Signal(object, object)  # type: ignore[type-arg,misc]  # Emits (obj_type_str, objects_list)

    def __init__(self, obj_type_str: str) -> None:
        """Initialize the loader thread."""
        super().__init__()
        self.obj_type_str = obj_type_str

    def run(self) -> None:
        """Load objects data in background thread."""
        try:
            from celestron_nexstar.api.astronomy.constellations import get_visible_asterisms, get_visible_constellations
            from celestron_nexstar.api.core.enums import CelestialObjectType
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner

            obj_type = CelestialObjectType(self.obj_type_str)
            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()
            # Different object types produce different payload shapes (names vs tuples vs planner objects).
            # The downstream Qt signal accepts `object`, so keep this untyped here.
            objects: object

            # Special handling for constellation type: show constellations
            if obj_type == CelestialObjectType.CONSTELLATION:
                # Load visible constellations
                db = get_database()
                with db._get_session() as session:
                    constellations = get_visible_constellations(
                        session,
                        conditions.latitude,
                        conditions.longitude,
                        conditions.timestamp,
                        min_altitude_deg=20.0,
                    )
                # Convert to list of constellation names for display
                objects = [const[0].name for const in constellations]  # const[0] is the Constellation object
            elif obj_type == CelestialObjectType.ASTERISM:
                # Load visible asterisms
                # Use lower threshold (0°) to show all asterisms above horizon,
                # since asterisms are educational/reference items and circumpolar
                # ones like Big Dipper should always be visible
                db = get_database()
                with db._get_session() as session:
                    asterisms = get_visible_asterisms(
                        session,
                        conditions.latitude,
                        conditions.longitude,
                        conditions.timestamp,
                        min_altitude_deg=0.0,
                    )
                # Store full asterism objects (tuples of (Asterism, alt, az)) so we can access member_stars
                objects = asterisms  # Keep full objects for asterisms
            elif obj_type == CelestialObjectType.VARIABLE_STAR:
                # Load variable stars and convert to RecommendedObject format
                from celestron_nexstar.api.astronomy.solar_system import get_moon_info
                from celestron_nexstar.api.astronomy.variable_stars import get_known_variable_stars
                from celestron_nexstar.api.catalogs.catalogs import CelestialObject
                from celestron_nexstar.api.core.enums import CelestialObjectType, SkyBrightness
                from celestron_nexstar.api.core.exceptions import DatabaseError
                from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
                from celestron_nexstar.api.observation.observation_planner import RecommendedObject
                from celestron_nexstar.api.observation.optics import get_current_configuration
                from celestron_nexstar.api.observation.visibility import assess_visibility

                db = get_database()
                config = get_current_configuration()
                location = get_observer_location()
                moon_info = get_moon_info(location.latitude, location.longitude, conditions.timestamp)
                moon_ra = moon_info.ra_hours if moon_info else None
                moon_dec = moon_info.dec_degrees if moon_info else None

                with db._get_session() as session:
                    try:
                        variable_stars = get_known_variable_stars(session)
                    except DatabaseError as e:
                        logger.warning(f"No variable stars loaded: {e}")
                        self.data_loaded.emit(self.obj_type_str, [])
                        return
                    try:
                        light_pollution = get_light_pollution_data(session, location.latitude, location.longitude)
                        bortle_to_sky_brightness = {
                            1: SkyBrightness.EXCELLENT,
                            2: SkyBrightness.EXCELLENT,
                            3: SkyBrightness.GOOD,
                            4: SkyBrightness.FAIR,
                            5: SkyBrightness.FAIR,
                            6: SkyBrightness.POOR,
                            7: SkyBrightness.URBAN,
                            8: SkyBrightness.URBAN,
                            9: SkyBrightness.URBAN,
                        }
                        sky_brightness = bortle_to_sky_brightness.get(
                            light_pollution.bortle_class.value, SkyBrightness.FAIR
                        )
                    except DatabaseError:
                        # Light pollution data not available, use default
                        logger.warning("Light pollution data not available, using default sky brightness")
                        sky_brightness = SkyBrightness.FAIR

                    # Convert to RecommendedObject format
                    recommended_objects = []
                    for var_star in variable_stars:
                        # Use average magnitude for display
                        avg_mag = (var_star.magnitude_min + var_star.magnitude_max) / 2.0
                        obj = CelestialObject(
                            name=var_star.name,
                            common_name=var_star.designation,
                            catalog="variable",
                            ra_hours=var_star.ra_hours,
                            dec_degrees=var_star.dec_degrees,
                            magnitude=avg_mag,
                            object_type=CelestialObjectType.VARIABLE_STAR,
                            description=f"{var_star.variable_type} - Mag {var_star.magnitude_min:.1f} to {var_star.magnitude_max:.1f}, Period: {var_star.period_days:.1f} days. {var_star.notes}",
                            constellation=None,
                        )

                        # Calculate visibility
                        vis_info = assess_visibility(
                            obj,
                            config=config,
                            sky_brightness=sky_brightness,
                            min_altitude_deg=20.0,
                            observer_lat=location.latitude,
                            observer_lon=location.longitude,
                            dt=conditions.timestamp,
                        )

                        visibility_prob_result = planner._calculate_visibility_probability(obj, conditions, vis_info)
                        if isinstance(visibility_prob_result, tuple):
                            visibility_prob = visibility_prob_result[0]
                        else:
                            visibility_prob = visibility_prob_result

                        moon_sep = planner._calculate_moon_separation_fast(obj, moon_ra, moon_dec)

                        # Create RecommendedObject
                        rec_obj = RecommendedObject(
                            obj=obj,
                            altitude=vis_info.altitude_deg or 0.0,
                            azimuth=vis_info.azimuth_deg or 0.0,
                            best_viewing_time=conditions.timestamp,
                            visible_duration_hours=8.0,
                            apparent_magnitude=avg_mag,
                            observability_score=vis_info.observability_score,
                            visibility_probability=visibility_prob,
                            priority=1 if visibility_prob > 0.5 else 3,
                            reason=f"Variable star: {var_star.variable_type}",
                            viewing_tips=(),
                            moon_separation_deg=moon_sep,
                        )
                        recommended_objects.append(rec_obj)

                    # Sort by visibility probability
                    recommended_objects.sort(key=lambda x: -x.visibility_probability)
                    objects = recommended_objects[:100]  # Limit to 100
            elif obj_type == CelestialObjectType.MESSIER:
                # Load all Messier catalog objects (from galaxies, nebulae, clusters tables)
                from celestron_nexstar.api.astronomy.solar_system import get_moon_info
                from celestron_nexstar.api.core.enums import SkyBrightness
                from celestron_nexstar.api.core.exceptions import DatabaseError
                from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
                from celestron_nexstar.api.observation.observation_planner import RecommendedObject
                from celestron_nexstar.api.observation.optics import get_current_configuration
                from celestron_nexstar.api.observation.visibility import assess_visibility

                db = get_database()
                config = get_current_configuration()
                location = get_observer_location()
                moon_info = get_moon_info(location.latitude, location.longitude, conditions.timestamp)
                moon_ra = moon_info.ra_hours if moon_info else None
                moon_dec = moon_info.dec_degrees if moon_info else None

                with db._get_session() as session:
                    # Get sky brightness
                    try:
                        light_pollution = get_light_pollution_data(session, location.latitude, location.longitude)
                        bortle_to_sky_brightness = {
                            1: SkyBrightness.EXCELLENT,
                            2: SkyBrightness.EXCELLENT,
                            3: SkyBrightness.GOOD,
                            4: SkyBrightness.FAIR,
                            5: SkyBrightness.FAIR,
                            6: SkyBrightness.POOR,
                            7: SkyBrightness.URBAN,
                            8: SkyBrightness.URBAN,
                            9: SkyBrightness.URBAN,
                        }
                        sky_brightness = bortle_to_sky_brightness.get(
                            light_pollution.bortle_class.value, SkyBrightness.FAIR
                        )
                    except DatabaseError:
                        sky_brightness = SkyBrightness.FAIR

                    # Get all Messier objects
                    messier_objects = db.get_messier_objects(max_magnitude=None, limit=110)

                    # Calculate visibility for each
                    recommended_objects = []
                    for obj in messier_objects:
                        vis_info = assess_visibility(
                            obj,
                            config=config,
                            sky_brightness=sky_brightness,
                            min_altitude_deg=20.0,
                            observer_lat=location.latitude,
                            observer_lon=location.longitude,
                            dt=conditions.timestamp,
                        )

                        visibility_prob_result = planner._calculate_visibility_probability(obj, conditions, vis_info)
                        if isinstance(visibility_prob_result, tuple):
                            visibility_prob = visibility_prob_result[0]
                        else:
                            visibility_prob = visibility_prob_result

                        moon_sep = planner._calculate_moon_separation_fast(obj, moon_ra, moon_dec)

                        # Calculate priority based on magnitude and visibility
                        mag = obj.magnitude or 99.0
                        if mag < 6.0 and visibility_prob > 0.6:
                            priority = 1
                        elif mag < 9.0 and visibility_prob > 0.4:
                            priority = 2
                        elif visibility_prob > 0.3:
                            priority = 3
                        elif visibility_prob > 0.1:
                            priority = 4
                        else:
                            priority = 5

                        rec_obj = RecommendedObject(
                            obj=obj,
                            altitude=vis_info.altitude_deg or 0.0,
                            azimuth=vis_info.azimuth_deg or 0.0,
                            best_viewing_time=conditions.timestamp,
                            visible_duration_hours=8.0,
                            apparent_magnitude=mag,
                            observability_score=vis_info.observability_score,
                            visibility_probability=visibility_prob,
                            priority=priority,
                            reason=f"Messier {obj.name}",
                            viewing_tips=(),
                            moon_separation_deg=moon_sep,
                        )
                        recommended_objects.append(rec_obj)

                    objects = recommended_objects
            elif obj_type == CelestialObjectType.ZODIACAL:
                # Load zodiacal objects (objects along the ecliptic - in zodiac constellations or near ecliptic)
                from celestron_nexstar.api.core.enums import SkyBrightness
                from celestron_nexstar.api.core.exceptions import DatabaseError
                from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
                from celestron_nexstar.api.observation.observation_planner import RecommendedObject
                from celestron_nexstar.api.observation.optics import get_current_configuration
                from celestron_nexstar.api.observation.visibility import assess_visibility

                db = get_database()
                config = get_current_configuration()
                location = get_observer_location()

                # Zodiac constellations
                zodiac_constellations = [
                    "Aries",
                    "Taurus",
                    "Gemini",
                    "Cancer",
                    "Leo",
                    "Virgo",
                    "Libra",
                    "Scorpius",
                    "Sagittarius",
                    "Capricornus",
                    "Aquarius",
                    "Pisces",
                ]

                with db._get_session() as session:
                    try:
                        light_pollution = get_light_pollution_data(session, location.latitude, location.longitude)
                        bortle_to_sky_brightness = {
                            1: SkyBrightness.EXCELLENT,
                            2: SkyBrightness.EXCELLENT,
                            3: SkyBrightness.GOOD,
                            4: SkyBrightness.FAIR,
                            5: SkyBrightness.FAIR,
                            6: SkyBrightness.POOR,
                            7: SkyBrightness.URBAN,
                            8: SkyBrightness.URBAN,
                            9: SkyBrightness.URBAN,
                        }
                        sky_brightness = bortle_to_sky_brightness.get(
                            light_pollution.bortle_class.value, SkyBrightness.FAIR
                        )
                    except DatabaseError:
                        # Light pollution data not available, use default
                        logger.warning("Light pollution data not available, using default sky brightness")
                        sky_brightness = SkyBrightness.FAIR

                    # Get objects in zodiac constellations
                    all_objects = []
                    seen_names = set()
                    for const in zodiac_constellations:
                        catalog_objects = db.filter_objects(constellation=const, limit=50)
                        for obj in catalog_objects:
                            if obj.name not in seen_names:
                                all_objects.append(obj)
                                seen_names.add(obj.name)

                    # Also get objects near ecliptic (declination between -8 and +8 degrees)
                    all_db_objects = db.filter_objects(limit=500)
                    for obj in all_db_objects:
                        if -8.0 <= obj.dec_degrees <= 8.0 and obj.name not in seen_names:
                            all_objects.append(obj)
                            seen_names.add(obj.name)

                    # Convert to RecommendedObject format
                    recommended_objects = []
                    for obj in all_objects:
                        # Calculate visibility
                        vis_info = assess_visibility(
                            obj,
                            config=config,
                            sky_brightness=sky_brightness,
                            min_altitude_deg=20.0,
                            observer_lat=location.latitude,
                            observer_lon=location.longitude,
                            dt=conditions.timestamp,
                        )

                        visibility_prob_result = planner._calculate_visibility_probability(obj, conditions, vis_info)
                        if isinstance(visibility_prob_result, tuple):
                            visibility_prob = visibility_prob_result[0]
                        else:
                            visibility_prob = visibility_prob_result

                        # Create RecommendedObject
                        rec_obj = RecommendedObject(
                            obj=obj,
                            altitude=vis_info.altitude_deg or 0.0,
                            azimuth=vis_info.azimuth_deg or 0.0,
                            best_viewing_time=conditions.timestamp,
                            visible_duration_hours=8.0,
                            apparent_magnitude=obj.magnitude or 0.0,
                            observability_score=vis_info.observability_score,
                            visibility_probability=visibility_prob,
                            priority=1 if visibility_prob > 0.5 else 3,
                            reason=f"Zodiacal object in {obj.constellation or 'ecliptic region'}",
                            viewing_tips=(),
                        )
                        recommended_objects.append(rec_obj)

                    # Sort by visibility probability
                    recommended_objects.sort(key=lambda x: -x.visibility_probability)
                    objects = recommended_objects[:100]  # Limit to 100
            else:
                if obj_type in (
                    CelestialObjectType.GALAXY,
                    CelestialObjectType.NEBULA,
                    CelestialObjectType.CLUSTER,
                ):
                    # Start with visible recommendations
                    objects = planner.get_recommended_objects(
                        conditions, obj_type, max_results=150, best_for_seeing=False
                    )

                    # Augment with bright DSOs even if currently below horizon so marquee targets still show.
                    try:
                        from celestron_nexstar.api.core.enums import SkyBrightness
                        from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
                        from celestron_nexstar.api.observation.observation_planner import RecommendedObject
                        from celestron_nexstar.api.observation.optics import get_current_configuration
                        from celestron_nexstar.api.observation.visibility import assess_visibility

                        config = get_current_configuration()
                        location = get_observer_location()
                        db = get_database()
                        with db._get_session() as session:
                            lp = get_light_pollution_data(session, location.latitude, location.longitude)
                        bortle_to_sky_brightness = {
                            1: SkyBrightness.EXCELLENT,
                            2: SkyBrightness.EXCELLENT,
                            3: SkyBrightness.GOOD,
                            4: SkyBrightness.FAIR,
                            5: SkyBrightness.FAIR,
                            6: SkyBrightness.POOR,
                            7: SkyBrightness.URBAN,
                            8: SkyBrightness.URBAN,
                            9: SkyBrightness.URBAN,
                        }
                        sky_brightness = bortle_to_sky_brightness.get(
                            lp.bortle_class.value if lp and lp.bortle_class else 4, SkyBrightness.FAIR
                        )

                        existing_names = set()
                        for rec in objects or []:
                            existing_names.add(rec.obj.name.lower())
                            if rec.obj.common_name:
                                existing_names.add(rec.obj.common_name.lower())

                        extra_objects = db.filter_objects(
                            object_type=obj_type,
                            max_magnitude=18.0,
                            limit=800,
                        )

                        augmented: list[RecommendedObject] = list(objects)
                        for obj in extra_objects:
                            name_key = obj.name.lower()
                            common_key = obj.common_name.lower() if obj.common_name else None
                            if name_key in existing_names or (common_key and common_key in existing_names):
                                continue

                            vis_info = assess_visibility(
                                obj,
                                config=config,
                                sky_brightness=sky_brightness,
                                min_altitude_deg=0.0,  # allow below-horizon objects into the list
                                observer_lat=location.latitude if location else None,
                                observer_lon=location.longitude if location else None,
                                dt=conditions.timestamp,
                            )

                            visibility_prob_result = planner._calculate_visibility_probability(
                                obj, conditions, vis_info
                            )
                            if isinstance(visibility_prob_result, tuple):
                                visibility_prob = visibility_prob_result[0]
                            else:
                                visibility_prob = visibility_prob_result or 0.0

                            priority = (
                                planner._determine_priority(obj, conditions, vis_info) if vis_info.is_visible else 5
                            )
                            reason = " / ".join(vis_info.reasons) if vis_info.reasons else "Not currently visible"

                            augmented.append(
                                RecommendedObject(
                                    obj=obj,
                                    altitude=vis_info.altitude_deg or 0.0,
                                    azimuth=vis_info.azimuth_deg or 0.0,
                                    best_viewing_time=conditions.timestamp,
                                    visible_duration_hours=0.0,
                                    apparent_magnitude=obj.magnitude or 0.0,
                                    observability_score=vis_info.observability_score,
                                    visibility_probability=visibility_prob,
                                    priority=priority,
                                    reason=reason,
                                    viewing_tips=(),
                                    moon_separation_deg=None,
                                )
                            )

                            existing_names.add(name_key)
                            if common_key:
                                existing_names.add(common_key)

                        augmented.sort(
                            key=lambda r: (
                                -r.visibility_probability,
                                r.obj.magnitude if r.obj.magnitude is not None else 99.0,
                                r.obj.name,
                            )
                        )
                        objects = augmented[:200]
                    except Exception:
                        objects = planner.get_recommended_objects(
                            conditions, obj_type, max_results=150, best_for_seeing=False
                        )
                else:
                    # Get recommended objects for this type
                    objects = planner.get_recommended_objects(
                        conditions, obj_type, max_results=100, best_for_seeing=False
                    )

            # Emit signal with loaded data
            self.data_loaded.emit(self.obj_type_str, objects)

        except Exception as e:
            # Emit None to indicate error
            logger.error(f"Error loading objects for type {self.obj_type_str}: {e}", exc_info=True)
            self.data_loaded.emit(self.obj_type_str, None)


class ClickableLabel(QLabel):
    """A clickable QLabel that emits a clicked signal."""

    clicked = Signal()  # type: ignore[type-arg,misc]

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Handle mouse press event."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class FavoriteTableWidgetItem(QTableWidgetItem):
    """Custom QTableWidgetItem for favorites column that sorts by favorite status."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Compare items for sorting - favorites (1) come before non-favorites (0)."""
        # Get sort value from UserRole + 1 (1 = favorite, 0 = not favorite)
        self_val = self.data(Qt.ItemDataRole.UserRole + 1) or 0
        other_val = other.data(Qt.ItemDataRole.UserRole + 1) or 0
        return self_val < other_val


class VisibilityTableWidgetItem(QTableWidgetItem):
    """Custom QTableWidgetItem for visibility column that sorts by visibility status."""

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Compare items for sorting - Visible (0) < Marginal (1) < Not Visible (2)."""
        # Get sort value from UserRole + 1 (0 = Visible, 1 = Marginal, 2 = Not Visible)
        self_val = self.data(Qt.ItemDataRole.UserRole + 1) or 0
        other_val = other.data(Qt.ItemDataRole.UserRole + 1) or 0
        return self_val < other_val


class MainWindow(QMainWindow):
    """Main application window for telescope control."""

    def _create_icon(self, icon_name: str, fallback_theme_names: list[str] | None = None) -> QIcon:
        """Create an icon using FontAwesome icons (via qtawesome) with theme icon fallbacks."""
        # Detect theme for icon color
        from PySide6.QtGui import QGuiApplication, QPalette

        is_dark = False
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

        # Map icon names to FontAwesome icon names
        # Prefer outline versions where available
        icon_map: dict[str, str] = {
            # Telescope operations
            "link": "mdi.lan-connect",  # No outline version available
            "link_off": "mdi.lan-disconnect",  # No outline version available
            "my_location": "fa5s.map-marker-alt",  # FontAwesome Regular (outline)
            "tune": "mdi.cog-outline",
            "crosshairs": "mdi.crosshairs-gps",
            # Planning tools
            "catalog": "mdi.folder-outline",
            "dashboard": "mdi.view-dashboard-outline",
            "list": "mdi.playlist-play",
            "map": "mdi.map-outline",
            "weather": "mdi.weather-cloudy",  # No outline version available
            "moon": "mdi.moon-waning-crescent",
            "sky_darkness": "mdi.weather-night",
            "checklist": "mdi.check-circle-outline",
            "time_slots": "mdi.clock-outline",
            "quick_reference": "mdi.book-open-variant",
            "transit_times": "mdi.transit-connection",
            "glossary": "mdi.book-open-page-variant",
            "settings": "mdi.cog-outline",
            "star": "mdi.star-outline",
            "favorite": "mdi.star",
            "bookmark": "mdi.bookmark",
            # Celestial objects (using alpha-box-outline pattern)
            "aurora": "mdi.alpha-a-box-outline",
            "binoculars": "mdi.alpha-b-box-outline",
            "comets": "mdi.alpha-c-box-outline",
            "asteroids": "mdi.alpha-a-box-outline",
            "eclipse": "mdi.alpha-e-box-outline",
            "iss": "mdi.alpha-i-box-outline",
            "meteors": "mdi.alpha-m-box-outline",
            "milky_way": "mdi.alpha-m-box-outline",  # Same as meteors (both start with 'm')
            "naked_eye": "mdi.alpha-n-box-outline",
            "occultations": "mdi.alpha-o-box-outline",
            "planets": "mdi.alpha-p-box-outline",
            "satellites": "mdi.alpha-s-box-outline",
            "space_weather": "mdi.alpha-s-box-outline",  # Same as satellites (both start with 's')
            "variables": "mdi.alpha-v-box-outline",
            "zodiacal": "mdi.alpha-z-box-outline",
            # Legacy
            "event": "fa5s.calendar",  # FontAwesome Regular (outline)
            "menu_book": "fa5s.book",  # FontAwesome Regular (outline)
            # Table controls
            "refresh": "mdi.refresh",
            "info": "mdi.information-outline",
            "download": "mdi.download-outline",
            "close": "mdi.close-outline",
            "close-circle": "mdi.close-circle-outline",
            "check-circle": "mdi.check-circle",
            "check": "mdi.check",
            # Communication
            "console": "mdi.console",  # No outline version available
            "utilities-log-viewer": "mdi.information-outline",
            "chart": "mdi.chart-line",
            "graph": "mdi.chart-timeline-variant",
            "analytics": "mdi.chart-box",
            "compare": "mdi.compare",
            "diff": "mdi.diff",
        }

        # Try FontAwesome icons via qtawesome first
        try:
            import qtawesome as qta  # type: ignore[import-not-found,import-untyped]

            # Get the FontAwesome icon name
            fa_icon_name = icon_map.get(icon_name)
            if fa_icon_name:
                # Use theme-appropriate color for icons
                icon_color = "#ffffff" if is_dark else "#000000"

                # Try the specified icon first
                try:
                    icon = qta.icon(fa_icon_name, color=icon_color)
                    if not icon.isNull():
                        return QIcon(icon)  # Cast to QIcon to satisfy type checker
                except (ValueError, KeyError, AttributeError):
                    # Icon doesn't exist, try fallback
                    pass

                # If icon failed and it's a Material Design icon without -outline, try outline version
                if fa_icon_name.startswith("mdi.") and not fa_icon_name.endswith("-outline"):
                    outline_name = f"{fa_icon_name}-outline"
                    try:
                        icon = qta.icon(outline_name, color=icon_color)
                        if not icon.isNull():
                            return QIcon(icon)
                    except (ValueError, KeyError, AttributeError, TypeError):
                        pass

                # If icon failed and it's FontAwesome Solid (fa5s), try Regular (fa5r) outline version
                if fa_icon_name.startswith("fa5s."):
                    regular_name = fa_icon_name.replace("fa5s.", "fa5r.", 1)
                    try:
                        icon = qta.icon(regular_name, color=icon_color)
                        if not icon.isNull():
                            return QIcon(icon)
                    except (ValueError, KeyError, AttributeError, TypeError):
                        pass
        except (ImportError, AttributeError, ValueError, TypeError, KeyError) as e:
            # Log the error for debugging
            logger.debug(f"qtawesome icon failed for '{icon_name}': {e}")

        # Try theme icons as fallback
        if fallback_theme_names:
            for theme_name in fallback_theme_names:
                icon = QIcon.fromTheme(theme_name)
                if not icon.isNull():
                    return icon

        # Final fallback: use a Qt standard icon so we never end up with a blank menu icon
        # (macOS often has no useful theme icons; qtawesome may be missing in some envs).
        try:
            from PySide6.QtWidgets import QApplication, QStyle

            style = QApplication.style()
            if style is not None:
                standard_map: dict[str, QStyle.StandardPixmap] = {
                    # Common toolbar/menu actions
                    "weather": QStyle.StandardPixmap.SP_MessageBoxInformation,
                    "moon": QStyle.StandardPixmap.SP_DialogHelpButton,
                    "info": QStyle.StandardPixmap.SP_MessageBoxInformation,
                    "refresh": QStyle.StandardPixmap.SP_BrowserReload,
                    "download": QStyle.StandardPixmap.SP_DialogSaveButton,
                    "close": QStyle.StandardPixmap.SP_DialogCloseButton,
                    "settings": QStyle.StandardPixmap.SP_FileDialogDetailedView,
                }
                std = standard_map.get(icon_name)
                if std is not None:
                    return style.standardIcon(std)
        except Exception:
            pass

        # Fallback to empty icon (will show as blank button)
        return QIcon()

    def _create_favorite_item(self, is_favorite: bool) -> FavoriteTableWidgetItem:
        """Create a FavoriteTableWidgetItem with check icon for favorites, blank for non-favorites."""
        if is_favorite:
            # Create check icon for favorite (green checkmark)
            try:
                import qtawesome as qta  # type: ignore[import-not-found,import-untyped]

                check_icon = qta.icon("mdi.check-circle", color="#4caf50")  # Green
                if check_icon.isNull():
                    check_icon = self._create_icon("check-circle", ["check-circle", "check", "dialog-ok"])
                item = FavoriteTableWidgetItem(QIcon(check_icon), "")
            except Exception:
                # Fallback to uncolored icon
                check_icon = self._create_icon("check-circle", ["check-circle", "check", "dialog-ok"])
                item = FavoriteTableWidgetItem(check_icon, "")

            # Center align the icon
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        else:
            # Blank item for non-favorites (no icon, no text)
            item = FavoriteTableWidgetItem("")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        return item

    def _determine_visibility_status(self, altitude: float, visibility_probability: float) -> tuple[str, str]:
        """
        Determine visibility status based on altitude and visibility probability.

        Returns:
            Tuple of (status, color) where status is "Visible", "Marginal", or "Not Visible"
            and color is "green", "yellow", or "red"
        """
        # Consider both altitude and visibility probability
        if altitude >= 20.0 and visibility_probability >= 0.5:
            return ("Visible", "green")
        elif altitude >= 10.0 and visibility_probability >= 0.3:
            return ("Marginal", "yellow")
        else:
            return ("Not Visible", "red")

    def _create_visibility_item(self, altitude: float, visibility_probability: float) -> VisibilityTableWidgetItem:
        """Create a VisibilityTableWidgetItem with visibility indicator icon."""
        status, _color = self._determine_visibility_status(altitude, visibility_probability)

        try:
            import qtawesome as qta  # type: ignore[import-not-found,import-untyped]

            if status == "Visible":
                # Green checkmark
                icon = qta.icon("mdi.check-circle", color="#4caf50")  # Green
                if icon.isNull():
                    icon = self._create_icon("check-circle", ["check-circle", "check", "dialog-ok"])
            elif status == "Marginal":
                # Yellow warning
                icon = qta.icon("mdi.alert-circle", color="#ffc107")  # Yellow/Amber
                if icon.isNull():
                    icon = self._create_icon("dialog-warning", ["warning", "alert"])
            else:  # Not Visible
                # Red X
                icon = qta.icon("mdi.close-circle", color="#f44336")  # Red
                if icon.isNull():
                    icon = self._create_icon("dialog-cancel", ["cancel", "close"])

            item = VisibilityTableWidgetItem(QIcon(icon), status)
        except Exception:
            # Fallback to text-only with color
            if status == "Visible":
                icon = self._create_icon("check-circle", ["check-circle", "check", "dialog-ok"])
            elif status == "Marginal":
                icon = self._create_icon("dialog-warning", ["warning", "alert"])
            else:
                icon = self._create_icon("dialog-cancel", ["cancel", "close"])
            item = VisibilityTableWidgetItem(QIcon(icon), status)

        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        # Store status for sorting: 0 = Visible, 1 = Marginal, 2 = Not Visible
        sort_value = 0 if status == "Visible" else (1 if status == "Marginal" else 2)
        item.setData(Qt.ItemDataRole.UserRole + 1, sort_value)
        return item

    def __init__(self, theme: FusionTheme | None = None) -> None:
        """Initialize the main window."""
        super().__init__()
        self._catalog_window = None  # Store reference to catalog window
        self._goto_queue_window = None  # Store reference to goto queue window
        self._sky_map_window = None  # Store reference to sky map window
        self._zenith_star_chart_window = None  # Store reference to zenith star chart window
        self._comets_dialog = None  # Store reference to comets info dialog
        self._asteroids_dialog = None  # Store reference to asteroids info dialog
        self.setWindowTitle("Celestron NexStar Telescope Control")

        # Explicitly ensure window has decorations (titlebar, borders, etc.)
        # This is especially important on Wayland/COSMIC where decorations can be missing
        # Use Qt.Window which includes all standard decorations by default
        flags = Qt.WindowType.Window
        # Remove any frameless hints that might have been set
        flags &= ~Qt.WindowType.FramelessWindowHint
        # Ensure standard window decorations are present
        flags |= Qt.WindowType.WindowTitleHint
        flags |= Qt.WindowType.WindowMinimizeButtonHint
        flags |= Qt.WindowType.WindowMaximizeButtonHint
        flags |= Qt.WindowType.WindowCloseButtonHint
        flags |= Qt.WindowType.WindowSystemMenuHint
        self.setWindowFlags(flags)

        self.setMinimumSize(900, 600)  # Increased width by 100px to accommodate all tabs without scrolling
        # Set the initial size wider than a minimum to ensure tabs are visible without scrolling
        self.resize(1050, 700)

        # Telescope connection state
        self.telescope: NexStarTelescope | None = None

        # Cache for loaded objects data (key: obj_type_str, value: list of objects)
        # Can be list[RecommendedObject] or list[str] for constellations/asterisms
        self._objects_cache: dict[str, list[RecommendedObject] | list[str]] = {}
        self._asterism_objects_cache: dict[str, Any] = {}  # Cache asterism objects for member_stars access

        # Track loading threads to prevent duplicate loads
        self._loading_threads: dict[str, ObjectsLoaderThread] = {}
        # Track visibility counting threads to prevent premature destruction
        self._visibility_threads: dict[QTableWidget, VisibilityCountThread] = {}
        # Keep references to threads that are shutting down so Python/Qt doesn't destroy them mid-run.
        self._stopping_threads: list[QThread] = []
        # Track telescope worker threads
        self._position_thread: GetPositionRADecThread | None = None
        self._location_thread: GetLocationThread | None = None
        self._disconnect_thread: DisconnectThread | None = None

        # Initialize theme (use provided theme or create default)
        if theme is None:
            from PySide6.QtWidgets import QApplication

            self.theme = FusionTheme(ThemeMode.SYSTEM)
            # Apply theme if app exists
            qapp = QApplication.instance()
            if qapp and isinstance(qapp, QApplication):
                self.theme.apply(qapp)
        else:
            self.theme = theme
        self.theme_mode_preference = self.theme.mode  # Track user preference

        # Minimal UI mode state
        self.minimal_ui_mode = False

        # Create menu bar with theme toggle
        self._create_menus()

        # Create toolbar with telescope control buttons
        self._create_toolbar()

        # Create top toolbar for table controls
        self._create_table_toolbar()

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Create telescope control panel
        self.control_panel = self._create_control_panel()
        main_layout.addWidget(self.control_panel)

        # Create collapsible log panel at bottom (header will be hidden, controlled by toolbar button)
        self.log_panel = CollapsibleLogPanel()
        self.log_panel.header.hide()  # Hide the header since we'll use a toolbar button
        # Ensure log panel starts collapsed (hidden)
        self.log_panel.log_text.hide()
        self.log_panel.setMaximumHeight(0)  # Start with no height
        self.log_panel.setMinimumHeight(0)
        main_layout.addWidget(self.log_panel)

        # Create debug log panel at bottom (header will be hidden, controlled by toolbar button)
        self.debug_panel = DebugLogPanel()
        self.debug_panel.header.hide()  # Hide the header since we'll use a toolbar button
        # Ensure debug panel starts collapsed (hidden)
        self.debug_panel.controls_widget.hide()
        self.debug_panel.log_text.hide()
        self.debug_panel.setMaximumHeight(0)  # Start with no height
        self.debug_panel.setMinimumHeight(0)
        main_layout.addWidget(self.debug_panel)

        # Create status bar at bottom
        self._create_status_bar()

        # Setup update timer for status bar
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_status_bar)
        self.update_timer.start(1000)  # Update every second

        # Initial status update
        self._update_status_bar()

        # Load data for the first tab
        if hasattr(self, "tab_widget") and self.tab_widget.count() > 0:
            first_tab = self.tab_widget.widget(0)
            if isinstance(first_tab, QTableWidget):
                self._load_objects_table(first_tab)

        # Hide any unwanted elements that might appear (like ".EA" button)
        # This could be a qt-material CSS element or toolbar overflow button
        self._hide_unwanted_elements()

        # Debug: Print all widgets to help identify the ".EA" button
        # Uncomment the line below to see all widgets in the console when the app starts
        # self._debug_print_widgets()

    def _debug_print_widgets(self) -> None:
        """Debug method to print all widgets and their text."""

        def print_widget_tree(widget: QWidget, indent: int = 0) -> None:
            prefix = "  " * indent
            widget_text = ""
            if hasattr(widget, "text"):
                widget_text = widget.text()
            elif hasattr(widget, "windowTitle"):
                widget_text = widget.windowTitle()
            elif hasattr(widget, "toolTip"):
                widget_text = widget.toolTip()
            obj_name = widget.objectName() or "<no name>"
            class_name = widget.__class__.__name__
            # Check if text contains "EA" or similar
            if "EA" in widget_text.upper() or "EA" in obj_name.upper() or "EA" in class_name.upper():
                print(f"*** FOUND EA: {prefix}{class_name} (name: {obj_name}, text: '{widget_text}')")
            print(f"{prefix}{class_name} (name: {obj_name}, text: '{widget_text}')")
            for child in widget.children():
                if isinstance(child, QWidget):
                    print_widget_tree(child, indent + 1)

        print("=== Widget Tree (looking for .EA) ===")
        print_widget_tree(self)
        print("=== Checking toolbar widgets ===")
        for toolbar in self.findChildren(QToolBar):
            print(f"Toolbar: {toolbar.objectName()}, widgets: {toolbar.findChildren(QWidget)}")
        print("=== Checking status bar widgets ===")
        if self.statusBar():
            for widget in self.statusBar().findChildren(QWidget):
                print(
                    f"StatusBar widget: {widget.__class__.__name__}, text: '{getattr(widget, 'text', lambda: '')()}', name: {widget.objectName()}"
                )

    def _hide_unwanted_elements(self) -> None:
        """Hide any unwanted UI elements that might appear."""
        # Try to find and hide the ".EA" button by checking all widgets after window is shown
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QLabel, QPushButton, QToolButton

        def find_and_hide_ea_element() -> None:
            """Find any widget with '.EA' in its text and hide it."""
            # Check all buttons
            for button in self.findChildren(QPushButton):
                text = button.text()
                if ".EA" in text or text == ".EA":
                    button.hide()
                    button.setVisible(False)
                    print(f"Found and hiding button with text: '{text}'")

            for tool_button in self.findChildren(QToolButton):
                text = tool_button.text()
                if ".EA" in text or text == ".EA":
                    tool_button.hide()
                    tool_button.setVisible(False)
                    print(f"Found and hiding tool button with text: '{text}'")

            for label in self.findChildren(QLabel):
                text = label.text()
                if ".EA" in text or text == ".EA":
                    label.hide()
                    label.setVisible(False)
                    print(f"Found and hiding label with text: '{text}'")

            # Also try CSS approach - more aggressive
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app and isinstance(app, QApplication):
                current_stylesheet = app.styleSheet()  # type: ignore[attr-defined]
                hide_css = """
                    /* Hide toolbar overflow and separators */
                    QToolBar::handle { width: 0px; }
                    QToolBar::separator { width: 0px; }
                """
                app.setStyleSheet(current_stylesheet + hide_css)  # type: ignore[attr-defined]

        # Try multiple times with delays to catch dynamically created elements
        QTimer.singleShot(0, find_and_hide_ea_element)
        QTimer.singleShot(100, find_and_hide_ea_element)
        QTimer.singleShot(500, find_and_hide_ea_element)
        QTimer.singleShot(1000, find_and_hide_ea_element)

    def _create_progress_dialog(self, label_text: str, parent: QWidget | None = None) -> QProgressDialog:
        """
        Create a progress dialog without a title bar.

        Args:
            label_text: Text to display in the progress dialog
            parent: Parent widget (defaults to self)

        Returns:
            QProgressDialog configured without title bar
        """
        if parent is None:
            parent = self
        progress = QProgressDialog(label_text, "Cancel", 0, 0, parent)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setCancelButton(None)  # Disable cancel button

        # Remove title bar by setting window flags
        flags = progress.windowFlags()
        flags &= ~Qt.WindowType.WindowTitleHint
        flags &= ~Qt.WindowType.WindowSystemMenuHint
        flags &= ~Qt.WindowType.WindowMinimizeButtonHint
        flags &= ~Qt.WindowType.WindowMaximizeButtonHint
        flags &= ~Qt.WindowType.WindowCloseButtonHint
        # Keep it as a dialog but without decorations
        flags |= Qt.WindowType.Dialog
        flags |= Qt.WindowType.FramelessWindowHint
        progress.setWindowFlags(flags)

        return progress

    def _create_menus(self) -> None:
        """Create the application menu bar with menus."""
        # Create File menu
        file_menu = self.menuBar().addMenu("&File")

        # Exit action
        exit_action = file_menu.addAction("E&xit")
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Exit the application")
        exit_action.triggered.connect(self.close)

        # Create View menu
        view_menu = self.menuBar().addMenu("&View")

        # Create Theme submenu
        theme_menu = view_menu.addMenu("&Theme")

        # Create action group for theme selection (exclusive)
        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)

        # Light theme action
        self.light_theme_action = theme_menu.addAction("☀️ Light Mode")
        self.light_theme_action.setCheckable(True)
        self.light_theme_action.setStatusTip("Switch to light theme")
        self.light_theme_action.triggered.connect(lambda: self._set_theme(ThemeMode.LIGHT))
        self.theme_action_group.addAction(self.light_theme_action)

        # Dark theme action
        self.dark_theme_action = theme_menu.addAction("🌙 Dark Mode")
        self.dark_theme_action.setCheckable(True)
        self.dark_theme_action.setStatusTip("Switch to dark theme")
        self.dark_theme_action.triggered.connect(lambda: self._set_theme(ThemeMode.DARK))
        self.theme_action_group.addAction(self.dark_theme_action)

        # System theme action
        self.system_theme_action = theme_menu.addAction("🖥️ System")
        self.system_theme_action.setCheckable(True)
        self.system_theme_action.setStatusTip("Follow OS system theme")
        self.system_theme_action.triggered.connect(lambda: self._set_theme(ThemeMode.SYSTEM))
        self.theme_action_group.addAction(self.system_theme_action)

        # Dark Sky Mode action (red-light theme)
        self.dark_sky_theme_action = theme_menu.addAction("🔴 Dark Sky Mode")
        self.dark_sky_theme_action.setCheckable(True)
        self.dark_sky_theme_action.setStatusTip("Red-light theme for preserving night vision")
        self.dark_sky_theme_action.triggered.connect(lambda: self._set_theme(ThemeMode.DARK_SKY))
        self.theme_action_group.addAction(self.dark_sky_theme_action)

        # Add separator before Minimal UI
        view_menu.addSeparator()

        # Minimal UI mode toggle
        self.minimal_ui_action = view_menu.addAction("Minimal UI Mode")
        self.minimal_ui_action.setCheckable(True)
        self.minimal_ui_action.setStatusTip("Hide menus, toolbars, and status bar for minimal interface")
        self.minimal_ui_action.setShortcut("Ctrl+M")
        self.minimal_ui_action.triggered.connect(self._toggle_minimal_ui)

        # Set initial checked state based on current theme
        self._update_theme_menu_state()

        # Monitor system theme changes
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            app.paletteChanged.connect(self._on_system_theme_changed)  # type: ignore[attr-defined]

    def showEvent(self, event: object) -> None:  # noqa: N802
        """Handle window show event - refresh icons after window is shown."""
        super().showEvent(event)  # type: ignore[arg-type]

        # Force window decorations on Wayland/COSMIC (sometimes needs to be done after show)
        # Check if we're on Wayland by checking environment variable
        import os

        is_wayland = os.environ.get("WAYLAND_DISPLAY") is not None or os.environ.get("XDG_SESSION_TYPE") == "wayland"

        # Use QTimer to ensure this happens after the window is fully shown
        def _ensure_decorations() -> None:
            # Always force decorations on Wayland, or if frameless is detected
            current_flags = self.windowFlags()
            needs_fix = is_wayland or (current_flags & Qt.WindowType.FramelessWindowHint)

            if needs_fix and not hasattr(self, "_decorations_fixed"):
                # Set standard window type with all decorations
                flags = Qt.WindowType.Window
                flags &= ~Qt.WindowType.FramelessWindowHint  # Explicitly remove frameless
                flags |= Qt.WindowType.WindowTitleHint
                flags |= Qt.WindowType.WindowMinimizeButtonHint
                flags |= Qt.WindowType.WindowMaximizeButtonHint
                flags |= Qt.WindowType.WindowCloseButtonHint
                flags |= Qt.WindowType.WindowSystemMenuHint
                self.setWindowFlags(flags)
                # Must call show() again after changing flags
                self.show()
                self._decorations_fixed = True

        # Try with a small delay to let the compositor finish initializing
        # Try multiple times with increasing delays for stubborn compositors
        QTimer.singleShot(50, _ensure_decorations)
        QTimer.singleShot(200, _ensure_decorations)
        QTimer.singleShot(500, _ensure_decorations)

        # Refresh toolbar icons after window is shown to ensure FontAwesome fonts are loaded
        self._refresh_toolbar_icons()

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        """Handle window close event - clean up all threads."""
        still_running = False
        # Stop and clean up all loading threads
        for obj_type_str, thread in list(self._loading_threads.items()):
            if thread.isRunning():
                thread.requestInterruption()
                thread.wait(5000)  # Wait up to 5 seconds for graceful shutdown
                if thread.isRunning():
                    thread.terminate()
                    thread.wait(5000)
            if thread.isRunning():
                still_running = True
                continue
            thread.deleteLater()
            del self._loading_threads[obj_type_str]

        # Stop and clean up all visibility counting threads
        for table, vis_thread in list(self._visibility_threads.items()):
            if vis_thread.isRunning():
                vis_thread.requestInterruption()
                vis_thread.wait(5000)  # Wait up to 5 seconds for graceful shutdown
                if vis_thread.isRunning():
                    vis_thread.terminate()
                    vis_thread.wait(5000)
            if vis_thread.isRunning():
                still_running = True
                continue
            vis_thread.deleteLater()
            del self._visibility_threads[table]

        # Stop any threads we've previously detached (best-effort).
        for stopping_thread in list(self._stopping_threads):
            try:
                if stopping_thread.isRunning():
                    stopping_thread.requestInterruption()
                    stopping_thread.wait(2000)
                    if stopping_thread.isRunning():
                        stopping_thread.terminate()
                        stopping_thread.wait(2000)
                if not stopping_thread.isRunning():
                    stopping_thread.deleteLater()
                    self._stopping_threads.remove(stopping_thread)
                else:
                    still_running = True
            except Exception:
                # If anything goes wrong here, keep the reference to avoid a crash.
                still_running = True

        # If any thread refuses to stop, don't let Qt destroy QThread wrappers while running.
        if still_running:
            logger.warning("Close requested while background threads are still running; delaying close to avoid crash.")
            event.ignore()
            return

        # Process events to allow thread cleanup
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        super().closeEvent(event)  # type: ignore[arg-type]

    def _create_toolbar(self) -> None:
        """Create multiple toolbars organized by function."""

        # Common toolbar settings
        def create_toolbar(name: str, area: Qt.ToolBarArea) -> QToolBar:
            """Helper to create a toolbar with common settings."""
            toolbar = QToolBar(name)
            toolbar.setMovable(True)
            toolbar.setIconSize(QSize(22, 22))
            toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            toolbar.setFloatable(True)
            # Set orientation based on toolbar area (left/right = vertical, top/bottom = horizontal)
            if area in (Qt.ToolBarArea.LeftToolBarArea, Qt.ToolBarArea.RightToolBarArea):
                toolbar.setOrientation(Qt.Orientation.Vertical)
            else:
                toolbar.setOrientation(Qt.Orientation.Horizontal)
            toolbar.setStyleSheet("""
                QToolBar::separator { width: 0px; }
                QToolBar QToolButton {
                    padding: 4px 8px;
                }
            """)
            self.addToolBar(area, toolbar)
            return toolbar

        # Left side toolbar - organized with QToolButton menus
        left_toolbar = create_toolbar("Left Toolbar", Qt.ToolBarArea.LeftToolBarArea)
        self.left_toolbar = left_toolbar  # Store reference for minimal UI mode

        # Telescope Operations menu button
        telescope_menu = QMenu("Telescope Operations", self)
        self._apply_menu_styles(telescope_menu)

        connect_icon = self._create_icon("link", ["network-connect", "network-wired", "network-workgroup"])
        self.connect_action = telescope_menu.addAction(connect_icon, "Connect")
        self.connect_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.connect_action.setToolTip("CONNECT")
        self.connect_action.setStatusTip("Connect to telescope")
        self.connect_action.triggered.connect(self._on_connect)

        disconnect_icon = self._create_icon("link_off", ["network-disconnect", "network-offline", "network-error"])
        self.disconnect_action = telescope_menu.addAction(disconnect_icon, "Disconnect")
        self.disconnect_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.disconnect_action.setToolTip("DISCONNECT")
        self.disconnect_action.setStatusTip("Disconnect from telescope")
        self.disconnect_action.triggered.connect(self._on_disconnect)
        self.disconnect_action.setEnabled(False)

        telescope_menu.addSeparator()

        calibrate_icon = self._create_icon("crosshairs", ["tools-check-spelling", "preferences-system", "configure"])
        self.calibrate_action = telescope_menu.addAction(calibrate_icon, "Calibrate")
        self.calibrate_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.calibrate_action.setToolTip("CALIBRATE")
        self.calibrate_action.setStatusTip("Calibrate telescope")
        self.calibrate_action.triggered.connect(self._on_calibrate)
        self.calibrate_action.setEnabled(False)

        align_icon = self._create_icon("my_location", ["edit-find", "system-search", "find-location"])
        self.align_action = telescope_menu.addAction(align_icon, "Align")
        self.align_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.align_action.setToolTip("ALIGN")
        self.align_action.setStatusTip("Align telescope")
        self.align_action.triggered.connect(self._on_align)
        self.align_action.setEnabled(False)

        telescope_menu.addSeparator()

        # Tracking History action
        tracking_icon = self._create_icon("chart", ["chart-line", "graph", "analytics"])
        self.tracking_history_action = telescope_menu.addAction(tracking_icon, "Tracking History Graph")
        self.tracking_history_action.setIconVisibleInMenu(True)
        self.tracking_history_action.setToolTip("TRACKING HISTORY")
        self.tracking_history_action.setStatusTip("View real-time tracking history graph")
        self.tracking_history_action.triggered.connect(self._on_tracking_history)
        self.tracking_history_action.setEnabled(False)

        telescope_button = QToolButton()
        telescope_button.setText("Telescope")
        telescope_button.setIcon(connect_icon)  # Use connect icon as default
        telescope_button.setMenu(telescope_menu)
        telescope_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        telescope_button.setToolTip("TELESCOPE OPERATIONS")
        telescope_button.setStatusTip("Telescope connection and control operations")
        left_toolbar.addWidget(telescope_button)
        self.telescope_button = telescope_button  # Store reference for icon refresh

        # Planning Tools menu button
        planning_menu = QMenu("Planning Tools", self)
        self._apply_menu_styles(planning_menu)

        # Object Management Group
        catalog_icon = self._create_icon("catalog", ["folder", "folder-open", "database"])
        self.catalog_action = planning_menu.addAction(catalog_icon, "Catalog")
        self.catalog_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.catalog_action.setToolTip("CATALOG")
        self.catalog_action.setStatusTip("Open catalog search window")
        self.catalog_action.triggered.connect(self._on_catalog)

        # Goto Queue action
        queue_icon = self._create_icon("list", ["view-list", "format-list-bulleted", "playlist-play", "list"])
        self.goto_queue_action = planning_menu.addAction(queue_icon, "Goto Queue / Sequence")
        self.goto_queue_action.setIconVisibleInMenu(True)
        self.goto_queue_action.setToolTip("GOTO QUEUE")
        self.goto_queue_action.setStatusTip("Open goto queue/sequence window")
        self.goto_queue_action.triggered.connect(self._on_goto_queue)

        favorites_icon = self._create_icon("star", ["star", "bookmark", "favorite"])
        self.favorites_action = planning_menu.addAction(favorites_icon, "Favorites")
        self.favorites_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.favorites_action.setToolTip("FAVORITES")
        self.favorites_action.setStatusTip("View favorite objects")
        self.favorites_action.triggered.connect(self._on_favorites)

        observation_log_icon = self._create_icon("menu_book", ["book-open-variant", "book", "document"])
        self.observation_log_action = planning_menu.addAction(observation_log_icon, "Observation Log")
        self.observation_log_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.observation_log_action.setToolTip("OBSERVATION LOG")
        self.observation_log_action.setStatusTip("View and manage observation logs")
        self.observation_log_action.triggered.connect(self._on_observation_log)

        planning_menu.addSeparator()

        # Planning & Analysis Group
        dashboard_icon = self._create_icon("dashboard", ["view-dashboard", "chart-line", "monitor-dashboard"])
        self.dashboard_action = planning_menu.addAction(dashboard_icon, "Live Dashboard")
        self.dashboard_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.dashboard_action.setToolTip("LIVE DASHBOARD")
        self.dashboard_action.setStatusTip("View real-time observing conditions dashboard")
        self.dashboard_action.triggered.connect(self._on_live_dashboard)

        # Sky Map
        sky_map_icon = self._create_icon("map", ["map", "globe", "earth", "map-marker"])
        self.sky_map_action = planning_menu.addAction(sky_map_icon, "Interactive Sky Map")
        self.sky_map_action.setIconVisibleInMenu(True)
        self.sky_map_action.setToolTip("SKY MAP")
        self.sky_map_action.setStatusTip("Open interactive sky map showing stars and telescope position")
        self.sky_map_action.triggered.connect(self._on_sky_map)

        # Zenith Star Chart
        star_chart_icon = self._create_icon("star", ["star", "star-outline", "star-circle"])
        self.zenith_star_chart_action = planning_menu.addAction(star_chart_icon, "Zenith Star Chart")
        self.zenith_star_chart_action.setIconVisibleInMenu(True)
        self.zenith_star_chart_action.setToolTip("ZENITH STAR CHART")
        self.zenith_star_chart_action.setStatusTip("Open full-sky zenith star chart view")
        self.zenith_star_chart_action.triggered.connect(self._on_zenith_star_chart)

        # Astronomical Calendar
        calendar_icon = self._create_icon("event", ["calendar", "calendar-month", "calendar-outline"])
        self.calendar_action = planning_menu.addAction(calendar_icon, "Astronomical Calendar")
        self.calendar_action.setIconVisibleInMenu(True)
        self.calendar_action.setToolTip("ASTRONOMICAL CALENDAR")
        self.calendar_action.setStatusTip("View astronomical events calendar")
        self.calendar_action.triggered.connect(self._on_astronomical_calendar)

        time_slots_icon = self._create_icon("time_slots", ["clock-outline", "timer"])
        self.time_slots_action = planning_menu.addAction(time_slots_icon, "Time Slots")
        self.time_slots_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.time_slots_action.setToolTip("TIME SLOTS")
        self.time_slots_action.setStatusTip("View available time slots")
        self.time_slots_action.triggered.connect(self._on_time_slots)

        transit_times_icon = self._create_icon("transit_times", ["transit-connection", "arrow-right-bold"])
        self.transit_times_action = planning_menu.addAction(transit_times_icon, "Transit Times")
        self.transit_times_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.transit_times_action.setToolTip("TRANSIT TIMES")
        self.transit_times_action.setStatusTip("View transit times")
        self.transit_times_action.triggered.connect(self._on_transit_times)

        planning_menu.addSeparator()

        # Equipment & Conditions Group
        # Equipment Manager
        equipment_icon = self._create_icon("settings", ["cog", "tools", "wrench"])
        self.equipment_action = planning_menu.addAction(equipment_icon, "Equipment Manager")
        self.equipment_action.setIconVisibleInMenu(True)
        self.equipment_action.setToolTip("EQUIPMENT MANAGER")
        self.equipment_action.setStatusTip("Manage eyepieces, filters, and cameras")
        self.equipment_action.triggered.connect(self._on_equipment_manager)

        weather_icon = self._create_icon("weather", ["weather-cloudy", "weather-partly-cloudy", "weather-sunny"])
        self.weather_action = planning_menu.addAction(weather_icon, "Weather")
        self.weather_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.weather_action.setToolTip("WEATHER")
        self.weather_action.setStatusTip("View current weather conditions")
        self.weather_action.triggered.connect(self._on_weather)

        moon_icon = self._create_icon("moon", ["moon-waxing-crescent", "moon-full", "moon-new", "weather-night"])
        self.moon_info_action = planning_menu.addAction(moon_icon, "Moon Info")
        self.moon_info_action.setIconVisibleInMenu(True)
        self.moon_info_action.setToolTip("MOON INFO")
        self.moon_info_action.setStatusTip("View moon information, phase, and position")
        self.moon_info_action.triggered.connect(self._on_moon_info)

        sky_darkness_icon = self._create_icon("sky_darkness", ["weather-night", "moon-waxing-crescent", "star"])
        self.sky_darkness_action = planning_menu.addAction(sky_darkness_icon, "Sky Darkness")
        self.sky_darkness_action.setIconVisibleInMenu(True)
        self.sky_darkness_action.setToolTip("SKY DARKNESS")
        self.sky_darkness_action.setStatusTip("View sky darkness information (Bortle class, SQM, limiting magnitudes)")
        self.sky_darkness_action.triggered.connect(self._on_sky_darkness)

        checklist_icon = self._create_icon("checklist", ["format-list-checks", "check-circle"])
        self.checklist_action = planning_menu.addAction(checklist_icon, "Checklist")
        self.checklist_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.checklist_action.setToolTip("CHECKLIST")
        self.checklist_action.setStatusTip("View observation checklist")
        self.checklist_action.triggered.connect(self._on_checklist)

        planning_menu.addSeparator()

        # Reference Group
        quick_ref_icon = self._create_icon("quick_reference", ["book-open-variant", "information"])
        self.quick_reference_action = planning_menu.addAction(quick_ref_icon, "Quick Reference")
        self.quick_reference_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.quick_reference_action.setToolTip("QUICK REFERENCE")
        self.quick_reference_action.setStatusTip("Open quick reference guide")
        self.quick_reference_action.triggered.connect(self._on_quick_reference)

        glossary_icon = self._create_icon("glossary", ["book-open-page-variant", "book-open-variant"])
        self.glossary_action = planning_menu.addAction(glossary_icon, "Glossary")
        self.glossary_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.glossary_action.setToolTip("GLOSSARY")
        self.glossary_action.setStatusTip("View astronomical glossary")
        self.glossary_action.triggered.connect(self._on_glossary)

        # Object Comparison Tool
        compare_icon = self._create_icon("compare", ["compare", "view-split-vertical", "diff"])
        self.compare_action = planning_menu.addAction(compare_icon, "Compare Objects")
        self.compare_action.setIconVisibleInMenu(True)
        self.compare_action.setToolTip("COMPARE OBJECTS")
        self.compare_action.setStatusTip("Compare objects side-by-side")
        self.compare_action.triggered.connect(self._on_compare_objects)

        planning_button = QToolButton()
        planning_button.setText("Planning")
        planning_button.setIcon(catalog_icon)  # Icon for the button itself
        planning_button.setMenu(planning_menu)
        planning_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)  # Only opens menu
        planning_button.setToolTip("PLANNING TOOLS")
        planning_button.setStatusTip("Observation planning and reference tools")
        left_toolbar.addWidget(planning_button)
        self.planning_button = planning_button  # Store reference for icon refresh

        # Spacer widget
        spacer_widget = QWidget()
        spacer_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        spacer_widget.setMinimumHeight(1)
        left_toolbar.addWidget(spacer_widget)

        # Tools menu button (Communication Log, Settings)
        tools_menu = QMenu("Tools", self)
        self._apply_menu_styles(tools_menu)

        log_icon = self._create_icon("console", ["terminal", "code-tags", "text-box"])
        self.log_toggle_action = tools_menu.addAction(log_icon, "Communication Log")
        self.log_toggle_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.log_toggle_action.setToolTip("COMMUNICATION LOG")
        self.log_toggle_action.setStatusTip("Toggle communication log panel")
        self.log_toggle_action.setCheckable(True)
        self.log_toggle_action.setChecked(False)
        self.log_toggle_action.triggered.connect(self._on_toggle_log)

        # Debug log toggle action
        debug_icon = self._create_icon(
            "utilities-log-viewer", ["debug-run", "text-x-log", "document-preview", "view-list-details"]
        )
        self.debug_toggle_action = tools_menu.addAction(debug_icon, "Debug Log")
        self.debug_toggle_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.debug_toggle_action.setToolTip("DEBUG LOG")
        self.debug_toggle_action.setStatusTip("Toggle debug log panel")
        self.debug_toggle_action.setCheckable(True)
        self.debug_toggle_action.setChecked(False)
        self.debug_toggle_action.triggered.connect(self._on_toggle_debug_log)

        tools_menu.addSeparator()

        settings_icon = self._create_icon("settings", ["cog", "settings"])
        self.settings_action = tools_menu.addAction(settings_icon, "Settings")
        self.settings_action.setIconVisibleInMenu(True)  # Ensure icon is visible in menu
        self.settings_action.setToolTip("SETTINGS")
        self.settings_action.setStatusTip("View and manage settings")
        self.settings_action.triggered.connect(self._on_settings)

        tools_button = QToolButton()
        tools_button.setText("Tools")
        tools_button.setIcon(settings_icon)  # Icon for the button itself
        tools_button.setMenu(tools_menu)
        tools_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)  # Only opens menu
        tools_button.setToolTip("TOOLS")
        tools_button.setStatusTip("Application tools and settings")
        left_toolbar.addWidget(tools_button)
        self.tools_button = tools_button  # Store reference for icon refresh

        # Right side toolbar - Celestial Objects menu
        right_toolbar = create_toolbar("Right Toolbar", Qt.ToolBarArea.RightToolBarArea)
        self.right_toolbar = right_toolbar  # Store reference for minimal UI mode

        # Celestial Objects menu button
        celestial_menu = QMenu("Celestial Objects", self)
        self._apply_menu_styles(celestial_menu)

        # Solar System Group
        solar_system_objects = [
            ("planets", "Planets", ["alpha-p-box-outline"]),
            ("comets", "Comets", ["alpha-c-box-outline"]),
            ("asteroids", "Asteroids", ["alpha-a-box-outline"]),
            ("eclipse", "Eclipse", ["alpha-e-box-outline"]),
        ]

        for obj_name, display_name, icon_names in solar_system_objects:
            icon = self._create_icon(obj_name, icon_names)
            action = celestial_menu.addAction(icon, display_name)
            action.setIconVisibleInMenu(True)
            action.setToolTip(display_name.upper())
            action.setStatusTip(f"View {display_name} information")
            action.triggered.connect(lambda checked, name=obj_name: self._on_celestial_object(name))
            setattr(self, f"{obj_name}_action", action)

        celestial_menu.addSeparator()

        # Deep Sky Group
        deep_sky_objects = [
            ("milky_way", "Milky Way", ["alpha-m-box-outline"]),
            ("naked_eye", "Naked Eye", ["alpha-n-box-outline"]),
            ("binoculars", "Binoculars", ["alpha-b-box-outline"]),
        ]

        for obj_name, display_name, icon_names in deep_sky_objects:
            icon = self._create_icon(obj_name, icon_names)
            action = celestial_menu.addAction(icon, display_name)
            action.setIconVisibleInMenu(True)
            action.setToolTip(display_name.upper())
            action.setStatusTip(f"View {display_name} information")
            action.triggered.connect(lambda checked, name=obj_name: self._on_celestial_object(name))
            setattr(self, f"{obj_name}_action", action)

        celestial_menu.addSeparator()

        # Events & Phenomena Group
        events_objects = [
            ("aurora", "Aurora", ["alpha-a-box-outline"]),
            ("meteors", "Meteors", ["alpha-m-box-outline"]),
            ("occultations", "Occultations", ["alpha-o-box-outline"]),
            ("iss", "ISS", ["alpha-i-box-outline"]),
            ("satellites", "Satellites", ["alpha-s-box-outline"]),
        ]

        for obj_name, display_name, icon_names in events_objects:
            icon = self._create_icon(obj_name, icon_names)
            action = celestial_menu.addAction(icon, display_name)
            action.setIconVisibleInMenu(True)
            action.setToolTip(display_name.upper())
            action.setStatusTip(f"View {display_name} information")
            action.triggered.connect(lambda checked, name=obj_name: self._on_celestial_object(name))
            setattr(self, f"{obj_name}_action", action)
            # Disable buttons until API is implemented
            if obj_name == "occultations":
                action.setEnabled(False)
                action.setToolTip("Occultations (Coming Soon)")
                action.setStatusTip("Occultations feature is not yet implemented")

        celestial_menu.addSeparator()

        # Space Conditions Group
        space_conditions_objects = [
            ("space_weather", "Space Weather", ["alpha-s-box-outline"]),
        ]

        for obj_name, display_name, icon_names in space_conditions_objects:
            icon = self._create_icon(obj_name, icon_names)
            action = celestial_menu.addAction(icon, display_name)
            action.setIconVisibleInMenu(True)
            action.setToolTip(display_name.upper())
            action.setStatusTip(f"View {display_name} information")
            action.triggered.connect(lambda checked, name=obj_name: self._on_celestial_object(name))
            setattr(self, f"{obj_name}_action", action)

        celestial_menu.addSeparator()

        # Advanced Group
        advanced_objects = [
            ("variables", "Variables", ["alpha-v-box-outline"]),
            ("zodiacal", "Zodiacal", ["alpha-z-box-outline"]),
        ]

        for obj_name, display_name, icon_names in advanced_objects:
            icon = self._create_icon(obj_name, icon_names)
            action = celestial_menu.addAction(icon, display_name)
            action.setIconVisibleInMenu(True)
            action.setToolTip(display_name.upper())
            action.setStatusTip(f"View {display_name} information")
            action.triggered.connect(lambda checked, name=obj_name: self._on_celestial_object(name))
            setattr(self, f"{obj_name}_action", action)
            # Enable buttons - features are now implemented
            if obj_name == "variables":
                action.setEnabled(True)
                action.setToolTip("Variable Stars")
                action.setStatusTip("View variable stars")
            elif obj_name == "zodiacal":
                action.setEnabled(True)
                action.setToolTip("Zodiacal Objects")
                action.setStatusTip("View objects along the ecliptic (zodiac)")

        celestial_button = QToolButton()
        celestial_button.setText("Objects")
        # Use planets icon for the button itself
        planets_icon = self._create_icon("planets", ["alpha-p-box-outline"])
        celestial_button.setIcon(planets_icon)
        celestial_button.setMenu(celestial_menu)
        celestial_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)  # Only opens menu
        celestial_button.setToolTip("CELESTIAL OBJECTS")
        celestial_button.setStatusTip("View information about celestial objects")
        right_toolbar.addWidget(celestial_button)
        self.celestial_button = celestial_button  # Store reference for icon refresh

    def _refresh_toolbar_icons(self) -> None:
        """Refresh toolbar icons after window is shown."""
        # Recreate icons to ensure FontAwesome/MDI fonts are loaded
        # Telescope operations
        self.connect_action.setIcon(
            self._create_icon("link", ["network-connect", "network-wired", "network-workgroup"])
        )
        # Refresh toolbar button icons
        if hasattr(self, "telescope_button"):
            self.telescope_button.setIcon(
                self._create_icon("link", ["network-connect", "network-wired", "network-workgroup"])
            )
        self.disconnect_action.setIcon(
            self._create_icon("link_off", ["network-disconnect", "network-offline", "network-error"])
        )
        self.calibrate_action.setIcon(
            self._create_icon("crosshairs", ["tools-check-spelling", "preferences-system", "configure"])
        )
        self.align_action.setIcon(self._create_icon("my_location", ["edit-find", "system-search", "find-location"]))
        if hasattr(self, "tracking_history_action"):
            self.tracking_history_action.setIcon(self._create_icon("chart", ["chart-line", "graph", "analytics"]))
        # Planning tools
        if hasattr(self, "favorites_action"):
            self.favorites_action.setIcon(self._create_icon("star", ["star", "bookmark", "favorite"]))
        if hasattr(self, "observation_log_action"):
            self.observation_log_action.setIcon(
                self._create_icon("menu_book", ["book-open-variant", "book", "document"])
            )
        if hasattr(self, "dashboard_action"):
            self.dashboard_action.setIcon(
                self._create_icon("dashboard", ["view-dashboard", "chart-line", "monitor-dashboard"])
            )
        if hasattr(self, "sky_map_action"):
            self.sky_map_action.setIcon(self._create_icon("map", ["map", "globe", "earth", "map-marker"]))
        if hasattr(self, "zenith_star_chart_action"):
            self.zenith_star_chart_action.setIcon(self._create_icon("star", ["star", "star-outline", "star-circle"]))
        if hasattr(self, "calendar_action"):
            self.calendar_action.setIcon(self._create_icon("event", ["calendar", "calendar-month", "calendar-outline"]))
        if hasattr(self, "equipment_action"):
            self.equipment_action.setIcon(self._create_icon("settings", ["cog", "tools", "wrench"]))
        self.weather_action.setIcon(
            self._create_icon("weather", ["weather-cloudy", "weather-partly-cloudy", "weather-sunny"])
        )
        if hasattr(self, "moon_info_action"):
            self.moon_info_action.setIcon(
                self._create_icon("moon", ["moon-waxing-crescent", "moon-full", "moon-new", "weather-night"])
            )
        if hasattr(self, "sky_darkness_action"):
            self.sky_darkness_action.setIcon(
                self._create_icon("sky_darkness", ["weather-night", "moon-waxing-crescent", "star"])
            )
        self.checklist_action.setIcon(self._create_icon("checklist", ["format-list-checks", "check-circle"]))
        self.time_slots_action.setIcon(self._create_icon("time_slots", ["clock-outline", "timer"]))
        self.quick_reference_action.setIcon(self._create_icon("quick_reference", ["book-open-variant", "information"]))
        self.transit_times_action.setIcon(
            self._create_icon("transit_times", ["transit-connection", "arrow-right-bold"])
        )
        self.glossary_action.setIcon(self._create_icon("glossary", ["book-open-page-variant", "book-open-variant"]))
        if hasattr(self, "compare_action"):
            self.compare_action.setIcon(self._create_icon("compare", ["compare", "view-split-vertical", "diff"]))
        self.settings_action.setIcon(self._create_icon("settings", ["cog", "settings"]))
        # Refresh tools button icon
        if hasattr(self, "tools_button"):
            self.tools_button.setIcon(self._create_icon("settings", ["cog", "settings"]))
        # Refresh filter clear button icon (theme-aware)
        if hasattr(self, "filter_clear_button"):
            self.filter_clear_button.setIcon(self._create_icon("close-circle", ["edit-clear", "window-close", "close"]))
        # Celestial objects (using alpha-box-outline pattern)
        for obj_name in [
            "aurora",
            "binoculars",
            "comets",
            "eclipse",
            "iss",
            "meteors",
            "milky_way",
            "naked_eye",
            "occultations",
            "planets",
            "satellites",
            "space_weather",
            "variables",
            "zodiacal",
        ]:
            action = getattr(self, f"{obj_name}_action", None)
            if action:
                # Get first letter of object name for alpha-box-outline icon
                first_letter = obj_name[0].lower()
                fallback_icon = f"alpha-{first_letter}-box-outline"
                action.setIcon(self._create_icon(obj_name, [fallback_icon]))
        # Refresh celestial button icon
        if hasattr(self, "celestial_button"):
            self.celestial_button.setIcon(self._create_icon("planets", ["alpha-p-box-outline"]))
        # Communication log toggle
        if hasattr(self, "log_toggle_action"):
            self.log_toggle_action.setIcon(self._create_icon("console", ["terminal", "code-tags", "text-box"]))
        # Debug log toggle
        if hasattr(self, "debug_toggle_action"):
            self.debug_toggle_action.setIcon(
                self._create_icon(
                    "utilities-log-viewer", ["debug-run", "text-x-log", "document-preview", "view-list-details"]
                )
            )
        # Catalog button
        if hasattr(self, "catalog_action"):
            self.catalog_action.setIcon(self._create_icon("catalog", ["folder", "folder-open", "folder-documents"]))
        # Refresh planning button icon
        if hasattr(self, "planning_button"):
            self.planning_button.setIcon(self._create_icon("catalog", ["folder", "folder-open", "database"]))
        # Goto Queue button
        if hasattr(self, "goto_queue_action"):
            self.goto_queue_action.setIcon(
                self._create_icon("list", ["view-list", "format-list-bulleted", "playlist-play", "list"])
            )
        # Table toolbar buttons
        if hasattr(self, "refresh_action"):
            self.refresh_action.setIcon(self._create_icon("refresh", ["view-refresh", "reload"]))
        if hasattr(self, "load_all_action"):
            self.load_all_action.setIcon(self._create_icon("download", ["download", "folder-download"]))
        if hasattr(self, "info_action"):
            self.info_action.setIcon(self._create_icon("info", ["dialog-information", "help-about"]))

    def _set_theme(self, mode: ThemeMode) -> None:
        """Set the theme to the specified mode."""
        self.theme_mode_preference = mode
        self.theme.set_mode(mode)
        self._update_theme_menu_state()

        # Ensure theme is applied to app
        from PySide6.QtWidgets import QApplication

        qapp = QApplication.instance()
        if qapp and isinstance(qapp, QApplication):
            self.theme.apply(qapp)

        # Refresh icons to match new theme
        self._refresh_toolbar_icons()
        # Update textbox placeholder text colors
        if hasattr(self, "filter_textbox"):
            self._update_textbox_placeholder_style(self.filter_textbox)

    def _update_textbox_placeholder_style(self, textbox: QLineEdit) -> None:
        """Update placeholder text color to be theme-aware."""
        from PySide6.QtGui import QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

            # Set placeholder text color based on theme
            # Use a lighter gray for dark mode, darker gray for light mode
            placeholder_color = "#999999" if is_dark else "#666666"
            textbox.setStyleSheet(
                f"""
                QLineEdit {{
                    color: {palette.color(QPalette.ColorRole.Text).name()};
                }}
                QLineEdit::placeholder {{
                    color: {placeholder_color};
                }}
            """
            )

    def _apply_menu_styles(self, menu: QMenu) -> None:
        """Apply theme-aware styles to a menu, including separators."""
        from PySide6.QtGui import QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

            # Set separator color based on theme
            # Use a lighter gray for dark mode, darker gray for light mode
            separator_color = "#555555" if is_dark else "#cccccc"

            menu.setStyleSheet(
                f"""
                QMenu::separator {{
                    height: 1px;
                    background: {separator_color};
                    margin-left: 5px;
                    margin-right: 5px;
                    margin-top: 3px;
                    margin-bottom: 3px;
                }}
                """
            )

    def _update_menu_styles(self) -> None:
        """Update styles for all menus when theme changes."""
        # Find all menus attached to tool buttons
        for toolbar in self.findChildren(QToolBar):
            for button in toolbar.findChildren(QToolButton):
                menu = button.menu()
                if menu:
                    self._apply_menu_styles(menu)

    def _on_system_theme_changed(self) -> None:
        """Handle system theme changes."""
        # Only update if user preference is SYSTEM
        if self.theme_mode_preference == ThemeMode.SYSTEM:
            self.theme.set_mode(ThemeMode.SYSTEM)
            # Ensure theme is applied to app
            from PySide6.QtWidgets import QApplication

            qapp = QApplication.instance()
            if qapp and isinstance(qapp, QApplication):
                self.theme.apply(qapp)
            # Refresh icons to match new theme
            self._refresh_toolbar_icons()
            # Update menu styles for separators
            self._update_menu_styles()
            # Update textbox placeholder text colors
            if hasattr(self, "filter_textbox"):
                self._update_textbox_placeholder_style(self.filter_textbox)

    def _update_theme_menu_state(self) -> None:
        """Update the checked state of theme menu actions."""
        # Uncheck all first
        for action in self.theme_action_group.actions():
            action.setChecked(False)

        # Check based on user preference
        if self.theme_mode_preference == ThemeMode.SYSTEM:
            self.system_theme_action.setChecked(True)
        elif self.theme_mode_preference == ThemeMode.DARK:
            self.dark_theme_action.setChecked(True)
        elif self.theme_mode_preference == ThemeMode.DARK_SKY:
            self.dark_sky_theme_action.setChecked(True)
        else:  # ThemeMode.LIGHT
            self.light_theme_action.setChecked(True)

    def _toggle_minimal_ui(self, checked: bool) -> None:
        """Toggle minimal UI mode - hide/show menus, toolbars, and status bar."""
        self.minimal_ui_mode = checked

        # Toggle menu bar visibility
        if self.menuBar():
            self.menuBar().setVisible(not checked)

        # Toggle toolbars visibility
        if hasattr(self, "left_toolbar"):
            self.left_toolbar.setVisible(not checked)
        if hasattr(self, "right_toolbar"):
            self.right_toolbar.setVisible(not checked)
        if hasattr(self, "top_toolbar"):
            self.top_toolbar.setVisible(not checked)
        # Hide all other toolbars
        for toolbar in self.findChildren(QToolBar):
            if toolbar not in [
                getattr(self, "left_toolbar", None),
                getattr(self, "right_toolbar", None),
                getattr(self, "top_toolbar", None),
            ]:
                toolbar.setVisible(not checked)

        # Toggle status bar visibility
        if self.statusBar():
            self.statusBar().setVisible(not checked)

        # Update action checked state
        if hasattr(self, "minimal_ui_action"):
            self.minimal_ui_action.setChecked(checked)

    def _create_control_panel(self) -> QWidget:
        """Create the telescope control panel with tabs for celestial object types."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Create tab bar for celestial object types
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Add a tab for each CelestialObjectType
        for obj_type in CelestialObjectType:
            # Create human-readable label (capitalize and replace underscores)
            label = obj_type.value.replace("_", " ").title()
            # Create a table widget for each tab
            table = self._create_objects_table(obj_type)
            self.tab_widget.addTab(table, label)

        layout.addWidget(self.tab_widget)

        return panel

    def _create_objects_table(self, obj_type: CelestialObjectType) -> QTableWidget:
        """Create a table widget displaying objects of the specified type."""
        table = QTableWidget()
        # For constellation and asterism tabs, show name list with favorites
        if obj_type == CelestialObjectType.CONSTELLATION:
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["Constellation", "Visible Stars", "Favorite"])
        elif obj_type == CelestialObjectType.ASTERISM:
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["Asterism", "Visible Stars", "Favorite"])
        # For star tab, add a Constellation and Asterism column
        elif obj_type == CelestialObjectType.STAR:
            table.setColumnCount(12)
            table.setHorizontalHeaderLabels(
                [
                    "Priority",
                    "Name",
                    "Constellation",
                    "Asterism",
                    "Mag",
                    "Alt",
                    "Visibility",
                    "Transit",
                    "Moon Sep",
                    "Chance",
                    "Tips",
                    "Favorite",
                ]
            )
        elif (
            obj_type in (CelestialObjectType.GALAXY, CelestialObjectType.CLUSTER)
            or obj_type == CelestialObjectType.NEBULA
        ):
            table.setColumnCount(11)
            table.setHorizontalHeaderLabels(
                [
                    "Priority",
                    "Name",
                    "Subtype",
                    "Mag",
                    "Alt",
                    "Visibility",
                    "Transit",
                    "Moon Sep",
                    "Chance",
                    "Tips",
                    "Favorite",
                ]
            )
        elif obj_type == CelestialObjectType.MOON:
            table.setColumnCount(12)
            table.setHorizontalHeaderLabels(
                [
                    "Priority",
                    "Name",
                    "Planet",
                    "Type",
                    "Mag",
                    "Alt",
                    "Visibility",
                    "Transit",
                    "Moon Sep",
                    "Chance",
                    "Tips",
                    "Favorite",
                ]
            )
        elif obj_type == CelestialObjectType.MESSIER:
            table.setColumnCount(11)
            table.setHorizontalHeaderLabels(
                [
                    "Priority",
                    "Name",
                    "Type",
                    "Mag",
                    "Alt",
                    "Visibility",
                    "Transit",
                    "Moon Sep",
                    "Chance",
                    "Tips",
                    "Favorite",
                ]
            )
        # For variable_star and zodiacal, use standard table format
        elif obj_type in (CelestialObjectType.VARIABLE_STAR, CelestialObjectType.ZODIACAL):
            table.setColumnCount(11)
            table.setHorizontalHeaderLabels(
                [
                    "Priority",
                    "Name",
                    "Type",
                    "Mag",
                    "Alt",
                    "Visibility",
                    "Transit",
                    "Moon Sep",
                    "Chance",
                    "Tips",
                    "Favorite",
                ]
            )
        else:
            table.setColumnCount(11)
            table.setHorizontalHeaderLabels(
                [
                    "Priority",
                    "Name",
                    "Type",
                    "Mag",
                    "Alt",
                    "Visibility",
                    "Transit",
                    "Moon Sep",
                    "Chance",
                    "Tips",
                    "Favorite",
                ]
            )

        # Set column widths - all columns are resizable with minimum width based on header text
        header = table.horizontalHeader()

        # Get header labels for minimum width calculation
        if (
            obj_type == CelestialObjectType.CONSTELLATION
            or obj_type == CelestialObjectType.ASTERISM
            or obj_type == CelestialObjectType.STAR
        ):
            pass
        else:
            pass

        # Auto-size all columns
        autosize_table_columns(table, stretch_last=False)

        # Store property to track if initial resize has been done
        table.setProperty("initial_resize_done", False)

        # Enable sorting
        table.setSortingEnabled(True)

        # Set selection behavior
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Connect selection change to update info button state
        table.itemSelectionChanged.connect(self._on_table_selection_changed)

        # Connect sort indicator change to track sorting
        header.sortIndicatorChanged.connect(
            lambda logical_index, order: self._on_sort_changed(table, logical_index, order)
        )

        # Connect double-click to copy cell text
        table.itemDoubleClicked.connect(self._on_cell_double_clicked)

        # Enable context menu for favorites
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos: self._on_table_context_menu(table, pos))

        # Load data asynchronously (will be populated when tab is shown)
        # Store the object type for later loading
        table.setProperty("object_type", obj_type.value)

        # Store sort state (column index, order)
        table.setProperty("sort_column", -1)
        table.setProperty("sort_order", Qt.SortOrder.AscendingOrder)

        return table

    def _load_objects_table(self, table: QTableWidget, show_progress: bool = True) -> None:
        """Load objects data into the table (checks cache first, then loads in background)."""
        obj_type_str = table.property("object_type")
        if not obj_type_str:
            return

        # Check cache first
        if obj_type_str in self._objects_cache:
            objects = self._objects_cache[obj_type_str]
            if objects:
                # Type ignore: objects can be list[str] for constellations/asterisms
                # but this method only handles list[RecommendedObject]
                if obj_type_str in ("constellation", "asterism"):
                    # These are handled separately in _on_tab_changed
                    return
                self._populate_table(table, objects)  # type: ignore[arg-type]
            return

        # Check if already loading
        if obj_type_str in self._loading_threads:
            return

        # Show loading dialog only if requested
        progress: QProgressDialog | None = None
        if show_progress:
            progress = self._create_progress_dialog(f"Loading {obj_type_str.replace('_', ' ').title()} objects...")
            progress.show()

        # Create and start worker thread
        thread = ObjectsLoaderThread(obj_type_str)
        thread.data_loaded.connect(lambda obj_type, objs: self._on_objects_loaded(obj_type, objs, table, progress))

        # Clean up thread when it finishes
        def cleanup_thread() -> None:
            if obj_type_str in self._loading_threads:
                del self._loading_threads[obj_type_str]
            thread.deleteLater()

        thread.finished.connect(cleanup_thread, Qt.ConnectionType.QueuedConnection)

        self._loading_threads[obj_type_str] = thread
        thread.start()

    def _on_objects_loaded(
        self,
        obj_type_str: str,
        objects: list[RecommendedObject] | list[str] | None,
        table: QTableWidget,
        progress: QProgressDialog | None,
    ) -> None:
        """Handle objects data loaded signal from worker thread."""
        # Close loading dialog if it was shown
        if progress is not None and progress.isVisible():
            progress.close()

        # Remove thread from tracking
        if obj_type_str in self._loading_threads:
            del self._loading_threads[obj_type_str]

        if objects is None:
            # Error occurred, already logged in thread
            return

        # Populate table (must be done on main thread)
        if objects:
            if obj_type_str == "constellation":
                # Cache the names for constellations
                self._objects_cache[obj_type_str] = objects  # type: ignore[assignment]
                self._populate_constellation_table(table, objects)  # type: ignore[arg-type]
            elif obj_type_str == "asterism":
                # For asterisms, objects is list of tuples (Asterism, alt, az)
                # Extract just the names for the table population and cache
                if isinstance(objects, list) and objects and isinstance(objects[0], tuple):
                    asterism_names = [asterism[0].name for asterism in objects]  # type: ignore[index,union-attr]
                    # Store names in cache (for refresh operations)
                    self._objects_cache[obj_type_str] = asterism_names  # type: ignore[assignment]
                    self._populate_constellation_table(table, asterism_names)  # type: ignore[arg-type]
                    # Store full objects in separate cache for member_stars access
                    self._asterism_objects_cache = {asterism[0].name: asterism[0] for asterism in objects}  # type: ignore[index,union-attr]
                else:
                    asterism_names = []
                    self._objects_cache[obj_type_str] = asterism_names
                    self._populate_constellation_table(table, asterism_names)
                    self._asterism_objects_cache = {}
            else:
                # Cache the data (even if empty, to indicate data was loaded)
                self._objects_cache[obj_type_str] = objects
                self._populate_table(table, objects)  # type: ignore[arg-type]
        else:
            # Data was loaded but no objects match criteria - show message
            self._show_no_data_message(table, obj_type_str)

    def _populate_table(self, table: QTableWidget, objects: list[RecommendedObject]) -> None:
        """Populate table with objects data (must be called on main thread)."""
        if not objects:
            return

        # Temporarily disable sorting while populating to improve performance
        table.setSortingEnabled(False)

        table.setRowCount(len(objects))

        # Get conditions for timezone (use cached if available, otherwise get fresh)
        try:
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner

            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()
            tz = get_local_timezone(conditions.latitude, conditions.longitude)
        except Exception:
            tz = None

        # Check if this is the star or moon tab (needs extra columns)
        obj_type_str = table.property("object_type")
        is_star_tab = obj_type_str == "star"
        is_moon_tab = obj_type_str == "moon"
        is_nebula_tab = obj_type_str == "nebula"
        is_galaxy_tab = obj_type_str == "galaxy"
        is_cluster_tab = obj_type_str == "cluster"
        is_messier_tab = obj_type_str == "messier"

        # Check all favorites in a single batch query (much more efficient)
        from celestron_nexstar.api.favorites import are_favorites

        object_names = [obj_rec.obj.name for obj_rec in objects]
        try:
            favorite_dict = are_favorites(object_names)
            # Convert dict to list in same order as objects
            favorite_statuses = [favorite_dict.get(name, False) for name in object_names]
        except Exception:
            # If batch check fails, fall back to all False
            favorite_statuses = [False] * len(objects)

        # Now populate table with all data
        for row, obj_rec in enumerate(objects):
            # Priority (stars)
            priority_stars = "★" * (6 - obj_rec.priority)
            table.setItem(row, 0, QTableWidgetItem(priority_stars))

            # Name (no star indicator - we have a dedicated favorites column)
            obj = obj_rec.obj
            display_name = obj.common_name or obj.name

            name_item = QTableWidgetItem(display_name)
            # Store object name in item data for context menu
            name_item.setData(Qt.ItemDataRole.UserRole, obj.name)
            table.setItem(row, 1, name_item)

            # Column indices per tab
            if is_star_tab:
                constellation_col = 2
                asterism_col = 3
                mag_col = 4
                alt_col = 5
                vis_col = 6
                transit_col = 7
                moonsep_col = 8
                prob_col = 9
                tips_col = 10
                fav_col = 11
            elif is_moon_tab:
                type_col = 3
                mag_col = 4
                alt_col = 5
                vis_col = 6
                transit_col = 7
                moonsep_col = 8
                prob_col = 9
                tips_col = 10
                fav_col = 11
            else:
                type_col = 2
                mag_col = 3
                alt_col = 4
                vis_col = 5
                transit_col = 6
                moonsep_col = 7
                prob_col = 8
                tips_col = 9
                fav_col = 10

            # Type
            if is_nebula_tab or is_galaxy_tab or is_cluster_tab:
                subtype_text = getattr(obj, "object_subtype", None) or "-"
                table.setItem(row, type_col, QTableWidgetItem(subtype_text))
            elif is_messier_tab:
                # For Messier objects, show human-readable type name
                from celestron_nexstar.api.catalogs.messier_types import get_messier_type_name

                type_code = getattr(obj, "object_subtype", None)
                type_name = get_messier_type_name(type_code)
                table.setItem(row, type_col, QTableWidgetItem(type_name))
            elif not is_star_tab:
                table.setItem(row, type_col, QTableWidgetItem(obj.object_type.value))

            # Planet column for moons
            if is_moon_tab:
                planet_text = obj.parent_planet or "-"
                table.setItem(row, 2, QTableWidgetItem(planet_text))

            # Constellation (only for star tab)
            if is_star_tab:
                constellation_text = obj.constellation or "-"
                table.setItem(row, constellation_col, QTableWidgetItem(constellation_text))
                asterism_text = obj.asterism or "-"
                table.setItem(row, asterism_col, QTableWidgetItem(asterism_text))

            # Magnitude
            mag_text = f"{obj_rec.apparent_magnitude:.2f}" if obj_rec.apparent_magnitude else "-"
            table.setItem(row, mag_col, QTableWidgetItem(mag_text))

            # Altitude
            alt_text = f"{obj_rec.altitude:.0f}°"
            table.setItem(row, alt_col, QTableWidgetItem(alt_text))

            # Visibility indicator
            visibility_item = self._create_visibility_item(obj_rec.altitude, obj_rec.visibility_probability)
            table.setItem(row, vis_col, visibility_item)

            # Transit time
            best_time = obj_rec.best_viewing_time
            if best_time.tzinfo is None:
                best_time = best_time.replace(tzinfo=UTC)
            if tz:
                local_time = best_time.astimezone(tz)
                time_str = local_time.strftime("%I:%M %p")
            else:
                time_str = best_time.strftime("%I:%M %p UTC")
            table.setItem(row, transit_col, QTableWidgetItem(time_str))

            # Moon separation
            moon_sep_text = "-"
            if obj_rec.moon_separation_deg is not None:
                moon_sep_text = f"{obj_rec.moon_separation_deg:.0f}°"
            table.setItem(row, moonsep_col, QTableWidgetItem(moon_sep_text))

            # Visibility probability
            prob = obj_rec.visibility_probability
            prob_text = f"{prob:.0%}"
            table.setItem(row, prob_col, QTableWidgetItem(prob_text))

            # Tips
            tips_text = "; ".join(obj_rec.viewing_tips[:2]) if obj_rec.viewing_tips else ""
            if len(tips_text) > 50:
                tips_text = tips_text[:47] + "..."
            table.setItem(row, tips_col, QTableWidgetItem(tips_text))

            # Favorite (check/X icon) - use pre-fetched result
            is_fav = favorite_statuses[row]
            favorite_item = self._create_favorite_item(is_fav)
            # Store object name in item data for context menu
            favorite_item.setData(Qt.ItemDataRole.UserRole, obj.name)
            # Store sort value in a custom role (UserRole + 1) for sorting: 1 = favorite, 0 = not
            # DisplayRole is empty string so no text shows
            favorite_item.setData(Qt.ItemDataRole.UserRole + 1, 1 if is_fav else 0)
            table.setItem(row, fav_col, favorite_item)

        # Re-enable sorting after populating
        table.setSortingEnabled(True)

        # Restore previous sort state if available, otherwise default to Priority (column 0)
        sort_column = table.property("sort_column")
        sort_order = table.property("sort_order")
        header = table.horizontalHeader()
        if sort_column >= 0:
            header.setSortIndicator(sort_column, sort_order)
        else:
            # Default to Priority column (0) descending on first load
            header.setSortIndicator(0, Qt.SortOrder.DescendingOrder)
            table.setProperty("sort_column", 0)
            table.setProperty("sort_order", Qt.SortOrder.DescendingOrder)

        # Resize columns to contents after initial population (one-time)
        if not table.property("initial_resize_done"):
            # Temporarily switch to ResizeToContents to set initial sizes
            for col in range(table.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
            # Force a resize event
            table.resizeColumnsToContents()
            # Switch back to Interactive mode for manual resizing
            for col in range(table.columnCount()):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            table.setProperty("initial_resize_done", True)

    def _show_no_data_message(self, table: QTableWidget, obj_type_str: str) -> None:
        """Show a message when data was loaded but no objects match criteria."""
        # Temporarily disable sorting
        table.setSortingEnabled(False)

        # Get human-readable type name
        type_name = obj_type_str.replace("_", " ").title()

        # Get original column count (preserve table structure)
        original_cols = table.columnCount()
        if original_cols == 0:
            # If no columns, set to 1 for the message
            table.setColumnCount(1)
            original_cols = 1

        # Set table to show one row with message
        table.setRowCount(1)

        # Create a message item
        message = f"No {type_name} objects match the current criteria.\n\n"
        message += "This could be due to:\n"
        message += "• Objects are below the horizon (< 20° altitude)\n"
        message += "• Objects are too faint for current conditions\n"
        message += "• No objects of this type are currently visible\n"
        message += "• Filter text is hiding all results"

        message_item = QTableWidgetItem(message)
        message_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable
        table.setItem(0, 0, message_item)

        # Center align the message
        item = table.item(0, 0)
        if item:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        # Make the message row span all columns
        if original_cols > 1:
            table.setSpan(0, 0, 1, original_cols)

        # Set column widths to prevent horizontal scrolling
        # Make columns stretch to fill available space without exceeding table width
        header = table.horizontalHeader()
        if original_cols > 1:
            # Set all columns to stretch mode so they fill the table width
            for col in range(original_cols):
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        else:
            # Single column - make it stretch
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        # Enable word wrapping for the table to handle long messages
        table.setWordWrap(True)

        # Set row height to accommodate message (with word wrapping)
        table.setRowHeight(0, 120)

        # Re-enable sorting (though it won't do much with one row)
        table.setSortingEnabled(True)

    def _show_no_data_message_alt(self, table: QTableWidget, obj_type_str: str) -> None:
        """Show a message when data was loaded but no objects match criteria."""
        # Temporarily disable sorting
        table.setSortingEnabled(False)

        # Get human-readable type name
        type_name = obj_type_str.replace("_", " ").title()

        # Set table to show one row with message
        table.setRowCount(1)
        # Keep original column count
        original_cols = table.columnCount()
        if original_cols == 0:
            table.setColumnCount(1)

        # Create a message item
        message = f"No {type_name} objects match the current criteria.\n\n"
        message += "This could be due to:\n"
        message += "• Objects are below the horizon (< 20° altitude)\n"
        message += "• Objects are too faint for current conditions\n"
        message += "• No objects of this type are currently visible\n"
        message += "• Filter text is hiding all results"

        message_item = QTableWidgetItem(message)
        message_item.setFlags(Qt.ItemFlag.NoItemFlags)  # Make it non-selectable
        table.setItem(0, 0, message_item)

        # Center align the message
        item = table.item(0, 0)
        if item:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        # Make the message row span all columns
        if original_cols > 1:
            table.setSpan(0, 0, 1, original_cols)

        # Set row height to accommodate message
        table.setRowHeight(0, 120)

        # Re-enable sorting (though it won't do much with one row)
        table.setSortingEnabled(True)

    def _count_visible_stars_for_asterisms_batch(
        self, asterism_names: list[str], asterism_objects: dict[str, Any]
    ) -> dict[str, int]:
        """Count the number of visible component stars for multiple asterisms in a single batch operation."""
        try:
            from celestron_nexstar.api.core.enums import SkyBrightness
            from celestron_nexstar.api.core.exceptions import DatabaseError
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner
            from celestron_nexstar.api.observation.optics import get_current_configuration
            from celestron_nexstar.api.observation.visibility import assess_visibility

            # Get conditions
            location = get_observer_location()
            config = get_current_configuration()
            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()

            def _count_all_stars() -> dict[str, int]:
                db = get_database()

                with db._get_session() as session:
                    # Get sky brightness from light pollution (once for all asterisms)
                    try:
                        light_pollution = get_light_pollution_data(session, location.latitude, location.longitude)
                        # Map Bortle class to SkyBrightness
                        bortle_to_sky_brightness = {
                            1: SkyBrightness.EXCELLENT,
                            2: SkyBrightness.EXCELLENT,
                            3: SkyBrightness.GOOD,
                            4: SkyBrightness.FAIR,
                            5: SkyBrightness.FAIR,
                            6: SkyBrightness.POOR,
                            7: SkyBrightness.URBAN,
                            8: SkyBrightness.URBAN,
                            9: SkyBrightness.URBAN,
                        }
                        sky_brightness = bortle_to_sky_brightness.get(
                            light_pollution.bortle_class.value, SkyBrightness.FAIR
                        )
                    except DatabaseError:
                        # Light pollution data not available, use default
                        logger.warning("Light pollution data not available, using default sky brightness")
                        sky_brightness = SkyBrightness.FAIR

                    # Count visible stars for each asterism
                    counts: dict[str, int] = {}
                    for asterism_name in asterism_names:
                        asterism = asterism_objects.get(asterism_name)
                        if not asterism or not asterism.member_stars:
                            counts[asterism_name] = 0
                            continue

                        visible_count = 0
                        # Look up each member star by name
                        for star_name in asterism.member_stars:
                            # Try to find the star in the database
                            star = db.get_by_name(star_name.strip())
                            if not star:
                                continue

                            try:
                                # Calculate visibility info (same as stars table)
                                vis_info = assess_visibility(
                                    star,
                                    config=config,
                                    sky_brightness=sky_brightness,
                                    min_altitude_deg=20.0,  # Same as stars table
                                    observer_lat=location.latitude,
                                    observer_lon=location.longitude,
                                    dt=conditions.timestamp,
                                )

                                # Use the same visibility probability calculation as the stars table
                                visibility_prob_result = planner._calculate_visibility_probability(
                                    star, conditions, vis_info
                                )

                                # Handle tuple return (probability, explanations) or just probability
                                if isinstance(visibility_prob_result, tuple):
                                    visibility_probability = visibility_prob_result[0]
                                else:
                                    visibility_probability = visibility_prob_result

                                # Count as visible using the same logic as the stars table visibility indicator
                                # A star is "visible" if it would be marked as "Visible" or "Marginal" in the table
                                altitude = vis_info.altitude_deg or 0.0
                                if altitude >= 20.0 and visibility_probability >= 0.5:
                                    # "Visible" status
                                    visible_count += 1
                                elif altitude >= 10.0 and visibility_probability >= 0.3:
                                    # "Marginal" status - still count as visible
                                    visible_count += 1
                            except Exception as e:
                                logger.debug(f"Error calculating visibility for star '{star_name}': {e}")
                                continue

                        counts[asterism_name] = visible_count

                    return counts

            result = _count_all_stars()
            return result if isinstance(result, dict) else dict.fromkeys(asterism_names, 0)
        except Exception as e:
            logger.debug(f"Error counting visible stars for asterisms: {e}")
            # Return zeros for all asterisms on error
            return dict.fromkeys(asterism_names, 0)

    def _count_visible_stars_batch(self, constellation_names: list[str]) -> dict[str, int]:
        """Count the number of visible stars for multiple constellations in a single batch operation."""
        print(f"DEBUG: _count_visible_stars_batch called with {len(constellation_names)} constellations")
        try:
            from celestron_nexstar.api.core.enums import SkyBrightness
            from celestron_nexstar.api.core.exceptions import DatabaseError
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner
            from celestron_nexstar.api.observation.optics import get_current_configuration
            from celestron_nexstar.api.observation.visibility import assess_visibility

            # Get conditions
            config = get_current_configuration()
            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()
            location = get_observer_location()
            location = get_observer_location()

            def _count_all_stars() -> dict[str, int]:
                db = get_database()

                with db._get_session() as session:
                    # Get sky brightness from light pollution (once for all constellations)
                    try:
                        light_pollution = get_light_pollution_data(session, location.latitude, location.longitude)
                        # Map Bortle class to SkyBrightness
                        bortle_to_sky_brightness = {
                            1: SkyBrightness.EXCELLENT,
                            2: SkyBrightness.EXCELLENT,
                            3: SkyBrightness.GOOD,
                            4: SkyBrightness.FAIR,
                            5: SkyBrightness.FAIR,
                            6: SkyBrightness.POOR,
                            7: SkyBrightness.URBAN,
                            8: SkyBrightness.URBAN,
                            9: SkyBrightness.URBAN,
                        }
                        sky_brightness = bortle_to_sky_brightness.get(
                            light_pollution.bortle_class.value, SkyBrightness.FAIR
                        )
                    except DatabaseError:
                        # Light pollution data not available, use default
                        logger.warning("Light pollution data not available, using default sky brightness")
                        sky_brightness = SkyBrightness.FAIR

                    # Debug: Log conditions once
                    seeing_score = conditions.seeing_score if hasattr(conditions, "seeing_score") else None
                    cloud_cover = (
                        conditions.weather.cloud_cover_percent
                        if hasattr(conditions, "weather") and conditions.weather
                        else None
                    )
                    logger.info(
                        f"Visibility conditions: seeing_score={seeing_score}, cloud_cover={cloud_cover}, timestamp={conditions.timestamp}"
                    )

                    # Count stars for each constellation
                    counts: dict[str, int] = {}
                    print(f"DEBUG: Starting to count stars for {len(constellation_names)} constellations")
                    for constellation_name in constellation_names:
                        # Get stars in this constellation
                        stars = db.filter_objects(object_type="star", constellation=constellation_name, limit=100)

                        # Debug logging
                        print(f"DEBUG: Constellation '{constellation_name}': Found {len(stars)} stars")
                        logger.info(f"Constellation '{constellation_name}': Found {len(stars)} stars")

                        visible_count = 0
                        for star in stars:
                            try:
                                # Calculate visibility info (same as stars table)
                                vis_info = assess_visibility(
                                    star,
                                    config=config,
                                    sky_brightness=sky_brightness,
                                    min_altitude_deg=20.0,  # Same as stars table
                                    observer_lat=location.latitude,
                                    observer_lon=location.longitude,
                                    dt=conditions.timestamp,
                                )

                                # Use the same visibility probability calculation as the stars table
                                visibility_prob_result = planner._calculate_visibility_probability(
                                    star, conditions, vis_info
                                )

                                # Handle tuple return (probability, explanations) or just probability
                                if isinstance(visibility_prob_result, tuple):
                                    visibility_probability = visibility_prob_result[0]
                                    explanations = visibility_prob_result[1]
                                else:
                                    visibility_probability = visibility_prob_result
                                    explanations = []

                                # Debug: Log first few stars for troubleshooting
                                if visible_count < 3 or len(stars) - visible_count < 3:
                                    logger.info(
                                        f"  Star '{star.name}': alt={vis_info.altitude_deg:.1f}°, "
                                        f"mag={star.magnitude}, prob={visibility_probability:.3f}, "
                                        f"obs_score={vis_info.observability_score:.3f}, "
                                        f"is_visible={vis_info.is_visible}"
                                    )
                                    if explanations:
                                        logger.info(f"    Explanations: {explanations}")

                                # Count as visible using the same logic as the stars table visibility indicator
                                # A star is "visible" if it would be marked as "Visible" or "Marginal" in the table
                                altitude = vis_info.altitude_deg or 0.0
                                if altitude >= 20.0 and visibility_probability >= 0.5:
                                    # "Visible" status
                                    visible_count += 1
                                elif altitude >= 10.0 and visibility_probability >= 0.3:
                                    # "Marginal" status - still count as visible
                                    visible_count += 1
                            except Exception as e:
                                logger.debug(f"Error calculating visibility for star '{star.name}': {e}")
                                continue

                        counts[constellation_name] = visible_count
                        print(
                            f"DEBUG: Constellation '{constellation_name}': {visible_count} visible stars out of {len(stars)} total"
                        )
                        logger.info(
                            f"Constellation '{constellation_name}': {visible_count} visible stars out of {len(stars)} total"
                        )

                    return counts

            result = _count_all_stars()
            print(f"DEBUG: _count_all_stars returned: {result}")
            logger.info(f"Visibility count results: {result}")
            return result
        except Exception as e:
            print(f"DEBUG: Exception in _count_visible_stars_batch: {e}")
            import traceback

            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            logger.error(f"Error counting visible stars: {e}", exc_info=True)
            # Return zeros for all constellations on error
            return dict.fromkeys(constellation_names, 0)

    def _populate_constellation_table(self, table: QTableWidget, constellation_names: list[str]) -> None:
        """Populate table with constellation names (must be called on main thread)."""
        if not constellation_names:
            # Show no data message for constellations/asterisms
            obj_type_str = table.property("object_type")
            if obj_type_str:
                self._show_no_data_message(table, obj_type_str)
            return

        # Sort constellation names alphabetically (A-Z)
        sorted_names = sorted(constellation_names, key=str.lower)

        # Temporarily disable sorting while populating to improve performance
        table.setSortingEnabled(False)

        table.setRowCount(len(sorted_names))

        # Check all favorites in a single batch query (much more efficient)
        from celestron_nexstar.api.favorites import are_favorites

        try:
            favorite_dict = are_favorites(sorted_names)
            # Convert dict to list in same order as sorted_names
            favorite_statuses = [favorite_dict.get(name, False) for name in sorted_names]
        except Exception:
            # If batch check fails, fall back to all False
            favorite_statuses = [False] * len(sorted_names)

        # Check if this is a constellation table (has 3 columns) or asterism table (has 3 columns now)
        is_constellation_table = table.columnCount() == 3
        obj_type_str = table.property("object_type")
        is_asterism_table = obj_type_str == "asterism"

        # Now populate table with all data (initially with 0 counts, will update when async count completes)
        visible_star_counts: dict[str, int] = dict.fromkeys(sorted_names, 0)

        for row, constellation_name in enumerate(sorted_names):
            # Constellation name (no star indicator - we have a dedicated favorites column)
            name_item = QTableWidgetItem(constellation_name)
            # Store object name in item data for context menu
            name_item.setData(Qt.ItemDataRole.UserRole, constellation_name)
            table.setItem(row, 0, name_item)

            if is_constellation_table:
                # Initially set to 0, will be updated when async count completes
                visible_count = visible_star_counts.get(constellation_name, 0)
                stars_item = QTableWidgetItem(str(visible_count))
                stars_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                # Store count as numeric value for proper sorting
                stars_item.setData(Qt.ItemDataRole.UserRole, visible_count)
                table.setItem(row, 1, stars_item)

                # Favorite (check/X icon) - use pre-fetched result
                is_fav = favorite_statuses[row]
                favorite_item = self._create_favorite_item(is_fav)
                # Store object name in item data for context menu
                favorite_item.setData(Qt.ItemDataRole.UserRole, constellation_name)
                # Store sort value in a custom role (UserRole + 1) for sorting: 1 = favorite, 0 = not
                # DisplayRole is empty string so no text shows
                favorite_item.setData(Qt.ItemDataRole.UserRole + 1, 1 if is_fav else 0)
                table.setItem(row, 2, favorite_item)

        # Re-enable sorting after populating
        table.setSortingEnabled(True)

        # Start background thread to count visible stars (non-blocking)
        if is_constellation_table:
            # Clean up any existing thread for this table
            if table in self._visibility_threads:
                old_thread = self._visibility_threads[table]
                if old_thread.isRunning():
                    # Detach the old thread safely: stop it, disconnect signals so it can't update the UI,
                    # and keep a reference until it finishes to avoid "QThread destroyed while running".
                    old_thread.requestInterruption()
                    with contextlib.suppress(Exception):
                        old_thread.count_ready.disconnect()
                    with contextlib.suppress(Exception):
                        old_thread.counts_complete.disconnect()
                    with contextlib.suppress(Exception):
                        old_thread.finished.disconnect()

                    if old_thread not in self._stopping_threads:
                        self._stopping_threads.append(old_thread)

                    def _finalize_old_thread(t: QThread = old_thread) -> None:
                        try:
                            if t in self._stopping_threads:
                                self._stopping_threads.remove(t)
                            t.deleteLater()
                        except Exception:
                            pass

                    old_thread.finished.connect(_finalize_old_thread, Qt.ConnectionType.QueuedConnection)
                else:
                    old_thread.deleteLater()
                del self._visibility_threads[table]

            asterism_objects = None
            if is_asterism_table:
                asterism_objects = self._asterism_objects_cache
                print(f"DEBUG: Creating visibility thread for asterisms with {len(asterism_objects)} cached objects")
                print(f"DEBUG: Asterism names: {sorted_names[:5]}...")  # Show first 5
                print(f"DEBUG: Cached asterism names: {list(asterism_objects.keys())[:5]}...")  # Show first 5

            visibility_thread = VisibilityCountThread(
                sorted_names,
                is_asterism=is_asterism_table,
                asterism_objects=asterism_objects,
            )

            # Store thread reference to prevent garbage collection
            self._visibility_threads[table] = visibility_thread

            def update_count(name: str, count: int) -> None:
                """Update a single row in the table with visibility count."""
                # Find the row with this name
                for row in range(table.rowCount()):
                    name_item = table.item(row, 0)
                    if name_item:
                        constellation_name = name_item.data(Qt.ItemDataRole.UserRole)
                        if constellation_name == name:
                            stars_item = table.item(row, 1)
                            if stars_item:
                                old_value = stars_item.text()
                                stars_item.setText(str(count))
                                stars_item.setData(Qt.ItemDataRole.UserRole, count)
                                print(f"DEBUG: Updated {name} from '{old_value}' to {count}")
                                logger.debug(f"Updated {name} visibility count to {count}")
                                break

            def cleanup_thread() -> None:
                """Clean up thread reference when finished."""
                if table in self._visibility_threads:
                    thread = self._visibility_threads.pop(table)
                    thread.deleteLater()

            # Use QueuedConnection to ensure signal is processed on main thread
            visibility_thread.count_ready.connect(update_count, Qt.ConnectionType.QueuedConnection)
            visibility_thread.counts_complete.connect(lambda: logger.info("All visibility counts completed"))
            visibility_thread.finished.connect(cleanup_thread, Qt.ConnectionType.QueuedConnection)
            print(f"DEBUG: Starting visibility count thread for {len(sorted_names)} constellations/asterisms")
            visibility_thread.start()

        # Set default sort indicator on Constellation column (A-Z ascending)
        header = table.horizontalHeader()
        header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
        table.setProperty("sort_column", 0)
        table.setProperty("sort_order", Qt.SortOrder.AscendingOrder)

        # Set column resize modes and minimum widths
        obj_type_str = table.property("object_type")
        if obj_type_str == "constellation":
            header_labels = ["Constellation", "Visible Stars", "Favorite"]
        elif obj_type_str == "asterism":
            header_labels = ["Asterism", "Visible Stars", "Favorite"]
        else:
            header_labels = ["Constellation", "Visible Stars", "Favorite"]  # Fallback

        # Calculate minimum widths based on header text
        font_metrics = QFontMetrics(header.font())
        min_widths = [font_metrics.horizontalAdvance(label) + 20 for label in header_labels]  # Add 20px padding

        # Set all columns to Interactive mode and minimum widths
        for col in range(table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            header.setMinimumSectionSize(min_widths[col])

    def _create_table_toolbar(self) -> None:
        """Create toolbar for table controls in the top toolbar area."""
        toolbar = QToolBar("Table Controls")
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self.top_toolbar = toolbar  # Store reference for minimal UI mode

        # Filter textbox (left side)
        filter_label = QLabel()
        toolbar.addWidget(filter_label)
        self.filter_textbox = QLineEdit()
        self.filter_textbox.setPlaceholderText("Filter objects...")
        self.filter_textbox.textChanged.connect(self._on_filter_changed)
        self._update_textbox_placeholder_style(self.filter_textbox)
        toolbar.addWidget(self.filter_textbox)

        # Clear filter button (theme-aware icon)
        self.filter_clear_button = QToolButton()
        self.filter_clear_button.setAutoRaise(True)
        self.filter_clear_button.setToolTip("Clear filter")
        self.filter_clear_button.setStatusTip("Clear filter text")
        self.filter_clear_button.setEnabled(False)
        self.filter_clear_button.setIcon(self._create_icon("close-circle", ["edit-clear", "window-close", "close"]))
        self.filter_clear_button.clicked.connect(lambda: self.filter_textbox.clear())  # type: ignore[arg-type]
        toolbar.addWidget(self.filter_clear_button)

        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Refresh button
        refresh_icon = self._create_icon("refresh", ["view-refresh", "reload"])
        self.refresh_action = toolbar.addAction(refresh_icon, "Refresh")
        self.refresh_action.setToolTip("REFRESH")
        self.refresh_action.setStatusTip("Refresh current tab")
        self.refresh_action.triggered.connect(self._on_refresh_clicked)

        # Load All button
        load_all_icon = self._create_icon("download", ["download", "folder-download"])
        self.load_all_action = toolbar.addAction(load_all_icon, "Load All")
        self.load_all_action.setToolTip("LOAD ALL")
        self.load_all_action.setStatusTip("Load all tabs")
        self.load_all_action.triggered.connect(self._on_load_all_clicked)

        # Info button (right side, initially disabled)
        info_icon = self._create_icon("info", ["dialog-information", "help-about"])
        self.info_action = toolbar.addAction(info_icon, "Info")
        self.info_action.setToolTip("INFO")
        self.info_action.setStatusTip("Show object information")
        self.info_action.setEnabled(False)  # Disabled until selection
        self.info_action.triggered.connect(self._on_info_clicked)

    def _on_table_selection_changed(self) -> None:
        """Handle table selection change - enable/disable info button."""
        # Get current table
        current_table = self._get_current_table()
        if current_table:
            selected_rows = current_table.selectionModel().selectedRows()
            # Enable if exactly 1 row is selected
            self.info_action.setEnabled(len(selected_rows) == 1)

    def _get_current_table(self) -> QTableWidget | None:
        """Get the currently visible table widget."""
        if not hasattr(self, "tab_widget"):
            return None
        current_index = self.tab_widget.currentIndex()
        if current_index < 0:
            return None
        widget = self.tab_widget.widget(current_index)
        if isinstance(widget, QTableWidget):
            return widget
        return None

    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click - reload current tab."""
        current_table = self._get_current_table()
        if current_table:
            # Clear cache for this object type
            obj_type_str = current_table.property("object_type")
            if obj_type_str and obj_type_str in self._objects_cache:
                del self._objects_cache[obj_type_str]
            if obj_type_str == "asterism":
                self._asterism_objects_cache.clear()

            # Clear table
            current_table.setRowCount(0)

            # Reload
            self._load_objects_table(current_table)

    def _on_load_all_clicked(self) -> None:
        """Handle load all button click - load data for all tabs."""
        if not hasattr(self, "tab_widget"):
            return

        # Get all tabs that need loading (includes all object types: stars, planets, galaxies, etc.
        # including variable_star and zodiacal)
        tabs_to_load = []
        for i in range(self.tab_widget.count()):
            tab_widget = self.tab_widget.widget(i)
            if isinstance(tab_widget, QTableWidget):
                obj_type_str = tab_widget.property("object_type")
                # Load if not cached and not already loading
                # This includes all types: star, planet, galaxy, nebula, cluster, double_star,
                # asterism, constellation, moon, variable_star, zodiacal
                if (
                    obj_type_str
                    and obj_type_str not in self._objects_cache
                    and obj_type_str not in self._loading_threads
                ):
                    tabs_to_load.append((i, tab_widget, obj_type_str))

        if not tabs_to_load:
            # All tabs are already loaded or loading
            return

        # Show loading dialog
        progress = self._create_progress_dialog(f"Loading all tabs ({len(tabs_to_load)} tabs)...")
        progress.setMaximum(len(tabs_to_load))
        progress.show()

        # Process events to show the dialog immediately
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        # Load each tab
        for idx, (_tab_index, table, obj_type_str) in enumerate(tabs_to_load):
            progress.setValue(idx)
            progress.setLabelText(
                f"Loading {obj_type_str.replace('_', ' ').title()} ({idx + 1}/{len(tabs_to_load)})..."
            )
            QApplication.processEvents()

            # Load the table (suppress individual progress dialog)
            self._load_objects_table(table, show_progress=False)

            # Wait for loading to complete (check if thread is done)
            if obj_type_str in self._loading_threads:
                thread = self._loading_threads[obj_type_str]
                if thread.isRunning():
                    thread.wait(5000)  # Wait up to 5 seconds for each tab
                # Thread cleanup is handled by the finished signal connection

        progress.setValue(len(tabs_to_load))
        progress.close()

        # Process events to allow any pending thread cleanup signals
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

    def _on_filter_changed(self, text: str) -> None:
        """Handle filter text change - filter table rows."""
        # Enable/disable clear button based on whether there's a filter value
        if hasattr(self, "filter_clear_button"):
            self.filter_clear_button.setEnabled(bool(text.strip()))

        current_table = self._get_current_table()
        if not current_table:
            return

        filter_text = text.lower().strip()

        # Show all rows if filter is empty
        if not filter_text:
            for row in range(current_table.rowCount()):
                current_table.showRow(row)
            return

        # Filter rows based on text matching any column
        for row in range(current_table.rowCount()):
            match = False
            for col in range(current_table.columnCount()):
                item = current_table.item(row, col)
                if item and filter_text in item.text().lower():
                    match = True
                    break
            current_table.setRowHidden(row, not match)

    def _on_info_clicked(self) -> None:
        """Handle info button click - show object information dialog."""
        current_table = self._get_current_table()
        if not current_table:
            return

        # Get selected row
        selected_rows = current_table.selectionModel().selectedRows()
        if not selected_rows or len(selected_rows) != 1:
            return

        row = selected_rows[0].row()

        # Check if this is the constellation or asterism tab
        obj_type = current_table.property("object_type")
        if obj_type == "constellation":
            # Get constellation name from column 0
            name_item = current_table.item(row, 0)
            if not name_item:
                return
            # Try to get from UserRole data first (clean name without star)
            constellation_name = name_item.data(Qt.ItemDataRole.UserRole)
            if not constellation_name:
                # Fallback: extract from display text (remove star if present)
                display_text = name_item.text()
                constellation_name = display_text.removeprefix("★ ").strip()

            # Show loading dialog
            progress = self._create_progress_dialog(f"Loading information for {constellation_name}...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show constellation info dialog
            from celestron_nexstar.gui.dialogs.constellation_info_dialog import ConstellationInfoDialog

            constellation_dialog = ConstellationInfoDialog(self, constellation_name)
            progress.close()
            constellation_dialog.exec()
        elif obj_type == "asterism":
            # Get asterism name from the table
            name_item = current_table.item(row, 0)
            if not name_item:
                return
            # Try to get from UserRole data first (clean name without star)
            asterism_name = name_item.data(Qt.ItemDataRole.UserRole)
            if not asterism_name:
                # Fallback: extract from display text (remove star if present)
                display_text = name_item.text()
                asterism_name = display_text.removeprefix("★ ").strip()

            # Show asterism info dialog
            from celestron_nexstar.gui.dialogs.asterism_info_dialog import AsterismInfoDialog

            asterism_dialog = AsterismInfoDialog(self, asterism_name)
            asterism_dialog.exec()
        else:
            # Get object name from the Name column (column 1)
            name_item = current_table.item(row, 1)
            if not name_item:
                return

            # Try to get from UserRole data first (clean name without star)
            object_name = name_item.data(Qt.ItemDataRole.UserRole)
            if not object_name:
                # Fallback: extract from display text (remove star if present)
                display_text = name_item.text()
                object_name = display_text.removeprefix("★ ").strip()

            # Show loading dialog
            progress = self._create_progress_dialog(f"Loading information for {object_name}...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show info dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.object_info_dialog import ObjectInfoDialog

            obj_dialog = ObjectInfoDialog(self, object_name)
            progress.close()
            obj_dialog.exec()

    def _on_sort_changed(self, table: QTableWidget, logical_index: int, order: Qt.SortOrder) -> None:
        """Handle sort indicator change - track sort column and order."""
        table.setProperty("sort_column", logical_index)
        table.setProperty("sort_order", order)

    def _on_table_context_menu(self, table: QTableWidget, position: QPoint) -> None:
        """Handle context menu request on table."""
        item = table.itemAt(position)
        if not item:
            return

        # Get the row
        row = item.row()

        # Determine which column has the name based on object type
        obj_type = table.property("object_type")
        name_item = table.item(row, 0) if obj_type in ("constellation", "asterism") else table.item(row, 1)

        if not name_item:
            return

        # Try to get from UserRole data first (clean name without star)
        object_name = name_item.data(Qt.ItemDataRole.UserRole)
        if not object_name:
            # Fallback: try to extract from display text (remove star if present)
            display_text = name_item.text()
            object_name = display_text.removeprefix("★ ").strip()

        if not object_name:
            return

        # Check if favorite

        from celestron_nexstar.api.favorites import is_favorite

        try:
            is_fav = is_favorite(object_name)
        except Exception:
            is_fav = False

        # Create context menu
        menu = QMenu(self)

        # Info action
        info_action = menu.addAction("Show Info")
        info_action.triggered.connect(lambda: self._on_context_menu_info(table, row))

        menu.addSeparator()

        # Favorite/Unfavorite action
        if is_fav:
            fav_action = menu.addAction("★ Remove from Favorites")
            fav_action.triggered.connect(lambda: self._on_context_menu_unfavorite(object_name, table))
        else:
            fav_action = menu.addAction("☆ Add to Favorites")
            fav_action.triggered.connect(lambda: self._on_context_menu_favorite(object_name, table))

        menu.addSeparator()

        # Add to Queue action (supports multiple selections)
        selected_count = len(table.selectionModel().selectedRows()) if table.selectionModel().selectedRows() else 0
        if selected_count > 1:
            add_to_queue_action = menu.addAction(f"Add {selected_count} Objects to Goto Queue")
        else:
            add_to_queue_action = menu.addAction("Add to Goto Queue")
        add_to_queue_action.triggered.connect(lambda: self._on_context_menu_add_to_queue(table, row))

        # Add All Stars to Queue action (for constellations and asterisms only)
        obj_type = table.property("object_type")
        if obj_type in ("constellation", "asterism"):
            add_stars_action = menu.addAction("Add All Stars to Goto Queue")
            add_stars_action.triggered.connect(lambda: self._on_context_menu_add_all_stars_to_queue(table, row))

        # Compare Objects action
        compare_action = menu.addAction("Compare Objects")
        compare_action.triggered.connect(lambda: self._on_context_menu_compare_objects(table, row))

        menu.addSeparator()

        # Log Observation action
        log_observation_action = menu.addAction("Log Observation")
        log_observation_action.triggered.connect(lambda: self._on_context_menu_log_observation(object_name))

        # Show menu at cursor position
        menu.exec(table.mapToGlobal(position))

    def _on_context_menu_info(self, table: QTableWidget, row: int) -> None:
        """Handle context menu info action."""
        # Determine which column has the name based on object type
        obj_type = table.property("object_type")
        name_item = table.item(row, 0) if obj_type in ("constellation", "asterism") else table.item(row, 1)

        if not name_item:
            return

        # Try to get from UserRole data first (clean name without star)
        object_name = name_item.data(Qt.ItemDataRole.UserRole)
        if not object_name:
            # Fallback: try to extract from display text
            display_text = name_item.text()
            object_name = display_text.removeprefix("★ ").strip()

        if object_name:
            # Use the existing info dialog functionality
            if obj_type == "constellation":
                from celestron_nexstar.gui.dialogs.constellation_info_dialog import ConstellationInfoDialog

                constellation_dialog = ConstellationInfoDialog(self, object_name)
                constellation_dialog.exec()
            elif obj_type == "asterism":
                from celestron_nexstar.gui.dialogs.asterism_info_dialog import AsterismInfoDialog

                asterism_dialog = AsterismInfoDialog(self, object_name)
                asterism_dialog.exec()
            else:
                from celestron_nexstar.gui.dialogs.object_info_dialog import ObjectInfoDialog

                obj_dialog = ObjectInfoDialog(self, object_name)
                obj_dialog.exec()
            # Refresh table in case favorite status changed
            self._refresh_table_favorites(table)

    def _on_context_menu_favorite(self, object_name: str, table: QTableWidget) -> None:
        """Handle context menu add to favorites action."""
        from celestron_nexstar.api.favorites import add_favorite

        try:
            # Get object type from table property
            obj_type = table.property("object_type")
            success = add_favorite(object_name, obj_type)
            if success:
                self._show_toast(f"Added '{object_name}' to favorites")
                # Refresh the table to show the star indicator
                self._refresh_table_favorites(table)
        except Exception as e:
            logger.error(f"Error adding favorite: {e}", exc_info=True)

    def _on_context_menu_unfavorite(self, object_name: str, table: QTableWidget) -> None:
        """Handle context menu remove from favorites action."""
        from celestron_nexstar.api.favorites import remove_favorite

        try:
            success = remove_favorite(object_name)
            if success:
                self._show_toast(f"Removed '{object_name}' from favorites")
                # Refresh the table to remove the star indicator
                self._refresh_table_favorites(table)
        except Exception as e:
            logger.error(f"Error removing favorite: {e}", exc_info=True)

    def _on_context_menu_add_to_queue(self, table: QTableWidget, row: int) -> None:
        """Handle context menu add to queue action."""
        # Get all selected rows (or just the right-clicked row if no selection)
        selected_rows = table.selectionModel().selectedRows()
        rows_to_add = [row] if not selected_rows else [r.row() for r in selected_rows]

        # Collect object names from selected rows
        obj_type = table.property("object_type")
        object_names: list[str] = []

        for r in rows_to_add:
            name_item = table.item(r, 0) if obj_type in ("constellation", "asterism") else table.item(r, 1)
            if not name_item:
                continue

            object_name = name_item.data(Qt.ItemDataRole.UserRole)
            if not object_name:
                display_text = name_item.text()
                object_name = display_text.removeprefix("★ ").strip()

            if object_name:
                object_names.append(object_name)

        if not object_names:
            return

        # Get the CelestialObjects

        from celestron_nexstar.api.catalogs.catalogs import get_object_by_name

        try:
            objects_to_add = []
            not_found = []

            for object_name in object_names:
                matches = get_object_by_name(object_name)
                if not matches:
                    not_found.append(object_name)
                else:
                    obj = matches[0].with_current_position()
                    objects_to_add.append(obj)

            # Show warning for objects not found
            if not_found:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self, "Objects Not Found", f"Could not find the following objects:\n{', '.join(not_found)}"
                )

            if not objects_to_add:
                return

            # Open or get goto queue window
            if not hasattr(self, "_goto_queue_window") or self._goto_queue_window is None:
                self._on_goto_queue()

            # Add objects to queue
            # Update telescope reference if needed
            if self._goto_queue_window is not None:
                if self._goto_queue_window.telescope != self.telescope:
                    self._goto_queue_window.telescope = self.telescope

                # Use add_objects for multiple, add_object for single (for efficiency)
                if len(objects_to_add) > 1:
                    self._goto_queue_window.add_objects(objects_to_add)
                else:
                    self._goto_queue_window.add_object(objects_to_add[0])

                self._goto_queue_window.show()
                self._goto_queue_window.raise_()
                self._goto_queue_window.activateWindow()

        except Exception as e:
            logger.error(f"Error adding objects to queue: {e}", exc_info=True)
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Error", f"Failed to add objects to queue: {e}")

    def _on_context_menu_add_all_stars_to_queue(self, table: QTableWidget, row: int) -> None:
        """Handle context menu add all stars to queue action for constellations/asterisms."""
        # Get object name
        obj_type = table.property("object_type")
        name_item = table.item(row, 0) if obj_type in ("constellation", "asterism") else table.item(row, 1)

        if not name_item:
            return

        object_name = name_item.data(Qt.ItemDataRole.UserRole)
        if not object_name:
            display_text = name_item.text()
            object_name = display_text.removeprefix("★ ").strip()

        if not object_name:
            return

        from PySide6.QtWidgets import QMessageBox

        from celestron_nexstar.api.catalogs.catalogs import get_object_by_name
        from celestron_nexstar.api.database.database import get_database

        try:
            stars_to_add = []

            if obj_type == "asterism":
                # Get asterism from cache to access member_stars
                asterism = self._asterism_objects_cache.get(object_name)
                if not asterism or not asterism.member_stars:
                    QMessageBox.information(self, "No Stars", f"Asterism '{object_name}' has no member stars defined.")
                    return

                # Look up each star by name
                for star_name in asterism.member_stars:
                    star_name = star_name.strip()
                    if not star_name:
                        continue
                    matches = get_object_by_name(star_name)
                    if matches:
                        obj = matches[0].with_current_position()
                        stars_to_add.append(obj)

            elif obj_type == "constellation":
                # Query database for all stars in this constellation
                db = get_database()
                stars = db.filter_objects(object_type="star", constellation=object_name, limit=200)
                for star in stars:
                    star = star.with_current_position()
                    stars_to_add.append(star)

            if not stars_to_add:
                QMessageBox.information(self, "No Stars Found", f"No stars found for {obj_type} '{object_name}'.")
                return

            # Open or get goto queue window
            if not hasattr(self, "_goto_queue_window") or self._goto_queue_window is None:
                self._on_goto_queue()

            # Add all stars to queue
            if self._goto_queue_window is not None:
                if self._goto_queue_window.telescope != self.telescope:
                    self._goto_queue_window.telescope = self.telescope

                self._goto_queue_window.add_objects(stars_to_add)
                self._goto_queue_window.show()
                self._goto_queue_window.raise_()
                self._goto_queue_window.activateWindow()

                QMessageBox.information(
                    self,
                    "Stars Added",
                    f"Added {len(stars_to_add)} star(s) from {obj_type} '{object_name}' to the goto queue.",
                )

        except Exception as e:
            logger.error(f"Error adding stars to queue: {e}", exc_info=True)
            QMessageBox.critical(self, "Error", f"Failed to add stars to queue: {e}")

    def _on_context_menu_log_observation(self, object_name: str) -> None:
        """Handle context menu log observation action."""
        from celestron_nexstar.gui.dialogs.observation_edit_dialog import ObservationEditDialog

        dialog = ObservationEditDialog(self, object_name=object_name)
        dialog.exec()

    def _refresh_table_favorites(self, table: QTableWidget) -> None:
        """Refresh favorite indicators in a table."""
        obj_type_str = table.property("object_type")
        if not obj_type_str:
            return

        # Reload the table data
        if obj_type_str in self._objects_cache:
            objects = self._objects_cache[obj_type_str]
            if objects:
                if obj_type_str in ("constellation", "asterism"):
                    self._populate_constellation_table(table, objects)  # type: ignore[arg-type]
                else:
                    self._populate_table(table, objects)  # type: ignore[arg-type]

    def _on_cell_double_clicked(self, item: QTableWidgetItem) -> None:
        """Handle cell double-click - copy cell text to clipboard."""
        text = item.text()
        if text:
            from PySide6.QtWidgets import QApplication

            clipboard = QApplication.clipboard()
            clipboard.setText(text)

            # Show toast notification with copied text
            self._show_toast(f"Copied: {text}")

    def _show_toast(self, message: str, duration_ms: int = 2000) -> None:
        """Show a toast notification message."""
        # Truncate long messages to prevent toast from being too wide
        max_length = 50
        display_message = message
        if len(message) > max_length:
            display_message = message[: max_length - 3] + "..."

        # Detect theme for toast styling
        from PySide6.QtGui import QPalette

        is_dark = False
        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            is_dark = brightness < 128

        # Create a label for the toast
        toast = QLabel(display_message, self)
        # Theme-aware toast styling
        bg_color = "rgba(0, 0, 0, 200)" if not is_dark else "rgba(255, 255, 255, 200)"
        text_color = "white" if not is_dark else "black"
        toast.setStyleSheet(
            f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 12px;
            }}
        """
        )
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.adjustSize()

        # Position toast in the center of the window
        x = (self.width() - toast.width()) // 2
        y = self.height() // 3  # Position in upper third
        toast.move(x, y)
        toast.raise_()
        toast.show()

        # Hide toast after duration
        QTimer.singleShot(duration_ms, toast.deleteLater)

    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change - load data for the selected tab if not already loaded."""
        if index < 0:
            return

        tab_widget = self.tab_widget.widget(index)
        if isinstance(tab_widget, QTableWidget):
            obj_type_str = tab_widget.property("object_type")
            # Only load/refresh visibility-heavy tabs when visible
            if obj_type_str in ("constellation", "asterism"):
                if obj_type_str not in self._objects_cache and tab_widget.rowCount() == 0:
                    self._load_objects_table(tab_widget)
            else:
                if obj_type_str and obj_type_str not in self._objects_cache and tab_widget.rowCount() == 0:
                    self._load_objects_table(tab_widget)
            # If data is in cache but table is empty, it means no data matches criteria
            # (_show_no_data_message will have been called)

    def _create_status_bar(self) -> None:
        """Create the status bar with GPS, date/time, and telescope position."""
        status_bar = QStatusBar()
        status_bar.setSizeGripEnabled(False)  # Disable default resize grip (on right)
        self.setStatusBar(status_bar)

        # GPS status (left side, temporary, clickable)
        self.gps_label = ClickableLabel()
        self.gps_label.setTextFormat(Qt.TextFormat.RichText)  # Enable HTML formatting
        self.gps_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.gps_label.clicked.connect(self._on_gps_clicked)
        status_bar.addWidget(self.gps_label)

        # Vertical separator
        self.separator = QLabel("|")
        self.separator.setObjectName("separator")
        status_bar.addWidget(self.separator)

        # Date & Time (left side, temporary, clickable, next to GPS)
        self.datetime_label = ClickableLabel()
        self.datetime_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.datetime_label.clicked.connect(self._on_datetime_clicked)
        status_bar.addWidget(self.datetime_label)

        # Add spacer to push permanent widgets to the right
        spacer = QLabel("")
        spacer.setMinimumWidth(0)
        spacer.setMaximumWidth(16777215)  # QWIDGETSIZE_MAX
        spacer.setObjectName("status_bar_spacer")
        status_bar.addPermanentWidget(spacer)

        # Telescope position (right side, permanent)
        self.position_label = QLabel("Position: --")
        status_bar.addPermanentWidget(self.position_label)

        # Add resize grip after the position control (on the right side)
        # Create a container widget for the resize grip
        resize_grip_container = QWidget()
        resize_grip_layout = QHBoxLayout(resize_grip_container)
        resize_grip_layout.setContentsMargins(0, 0, 0, 0)
        resize_grip_layout.setSpacing(0)

        # Create a size grip and add it to the container
        resize_grip = QSizeGrip(resize_grip_container)
        resize_grip_layout.addWidget(resize_grip)
        resize_grip_container.setFixedWidth(16)  # Set fixed width for the grip

        # Add the resize grip container after the position label
        status_bar.addPermanentWidget(resize_grip_container)

    def _update_status_bar(self) -> None:
        """Update the status bar with current information."""
        # Update GPS status
        self._update_gps_status()

        # Update date & time (without label prefix)
        try:
            location = get_observer_location()
            now = datetime.now(UTC)  # Use UTC time, then convert to local
            time_str = format_local_time(now, location.latitude, location.longitude)
            # Extract just the time part (remove date if needed, or show full string)
            self.datetime_label.setText(time_str)
        except Exception as e:
            # Log error for debugging
            logger.debug(f"Error updating date/time: {e}", exc_info=True)
            # Fallback to simple time display
            try:
                now = datetime.now()
                time_str = now.strftime("%Y-%m-%d %I:%M %p")
                self.datetime_label.setText(time_str)
            except Exception:
                self.datetime_label.setText("--")

        # Update telescope position if connected
        if self.telescope and self.telescope.protocol.is_open():
            # Use worker thread to avoid blocking UI
            if self._position_thread is None or not self._position_thread.isRunning():
                self._position_thread = GetPositionRADecThread(self.telescope)
                self._position_thread.position_ready.connect(
                    lambda coords: self.position_label.setText(
                        f"Position: RA {coords.ra_hours:.4f}h, Dec {coords.dec_degrees:+.4f}°"
                    )
                )
                self._position_thread.error_occurred.connect(lambda _: self.position_label.setText("Position: --"))
                self._position_thread.finished.connect(lambda: setattr(self, "_position_thread", None))
                self._position_thread.start()
        else:
            self.position_label.setText("Position: --")

    def _update_gps_status(self) -> None:
        """Update GPS status indicator color based on connection and GPS availability."""
        # Default: red (not connected or no GPS)

        # Check if telescope is connected
        if self.telescope and self.telescope.protocol.is_open():
            # Use worker thread to avoid blocking UI
            if self._location_thread is None or not self._location_thread.isRunning():
                self._location_thread = GetLocationThread(self.telescope)
                self._location_thread.location_ready.connect(
                    lambda location_result: self._update_gps_icon_color(
                        location_result.latitude, location_result.longitude
                    )
                )
                self._location_thread.error_occurred.connect(lambda _: self._set_gps_icon_color("#dc3545"))
                self._location_thread.finished.connect(lambda: setattr(self, "_location_thread", None))
                self._location_thread.start()
                return  # Icon color will be updated via signal
        else:
            # Red: Not connected
            self._set_gps_icon_color("#dc3545")

    def _update_gps_icon_color(self, lat: float, lon: float) -> None:
        """Update GPS icon color based on location validity."""
        # Check if GPS coordinates are valid (not 0,0)
        icon_color = "#28a745" if lat != 0.0 and lon != 0.0 else "#ffc107"  # Green if valid, yellow if searching
        self._set_gps_icon_color(icon_color)

    def _set_gps_icon_color(self, icon_color: str) -> None:
        """Set GPS status indicator color."""
        # Set text with HTML formatting: colored icon
        status_text = f'GPS: <span style="color: {icon_color};">●</span>'
        self.gps_label.setText(status_text)

    def _on_gps_clicked(self) -> None:
        """Handle GPS status label click - opens GPS info dialog."""
        dialog = GPSInfoDialog(self, self.telescope)
        dialog.exec()

    def _on_datetime_clicked(self) -> None:
        """Handle date/time label click - opens time info dialog."""
        dialog = TimeInfoDialog(self, self.telescope)
        dialog.exec()

    def _on_connect(self) -> None:
        """Handle connect button click."""
        # TODO: Open connection dialog
        # For now, just enable/disable buttons
        self.connect_action.setEnabled(False)
        self.disconnect_action.setEnabled(True)
        self.align_action.setEnabled(True)
        self.calibrate_action.setEnabled(True)
        if hasattr(self, "tracking_history_action"):
            self.tracking_history_action.setEnabled(True)

    def _on_disconnect(self) -> None:
        """Handle disconnect button click."""
        if self.telescope:
            # Use worker thread to avoid blocking UI
            if self._disconnect_thread is None or not self._disconnect_thread.isRunning():
                self._disconnect_thread = DisconnectThread(self.telescope)
                self._disconnect_thread.disconnect_complete.connect(self._on_disconnect_complete)
                self._disconnect_thread.error_occurred.connect(
                    lambda _: self._on_disconnect_complete()
                )  # Still complete even on error
                self._disconnect_thread.finished.connect(lambda: setattr(self, "_disconnect_thread", None))
                self._disconnect_thread.start()
            else:
                # Thread already running, just update UI state
                self._on_disconnect_complete()
        else:
            self._on_disconnect_complete()

    def _on_disconnect_complete(self) -> None:
        """Handle disconnect completion."""
        self.telescope = None
        self.connect_action.setEnabled(True)
        self.disconnect_action.setEnabled(False)
        self.align_action.setEnabled(False)
        self.calibrate_action.setEnabled(False)
        if hasattr(self, "tracking_history_action"):
            self.tracking_history_action.setEnabled(False)

    def _on_align(self) -> None:
        """Handle align button click."""
        from celestron_nexstar.gui.dialogs.alignment_assistant_dialog import AlignmentAssistantDialog

        dialog = AlignmentAssistantDialog(self, telescope=self.telescope)
        dialog.exec()

    def _on_calibrate(self) -> None:
        """Handle calibrate button click."""
        from celestron_nexstar.gui.dialogs.calibration_assistant_dialog import CalibrationAssistantDialog

        dialog = CalibrationAssistantDialog(self, telescope=self.telescope)
        dialog.exec()

    def _on_tracking_history(self) -> None:
        """Handle tracking history button click."""
        from celestron_nexstar.gui.dialogs.tracking_history_dialog import TrackingHistoryDialog

        dialog = TrackingHistoryDialog(self, telescope=self.telescope)
        dialog.exec()

    def _on_planning(self) -> None:
        """Handle planning button click - opens planning window."""
        # TODO: Open planning window
        pass

    def _on_catalog(self) -> None:
        """Handle catalog button click - open catalog search window."""
        from celestron_nexstar.gui.windows.catalog_window import CatalogSearchWindow

        # Check if window already exists
        if not hasattr(self, "_catalog_window") or self._catalog_window is None:
            self._catalog_window = CatalogSearchWindow(self)
            self._catalog_window.destroyed.connect(lambda: setattr(self, "_catalog_window", None))

        self._catalog_window.show()
        self._catalog_window.raise_()
        self._catalog_window.activateWindow()

    def _on_goto_queue(self) -> None:
        """Handle goto queue button click - open goto queue window."""
        from celestron_nexstar.gui.windows.goto_queue_window import GotoQueueWindow

        # Check if window already exists
        if not hasattr(self, "_goto_queue_window") or self._goto_queue_window is None:
            self._goto_queue_window = GotoQueueWindow(self, telescope=self.telescope)
            self._goto_queue_window.destroyed.connect(lambda: setattr(self, "_goto_queue_window", None))
        else:
            # Update telescope reference if it changed
            self._goto_queue_window.telescope = self.telescope

        self._goto_queue_window.show()
        self._goto_queue_window.raise_()
        self._goto_queue_window.activateWindow()

    def _on_sky_map(self) -> None:
        """Handle sky map button click - open sky map window."""
        from celestron_nexstar.gui.windows.sky_map_window import SkyMapWindow

        # Check if window already exists
        if not hasattr(self, "_sky_map_window") or self._sky_map_window is None:
            self._sky_map_window = SkyMapWindow(self, telescope=self.telescope)
            self._sky_map_window.destroyed.connect(lambda: setattr(self, "_sky_map_window", None))
        else:
            # Update telescope reference if it changed
            if hasattr(self._sky_map_window, "sky_map"):
                self._sky_map_window.sky_map.telescope = self.telescope

        self._sky_map_window.show()
        self._sky_map_window.raise_()
        self._sky_map_window.activateWindow()

    def _on_zenith_star_chart(self) -> None:
        """Handle zenith star chart button click - open zenith star chart window."""
        from celestron_nexstar.gui.windows.zenith_star_chart_window import ZenithStarChartWindow

        # Check if window already exists
        if not hasattr(self, "_zenith_star_chart_window") or self._zenith_star_chart_window is None:
            self._zenith_star_chart_window = ZenithStarChartWindow(self, telescope=self.telescope)
            self._zenith_star_chart_window.destroyed.connect(lambda: setattr(self, "_zenith_star_chart_window", None))
        else:
            # Update telescope reference if it changed
            if hasattr(self._zenith_star_chart_window, "star_chart"):
                self._zenith_star_chart_window.star_chart.telescope = self.telescope

        self._zenith_star_chart_window.show()
        self._zenith_star_chart_window.raise_()
        self._zenith_star_chart_window.activateWindow()

    def _on_weather(self) -> None:
        """Handle weather button click."""
        dialog = WeatherInfoDialog(self)
        dialog.exec()

    def _on_moon_info(self) -> None:
        """Handle moon info button click."""
        dialog = MoonInfoDialog(self)
        dialog.exec()

    def _on_sky_darkness(self) -> None:
        """Handle sky darkness button click - show sky darkness information."""
        try:
            from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QMessageBox, QTextEdit, QVBoxLayout

            from celestron_nexstar.api.core.enums import SkyBrightness
            from celestron_nexstar.api.core.exceptions import DatabaseError
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.location.light_pollution import get_light_pollution_data
            from celestron_nexstar.api.location.observer import get_observer_location
            from celestron_nexstar.api.observation.optics import calculate_limiting_magnitude, get_current_configuration

            # Show progress dialog
            progress = self._create_progress_dialog("Loading sky darkness information...")
            progress.show()
            QApplication.processEvents()

            # Get location and light pollution data
            db = get_database()
            location = get_observer_location()

            try:
                with db._get_session() as session:
                    light_pollution = get_light_pollution_data(session, location.latitude, location.longitude)

                # Map Bortle class to SkyBrightness
                bortle_to_sky_brightness = {
                    1: SkyBrightness.EXCELLENT,
                    2: SkyBrightness.EXCELLENT,
                    3: SkyBrightness.GOOD,
                    4: SkyBrightness.GOOD,
                    5: SkyBrightness.FAIR,
                    6: SkyBrightness.FAIR,
                    7: SkyBrightness.POOR,
                    8: SkyBrightness.POOR,
                    9: SkyBrightness.URBAN,
                }
                sky_brightness = bortle_to_sky_brightness.get(light_pollution.bortle_class.value, SkyBrightness.FAIR)
            except DatabaseError as e:
                # Light pollution data not available, show error message
                progress.close()
                QMessageBox.warning(
                    self,
                    "Light Pollution Data Not Available",
                    f"Light pollution data is not available for your location.\n\n{e!s}\n\n"
                    "Sky darkness information cannot be displayed without this data.",
                )
                return

            # Get telescope configuration and calculate telescope limiting magnitude
            telescope_limit = None
            telescope_name = "Not configured"
            try:
                config = get_current_configuration()
                if config:
                    telescope_name = config.telescope.display_name
                    exit_pupil = config.eyepiece.exit_pupil_mm(config.telescope)
                    telescope_limit = calculate_limiting_magnitude(
                        config.telescope.aperture_mm, sky_brightness, exit_pupil
                    )
            except Exception:
                # No telescope configured, that's okay
                pass

            progress.close()

            # Create dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Sky Darkness Information")
            dialog.setMinimumWidth(500)
            dialog.setMinimumHeight(400)
            dialog.resize(600, 500)

            layout = QVBoxLayout(dialog)

            # Create text area with formatted information
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setAcceptRichText(True)

            # Make text edit background transparent so it uses dialog's theme background
            text_edit.setStyleSheet("""
                QTextEdit {
                    background-color: transparent;
                    border: none;
                }
            """)

            # Detect theme using palette (same as other dialogs)
            def _is_dark_theme() -> bool:
                from PySide6.QtGui import QGuiApplication, QPalette

                app = QGuiApplication.instance()
                if app and isinstance(app, QGuiApplication):
                    palette = app.palette()
                    window_color = palette.color(QPalette.ColorRole.Window)
                    brightness = window_color.lightness()
                    return bool(brightness < 128)
                return False

            is_dark = _is_dark_theme()
            text_color = "#ffffff" if is_dark else "#000000"
            text_dim_color = "#9e9e9e" if is_dark else "#666666"
            header_color = "#4A90E2"

            # Format the information
            bortle_descriptions = {
                1: "Excellent dark-sky site",
                2: "Typical truly dark site",
                3: "Rural sky",
                4: "Rural/suburban transition",
                5: "Suburban sky",
                6: "Bright suburban sky",
                7: "Suburban/urban transition. Sky grayish white.",
                8: "City sky",
                9: "Inner-city sky",
            }
            bortle_desc = bortle_descriptions.get(light_pollution.bortle_class.value, "Unknown")

            html_content = f"""
            <h2 style="color: {header_color}; margin-bottom: 10px;">Sky Darkness</h2>

            <table style="width: 100%; border-collapse: collapse; margin: 10px 0;">
                <tr>
                    <td style="padding: 8px; font-weight: bold; width: 200px;">Bortle Class:</td>
                    <td style="padding: 8px;">{light_pollution.bortle_class.value} ({bortle_desc})</td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold;">SQM:</td>
                    <td style="padding: 8px;">{light_pollution.sqm_value:.2f} mag/arcsec²</td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Naked Eye Limit:</td>
                    <td style="padding: 8px;">{light_pollution.naked_eye_limiting_magnitude:.2f} mag</td>
                </tr>
            """

            if telescope_limit:
                html_content += f"""
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Telescope Limit:</td>
                    <td style="padding: 8px;">{telescope_limit:.2f} mag ({telescope_name})</td>
                </tr>
                """
            else:
                html_content += f"""
                <tr>
                    <td style="padding: 8px; font-weight: bold;">Telescope Limit:</td>
                    <td style="padding: 8px; color: {text_dim_color};">Not available (telescope not configured)</td>
                </tr>
                """

            html_content += """
            </table>
            """

            # Add explanations section
            sqm_condition = (
                "excellent dark sky conditions"
                if light_pollution.sqm_value >= 21.5
                else "good dark sky conditions"
                if light_pollution.sqm_value >= 20.5
                else "moderate light pollution"
                if light_pollution.sqm_value >= 19.0
                else "significant light pollution"
            )
            naked_eye_condition = (
                "you can see quite faint stars - excellent conditions!"
                if light_pollution.naked_eye_limiting_magnitude >= 6.0
                else "you can see moderately faint stars"
                if light_pollution.naked_eye_limiting_magnitude >= 5.0
                else "you can see bright stars, but light pollution limits fainter objects"
            )

            html_content += f"""
            <h3 style="color: {header_color}; margin-top: 20px; margin-bottom: 10px;">Understanding These Values</h3>
            <ul style="margin: 10px 0; padding-left: 20px; line-height: 1.6;">
                <li style="margin-bottom: 8px;">
                    <b>Bortle Class:</b> A scale from 1 (excellent dark sky) to 9 (inner-city sky).
                    Lower numbers mean darker skies and better observing conditions. Class 1-2 sites are
                    excellent for deep-sky observing, while Class 7-9 are best for bright objects only.
                </li>
                <li style="margin-bottom: 8px;">
                    <b>SQM (Sky Quality Meter):</b> Measures sky brightness in magnitudes per square arcsecond.
                    Higher values mean darker skies. Typical ranges: 17-18 (city), 19-20 (suburban),
                    21-22 (rural/dark site). Your value of {light_pollution.sqm_value:.2f} indicates
                    {sqm_condition}.
                </li>
                <li style="margin-bottom: 8px;">
                    <b>Limiting Magnitude:</b> The faintest star you can see with the naked eye.
                    Under dark skies (Bortle 1-2), you might see magnitude 6-7. In cities (Bortle 8-9),
                    you might only see magnitude 3-4. Your limit of {light_pollution.naked_eye_limiting_magnitude:.2f} means
                    {naked_eye_condition}.
                </li>
            """

            if telescope_limit:
                html_content += f"""
                <li style="margin-bottom: 8px;">
                    <b>Telescope Limiting Magnitude:</b> The faintest object your telescope can show under
                    these sky conditions. With your {telescope_name}, you can see objects down to magnitude
                    {telescope_limit:.2f}. Remember: this is theoretical - actual visibility depends on
                    object type, contrast, and your experience level.
                </li>
                """

            html_content += """
            </ul>
            """

            # Add additional information
            html_content += f"""
            <h3 style="color: {header_color}; margin-top: 20px; margin-bottom: 10px;">Sky Characteristics</h3>
            <ul style="margin: 10px 0; padding-left: 20px;">
                <li>Milky Way: {"Visible" if light_pollution.milky_way_visible else "Not visible"}</li>
                <li>Airglow: {"Visible" if light_pollution.airglow_visible else "Not visible"}</li>
                <li>Zodiacal Light: {"Visible" if light_pollution.zodiacal_light_visible else "Not visible"}</li>
            </ul>
            """

            if light_pollution.description:
                html_content += f"""
                <h3 style="color: {header_color}; margin-top: 20px; margin-bottom: 10px;">Description</h3>
                <p style="margin: 10px 0;">{light_pollution.description}</p>
                """

            if light_pollution.recommendations:
                html_content += f"""
                <h3 style="color: {header_color}; margin-top: 20px; margin-bottom: 10px;">Recommendations</h3>
                <ul style="margin: 10px 0; padding-left: 20px;">
                """
                for rec in light_pollution.recommendations:
                    html_content += f"<li>{rec}</li>"
                html_content += "</ul>"

            # Set body background to transparent so it uses dialog's theme background
            full_html = f"""
            <html>
            <body style="background-color: transparent; color: {text_color}; font-family: Arial, sans-serif; padding: 15px;">
            {html_content}
            </body>
            </html>
            """

            text_edit.setHtml(full_html)
            layout.addWidget(text_edit)

            # Add OK button
            button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
            button_box.accepted.connect(dialog.accept)
            layout.addWidget(button_box)

            dialog.exec()

        except Exception as e:
            logger.error(f"Error loading sky darkness information: {e}", exc_info=True)
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.critical(self, "Error", f"Failed to load sky darkness information: {e}")

    def _on_favorites(self) -> None:
        """Handle favorites button click."""
        from celestron_nexstar.gui.dialogs.favorites_dialog import FavoritesDialog

        dialog = FavoritesDialog(self)
        dialog.exec()

    def _on_observation_log(self) -> None:
        """Handle observation log button click."""
        from celestron_nexstar.gui.dialogs.observation_log_dialog import ObservationLogDialog

        dialog = ObservationLogDialog(self)
        dialog.exec()

    def _on_live_dashboard(self) -> None:
        """Handle live dashboard button click."""
        from celestron_nexstar.gui.dialogs.live_dashboard_dialog import LiveDashboardDialog

        dialog = LiveDashboardDialog(self)
        dialog.exec()

    def _on_astronomical_calendar(self) -> None:
        """Handle astronomical calendar button click."""
        from celestron_nexstar.gui.dialogs.astronomical_calendar_dialog import (
            AstronomicalCalendarDialog,
        )

        dialog = AstronomicalCalendarDialog(self)
        dialog.exec()

    def _on_equipment_manager(self) -> None:
        """Handle equipment manager button click."""
        from celestron_nexstar.gui.dialogs.equipment_manager_dialog import EquipmentManagerDialog

        dialog = EquipmentManagerDialog(self)
        dialog.exec()

    def _on_checklist(self) -> None:
        """Handle checklist button click."""
        # TODO: Open checklist window
        pass

    def _on_time_slots(self) -> None:
        """Handle time slots button click."""
        # Show progress dialog while loading
        progress = self._create_progress_dialog("Loading time slots and recommendations...")
        progress.show()

        # Process events to show the dialog immediately
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        # Show time slots dialog (it will load data in its constructor)
        from celestron_nexstar.gui.dialogs.time_slots_dialog import TimeSlotsInfoDialog

        dialog = TimeSlotsInfoDialog(self)
        progress.close()
        dialog.exec()

    def _on_quick_reference(self) -> None:
        """Handle quick reference button click."""
        # TODO: Open quick reference window
        pass

    def _on_transit_times(self) -> None:
        """Handle transit times button click."""
        # Show progress dialog while loading
        progress = self._create_progress_dialog("Loading transit times...")
        progress.show()

        # Process events to show the dialog immediately
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()

        # Show transit times dialog (it will load data in its constructor)
        from celestron_nexstar.gui.dialogs.transit_times_dialog import TransitTimesInfoDialog

        dialog = TransitTimesInfoDialog(self)
        progress.close()
        dialog.exec()

    def _on_glossary(self) -> None:
        """Handle glossary button click."""
        from celestron_nexstar.gui.dialogs.glossary_dialog import GlossaryDialog

        dialog = GlossaryDialog(self)
        dialog.exec()

    def _on_compare_objects(self) -> None:
        """Handle compare objects button click."""
        from celestron_nexstar.gui.dialogs.object_comparison_dialog import ObjectComparisonDialog

        dialog = ObjectComparisonDialog(self)
        dialog.exec()

    def _on_context_menu_compare_objects(self, table: QTableWidget, row: int) -> None:
        """Handle context menu compare objects action."""
        # Get all selected rows, or fall back to the clicked row if none selected
        selected_indices = table.selectionModel().selectedRows()
        rows_to_process = [idx.row() for idx in selected_indices] if selected_indices else [row]

        obj_type = table.property("object_type")
        object_names = []

        # Extract object names from all selected rows
        for row_num in rows_to_process:
            name_item = table.item(row_num, 0) if obj_type in ("constellation", "asterism") else table.item(row_num, 1)

            if not name_item:
                continue

            object_name = name_item.data(Qt.ItemDataRole.UserRole)
            if not object_name:
                display_text = name_item.text()
                object_name = display_text.removeprefix("★ ").strip()

            if object_name and object_name not in object_names:
                object_names.append(object_name)

        if not object_names:
            return

        # Open comparison dialog with all selected objects
        from celestron_nexstar.gui.dialogs.object_comparison_dialog import ObjectComparisonDialog

        dialog = ObjectComparisonDialog(self, initial_objects=object_names)
        dialog.exec()

    def _on_settings(self) -> None:
        """Handle settings button click."""
        from celestron_nexstar.gui.dialogs.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self)
        dialog.exec()

    def _on_celestial_object(self, object_name: str) -> None:
        """Handle celestial object button click."""
        if object_name == "aurora":
            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading aurora visibility information...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show aurora dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.aurora_info_dialog import AuroraInfoDialog

            self._aurora_dialog = AuroraInfoDialog(self)
            self._aurora_dialog.finished.connect(lambda: setattr(self, "_aurora_dialog", None))
            progress.close()
            self._aurora_dialog.show()
        elif object_name == "iss":
            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading ISS pass predictions...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show ISS dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.iss_info_dialog import ISSInfoDialog

            self._iss_dialog = ISSInfoDialog(self)
            self._iss_dialog.finished.connect(lambda: setattr(self, "_iss_dialog", None))
            progress.close()
            self._iss_dialog.show()
        elif object_name == "binoculars":
            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading binocular viewing information...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show binoculars dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.binoculars_info_dialog import BinocularsInfoDialog

            self._binoculars_dialog = BinocularsInfoDialog(self)
            self._binoculars_dialog.finished.connect(lambda: setattr(self, "_binoculars_dialog", None))
            progress.close()
            self._binoculars_dialog.show()
        elif object_name == "naked_eye":
            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading naked-eye viewing information...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show naked-eye dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.naked_eye_info_dialog import NakedEyeInfoDialog

            self._naked_eye_dialog = NakedEyeInfoDialog(self)
            self._naked_eye_dialog.finished.connect(lambda: setattr(self, "_naked_eye_dialog", None))
            progress.close()
            self._naked_eye_dialog.show()
        elif object_name == "comets":
            # Check if dialog already open
            if self._comets_dialog is not None:
                self._comets_dialog.raise_()
                self._comets_dialog.activateWindow()
                return

            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading comet visibility information...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show comets dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.comets_info_dialog import CometsInfoDialog

            self._comets_dialog = CometsInfoDialog(self)
            self._comets_dialog.finished.connect(lambda: setattr(self, "_comets_dialog", None))
            progress.close()
            self._comets_dialog.show()
        elif object_name == "asteroids":
            # Check if dialog already open
            if self._asteroids_dialog is not None:
                self._asteroids_dialog.raise_()
                self._asteroids_dialog.activateWindow()
                return

            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading asteroid visibility information...")
            progress.show()

            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            from celestron_nexstar.gui.dialogs.asteroids_info_dialog import AsteroidsInfoDialog

            self._asteroids_dialog = AsteroidsInfoDialog(self)
            self._asteroids_dialog.finished.connect(lambda: setattr(self, "_asteroids_dialog", None))
            progress.close()
            self._asteroids_dialog.show()
        elif object_name == "eclipse":
            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading eclipse information...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show eclipse dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.eclipse_info_dialog import EclipseInfoDialog

            self._eclipse_dialog = EclipseInfoDialog(self, progress=progress)
            self._eclipse_dialog.finished.connect(lambda: setattr(self, "_eclipse_dialog", None))
            progress.close()
            self._eclipse_dialog.show()
        elif object_name == "planets":
            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading planetary events information...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show planets dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.planets_info_dialog import PlanetsInfoDialog

            self._planets_dialog = PlanetsInfoDialog(self, progress=progress)
            self._planets_dialog.finished.connect(lambda: setattr(self, "_planets_dialog", None))
            progress.close()
            self._planets_dialog.show()
        elif object_name == "space_weather":
            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading space weather information...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show space weather dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.space_weather_info_dialog import SpaceWeatherInfoDialog

            self._space_weather_dialog = SpaceWeatherInfoDialog(self)
            self._space_weather_dialog.finished.connect(lambda: setattr(self, "_space_weather_dialog", None))
            progress.close()
            self._space_weather_dialog.show()
        elif object_name == "satellites":
            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading satellite passes information...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show satellites dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.satellites_info_dialog import SatellitesInfoDialog

            self._satellites_dialog = SatellitesInfoDialog(self, progress=progress)
            self._satellites_dialog.finished.connect(lambda: setattr(self, "_satellites_dialog", None))
            progress.close()
            self._satellites_dialog.show()
        elif object_name == "meteors":
            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading meteor shower predictions...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            # Show meteors dialog (it will load data in its constructor)
            from celestron_nexstar.gui.dialogs.meteors_info_dialog import MeteorsInfoDialog

            self._meteors_dialog = MeteorsInfoDialog(self, progress=progress)
            self._meteors_dialog.finished.connect(lambda: setattr(self, "_meteors_dialog", None))
            progress.close()
            self._meteors_dialog.show()
        elif object_name == "milky_way":
            # Show progress dialog while loading
            progress = self._create_progress_dialog("Loading Milky Way visibility information...")
            progress.show()

            # Process events to show the dialog immediately
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()

            from celestron_nexstar.gui.dialogs.milky_way_info_dialog import MilkyWayInfoDialog

            self._milky_way_dialog = MilkyWayInfoDialog(self, progress=progress)
            self._milky_way_dialog.finished.connect(lambda: setattr(self, "_milky_way_dialog", None))
            progress.close()
            self._milky_way_dialog.show()
        elif object_name == "variables":
            # Switch to Variable Star tab
            # Find the tab index for Variable Star
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == "Variable Star":
                    self.tab_widget.setCurrentIndex(i)
                    break
        elif object_name == "zodiacal":
            # Switch to Zodiacal tab
            # Find the tab index for Zodiacal
            for i in range(self.tab_widget.count()):
                if self.tab_widget.tabText(i) == "Zodiacal":
                    self.tab_widget.setCurrentIndex(i)
                    break
        else:
            # TODO: Open celestial object window for other objects
            pass

    def _on_toggle_log(self, checked: bool) -> None:
        """Handle communication log toggle button click."""
        if checked:
            # Show log panel
            self.log_panel.log_text.show()
            self.log_panel.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            self.log_panel.setMinimumHeight(150)  # Minimum height when expanded
        else:
            # Hide log panel
            self.log_panel.log_text.hide()
            self.log_panel.setMaximumHeight(30)  # Collapsed height
            self.log_panel.setMinimumHeight(30)

    def _on_toggle_debug_log(self, checked: bool) -> None:
        """Handle debug log toggle button click."""
        if checked:
            # Show debug panel
            self.debug_panel.controls_widget.show()
            self.debug_panel.log_text.show()
            self.debug_panel.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
            self.debug_panel.setMinimumHeight(200)  # Minimum height when expanded
        else:
            # Hide debug panel
            self.debug_panel.controls_widget.hide()
            self.debug_panel.log_text.hide()
            self.debug_panel.setMaximumHeight(0)  # Collapsed height
            self.debug_panel.setMinimumHeight(0)
