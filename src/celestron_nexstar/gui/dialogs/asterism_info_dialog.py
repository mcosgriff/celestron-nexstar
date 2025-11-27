"""
Dialog to display detailed information about an asterism.
"""

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Coroutine
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


class AsterismInfoDialog(QDialog):
    """Dialog to display detailed information about an asterism."""

    def __init__(self, parent: QWidget | None, asterism_name: str) -> None:
        """Initialize the asterism info dialog."""
        super().__init__(parent)
        self.setWindowTitle(f"Asterism Information: {asterism_name}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.resize(600, 700)  # Match ObjectInfoDialog width

        self.asterism_name = asterism_name

        # Create layout
        layout = QVBoxLayout(self)

        # Create scrollable text area with rich HTML formatting
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setAcceptRichText(True)
        layout.addWidget(self.info_text)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load asterism information
        self._load_asterism_info()

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

    def _load_asterism_info(self) -> None:
        """Load asterism information."""
        colors = self._get_theme_colors()
        try:
            from celestron_nexstar.api.astronomy.constellations import get_famous_asterisms
            from celestron_nexstar.api.core.utils import format_dec, format_ra

            async def _load_data() -> Any | None:
                from celestron_nexstar.api.database.models import get_db_session

                async with get_db_session() as session:
                    asterisms = await get_famous_asterisms(session)
                    for asterism in asterisms:
                        if asterism.name == self.asterism_name:
                            return asterism
                    return None

            asterism = _run_async_safe(_load_data())

            if not asterism:
                self.info_text.setHtml(
                    f"<p style='color: {colors['error']};'><b>Error:</b> Asterism '{self.asterism_name}' not found</p>"
                )
                return

            # Build HTML content
            html_parts = []

            # Asterism name (bold cyan)
            name_html = f"<p style='font-size: 18px; font-weight: bold; color: {colors['cyan']}; margin-bottom: 10px;'>{asterism.name}"
            if asterism.alt_names:
                alt_names_str = ", ".join(asterism.alt_names)
                name_html += f" <span style='color: {colors['text_dim']}; font-weight: normal; font-size: 14px;'>({alt_names_str})</span>"
            name_html += "</p>"
            html_parts.append(name_html)

            # Coordinates section
            html_parts.append(
                f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Coordinates:</p>"
            )
            ra_str = format_ra(asterism.ra_hours)
            dec_str = format_dec(asterism.dec_degrees)
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
            if asterism.size_degrees:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Size: {asterism.size_degrees:.1f}°</p>"
                )
            if asterism.parent_constellation:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Parent Constellation: {asterism.parent_constellation}</p>"
                )
            if asterism.season:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Best Season: {asterism.season}</p>"
                )
            if asterism.hemisphere:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Hemisphere: {asterism.hemisphere}</p>"
                )
            if hasattr(asterism, "shape_description") and asterism.shape_description:
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>Shape: {asterism.shape_description}</p>"
                )

            # Description
            if asterism.description:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Description:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>{asterism.description}</p>"
                )

            # Guidepost info
            if hasattr(asterism, "guidepost_info") and asterism.guidepost_info:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Using as a Guidepost:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>{asterism.guidepost_info}</p>"
                )

            # Cultural information
            if hasattr(asterism, "cultural_info") and asterism.cultural_info:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Cultural & Mythological Information:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>{asterism.cultural_info}</p>"
                )

            # Historical notes
            if hasattr(asterism, "historical_notes") and asterism.historical_notes:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Historical Notes:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>{asterism.historical_notes}</p>"
                )

            # Component stars
            if asterism.member_stars:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Component Stars:</p>"
                )
                stars_str = ", ".join(asterism.member_stars)
                html_parts.append(f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>{stars_str}</p>")

            # Wikipedia link
            if hasattr(asterism, "wikipedia_url") and asterism.wikipedia_url:
                html_parts.append(
                    f"<p style='font-weight: bold; color: {colors['header']}; margin-top: 15px; margin-bottom: 5px;'>Reference:</p>"
                )
                html_parts.append(
                    f"<p style='margin-left: 20px; margin-top: 5px; margin-bottom: 5px;'>"
                    f"<a href='{asterism.wikipedia_url}' style='color: {colors['cyan']};'>{asterism.wikipedia_url}</a>"
                    f"</p>"
                )

            # Set HTML content
            self.info_text.setHtml("".join(html_parts))

        except Exception as e:
            logger.error(f"Error loading asterism info: {e}", exc_info=True)
            self.info_text.setHtml(
                f"<p style='color: {colors['error']};'><b>Error:</b> Failed to load asterism information: {e}</p>"
            )
