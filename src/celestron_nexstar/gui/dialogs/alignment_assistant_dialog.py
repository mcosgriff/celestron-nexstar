"""
Alignment Assistant Dialog

Step-by-step wizard for telescope alignment with visual guides and quality indicators.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from celestron_nexstar.api.core.utils import format_dec, format_ra
from celestron_nexstar.api.location.observer import get_observer_location
from celestron_nexstar.api.telescope.alignment import (
    SkyAlignGroup,
    SkyAlignObject,
    TwoStarAlignPair,
    get_alignment_conditions,
    suggest_skyalign_objects,
    suggest_two_star_align_objects,
)


if TYPE_CHECKING:
    from celestron_nexstar import NexStarTelescope

logger = logging.getLogger(__name__)


class AlignmentAssistantDialog(QDialog):
    """Step-by-step alignment wizard dialog."""

    def __init__(self, parent: QWidget | None = None, telescope: NexStarTelescope | None = None) -> None:
        """Initialize the alignment assistant dialog."""
        super().__init__(parent)
        self.setWindowTitle("Alignment Assistant")
        self.setMinimumWidth(800)
        self.setMinimumHeight(600)

        self.telescope = telescope
        self.current_step = 0
        self.selected_method: str | None = None  # "skyalign", "two_star", "one_star"
        self.selected_group: SkyAlignGroup | None = None
        self.selected_pair: TwoStarAlignPair | None = None
        self.selected_object: SkyAlignObject | None = None
        self.current_object_index = 0  # For SkyAlign (0, 1, 2)

        # Main layout
        main_layout = QVBoxLayout(self)

        # Step indicator
        self.step_label = QLabel("Step 1 of 5: Select Alignment Method")
        step_font = QFont()
        step_font.setBold(True)
        step_font.setPointSize(12)
        self.step_label.setFont(step_font)
        main_layout.addWidget(self.step_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 5)
        self.progress_bar.setValue(1)
        main_layout.addWidget(self.progress_bar)

        # Content area (scrollable)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        scroll_area.setWidget(self.content_widget)
        main_layout.addWidget(scroll_area, stretch=1)

        # Button box
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Next")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).clicked.connect(self._on_next_clicked)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

        # Initialize first step
        self._show_method_selection()

    def _clear_content(self) -> None:
        """Clear the content area."""
        while self.content_layout.count():
            child = self.content_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()

    def _show_method_selection(self) -> None:
        """Show alignment method selection step."""
        self.current_step = 1
        self._clear_content()
        self.step_label.setText("Step 1 of 5: Select Alignment Method")
        self.progress_bar.setValue(1)

        # Method selection
        info_label = QLabel(
            "Choose an alignment method:\n\n"
            "• <b>SkyAlign</b> (Recommended for beginners): Align using 3 bright objects. "
            "You don't need to know their names - just center them in the eyepiece.\n\n"
            "• <b>Two-Star Alignment</b>: Traditional alignment using 2 known stars. "
            "More accurate but requires knowing star names.\n\n"
            "• <b>One-Star Alignment</b>: Quick alignment using a single star. "
            "Fastest but least accurate."
        )
        info_label.setWordWrap(True)
        self.content_layout.addWidget(info_label)

        # Method buttons
        methods_layout = QVBoxLayout()

        skyalign_btn = QPushButton("SkyAlign (3 Objects)")
        skyalign_btn.setMinimumHeight(50)
        skyalign_btn.clicked.connect(lambda: self._select_method("skyalign"))
        methods_layout.addWidget(skyalign_btn)

        two_star_btn = QPushButton("Two-Star Alignment")
        two_star_btn.setMinimumHeight(50)
        two_star_btn.clicked.connect(lambda: self._select_method("two_star"))
        methods_layout.addWidget(two_star_btn)

        one_star_btn = QPushButton("One-Star Alignment")
        one_star_btn.setMinimumHeight(50)
        one_star_btn.clicked.connect(lambda: self._select_method("one_star"))
        methods_layout.addWidget(one_star_btn)

        self.content_layout.addLayout(methods_layout)
        self.content_layout.addStretch()

        # Disable Next button until method is selected
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def _select_method(self, method: str) -> None:
        """Select alignment method and proceed."""
        self.selected_method = method
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        # Highlight selected button (simple visual feedback)
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i)
            if item:
                layout = item.layout()
                if layout:
                    for j in range(layout.count()):
                        layout_item = layout.itemAt(j)
                        if layout_item:
                            widget = layout_item.widget()
                            if isinstance(widget, QPushButton):
                                widget.setStyleSheet("")

        # Find and highlight the clicked button
        sender = self.sender()
        if isinstance(sender, QPushButton):
            sender.setStyleSheet("background-color: #4CAF50; color: white;")

    def _on_next_clicked(self) -> None:
        """Handle Next button click."""
        if self.current_step == 1:
            # Method selected, show object selection
            if self.selected_method == "skyalign":
                self._show_skyalign_selection()
            elif self.selected_method == "two_star":
                self._show_two_star_selection()
            elif self.selected_method == "one_star":
                self._show_one_star_selection()
        elif self.current_step == 2:
            # Objects selected, get selection and show alignment instructions
            if self.selected_method == "skyalign":
                if hasattr(self, "_groups_list"):
                    current_item = self._groups_list.currentItem()
                    if current_item:
                        self.selected_group = current_item.data(Qt.ItemDataRole.UserRole)
                        self.current_object_index = 0
                        self._show_skyalign_instructions()
                    else:
                        QMessageBox.warning(self, "No Selection", "Please select an object group first.")
                else:
                    QMessageBox.warning(self, "No Selection", "Please select an object group first.")
            elif self.selected_method == "two_star":
                if hasattr(self, "_pairs_list"):
                    current_item = self._pairs_list.currentItem()
                    if current_item:
                        self.selected_pair = current_item.data(Qt.ItemDataRole.UserRole)
                        self.current_object_index = 0
                        self._show_two_star_instructions()
                    else:
                        QMessageBox.warning(self, "No Selection", "Please select a star pair first.")
                else:
                    QMessageBox.warning(self, "No Selection", "Please select a star pair first.")
            elif self.selected_method == "one_star":
                self._show_one_star_instructions()
        elif self.current_step == 3:
            # Ready to align, show sync step
            self._show_sync_step()
        elif self.current_step == 4:
            # Sync complete, show next object or completion
            if self.selected_method == "skyalign" and self.current_object_index < 2:
                self.current_object_index += 1
                self._show_skyalign_instructions()
            elif self.selected_method == "two_star" and self.current_object_index == 0:
                self.current_object_index = 1
                self._show_two_star_instructions()
            else:
                self._show_completion()
        elif self.current_step == 5:
            # Completion, close dialog
            self.accept()

    def _show_skyalign_selection(self) -> None:
        """Show SkyAlign object group selection."""
        self.current_step = 2
        self._clear_content()
        self.step_label.setText("Step 2 of 5: Select Object Group")
        self.progress_bar.setValue(2)

        info_label = QLabel("Loading suitable object groups...")
        self.content_layout.addWidget(info_label)

        # Load suggestions in background
        def load_suggestions() -> None:
            try:
                observer = get_observer_location()
                conditions = get_alignment_conditions(observer_lat=observer.latitude, observer_lon=observer.longitude)
                groups = suggest_skyalign_objects(
                    observer_lat=observer.latitude,
                    observer_lon=observer.longitude,
                    max_groups=10,
                    cloud_cover_percent=conditions.cloud_cover_percent,
                    moon_ra_hours=conditions.moon_ra_hours,
                    moon_dec_degrees=conditions.moon_dec_degrees,
                    moon_illumination=conditions.moon_illumination,
                    seeing_score=conditions.seeing_score,
                )

                # Update UI on main thread
                self._display_skyalign_groups(groups)
            except Exception as e:
                logger.error(f"Error loading SkyAlign suggestions: {e}", exc_info=True)
                info_label.setText(f"Error loading suggestions: {e}")

        # Run in background
        import threading

        thread = threading.Thread(target=load_suggestions, daemon=True)
        thread.start()

    def _display_skyalign_groups(self, groups: list[SkyAlignGroup]) -> None:
        """Display SkyAlign groups for selection."""
        self._clear_content()

        if not groups:
            info_label = QLabel(
                "No suitable object groups found. Please ensure:\n"
                "• Location and time are set correctly\n"
                "• At least 3 bright objects are visible\n"
                "• Objects are well-separated (≥30° apart)"
            )
            info_label.setWordWrap(True)
            self.content_layout.addWidget(info_label)
            self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return

        info_label = QLabel(
            "Select a group of 3 objects for alignment. Groups are sorted by quality "
            "(best first). Look for groups with:\n"
            "• High separation scores (objects well-spaced)\n"
            "• High observability scores (objects easy to see)\n"
            "• Good conditions scores (clear skies)"
        )
        info_label.setWordWrap(True)
        self.content_layout.addWidget(info_label)

        # Groups list
        groups_list = QListWidget()
        for i, group in enumerate(groups):
            obj1, obj2, obj3 = group.objects
            item_text = (
                f"Group {i + 1}: {obj1.display_name}, {obj2.display_name}, {obj3.display_name}\n"
                f"  Separation: {group.min_separation_deg:.1f}° | "
                f"Quality: {group.separation_score * group.avg_observability_score * group.conditions_score:.2f}"
            )
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, group)
            groups_list.addItem(item)

        groups_list.itemSelectionChanged.connect(
            lambda: self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
                bool(groups_list.currentItem())
            )
        )
        groups_list.itemDoubleClicked.connect(self._on_next_clicked)
        self.content_layout.addWidget(groups_list)

        # Store reference for selection
        self._groups_list = groups_list

    def _show_two_star_selection(self) -> None:
        """Show Two-Star alignment pair selection."""
        self.current_step = 2
        self._clear_content()
        self.step_label.setText("Step 2 of 5: Select Star Pair")
        self.progress_bar.setValue(2)

        info_label = QLabel("Loading suitable star pairs...")
        self.content_layout.addWidget(info_label)

        # Load suggestions in background
        def load_suggestions() -> None:
            try:
                observer = get_observer_location()
                conditions = get_alignment_conditions(observer_lat=observer.latitude, observer_lon=observer.longitude)
                pairs = suggest_two_star_align_objects(
                    observer_lat=observer.latitude,
                    observer_lon=observer.longitude,
                    max_pairs=10,
                    cloud_cover_percent=conditions.cloud_cover_percent,
                    moon_ra_hours=conditions.moon_ra_hours,
                    moon_dec_degrees=conditions.moon_dec_degrees,
                    moon_illumination=conditions.moon_illumination,
                    seeing_score=conditions.seeing_score,
                )

                # Update UI on main thread
                self._display_two_star_pairs(pairs)
            except Exception as e:
                logger.error(f"Error loading Two-Star suggestions: {e}", exc_info=True)
                info_label.setText(f"Error loading suggestions: {e}")

        # Run in background
        import threading

        thread = threading.Thread(target=load_suggestions, daemon=True)
        thread.start()

    def _display_two_star_pairs(self, pairs: list[TwoStarAlignPair]) -> None:
        """Display Two-Star pairs for selection."""
        self._clear_content()

        if not pairs:
            info_label = QLabel(
                "No suitable star pairs found. Please ensure:\n"
                "• Location and time are set correctly\n"
                "• At least 2 bright stars are visible\n"
                "• Stars are well-separated"
            )
            info_label.setWordWrap(True)
            self.content_layout.addWidget(info_label)
            self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
            return

        info_label = QLabel("Select a pair of stars for alignment. Pairs are sorted by quality (best first).")
        info_label.setWordWrap(True)
        self.content_layout.addWidget(info_label)

        # Pairs list
        pairs_list = QListWidget()
        for i, pair in enumerate(pairs):
            item_text = (
                f"Pair {i + 1}: {pair.star1.display_name} → {pair.star2.display_name}\n"
                f"  Separation: {pair.separation_deg:.1f}° | "
                f"Quality: {pair.separation_score * pair.avg_observability_score * pair.conditions_score:.2f}"
            )
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, pair)
            pairs_list.addItem(item)

        pairs_list.itemSelectionChanged.connect(
            lambda: self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
                bool(pairs_list.currentItem())
            )
        )
        pairs_list.itemDoubleClicked.connect(self._on_next_clicked)
        self.content_layout.addWidget(pairs_list)

        # Store reference for selection
        self._pairs_list = pairs_list

    def _show_one_star_selection(self) -> None:
        """Show One-Star alignment object selection."""
        self.current_step = 2
        self._clear_content()
        self.step_label.setText("Step 2 of 5: Select Star")
        self.progress_bar.setValue(2)

        info_label = QLabel("One-star alignment is not yet fully implemented in the GUI.")
        info_label.setWordWrap(True)
        self.content_layout.addWidget(info_label)
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def _show_skyalign_instructions(self) -> None:
        """Show SkyAlign alignment instructions for current object."""
        if not self.selected_group and hasattr(self, "_groups_list"):
            # Get selected group
            current_item = self._groups_list.currentItem()
            if current_item:
                self.selected_group = current_item.data(Qt.ItemDataRole.UserRole)

        if not self.selected_group:
            QMessageBox.warning(self, "No Selection", "Please select an object group first.")
            return

        self.current_step = 3
        self._clear_content()
        obj = self.selected_group.objects[self.current_object_index]
        step_num = self.current_object_index + 1
        self.step_label.setText(f"Step 3 of 5: Align Object {step_num} of 3")
        self.progress_bar.setValue(3)

        # Object info
        info_text = (
            f"<h3>Object {step_num}: {obj.display_name}</h3>"
            f"<p><b>Position:</b> RA {format_ra(obj.obj.ra_hours)}, Dec {format_dec(obj.obj.dec_degrees)}</p>"
            f"<p><b>Altitude:</b> {obj.visibility.altitude_deg:.1f}°</p>"
            f"<p><b>Azimuth:</b> {obj.visibility.azimuth_deg:.1f}°</p>"
        )

        if obj.visibility.altitude_deg is not None and obj.visibility.altitude_deg < 20:
            info_text += "<p style='color: red;'><b>Warning:</b> Object is low on the horizon. "
            info_text += "Alignment may be less accurate.</p>"

        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        self.content_layout.addWidget(info_label)

        # Instructions
        instructions = QLabel(
            "<h4>Instructions:</h4>"
            "<ol>"
            "<li>Use the hand control or arrow buttons to manually center this object in your eyepiece</li>"
            "<li>Make sure the object is precisely centered (use highest magnification eyepiece if possible)</li>"
            "<li>Click 'Sync' when the object is centered</li>"
            "</ol>"
        )
        instructions.setWordWrap(True)
        self.content_layout.addWidget(instructions)

        # Sync button
        sync_btn = QPushButton(f"Sync on {obj.display_name}")
        sync_btn.setMinimumHeight(50)
        sync_btn.clicked.connect(lambda: self._sync_object(obj))
        self.content_layout.addWidget(sync_btn)

        self.content_layout.addStretch()

        # Update Next button
        if self.current_object_index == 0:
            self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Skip to Next")
            self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        else:
            self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Next")
            self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def _show_two_star_instructions(self) -> None:
        """Show Two-Star alignment instructions."""
        if not self.selected_pair and hasattr(self, "_pairs_list"):
            # Get selected pair
            current_item = self._pairs_list.currentItem()
            if current_item:
                self.selected_pair = current_item.data(Qt.ItemDataRole.UserRole)

        if not self.selected_pair:
            QMessageBox.warning(self, "No Selection", "Please select a star pair first.")
            return

        self.current_step = 3
        self._clear_content()

        if self.current_object_index == 0:
            # First star
            obj = self.selected_pair.star1
            self.step_label.setText("Step 3 of 5: Align First Star")
            self.progress_bar.setValue(3)

            info_text = (
                f"<h3>First Star: {obj.display_name}</h3>"
                f"<p><b>Position:</b> RA {format_ra(obj.obj.ra_hours)}, Dec {format_dec(obj.obj.dec_degrees)}</p>"
                f"<p><b>Altitude:</b> {obj.visibility.altitude_deg:.1f}°</p>"
                f"<p><b>Azimuth:</b> {obj.visibility.azimuth_deg:.1f}°</p>"
            )

            instructions = QLabel(
                "<h4>Instructions:</h4>"
                "<ol>"
                "<li>Manually center this star in your eyepiece using the hand control</li>"
                "<li>Make sure the star is precisely centered</li>"
                "<li>Click 'Sync' when the star is centered</li>"
                "</ol>"
            )

            sync_btn = QPushButton(f"Sync on {obj.display_name}")
        else:
            # Second star
            obj = self.selected_pair.star2
            self.step_label.setText("Step 4 of 5: Align Second Star")
            self.progress_bar.setValue(4)

            info_text = (
                f"<h3>Second Star: {obj.display_name}</h3>"
                f"<p><b>Position:</b> RA {format_ra(obj.obj.ra_hours)}, Dec {format_dec(obj.obj.dec_degrees)}</p>"
                f"<p><b>Altitude:</b> {obj.visibility.altitude_deg:.1f}°</p>"
                f"<p><b>Azimuth:</b> {obj.visibility.azimuth_deg:.1f}°</p>"
            )

            instructions = QLabel(
                "<h4>Instructions:</h4>"
                "<ol>"
                "<li>The telescope will automatically slew to this star</li>"
                "<li>Fine-tune the position to center the star in your eyepiece</li>"
                "<li>Click 'Sync' when the star is centered</li>"
                "</ol>"
            )

            sync_btn = QPushButton(f"Sync on {obj.display_name}")

            # Goto button for second star
            if self.telescope:
                goto_btn = QPushButton(f"Goto {obj.display_name}")
                goto_btn.setMinimumHeight(50)
                goto_btn.clicked.connect(lambda: self._goto_object(obj))
                self.content_layout.addWidget(goto_btn)

        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        self.content_layout.addWidget(info_label)

        instructions.setWordWrap(True)
        self.content_layout.addWidget(instructions)

        sync_btn.setMinimumHeight(50)
        sync_btn.clicked.connect(lambda: self._sync_object(obj))
        self.content_layout.addWidget(sync_btn)

        self.content_layout.addStretch()

        # Update Next button
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Next")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def _show_one_star_instructions(self) -> None:
        """Show One-Star alignment instructions."""
        # Not fully implemented yet
        pass

    def _show_sync_step(self) -> None:
        """Show sync confirmation step."""
        # This is handled in the instruction steps
        pass

    def _show_completion(self) -> None:
        """Show alignment completion."""
        self.current_step = 5
        self._clear_content()
        self.step_label.setText("Step 5 of 5: Alignment Complete")
        self.progress_bar.setValue(5)

        completion_text = (
            "<h2>Alignment Complete!</h2>"
            "<p>Your telescope has been successfully aligned.</p>"
            "<p><b>Next Steps:</b></p>"
            "<ul>"
            "<li>Test the alignment by performing a goto to a known object</li>"
            "<li>Check the alignment accuracy</li>"
            "<li>If accuracy is poor, try re-aligning with different objects</li>"
            "</ul>"
        )

        completion_label = QLabel(completion_text)
        completion_label.setWordWrap(True)
        self.content_layout.addWidget(completion_label)

        self.content_layout.addStretch()

        # Update button
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Finish")
        self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def _sync_object(self, obj: SkyAlignObject) -> None:
        """Sync telescope to the selected object."""
        if not self.telescope:
            QMessageBox.warning(self, "No Telescope", "Telescope is not connected.")
            return

        try:
            # Update object position for dynamic objects
            updated_obj = obj.obj.with_current_position()

            # Perform sync
            success = asyncio.run(self.telescope.sync_ra_dec(updated_obj.ra_hours, updated_obj.dec_degrees))

            if success:
                QMessageBox.information(self, "Sync Successful", f"Successfully synced on {obj.display_name}.")
                # Enable Next button
                self.button_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
            else:
                QMessageBox.warning(self, "Sync Failed", "Failed to sync telescope position.")
        except Exception as e:
            logger.error(f"Error syncing object: {e}", exc_info=True)
            QMessageBox.critical(self, "Sync Error", f"Error syncing telescope: {e}")

    def _goto_object(self, obj: SkyAlignObject) -> None:
        """Goto the selected object."""
        if not self.telescope:
            QMessageBox.warning(self, "No Telescope", "Telescope is not connected.")
            return

        try:
            # Update object position for dynamic objects
            updated_obj = obj.obj.with_current_position()

            # Perform goto
            success = asyncio.run(self.telescope.goto_ra_dec(updated_obj.ra_hours, updated_obj.dec_degrees))

            if success:
                QMessageBox.information(
                    self, "Goto Started", f"Slewing to {obj.display_name}. Please wait for slew to complete."
                )
            else:
                QMessageBox.warning(self, "Goto Failed", "Failed to start goto operation.")
        except Exception as e:
            logger.error(f"Error going to object: {e}", exc_info=True)
            QMessageBox.critical(self, "Goto Error", f"Error slewing telescope: {e}")
