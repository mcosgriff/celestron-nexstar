# TUI Framework Options for Full-Screen CLI Applications

## Current Situation

We're currently using **prompt_toolkit**, which is excellent for command-line interfaces and interactive prompts, but has limitations for full-screen applications with modal dialogs:

- **Modal dialogs**: Creating overlays requires complex float management and key binding merging
- **State management**: No built-in state management or widget system
- **Layout complexity**: Manual layout construction with containers
- **Event handling**: Lower-level event system

## Recommended Framework: **Textual**

**Textual** (by the Rich team) is specifically designed for full-screen terminal applications and would make this much easier:

### Advantages

1. **Built-in Modal Support**: Easy modal dialogs that overlay on existing content
2. **Widget System**: Pre-built components (buttons, inputs, dialogs, etc.)
3. **CSS-like Styling**: Familiar styling system
4. **Reactive Updates**: Automatic UI updates when data changes
5. **Layout Management**: Grid and flexbox-like layouts
6. **Event System**: Clean event-driven architecture
7. **Async Support**: Built-in async/await support

### Example Migration

```python
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Header, Footer, Input, Button, Static
from textual.screen import ModalScreen

class LocationInputScreen(ModalScreen):
    """Modal dialog for location input."""
    
    def compose(self) -> ComposeResult:
        yield Container(
            Static("[Location] Enter location to geocode:", classes="title"),
            Static('Examples: "New York, NY", "90210", "London, UK"'),
            Input(placeholder="Enter location...", id="location_input"),
            Horizontal(
                Button("OK", variant="primary", id="ok"),
                Button("Cancel", id="cancel"),
            ),
            classes="dialog",
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            location = self.query_one("#location_input", Input).value
            self.dismiss(location)
        else:
            self.dismiss(None)

class TUIApp(App):
    """Main TUI application."""
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            # Your panes here
        )
        yield Footer()
    
    async def on_key(self, event) -> None:
        if event.key == "l":
            result = await self.push_screen(LocationInputScreen())
            if result:
                # Handle location update
                pass
```

### Migration Path

1. **Gradual Migration**: Can run alongside prompt_toolkit initially
2. **Component-by-Component**: Migrate one pane at a time
3. **Preserve Business Logic**: API layer remains unchanged

## Other Framework Options

### 1. **Rich Live Display**
- **Pros**: Simple, works with existing Rich usage
- **Cons**: Limited widget support, no modal dialogs
- **Best for**: Simple status displays, not full applications

### 2. **Blessed**
- **Pros**: Low-level terminal control, good for games
- **Cons**: Very low-level, no widget system
- **Best for**: Terminal games, not business applications

### 3. **npyscreen**
- **Pros**: Mature, widget-based
- **Cons**: Older API, less modern, limited styling
- **Best for**: Legacy applications

### 4. **urwid**
- **Pros**: Mature, flexible layout system
- **Cons**: Complex API, less intuitive than Textual
- **Best for**: Complex layouts, but Textual is easier

## Recommendation

**Migrate to Textual** for the following reasons:

1. **Active Development**: Actively maintained by Rich team
2. **Modern Python**: Uses modern Python features (async, type hints)
3. **Better DX**: Much easier to build complex UIs
4. **Modal Support**: Built-in modal dialog system
5. **Documentation**: Excellent documentation and examples
6. **Community**: Growing community, used by many projects

## Implementation Strategy

1. **Phase 1**: Keep prompt_toolkit, add Textual as optional dependency
2. **Phase 2**: Create Textual version of one pane (e.g., conditions pane)
3. **Phase 3**: Migrate remaining panes
4. **Phase 4**: Replace prompt_toolkit entirely

## Resources

- **Textual Documentation**: https://textual.textualize.io/
- **Textual Examples**: https://github.com/Textualize/textual/tree/main/examples
- **Textual GitHub**: https://github.com/Textualize/textual

