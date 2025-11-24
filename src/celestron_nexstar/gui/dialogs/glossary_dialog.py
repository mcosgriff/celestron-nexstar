"""
Dialog to display astronomical glossary terms organized by category.
"""

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)


class GlossaryDialog(QDialog):
    """Dialog to display astronomical glossary terms with tabs for each category."""

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the glossary dialog."""
        super().__init__(parent)
        self.setWindowTitle("Astronomical Glossary")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self.resize(900, 700)

        # Create layout
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # Get monospace font from application property, fallback to system fonts
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        monospace_font = app.property("monospace_font") if app and app.property("monospace_font") else None
        self._font_family = (
            f"'{monospace_font}', 'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
            if monospace_font
            else "'Courier New', 'Consolas', 'Monaco', 'Menlo', monospace"
        )

        # Import glossary terms
        from celestron_nexstar.cli.commands.glossary import GLOSSARY_TERMS

        self.glossary_terms = GLOSSARY_TERMS

        # Create tabs for each category
        for category in sorted(self.glossary_terms.keys()):
            self._create_category_tab(category)

        # Add button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

        # Load all category data
        for category in sorted(self.glossary_terms.keys()):
            self._load_category_info(category)

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
            "header": "#00bcd4" if is_dark else "#00838f",
            "cyan": "#00bcd4" if is_dark else "#00838f",
            "green": "#4caf50" if is_dark else "#2e7d32",
            "yellow": "#ffc107" if is_dark else "#f57c00",
            "red": "#f44336" if is_dark else "#c62828",
            "error": "#f44336" if is_dark else "#c62828",
        }

    def _create_category_tab(self, category: str) -> None:
        """Create a tab for a glossary category."""
        category_text = QTextEdit()
        category_text.setReadOnly(True)
        category_text.setAcceptRichText(True)
        category_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-family: {self._font_family};
                background-color: transparent;
                border: none;
            }}
        """
        )
        # Store reference to the text widget by category name
        setattr(self, f"{category.lower().replace(' ', '_')}_text", category_text)
        self.tab_widget.addTab(category_text, category)

    def _load_category_info(self, category: str) -> None:
        """Load glossary terms for a specific category."""
        colors = self._get_theme_colors()
        try:
            terms = self.glossary_terms[category]
            text_widget = getattr(self, f"{category.lower().replace(' ', '_')}_text")

            html_content = []
            html_content.append(
                f"<p style='margin-bottom: 15px;'><span style='color: {colors['header']}; font-size: 14pt; font-weight: bold;'>{category}</span></p>"
            )

            # Sort terms alphabetically
            sorted_terms = sorted(terms.items())

            for term_name, definition in sorted_terms:
                # Term header
                html_content.append(
                    f"<p style='margin-top: 15px; margin-bottom: 5px;'><span style='color: {colors['cyan']}; font-weight: bold; font-size: 12pt;'>{term_name}</span></p>"
                )
                # Full definition
                html_content.append(
                    f"<p style='color: {colors['text']}; margin-left: 20px; margin-bottom: 10px; line-height: 1.5;'>{definition}</p>"
                )

            text_widget.setHtml("\n".join(html_content))

        except Exception as e:
            logger.error(f"Error loading glossary category '{category}': {e}", exc_info=True)
            colors = self._get_theme_colors()
            text_widget = getattr(self, f"{category.lower().replace(' ', '_')}_text", None)
            if text_widget:
                text_widget.setHtml(
                    f"<p><span style='color: {colors['error']};'><b>Error:</b> Failed to load glossary category: {e}</span></p>"
                )
