"""Small widgets the launcher builds its screens from."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import toga


def refresh_on_new_width(container: Any, refresh: Callable[[], None]) -> None:
    """Call `refresh` when a native container gets a new width.

    A scroll view in a tab that hasn't been shown lays its content out before it
    has a width, and Toga's refreshes on showing the tab can run before the
    width arrives too. Nothing lays the content out after that, so it stays at
    its minimum width: flex can't help, as the content's own width is what's
    too small. Waiting for the native layout, not a timer, also covers rotation.
    Only a change of width refreshes, as a refresh causes a native layout.
    """
    seen = 0.0

    def laid_out(_container: Any) -> None:
        nonlocal seen
        width = container.width
        if width and width != seen:
            seen = width
            refresh()

    container.on_native_layout = laid_out


class LabelledProgress(toga.Box):
    def __init__(self, **kwargs: Any) -> None:
        self.bar = toga.ProgressBar(flex=1)
        self.text = toga.Label("")
        super().__init__(direction="row", children=[self.bar, self.text], **kwargs)

    def start(self, limit: int = 0) -> None:
        self.bar.max = limit if limit > 0 else None
        self.bar.start()
        self.update(0)

    def update(self, value: int) -> None:
        if self.bar.max:
            if self.bar.max == 100:
                self.text.text = f"{value}%"
            else:
                self.text.text = f"{value}/{self.bar.max}"
        else:
            self.text.text = ""
        self.bar.value = value

    def stop(self) -> None:
        if self.bar.max:
            self.update(int(self.bar.max))
        self.bar.stop()


class LabelledActivity(toga.Box):
    def __init__(self, **kwargs) -> None:
        self.activity = toga.ActivityIndicator()
        self.text = toga.Label("", flex=1)
        super().__init__(direction="row", children=[self.activity, self.text], **kwargs)

    def update(self, value: str = "", on: bool = True) -> None:
        self.activity.start() if on else self.activity.stop()
        self.text.text = value


class NotAnOptionContainer(toga.Box):
    """A row of tab buttons standing in for OptionContainer on iPad.

    toga-iOS's OptionContainer becomes iPadOS's floating tab bar, but the tabs'
    content isn't laid out below it: the list's first row hides under the bar,
    and Help and Setup come out blank (checked on iPadOS 27, #112). So iPad
    gets this instead. It looks like a tab bar: each button has its tab's
    icon, and the selected tab is bold in the accent colour while the others
    are grey.
    """

    # Points: a tab bar icon's size, and room for an iPad window's corner grip
    ICON_SIZE = 24
    RESIZE_HANDLE = 24
    UNSELECTED = "gray"

    class CurrentTab:
        """The selected tab, shaped like OptionContainer's (``.text``)."""

        def __init__(self, text: str) -> None:
            """Name the selected tab."""
            self.text = text

    def __init__(
        self,
        content: Sequence[tuple[str, toga.Widget, Path | None]],
        on_select: Callable[[toga.Widget], None] | None = None,
        **kwargs: Any,
    ) -> None:
        """Build the row from OptionContainer-style (title, content, icon) tabs."""
        self.content = list(content)
        self.on_selected = on_select
        self.icons: dict[str, toga.Icon] = {}
        self.buttons = [self.tab_button(title, icon) for title, _, icon in self.content]
        self.tab_row = toga.Row(
            children=list(self.buttons),
            margin_right=self.RESIZE_HANDLE,
            margin_bottom=4,
        )
        super().__init__(
            direction="column",
            children=[toga.Column(flex=1), self.tab_row],
            **kwargs,
        )
        self.swap_in_name(self.content[0][0])

    def tab_button(self, title: str, icon_path: Path | None) -> toga.Button:
        """One tab's button, remembering its icon if the file exists.

        Toga won't put both text and an icon on a button, so the icon is
        kept here and drawn beside the title natively (see _show_icon).
        """
        button = toga.Button(title, on_press=self.swap_in, flex=1)
        if icon_path is not None and Path(icon_path).exists():
            self.icons[title] = toga.Icon(icon_path)
        return button

    def show_selected(self, title: str) -> None:
        """Mark the selected tab: bold in the accent colour; others grey."""
        for button in self.buttons:
            selected = button.text == title
            # Tint first: toga-iOS draws a reset title colour in the tint
            self._show_icon(button, selected)
            button.style.font_weight = "bold" if selected else "normal"
            if selected:
                del button.style.color  # the accent colour, as Toga draws it
            else:
                button.style.color = self.UNSELECTED

    def _show_icon(self, button: toga.Button, selected: bool) -> None:
        """On iOS, draw the tab's icon beside its title, tinted like it.

        The icons are black line art, which would vanish in dark mode, so each
        is drawn as a template at tab bar size: the accent colour when
        selected, grey otherwise, and dimmed by UIKit when disabled.
        """
        if sys.platform != "ios":
            return
        from toga_iOS.libs import UIColor, UIControlStateNormal

        icon = self.icons.get(str(button.text))
        if icon is None:
            return
        native = button._impl.native
        image = icon._impl._as_size(self.ICON_SIZE).imageWithRenderingMode(
            2  # UIImageRenderingModeAlwaysTemplate
        )
        native.setImage(image, forState=UIControlStateNormal)
        # The same grey as the title (UNSELECTED); None inherits the accent
        native.tintColor = None if selected else UIColor.grayColor

    def swap_in_name(self, t: str) -> None:
        """Show the tab titled `t`, and report the change."""
        for tab in self.content:
            if tab[0] == t:
                tab[1].style.flex = 1
                self.replace(self.children[0], tab[1])
                self._current_tab = NotAnOptionContainer.CurrentTab(t)
                self.show_selected(t)
                if self.on_selected:
                    self.on_selected(self)
                break

    def swap_in(self, w: toga.Button, **kwargs: Any) -> None:
        """A tab button was pressed."""
        self.swap_in_name(str(w.text))

    @property
    def current_tab(self) -> CurrentTab:
        """The selected tab."""
        return self._current_tab

    @current_tab.setter
    def current_tab(self, value: str) -> None:
        self.swap_in_name(value)


class LabelledSelection(toga.Box):
    """
    Toga Box combining a text Label and Selection dropdown widget.

    :param label_text: Label text prefix.
    :type label_text: str
    :param value_text: Initially selected item value.
    :type value_text: str
    :param value_list: List of available selection items.
    :type value_list: list
    :param callback: Change event callback handler.
    :type callback: callable
    :param id: Widget identifier.
    :type id: str
    """

    def __init__(self, label_text: str, **kwargs):
        self.selection = toga.Selection(flex=1, **kwargs)
        super().__init__(
            direction="row",
            align_items="center",
            children=[
                toga.Label(label_text + ": "),
                self.selection,
            ],
        )

    @property
    def value(self):
        return self.selection.value
