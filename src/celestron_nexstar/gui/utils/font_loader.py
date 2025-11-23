"""
Font loading utility for JetBrains Mono font.

Downloads and loads the JetBrains Mono font from Nerd Fonts for use in the GUI.
"""

import logging
import urllib.request
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from PySide6.QtGui import QFontDatabase

logger = logging.getLogger(__name__)

# Font download URL
JETBRAINS_MONO_URL = "https://github.com/ryanoasis/nerd-fonts/releases/download/v3.4.0/JetBrainsMono.zip"
FONT_FAMILY_NAME = "JetBrains Mono"


def get_font_cache_dir() -> Path:
    """Get the cache directory for fonts."""
    cache_dir = Path.home() / ".cache" / "celestron-nexstar" / "fonts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def download_font() -> Path:
    """
    Download the JetBrains Mono font zip file.

    Returns:
        Path to the downloaded zip file

    Raises:
        Exception: If download fails
    """
    cache_dir = get_font_cache_dir()
    zip_path = cache_dir / "JetBrainsMono.zip"

    # Return cached file if it exists
    if zip_path.exists():
        logger.debug(f"Using cached font file: {zip_path}")
        return zip_path

    # Download the font
    logger.info(f"Downloading JetBrains Mono font from {JETBRAINS_MONO_URL}")
    try:
        with urllib.request.urlopen(JETBRAINS_MONO_URL) as response:
            data = response.read()
            zip_path.write_bytes(data)
        logger.info(f"Downloaded {len(data):,} bytes to {zip_path}")
        return zip_path
    except Exception as e:
        logger.error(f"Failed to download font: {e}")
        raise


def extract_font_file(zip_path: Path) -> Path:
    """
    Extract the JetBrains Mono Regular font file from the zip.

    Args:
        zip_path: Path to the font zip file

    Returns:
        Path to the extracted .ttf font file

    Raises:
        Exception: If extraction fails
    """
    cache_dir = get_font_cache_dir()
    font_file = cache_dir / "JetBrainsMono-Regular.ttf"

    # Return extracted file if it exists
    if font_file.exists():
        logger.debug(f"Using cached font file: {font_file}")
        return font_file

    # Extract the font file from zip
    logger.info(f"Extracting font from {zip_path}")
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            # Look for the Regular variant of JetBrains Mono
            # The zip contains multiple variants, we want the Regular one
            font_names = [name for name in zip_ref.namelist() if "JetBrainsMono-Regular.ttf" in name]
            if not font_names:
                # Fallback: look for any JetBrainsMono .ttf file
                font_names = [name for name in zip_ref.namelist() if "JetBrainsMono" in name and name.endswith(".ttf")]
                if not font_names:
                    raise ValueError("No JetBrains Mono font file found in zip")

            # Use the first matching font file
            font_name = font_names[0]
            logger.debug(f"Extracting {font_name} from zip")
            zip_ref.extract(font_name, cache_dir)

            # Handle subdirectories in zip - find the actual extracted file
            # zip_ref.extract preserves directory structure, so font_name might include subdirs
            extracted_path = cache_dir / font_name
            if not extracted_path.exists():
                # Search for the extracted file (in case of subdirectories)
                found_files = list(cache_dir.rglob("JetBrainsMono-Regular.ttf"))
                if found_files:
                    extracted_path = found_files[0]
                else:
                    # Fallback: look for any JetBrainsMono .ttf file
                    found_files = list(cache_dir.rglob("JetBrainsMono*.ttf"))
                    if found_files:
                        extracted_path = found_files[0]

            # Move to consistent location if needed
            if extracted_path.exists() and extracted_path != font_file:
                # Ensure parent directory exists
                font_file.parent.mkdir(parents=True, exist_ok=True)
                if font_file.exists():
                    font_file.unlink()  # Remove existing file if present
                extracted_path.rename(font_file)

        logger.info(f"Extracted font to {font_file}")
        return font_file
    except Exception as e:
        logger.error(f"Failed to extract font: {e}")
        raise


def _find_jetbrains_mono_in_system(font_db: "QFontDatabase") -> str | None:
    """
    Check if JetBrains Mono is already available in the system fonts.

    Args:
        font_db: QFontDatabase instance

    Returns:
        Font family name if found, None otherwise
    """
    # Common variations of the font name
    font_name_variations = [
        "JetBrains Mono",
        "JetBrainsMono",
        "JetBrains Mono Regular",
        "JetBrainsMono-Regular",
        "JetBrainsMono Nerd Font",
        "JetBrainsMono Nerd Font Regular",
    ]

    available_families = font_db.families()
    if not available_families:
        return None

    # Check for exact matches first
    for variation in font_name_variations:
        if variation in available_families:
            logger.debug(f"Found system font: {variation}")
            return variation

    # Check for case-insensitive matches
    available_lower = {name.lower(): name for name in available_families}
    for variation in font_name_variations:
        if variation.lower() in available_lower:
            found_name = available_lower[variation.lower()]
            logger.debug(f"Found system font (case-insensitive): {found_name}")
            return str(found_name)

    # Check for partial matches (contains "JetBrains" and "Mono")
    for family in available_families:
        family_lower = family.lower()
        if "jetbrains" in family_lower and "mono" in family_lower:
            logger.debug(f"Found system font (partial match): {family}")
            return str(family)

    return None


def load_jetbrains_mono() -> str | None:
    """
    Check for JetBrains Mono in system fonts first, then download and load if not found.

    Returns:
        Font family name if successful, None otherwise
    """
    try:
        from PySide6.QtGui import QFontDatabase

        font_db = QFontDatabase()

        # First, check if font is already available in the system
        system_font = _find_jetbrains_mono_in_system(font_db)
        if system_font:
            logger.info(f"Using system-installed font: {system_font}")
            return system_font

        # Font not found in system, try to download and load
        logger.info("JetBrains Mono not found in system fonts, attempting to download...")
        try:
            zip_path = download_font()
            font_file = extract_font_file(zip_path)

            # Load font into Qt's font database
            font_id = font_db.addApplicationFont(str(font_file))
            if font_id == -1:
                logger.error("Failed to load font into Qt font database")
                return None

            # Get the actual font family name from Qt
            families = font_db.applicationFontFamilies(font_id)
            if families:
                family_name = families[0]
                logger.info(f"Successfully loaded downloaded font: {family_name}")
                return str(family_name)
            else:
                logger.warning("Font loaded but no family name returned")
                return FONT_FAMILY_NAME
        except Exception as download_error:
            logger.warning(f"Could not download/load font: {download_error}")
            logger.info("Falling back to system monospace fonts")
            return None

    except Exception as e:
        logger.error(f"Error loading JetBrains Mono font: {e}", exc_info=True)
        return None
