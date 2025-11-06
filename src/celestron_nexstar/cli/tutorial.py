"""
Interactive Tutorial System

Provides guided walkthroughs of the NexStar CLI shell features with
step-by-step lessons and interactive demonstrations.
"""

from dataclasses import dataclass
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm


@dataclass
class Lesson:
    """A single tutorial lesson."""

    title: str
    description: str
    steps: list[tuple[str, str]]  # (instruction, example_command)
    demo_mode: bool = False  # If True, runs in demo mode (no telescope needed)


class TutorialSystem:
    """Interactive tutorial system for the NexStar shell."""

    def __init__(self, console: Console):
        self.console = console
        self.current_lesson = 0
        self.lessons = self._create_lessons()

    def _create_lessons(self) -> list[Lesson]:
        """Create all tutorial lessons."""
        return [
            Lesson(
                title="Welcome to NexStar Interactive Shell",
                description="Learn the basics of navigating the shell interface",
                steps=[
                    ("The shell has tab completion - try typing 'cat' and press TAB", "catalog"),
                    ("Press TAB twice to see all available commands", "<TAB><TAB>"),
                    ("Type 'help' to see detailed command information", "help"),
                    ("Use Ctrl+P / Ctrl+N to navigate command history (previous/next)", "Ctrl+P / Ctrl+N"),
                    ("Press CTRL+C to cancel current input, CTRL+D or 'exit' to quit", "exit"),
                ],
                demo_mode=True
            ),
            Lesson(
                title="Interactive Movement Control",
                description="Control your telescope with arrow keys in real-time",
                steps=[
                    ("Arrow keys (↑↓←→) ALWAYS move the telescope - no mode switching!", ""),
                    ("Just press and hold an arrow key to move in that direction", ""),
                    ("No Enter key needed - telescope responds instantly!", ""),
                    ("Press '+' to increase speed, '-' to decrease", "+/-"),
                    ("Speed range: 0 (slowest) to 9 (fastest), default is 5 (medium)", ""),
                    ("Status bar shows current speed like 'Speed:5/9'", ""),
                    ("Press ESC to stop all movement immediately", "ESC"),
                    ("Watch the status bar: Green = stopped, Red = moving with direction", ""),
                    ("Command history uses Ctrl+P (previous) and Ctrl+N (next) instead", "Ctrl+P / Ctrl+N"),
                ],
                demo_mode=False
            ),
            Lesson(
                title="Background Position Tracking",
                description="Monitor telescope position in real-time",
                steps=[
                    ("Tracking shows live telescope position in the status bar", ""),
                    ("Start tracking manually with this command:", "tracking start"),
                    ("Adjust update frequency (0.5-30 seconds):", "tracking interval 1.0"),
                    ("View tracking statistics:", "tracking stats"),
                    ("View position history:", "tracking history --last 10"),
                    ("Stop tracking:", "tracking stop"),
                ],
                demo_mode=False
            ),
            Lesson(
                title="Advanced Tracking Features",
                description="Export, collision detection, and visualization",
                steps=[
                    ("Export position history to CSV or JSON:", "tracking export positions.csv"),
                    ("Set collision alert threshold (degrees/sec):", "tracking alert-threshold 5.0"),
                    ("Enable ASCII star chart in status bar:", "tracking chart on"),
                    ("The chart shows compass direction and altitude", ""),
                    ("Clear tracking history:", "tracking clear"),
                ],
                demo_mode=False
            ),
            Lesson(
                title="Exploring Celestial Objects",
                description="Browse catalogs and find objects to observe",
                steps=[
                    ("List all available catalogs:", "catalog catalogs"),
                    ("View objects in a catalog:", "catalog list --catalog messier"),
                    ("Search for objects by name:", "catalog search andromeda"),
                    ("Get detailed object information:", "catalog info M31"),
                    ("View planetary moons:", "catalog list --catalog jupiter-moons"),
                ],
                demo_mode=True
            ),
            Lesson(
                title="Telescope Configuration",
                description="Set up your telescope and observing location",
                steps=[
                    ("Configure your telescope model:", "optics config --telescope nexstar_6se --eyepiece 25"),
                    ("View current configuration:", "optics show"),
                    ("Set your observing location:", 'location set --lat 34.05 --lon -118.24 --name "Los Angeles"'),
                    ("Or use geocoding:", 'location geocode "New York, NY"'),
                    ("View current location:", "location show"),
                ],
                demo_mode=True
            ),
            Lesson(
                title="Basic Telescope Control",
                description="Connect and control your telescope",
                steps=[
                    ("Connect to telescope:", "connect --port /dev/ttyUSB0"),
                    ("Get current position:", "position get"),
                    ("Slew to an object from catalog:", "goto object --name Jupiter"),
                    ("Or slew to coordinates:", "goto ra-dec --ra 5.5 --dec 22.5"),
                    ("Set tracking mode:", "track set --mode alt_az"),
                ],
                demo_mode=False
            ),
            Lesson(
                title="Alignment and Syncing",
                description="Improve telescope pointing accuracy",
                steps=[
                    ("Center a known star manually using arrow keys", ""),
                    ("Then sync to its known position:", "align sync --ra 5.5 --dec 22.5"),
                    ("This calibrates the telescope for better accuracy", ""),
                    ("Tracking starts automatically after alignment", ""),
                    ("Perform 2-3 star alignment for best results", ""),
                ],
                demo_mode=False
            ),
            Lesson(
                title="Ephemeris Management",
                description="Download data for planetary calculations",
                steps=[
                    ("View available ephemeris sets:", "ephemeris sets"),
                    ("List installed files:", "ephemeris list"),
                    ("Download standard set (recommended):", "ephemeris download standard"),
                    ("This enables accurate planetary moon positions", ""),
                    ("Verify downloaded files:", "ephemeris verify"),
                ],
                demo_mode=True
            ),
            Lesson(
                title="Shell Tips & Tricks",
                description="Power user features and shortcuts",
                steps=[
                    ("Use 'clear' to clear the screen", "clear"),
                    ("Command history persists between sessions", ""),
                    ("Status bar updates in real-time (0.5s refresh)", ""),
                    ("Multiple status indicators can show simultaneously", ""),
                    ("All commands support --help for detailed usage", "catalog --help"),
                    ("The shell is fully scriptable via command mode", ""),
                ],
                demo_mode=True
            ),
        ]

    def start(self) -> None:
        """Start the interactive tutorial."""
        self.console.print("\n[bold green]╔══════════════════════════════════════════════════╗[/bold green]")
        self.console.print("[bold green]║[/bold green]   [bold cyan]NexStar Interactive Tutorial[/bold cyan]              [bold green]║[/bold green]")
        self.console.print("[bold green]╚══════════════════════════════════════════════════╝[/bold green]\n")

        self.console.print("[dim]This tutorial will guide you through all the features "
                          "of the NexStar Interactive Shell.[/dim]\n")

        # Show lesson menu
        self._show_menu()

    def _show_menu(self) -> None:
        """Show the tutorial lesson menu."""
        self.console.print("\n[bold]Available Lessons:[/bold]\n")

        for i, lesson in enumerate(self.lessons, 1):
            mode_badge = "[green](Demo)[/green]" if lesson.demo_mode else "[yellow](Telescope Required)[/yellow]"
            self.console.print(f"  {i}. [cyan]{lesson.title}[/cyan] {mode_badge}")
            self.console.print(f"     [dim]{lesson.description}[/dim]")

        self.console.print("\n[bold]Options:[/bold]")
        self.console.print("  • Type a lesson number to start that lesson")
        self.console.print("  • Type 'all' to run all lessons in sequence")
        self.console.print("  • Type 'demo' to run only demo lessons (no telescope needed)")
        self.console.print("  • Type 'exit' to return to shell\n")

    def run_lesson(self, lesson_index: int) -> None:
        """Run a specific lesson.

        Args:
            lesson_index: 0-based index of lesson to run
        """
        if lesson_index < 0 or lesson_index >= len(self.lessons):
            self.console.print("[red]Invalid lesson number[/red]")
            return

        lesson = self.lessons[lesson_index]

        # Display lesson header
        self.console.print(f"\n[bold cyan]═══ Lesson {lesson_index + 1}: {lesson.title} ═══[/bold cyan]\n")
        self.console.print(f"[dim]{lesson.description}[/dim]\n")

        if not lesson.demo_mode:
            self.console.print("[yellow]⚠ This lesson requires a connected telescope[/yellow]\n")

        # Display all steps
        for i, (instruction, example) in enumerate(lesson.steps, 1):
            panel_content = f"[bold]{i}. {escape(instruction)}[/bold]"
            if example:
                panel_content += f"\n\n[dim]Example:[/dim] [green]{escape(example)}[/green]"

            self.console.print(Panel(
                panel_content,
                border_style="cyan",
                padding=(0, 2)
            ))

            # Wait for user to acknowledge (except last step)
            if i < len(lesson.steps):
                if not Confirm.ask("\n[dim]Ready for next step?[/dim]", default=True):
                    self.console.print("[yellow]Lesson paused. Type 'tutorial' to resume.[/yellow]")
                    return
                self.console.print()

        # Lesson complete
        self.console.print(f"\n[bold green]✓ Lesson {lesson_index + 1} Complete![/bold green]")
        self.console.print("[dim]Feel free to practice these commands in the shell.[/dim]\n")

    def run_all_lessons(self, demo_only: bool = False) -> None:
        """Run all lessons in sequence.

        Args:
            demo_only: If True, only run demo lessons
        """
        lessons_to_run = [
            (i, lesson) for i, lesson in enumerate(self.lessons)
            if not demo_only or lesson.demo_mode
        ]

        mode_str = "demo " if demo_only else ""
        self.console.print(f"\n[bold]Running {len(lessons_to_run)} {mode_str}lessons...[/bold]\n")

        for i, lesson in lessons_to_run:
            self.run_lesson(i)

            if i < len(lessons_to_run) - 1:
                if not Confirm.ask("\n[dim]Continue to next lesson?[/dim]", default=True):
                    self.console.print("[yellow]Tutorial paused.[/yellow]")
                    return

        self.console.print("\n[bold green]🎉 Tutorial Complete![/bold green]")
        self.console.print("[dim]You're ready to explore the NexStar shell.[/dim]\n")

    def get_quick_tips(self) -> list[str]:
        """Get a list of quick tips for display.

        Returns:
            List of tip strings
        """
        return [
            "Press TAB for command completion",
            "Arrow keys (↑↓←→) always move telescope",
            "Press Ctrl+P/Ctrl+N for command history",
            "Press +/- to adjust slew speed (0-9)",
            "Type 'help' to see all commands",
            "Type 'tutorial' to start the interactive tutorial",
            "Background tracking shows position in status bar",
            "Press ESC for emergency stop",
        ]
