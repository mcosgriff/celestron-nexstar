"""
Glossary Command

Displays astronomical terms and definitions.
"""

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


app = typer.Typer(
    name="glossary",
    help="Astronomical terms glossary",
    rich_help_panel="Utilities",
)

console = Console()

# Glossary terms organized by category
GLOSSARY_TERMS: dict[str, dict[str, str]] = {
    "Object Types": {
        "Asterism": (
            "A recognizable pattern of stars that is not one of the 88 official constellations. "
            "Examples include the Big Dipper (part of Ursa Major), the Summer Triangle, and the "
            "Winter Hexagon. Asterisms are useful for navigation and star-hopping."
        ),
        "Constellation": (
            "One of 88 officially recognized regions of the sky defined by the International "
            "Astronomical Union (IAU). Each constellation represents a specific area of the "
            "celestial sphere and often has mythological or cultural significance. Constellations "
            "help astronomers organize and locate celestial objects."
        ),
        "Deep Sky Object (DSO)": (
            "Any astronomical object that is not a star or a solar system object. This includes "
            "galaxies, nebulae, star clusters, and other extended objects beyond our solar system. "
            "DSOs are typically faint and require telescopes or binoculars to observe."
        ),
        "Messier Object": (
            "A catalog of 110 bright deep sky objects compiled by French astronomer Charles Messier "
            "in the 18th century. Messier created this list to help comet hunters avoid confusing "
            "these objects with comets. The catalog includes galaxies, nebulae, and star clusters, "
            "and many are popular targets for amateur astronomers."
        ),
        "NGC Object": (
            "An object from the New General Catalogue of Nebulae and Clusters of Stars (NGC), "
            "compiled by John Louis Emil Dreyer in 1888. The NGC contains 7,840 objects and is "
            "one of the most comprehensive catalogs of deep sky objects. Many NGC objects are "
            "visible with amateur telescopes."
        ),
        "Caldwell Object": (
            "A catalog of 109 bright deep sky objects compiled by British amateur astronomer "
            "Sir Patrick Caldwell-Moore. The catalog complements the Messier catalog and includes "
            "objects visible from the Northern Hemisphere, many of which are excellent targets "
            "for amateur telescopes."
        ),
    },
    "Galaxies": {
        "Local Group": (
            "A gravitationally bound group of more than 50 galaxies that includes the Milky Way, "
            "Andromeda Galaxy (M31), Triangulum Galaxy (M33), and many dwarf galaxies. The Local "
            "Group spans about 10 million light-years and is part of the Virgo Supercluster."
        ),
        "Milky Way Halo": (
            "The spherical region surrounding the Milky Way galaxy that contains globular clusters, "
            "dwarf galaxies, and dark matter. The halo extends far beyond the visible disk of the "
            "galaxy and contains some of the oldest stars in the Milky Way."
        ),
        "Globular Cluster": (
            "A tightly bound, spherical collection of hundreds of thousands to millions of old stars "
            "that orbit a galactic core. Globular clusters are found in the halos of galaxies and "
            "are among the oldest objects in the universe, with ages typically over 10 billion years."
        ),
        "Dwarf Galaxy": (
            "A small galaxy composed of up to several billion stars, much smaller than the Milky Way. "
            "Dwarf galaxies are the most common type of galaxy in the universe. Many orbit larger "
            "galaxies as satellites, such as the Large and Small Magellanic Clouds that orbit the "
            "Milky Way."
        ),
    },
    "Nebulae": {
        "Emission Nebula": (
            "A cloud of ionized gas that emits light of various colors. These nebulae are often "
            "associated with star-forming regions where young, hot stars ionize surrounding "
            "hydrogen gas. Examples include the Orion Nebula (M42) and the Lagoon Nebula (M8)."
        ),
        "Reflection Nebula": (
            "A cloud of interstellar dust that reflects the light of nearby stars. Unlike emission "
            "nebulae, reflection nebulae do not emit their own light but scatter starlight, "
            "typically appearing blue due to the same scattering effect that makes the sky blue."
        ),
        "Planetary Nebula": (
            "A shell of ionized gas ejected from red giant stars late in their evolution. Despite "
            "the name, planetary nebulae have nothing to do with planets; early astronomers "
            "thought they resembled planetary disks. Examples include the Ring Nebula (M57) and "
            "the Helix Nebula (NGC 7293)."
        ),
        "Supernova Remnant": (
            "The expanding shell of gas and dust left behind after a massive star explodes as a "
            "supernova. These remnants can be visible for thousands of years and are important "
            "sources of cosmic rays and heavy elements. Examples include the Crab Nebula (M1) "
            "and the Veil Nebula."
        ),
    },
    "Star Clusters": {
        "Open Cluster": (
            "A loosely bound group of stars that formed from the same molecular cloud. Open clusters "
            "typically contain hundreds to thousands of stars and are found in the spiral arms of "
            "galaxies. They are relatively young (millions to hundreds of millions of years old) "
            "and will eventually disperse. Examples include the Pleiades (M45) and the Hyades."
        ),
        "Star Association": (
            "A loose grouping of stars that share a common origin but are not gravitationally bound. "
            "These stars are moving away from each other and will eventually disperse. Star "
            "associations are typically very young and contain massive, hot stars."
        ),
    },
    "Stars": {
        "Variable Star": (
            "A star whose brightness changes over time. Variability can be caused by pulsation, "
            "eclipses, rotation, or eruptions. Variable stars are important for measuring distances "
            "in the universe and understanding stellar evolution."
        ),
        "Double Star": (
            "Two stars that appear close together in the sky. Double stars can be binary systems "
            "(gravitationally bound) or optical doubles (merely aligned from our perspective). "
            "Binary stars are important for determining stellar masses."
        ),
        "Multiple Star System": (
            "A system of three or more stars that are gravitationally bound. These can include "
            "triple, quadruple, or even more complex systems. The most common are triple star "
            "systems."
        ),
    },
    "Solar System": {
        "Planet": (
            "A celestial body that orbits a star, is massive enough to be rounded by its own gravity, "
            "has cleared its orbital neighborhood of other objects, and is not a moon. In our solar "
            "system, there are eight planets: Mercury, Venus, Earth, Mars, Jupiter, Saturn, "
            "Uranus, and Neptune."
        ),
        "Dwarf Planet": (
            "A celestial body that orbits a star and is massive enough to be rounded by its own "
            "gravity but has not cleared its orbital neighborhood. Examples include Pluto, Ceres, "
            "and Eris."
        ),
        "Moon": (
            "A natural satellite that orbits a planet or dwarf planet. Moons vary greatly in size, "
            "from small irregular bodies to large spherical objects like Earth's Moon or Jupiter's "
            "Galilean moons."
        ),
        "Comet": (
            "A small icy body that, when passing close to the Sun, heats up and releases gases, "
            "creating a visible atmosphere (coma) and sometimes a tail. Comets originate from the "
            "outer solar system and have highly elliptical orbits."
        ),
        "Asteroid": (
            "A small rocky body that orbits the Sun, primarily found in the asteroid belt between "
            "Mars and Jupiter. Asteroids are remnants from the early solar system and vary in size "
            "from small rocks to objects hundreds of kilometers across."
        ),
    },
    "Observation": {
        "Magnitude": (
            "A measure of the brightness of a celestial object. The magnitude scale is logarithmic "
            "and inverted: brighter objects have lower (or more negative) magnitudes. The naked eye "
            "can typically see objects down to magnitude 6 under dark skies. Each magnitude step "
            "represents a brightness difference of about 2.5 times."
        ),
        "Apparent Magnitude": (
            "The brightness of a celestial object as seen from Earth, without accounting for distance. "
            "This is what observers actually see and is affected by the object's intrinsic brightness "
            "and its distance from Earth."
        ),
        "Limiting Magnitude": (
            "The faintest magnitude visible with a given instrument (naked eye, binoculars, or "
            "telescope) under specific observing conditions. It depends on aperture, sky conditions, "
            "and light pollution."
        ),
        "Light Pollution": (
            "Artificial light that brightens the night sky, making it difficult to observe faint "
            "celestial objects. Light pollution is measured using the Bortle scale (1-9) or Sky "
            "Quality Meter (SQM) values. Darker skies have lower Bortle numbers and higher SQM values."
        ),
        "Bortle Scale": (
            "A nine-level scale (1-9) that measures the darkness of the night sky, with 1 being "
            "excellent dark-sky conditions and 9 being inner-city skies. The scale was created by "
            "John E. Bortle and is widely used by amateur astronomers to describe observing conditions."
        ),
        "SQM (Sky Quality Meter)": (
            "A measure of sky brightness in magnitudes per square arcsecond. Higher SQM values "
            "indicate darker skies. Typical values range from about 17 (bright city) to 22 "
            "(excellent dark sky)."
        ),
    },
    "Coordinates": {
        "Right Ascension (RA)": (
            "The celestial equivalent of longitude, measured in hours, minutes, and seconds (0-24 "
            "hours). RA increases eastward from the vernal equinox and is used with declination to "
            "locate objects in the sky."
        ),
        "Declination (Dec)": (
            "The celestial equivalent of latitude, measured in degrees, arcminutes, and arcseconds "
            "(-90° to +90°). Declination measures how far north or south an object is from the "
            "celestial equator."
        ),
        "Celestial Equator": (
            "The projection of Earth's equator onto the celestial sphere. It divides the sky into "
            "northern and southern hemispheres and has a declination of 0°."
        ),
        "Ecliptic": (
            "The apparent path of the Sun across the sky over the course of a year. The ecliptic "
            "is inclined about 23.5° to the celestial equator and is the plane of Earth's orbit "
            "around the Sun."
        ),
    },
}


