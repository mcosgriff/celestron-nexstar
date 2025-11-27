"""
Dialog to display detailed information about a constellation, including its stars.
"""

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


def _run_async_safe(coro: Coroutine[Any, Any, Any]) -> Any:
    """
    Run an async coroutine from a sync context, handling both cases:
    - If called from sync context: uses asyncio.run()
    - If called from async context: creates new event loop in thread

    Args:
        coro: The coroutine to run

    Returns:
        The result of the coroutine
    """
    try:
        # Check if we're in an async context
        asyncio.get_running_loop()
        # We're in an async context, need to use a thread with new event loop
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()

        def run_in_thread() -> None:
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                result = new_loop.run_until_complete(coro)
                future.set_result(result)
                new_loop.close()
            except Exception as e:
                future.set_exception(e)

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        return future.result()
    except RuntimeError:
        # No running loop, use asyncio.run()
        return asyncio.run(coro)


class ConstellationInfoDialog(QDialog):
    """Dialog to display detailed information about a constellation and its stars."""

    def __init__(self, parent: QWidget | None, constellation_name: str) -> None:
        """Initialize the constellation info dialog."""
        super().__init__(parent)
        self.setWindowTitle(f"Constellation Information: {constellation_name}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.resize(600, 700)  # Match ObjectInfoDialog width

        self.constellation_name = constellation_name
        self.svg_path: Path | None = None  # Store SVG path for double-click viewing

        # Create layout
        layout = QVBoxLayout(self)

        # Create scrollable text area with rich HTML formatting
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setAcceptRichText(True)
        # Handle double-clicks to enlarge SVG
        # Store handler reference (will be called via event filter)
        self._double_click_handler = self._on_text_double_click
        layout.addWidget(self.info_text)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load constellation information
        self._load_constellation_info()

    def _is_dark_theme(self) -> bool:
        """Detect if the current theme is dark mode."""
        from PySide6.QtGui import QGuiApplication, QPalette

        app = QGuiApplication.instance()
        if app and isinstance(app, QGuiApplication):
            palette = app.palette()
            window_color = palette.color(QPalette.ColorRole.Window)
            brightness = window_color.lightness()
            return bool(brightness < 128)
        return False

    def _get_theme_colors(self) -> dict[str, str]:
        """Get theme-aware colors."""
        is_dark = self._is_dark_theme()
        return {
            "text": "#ffffff" if is_dark else "#000000",
            "text_dim": "#9e9e9e" if is_dark else "#666666",
            "header": "#ffc107" if is_dark else "#f57c00",
            "cyan": "#00bcd4" if is_dark else "#00838f",
            "green": "#4caf50" if is_dark else "#2e7d32",
            "red": "#f44336" if is_dark else "#c62828",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _load_constellation_info(self) -> None:
        """Load constellation information and its stars."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.astronomy.constellations import get_prominent_constellations
            from celestron_nexstar.api.core.enums import CelestialObjectType
            from celestron_nexstar.api.core.utils import format_dec, format_ra
            from celestron_nexstar.api.database.database import get_database
            from celestron_nexstar.api.observation.observation_planner import ObservationPlanner

            # Get conditions and recommended stars outside async context
            # (both use asyncio.run internally)
            planner = ObservationPlanner()
            conditions = planner.get_tonight_conditions()
            all_recommended_stars = planner.get_recommended_objects(
                conditions, CelestialObjectType.STAR, max_results=1000, best_for_seeing=False
            )

            # Create a map of star names to recommended objects
            star_map = {}
            for rec in all_recommended_stars:
                star_map[rec.obj.name] = rec
                if rec.obj.common_name:
                    star_map[rec.obj.common_name] = rec

            async def _load_data() -> tuple[dict[str, Any], list[Any]]:
                db = get_database()
                async with db._AsyncSession() as session:
                    # Get constellation info
                    constellations = await get_prominent_constellations(session)
                    constellation = None
                    for const in constellations:
                        if const.name == self.constellation_name:
                            constellation = const
                            break

                    if not constellation:
                        return {}, []

                    # Get stars in this constellation
                    stars = await db.filter_objects(
                        object_type="star", constellation=self.constellation_name, limit=100
                    )

                    # Match stars to their recommended objects (from outside async context)
                    star_data = []
                    for star in stars:
                        rec = star_map.get(star.name) or star_map.get(star.common_name or "")
                        if rec:
                            star_data.append(rec)

                    # Sort by visibility probability (chance) descending, then by priority
                    star_data.sort(key=lambda x: (x.visibility_probability, x.priority), reverse=True)

                    return {
                        "name": constellation.name,
                        "abbreviation": constellation.abbreviation,
                        "ra_hours": constellation.ra_hours,
                        "dec_degrees": constellation.dec_degrees,
                        "area_sq_deg": constellation.area_sq_deg,
                        "brightest_star": constellation.brightest_star,
                        "magnitude": constellation.magnitude,
                        "season": constellation.season,
                        "hemisphere": constellation.hemisphere,
                        "description": constellation.description,
                    }, star_data

            constellation_data, star_data = _run_async_safe(_load_data())

            if not constellation_data:
                self.info_text.setHtml(
                    f"<p style='color: {colors['error']};'><b>Error:</b> Constellation '{self.constellation_name}' not found</p>"
                )
                return

            # Build HTML content
            html_parts = []

            # Constellation name (bold cyan)
            name_html = f"<p style='font-size: 18px; font-weight: bold; color: {colors['cyan']}; margin-bottom: 10px;'>{constellation_data['name']}"
            if constellation_data.get("abbreviation"):
                name_html += f" <span style='color: {colors['cyan']}; font-weight: normal;'>({constellation_data['abbreviation']})</span>"
            name_html += "</p>"
            html_parts.append(name_html)

            # Try to load and display constellation SVG
            try:
                import re
                import urllib.parse

                from celestron_nexstar.api.astronomy.constellation_images import get_constellation_svg

                svg_path = _run_async_safe(get_constellation_svg(constellation_data["name"]))
                if svg_path and svg_path.exists():
                    # Store SVG path for double-click viewing
                    self.svg_path = svg_path

                    # Read SVG content and embed it in HTML
                    svg_content = svg_path.read_text(encoding="utf-8")

                    # Add a white background to the SVG if it doesn't have one
                    # This ensures the SVG is visible on dark themes
                    # Check if SVG already has a background rectangle
                    if not re.search(
                        r'<rect[^>]*fill\s*=\s*["\'](?:white|#fff|#ffffff|#f5f5f5|#e0e0e0)', svg_content, re.IGNORECASE
                    ):
                        # Find the opening <svg> tag and add a background rectangle after it
                        svg_match = re.search(r"(<svg[^>]*>)", svg_content, re.IGNORECASE)
                        if svg_match:
                            # Extract viewBox or width/height to determine SVG dimensions
                            viewbox_match = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', svg_content, re.IGNORECASE)
                            width_match = re.search(r'width\s*=\s*["\']([^"\']+)["\']', svg_content, re.IGNORECASE)
                            height_match = re.search(r'height\s*=\s*["\']([^"\']+)["\']', svg_content, re.IGNORECASE)

                            # Default dimensions if not found
                            x, y, width, height = 0, 0, 1000, 1000

                            if viewbox_match:
                                # Parse viewBox="x y width height"
                                viewbox_parts = viewbox_match.group(1).split()
                                if len(viewbox_parts) >= 4:
                                    x, y, width, height = [float(v) for v in viewbox_parts[:4]]  # type: ignore[assignment]
                            elif width_match and height_match:
                                # Use width and height attributes
                                width = float(re.sub(r"[^\d.]", "", width_match.group(1)))  # type: ignore[assignment]
                                height = float(re.sub(r"[^\d.]", "", height_match.group(1)))  # type: ignore[assignment]

                            # Add white background rectangle
                            bg_rect = f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="#ffffff" stroke="none"/>'
                            svg_content = svg_content.replace(svg_match.group(1), svg_match.group(1) + bg_rect, 1)

                    # URL encode the SVG content for data URI
                    svg_encoded = urllib.parse.quote(svg_content)
                    # Limit SVG size for display (max width 400px)
                    # Use transparent background so it matches the QTextEdit background exactly
                    # The SVG itself has a white background, so it will be visible
                    html_parts.append(
                        f"<div style='margin: 15px 0; text-align: center; padding: 5px; background-color: transparent; display: inline-block;'>"
                        f"<img src='data:image/svg+xml;charset=utf-8,{svg_encoded}' "
                        f"style='max-width: 400px; max-height: 400px; width: auto; height: auto; display: block;' "
                        f"alt='{constellation_data['name']} constellation diagram' />"
                        f"<p style='margin-top: 5px; font-size: 0.9em; color: {colors['text_dim']};'>Double-click image to enlarge</p>"
                        f"</div>"
                    )
            except Exception as e:
                logger.debug(f"Could not load constellation SVG: {e}")
                # Silently fail - SVG is optional

            # Coordinates section
            html_parts.append(
                f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Coordinates:</p>"
            )
            ra_str = format_ra(constellation_data["ra_hours"])
            dec_str = format_dec(constellation_data["dec_degrees"])
            html_parts.append(
                f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                f"<span style='color: {colors['green']};'>RA:</span> {ra_str}<br>"
                f"<span style='color: {colors['green']};'>Dec:</span> {dec_str}"
                f"</p>"
            )

            # Properties section
            html_parts.append(
                f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Properties:</p>"
            )
            if constellation_data.get("area_sq_deg"):
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Area: {constellation_data['area_sq_deg']:.1f} square degrees</p>"
                )
            if constellation_data.get("brightest_star"):
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Brightest Star: {constellation_data['brightest_star']}</p>"
                )
            if constellation_data.get("magnitude"):
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Brightest Star Magnitude: {constellation_data['magnitude']:.2f}</p>"
                )
            if constellation_data.get("season"):
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Best Season: {constellation_data['season']}</p>"
                )
            if constellation_data.get("hemisphere"):
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Hemisphere: {constellation_data['hemisphere']}</p>"
                )

            # Description
            if constellation_data.get("description"):
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Description:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>{constellation_data['description']}</p>"
                )

            # Stars section
            html_parts.append(
                f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Stars in {constellation_data['name']} ({len(star_data)} visible):</p>"
            )

            if star_data:
                # Create table
                html_parts.append(
                    "<table style='border-collapse: collapse; width: 100%; margin-left: 20px; margin-top: 10px;'>"
                )
                html_parts.append(
                    "<tr style='background-color: rgba(255, 193, 7, 0.2);'>"
                    "<th style='padding: 8px; text-align: left; border-bottom: 2px solid #ffc107;'>Name</th>"
                    "<th style='padding: 8px; text-align: right; border-bottom: 2px solid #ffc107;'>Mag</th>"
                    "<th style='padding: 8px; text-align: right; border-bottom: 2px solid #ffc107;'>Alt</th>"
                    "<th style='padding: 8px; text-align: right; border-bottom: 2px solid #ffc107;'>Chance</th>"
                    "</tr>"
                )

                for rec in star_data[:50]:  # Limit to top 50 stars
                    obj = rec.obj
                    display_name = obj.common_name or obj.name
                    mag_text = f"{rec.apparent_magnitude:.2f}" if rec.apparent_magnitude else "-"
                    alt_text = f"{rec.altitude:.0f}°"
                    prob_text = f"{rec.visibility_probability:.0%}"

                    # Color code by visibility probability
                    if rec.visibility_probability >= 0.8:
                        prob_color = colors["green"]
                    elif rec.visibility_probability >= 0.5:
                        prob_color = colors["yellow"]
                    else:
                        prob_color = colors["text_dim"]

                    html_parts.append(
                        f"<tr>"
                        f"<td style='padding: 5px; border-bottom: 1px solid rgba(255, 255, 255, 0.1);'>{display_name}</td>"
                        f"<td style='padding: 5px; text-align: right; border-bottom: 1px solid rgba(255, 255, 255, 0.1);'>{mag_text}</td>"
                        f"<td style='padding: 5px; text-align: right; border-bottom: 1px solid rgba(255, 255, 255, 0.1);'>{alt_text}</td>"
                        f"<td style='padding: 5px; text-align: right; border-bottom: 1px solid rgba(255, 255, 255, 0.1);'>"
                        f"<span style='color: {prob_color};'>{prob_text}</span></td>"
                        f"</tr>"
                    )

                html_parts.append("</table>")
            else:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px; color: {colors['text_dim']};'>No visible stars found in this constellation.</p>"
                )

            # Set HTML content
            self.info_text.setHtml("".join(html_parts))

        except Exception as e:
            logger.error(f"Error loading constellation info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p style='color: {colors['error']};'><b>Error:</b> Failed to load constellation information: {e}</p>"
            )

    def _on_text_double_click(self, event: Any) -> None:
        """Handle double-click events - open SVG if available."""
        # Check if we have an SVG
        if self.svg_path is not None and self.svg_path.exists():
            try:
                # Get cursor position at click location
                if hasattr(event, "position"):
                    pos = event.position().toPoint()
                elif hasattr(event, "pos"):
                    pos = event.pos()
                else:
                    pos = event.globalPos()

                cursor = self.info_text.cursorForPosition(pos)
                # If cursor is in the first part of the document (where SVG is), show enlarged view
                if cursor.position() < 5000:  # Rough check - SVG is near the top
                    self._show_enlarged_svg()
                    return
            except Exception:
                # If we can't determine position, just show the enlarged view on any double-click
                # when SVG is available (user can double-click anywhere near the image)
                self._show_enlarged_svg()
                return

        # Call original double-click handler for normal text selection
        from PySide6.QtWidgets import QTextEdit

        QTextEdit.mouseDoubleClickEvent(self.info_text, event)

    def _show_enlarged_svg(self) -> None:
        """Show the constellation SVG in a larger dialog."""
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QScrollArea, QSizePolicy, QVBoxLayout

        # Try to import QSvgWidget (it's in QtSvgWidgets in PySide6)
        use_svg_widget = False
        q_svg_widget_class = None
        try:
            from PySide6.QtSvgWidgets import QSvgWidget

            q_svg_widget_class = QSvgWidget
            use_svg_widget = True
        except ImportError:
            pass

        # Get SVG dimensions to size the dialog appropriately
        svg_width = 1000
        svg_height = 1000
        aspect_ratio = 1.0

        if use_svg_widget and q_svg_widget_class is not None:
            try:
                temp_widget = q_svg_widget_class(str(self.svg_path))
                svg_renderer = temp_widget.renderer()
                if svg_renderer and svg_renderer.isValid():
                    svg_size = svg_renderer.defaultSize()
                    if svg_size.isValid() and svg_size.width() > 0 and svg_size.height() > 0:
                        svg_width = svg_size.width()
                        svg_height = svg_size.height()
                        aspect_ratio = svg_height / svg_width
            except Exception:
                pass

        # Calculate dialog size: SVG size + minimal padding for margins and button
        # Add ~80px for margins (10px * 2 on each side) + ~60px for button area
        padding_width = 80
        padding_height = 100  # Extra for button
        dialog_width = min(svg_width + padding_width, 1400)  # Cap at reasonable max
        dialog_height = min(svg_height + padding_height, 1000)  # Cap at reasonable max

        # Create dialog for enlarged view
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{self.constellation_name} - Constellation Diagram")
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(400)
        dialog.resize(int(dialog_width), int(dialog_height))

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(5, 5, 5, 5)  # Minimal margins
        layout.setSpacing(5)  # Minimal spacing

        # Create scroll area for the SVG
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Try to use QSvgWidget for better SVG rendering
        svg_widget_success = False
        if use_svg_widget and q_svg_widget_class is not None:
            try:
                # Use a custom widget that maintains aspect ratio
                from PySide6.QtCore import QSize

                # Create a type alias to work around mypy's limitation with conditional imports
                _SvgWidgetBase = q_svg_widget_class  # type: ignore[assignment,misc]  # noqa: N806

                class AspectRatioSvgWidget(_SvgWidgetBase):  # type: ignore[valid-type]
                    """QSvgWidget that maintains aspect ratio when resizing."""

                    def __init__(self, path: str, aspect_ratio: float) -> None:
                        super().__init__(path)
                        self.aspect_ratio = aspect_ratio

                    def sizeHint(self) -> QSize:  # noqa: N802
                        """Return a size hint that maintains aspect ratio."""
                        width = 1000  # Preferred width
                        height = int(width * self.aspect_ratio)
                        return QSize(width, height)

                    def resizeEvent(self, event: Any) -> None:  # noqa: N802
                        """Maintain aspect ratio when resizing."""
                        size = event.size()
                        width = size.width()
                        height = int(width * self.aspect_ratio)

                        # If calculated height exceeds available height, use height instead
                        if height > size.height():
                            height = size.height()
                            width = int(height / self.aspect_ratio)

                        self.resize(width, height)
                        super().resizeEvent(event)

                aspect_svg_widget = AspectRatioSvgWidget(str(self.svg_path), aspect_ratio)
                aspect_svg_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

                # Create a container widget with white background
                container = QLabel()
                container.setStyleSheet("background-color: #ffffff;")
                container_layout = QVBoxLayout(container)
                container_layout.setContentsMargins(10, 10, 10, 10)  # Reduced margins
                container_layout.setSpacing(0)
                container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                container_layout.addWidget(aspect_svg_widget)

                scroll_area.setWidget(container)
                layout.addWidget(scroll_area)
                svg_widget_success = True

            except Exception as e:
                # Fallback to QTextEdit if QSvgWidget fails
                logger.warning(f"Could not use QSvgWidget, falling back to QTextEdit: {e}")

        # Fallback to QTextEdit if QSvgWidget is not available or failed
        if not svg_widget_success:
            from PySide6.QtWidgets import QTextEdit

            svg_display = QTextEdit()
            svg_display.setReadOnly(True)
            svg_display.setAcceptRichText(True)
            svg_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            try:
                if self.svg_path is None:
                    return
                svg_content = self.svg_path.read_text(encoding="utf-8")
                import re
                import urllib.parse

                # Add white background to SVG if needed
                if not re.search(
                    r'<rect[^>]*fill\s*=\s*["\'](?:white|#fff|#ffffff|#f5f5f5|#e0e0e0)', svg_content, re.IGNORECASE
                ):
                    svg_match = re.search(r"(<svg[^>]*>)", svg_content, re.IGNORECASE)
                    if svg_match:
                        viewbox_match = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', svg_content, re.IGNORECASE)
                        width_match = re.search(r'width\s*=\s*["\']([^"\']+)["\']', svg_content, re.IGNORECASE)
                        height_match = re.search(r'height\s*=\s*["\']([^"\']+)["\']', svg_content, re.IGNORECASE)

                        x, y, width, height = 0, 0, 1000, 1000

                        if viewbox_match:
                            viewbox_parts = viewbox_match.group(1).split()
                            if len(viewbox_parts) >= 4:
                                x, y, width, height = [float(v) for v in viewbox_parts[:4]]  # type: ignore[assignment]
                        elif width_match and height_match:
                            width = float(re.sub(r"[^\d.]", "", width_match.group(1)))  # type: ignore[assignment]
                            height = float(re.sub(r"[^\d.]", "", height_match.group(1)))  # type: ignore[assignment]

                        bg_rect = (
                            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="#ffffff" stroke="none"/>'
                        )
                        svg_content = svg_content.replace(svg_match.group(1), svg_match.group(1) + bg_rect, 1)

                svg_encoded = urllib.parse.quote(svg_content)

                # Use viewport-based sizing
                html = f"""
                <html>
                <head>
                    <style>
                        body {{
                            margin: 0;
                            padding: 20px;
                            background-color: #ffffff;
                            text-align: center;
                        }}
                        img {{
                            width: 95vw;
                            height: auto;
                            max-width: 95vw;
                            max-height: 90vh;
                        }}
                    </style>
                </head>
                <body>
                    <img src='data:image/svg+xml;charset=utf-8,{svg_encoded}'
                         alt='{self.constellation_name} constellation diagram' />
                </body>
                </html>
                """
                svg_display.setHtml(html)
            except Exception as e2:
                logger.error(f"Error loading enlarged SVG: {e2}")
                svg_display.setHtml(f"<p>Error loading image: {e2}</p>")

            layout.addWidget(svg_display)

        # Add close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Show dialog
        dialog.exec()
