"""
Catalog Worker Threads

QThread workers for async catalog operations to prevent UI blocking.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from celestron_nexstar.api.catalogs.catalogs import search_objects


logger = logging.getLogger(__name__)


class SearchObjectsWorker(QThread):
    """Worker thread to search for celestial objects."""

    results_ready = Signal(list)  # type: ignore[type-arg,misc]  # Emits list[CelestialObject]
    error_occurred = Signal(str)  # type: ignore[type-arg,misc]  # Emits error message

    def __init__(self, query: str, catalog_name: str | None = None, update_positions: bool = False) -> None:
        """
        Initialize the search worker.

        Args:
            query: Search query string
            catalog_name: Optional catalog name to filter by
            update_positions: Whether to update positions for dynamic objects
        """
        super().__init__()
        self.query = query
        self.catalog_name = catalog_name
        self.update_positions = update_positions

    def run(self) -> None:
        """Perform search in background thread."""
        try:
            logger.debug(f"Searching for: {self.query} (catalog: {self.catalog_name})")
            results = search_objects(self.query, catalog_name=self.catalog_name, update_positions=self.update_positions)
            logger.debug(f"Search found {len(results)} results")
            self.results_ready.emit(results)
        except Exception as e:
            logger.error(f"Error searching objects: {e}", exc_info=True)
            self.error_occurred.emit(str(e))