@app.command()
def show(
    term: Annotated[
        str | None,
        typer.Argument(help="Specific term to look up (optional)"),
    ] = None,
    category: Annotated[
        str | None,
        typer.Option("--category", "-c", help="Filter by category"),
    ] = None,
) -> None:
    """
    Display astronomical terms glossary.

    Examples:
        nexstar glossary                    # Show all terms
        nexstar glossary "Messier Object"  # Look up specific term
        nexstar glossary --category "Object Types"  # Show terms in category
    """
    if term:
        # Look up specific term
        found = False
        for cat, terms in GLOSSARY_TERMS.items():
            if category and cat != category:
                continue
            if term in terms:
                console.print(f"\n[bold cyan]{term}[/bold cyan]")
                console.print(f"[dim]{cat}[/dim]\n")
                console.print(Panel(terms[term], border_style="blue"))
                found = True
                break

        if not found:
            console.print(f"[red]Term '{term}' not found in glossary.[/red]")
            console.print("\n[dim]Use 'nexstar glossary' to see all available terms.[/dim]")
            raise typer.Exit(code=1)
    else:
        # Show all terms or filtered by category
        categories_to_show = [category] if category else list(GLOSSARY_TERMS.keys())

        if category and category not in GLOSSARY_TERMS:
            console.print(f"[red]Category '{category}' not found.[/red]")
            console.print("\n[dim]Available categories:[/dim]")
            for cat in GLOSSARY_TERMS:
                console.print(f"  • {cat}")
            raise typer.Exit(code=1)

        for cat in categories_to_show:
            if cat not in GLOSSARY_TERMS:
                continue

            console.print(f"\n[bold cyan]{cat}[/bold cyan]\n")

            table = Table(
                show_header=True,
                header_style="bold magenta",
                box=None,
                padding=(0, 2),
            )
            table.add_column("Term", style="bold", width=25)
            table.add_column("Definition", style="")

            for term_name, definition in sorted(GLOSSARY_TERMS[cat].items()):
                # Truncate long definitions for table view
                short_def = definition[:97] + "..." if len(definition) > 100 else definition
                table.add_row(term_name, short_def)

            console.print(table)

        console.print("\n[dim]Use 'nexstar glossary <term>' to see full definition of a specific term.[/dim]")
        console.print("[dim]Use 'nexstar glossary --category <category>' to filter by category.[/dim]\n")
