import datetime as dt
import tempfile
from pathlib import Path

import toga
from markdown import markdown as md
from toga.style import Pack

from . import functions


def close_keyboard(widget):
    """Triggered when the user presses 'Return' or 'Done' on the iPad keyboard."""
    # Dismiss the keyboard by resigning First Responder status
    try:
        # Check if we are running on iOS/iPadOS via the native implementation handle
        if hasattr(widget, "_impl") and hasattr(widget._impl, "native"):
            native_textfield = widget._impl.native

            # Fire the native UIKit selector to lower the keyboard
            native_textfield.resignFirstResponder()
            print("[UIKit] Keyboard dismissed via resignFirstResponder.")
    except Exception as e:  # noqa: BLE001 (desktop runners have no UIKit)
        # Graceful fallback for macOS/Windows desktop development runners
        print(f"[Platform Fallback] Could not reach native interface: {e}")


class LabelledDateTime(toga.Box):
    def __init__(self, label_text, value_datetime=None, callback=None, id=None):
        self.wd = toga.DateInput(
            value=value_datetime.date() if value_datetime else None,
            flex=1,
            on_change=self.update_value,
        )
        self.wt = toga.TimeInput(
            value=value_datetime.time() if value_datetime else None,
            flex=1,
            on_change=self.update_value,
        )
        self.callback = callback
        super().__init__(
            direction="row",
            align_items="center",
            children=[toga.Label(label_text + ": "), self.wd, self.wt],
            id=id,
        )

    @property
    def value(self):
        return dt.datetime.combine(self.wd.value, self.wt.value)  # pyright: ignore[reportAttributeAccessIssue]

    @value.setter
    def value(self, value):
        self.wd = value.date() if value else dt.date.today()
        self.wt = value.time() if value else dt.datetime.now().time()

    def update_value(self, w):
        if self.callback:
            self.callback(self)


class ImagePanel(toga.Box):
    def __init__(self, direction="row", callback=None, **kwargs):
        self.callback = callback
        self.img = toga.ImageView(flex=1)
        self.img_path = None
        super().__init__(
            align_items="center",
            direction=direction,
            children=[
                self.img,
                toga.Box(
                    direction="column" if direction == "row" else "row",
                    children=[
                        toga.Button(
                            "Open",
                            on_press=self.do_open,
                            flex=1 if direction == "column" else 0,
                        ),
                        toga.Button(
                            "Paste",
                            on_press=self.do_paste,
                            flex=1 if direction == "column" else 0,
                        ),
                        toga.Button(
                            "Clear",
                            on_press=self.do_clear,
                            flex=1 if direction == "column" else 0,
                        ),
                    ],
                ),
            ],
            **kwargs,
        )

    def do_paste(self, button):
        with tempfile.NamedTemporaryFile(
            dir=str(Path("~/Documents").expanduser()),
            prefix="logo_",
            suffix=".png",
            delete=False,
        ) as custom_temp:
            print(custom_temp.name)
        # Output will look something like: /tmp/my_toga_app_a7b9x_z.png (on macOS/iOS)
        if functions.save_image_from_pasteboard(custom_temp.name):
            self.img.image = custom_temp.name
            self.img_path = custom_temp.name
            if self.callback:
                self.callback(self)
        else:
            custom_temp.unlink()

    def do_open(self, button):
        pass

    def do_clear(self, button=None):
        self.img.image = None
        self.img_path = None
        if self.callback:
            self.callback(self)

    @property
    def value(self):
        return self.img_path

    def reset(self):
        return self.do_clear()


class LabelledImage(toga.Box):
    def __init__(self, label_text, callback=None):
        self.callback = callback
        self.img = ImagePanel(callback=callback, flex=1)
        super().__init__(
            style=Pack(align_items="center"),
            children=[toga.Label(label_text + ": "), self.img],
        )

    @property
    def value(self):
        return self.img.value


class LabelledSwitch(toga.Switch):
    def __init__(self, label_text, value, callback=None, id=None, **kwargs):
        super().__init__(
            text=label_text + ": ", id=id, on_change=callback, value=value, **kwargs
        )


class LabelledText(toga.Box):
    def __init__(
        self,
        label_text,
        value_text="",
        callback=None,
        confirm=None,
        readonly=False,
        multiline=False,
        id=None,
        **kwargs,
    ):
        self.w = (
            toga.MultilineTextInput(
                id=id, value=value_text, flex=1, on_change=callback, readonly=readonly
            )
            if multiline
            else toga.TextInput(
                id=id,
                value=value_text,
                flex=1,
                on_change=callback,
                on_confirm=lambda w: (  # pyright: ignore[reportArgumentType]
                    close_keyboard(w),
                    confirm(w) if confirm else None,
                ),
                readonly=readonly,
            )
        )
        super().__init__(
            direction="column" if multiline else "row",
            align_items="start" if multiline else "center",
            children=[toga.Label(label_text + ": "), self.w],
            **kwargs,
        )

    @property
    def value(self):
        return self.w.value

    @value.setter
    def value(self, value):
        self.w.value = value


class MarkdownView(toga.WebView):
    def wrap(body):
        return f"""
<html>
    <head>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; line-height: 1.6; padding: 20px; color: #333; }}
            code {{ background-color: #f6f8fa; padding: 2px 4px; border-radius: 3px; font-family: monospace; }}
            pre {{ background-color: #f6f8fa; padding: 16px; overflow: auto; border-radius: 6px; }}
            img {{ max-width: 100%; height: auto; }}
        </style>
    </head>
    <body>
        {body}
    </body>
</html>
"""

    def __init__(self, value="", **kwargs):
        for kw in ["content", "url"]:
            kwargs.pop(kw, None)
        self._value = value
        super().__init__(content=MarkdownView.wrap(md(value)), **kwargs)  # pyright: ignore[reportArgumentType]

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        self.content = MarkdownView.wrap(md(value))  # pyright: ignore[reportArgumentType]


def create_labelled_number(
    label_text, value_num=0, callback=None, readonly=False, id=None
):
    lbl_num = toga.Row(style=Pack(align_items="center"))
    lbl = toga.Label(label_text + ": ")

    num = toga.NumberInput(
        id=id,
        value=value_num,
        style=Pack(flex=1),
        on_change=callback,
        readonly=readonly,
    )

    lbl_num.add(lbl)
    lbl_num.add(num)

    return lbl_num


def create_labelled_options(
    label_text, value_text="", value_list=None, callback=None, id=None
):
    value_list = [] if value_list is None else value_list
    lbl_opt = toga.Row(style=Pack(align_items="center"))
    lbl = toga.Label(label_text + ": ")

    opt = toga.Selection(
        id=id,
        items=value_list,
        value=value_text,
        style=Pack(flex=1),
        on_change=callback,
    )

    lbl_opt.add(lbl)
    lbl_opt.add(opt)

    return lbl_opt


def create_form_field(field_name, field_type, default_value=None, callback=None):
    match field_type:
        case "bool":
            return LabelledSwitch(
                value=default_value, label_text=field_name.capitalize(), id=field_name
            )
        case "datetime":
            return LabelledDateTime(
                label_text=field_name.capitalize(), callback=callback, id=field_name
            )
        case "list":
            return LabelledText(
                label_text=field_name.capitalize(),
                callback=callback,
                value_text=default_value,  # pyright: ignore[reportArgumentType]
                id=field_name,
            )
        case "text":
            return LabelledText(
                label_text=field_name.capitalize(),
                value_text=default_value,  # pyright: ignore[reportArgumentType]
                callback=callback,
                id=field_name,
            )
        case "image":
            return LabelledImage(field_name.capitalize(), callback=callback)
        case _:
            return None


def reset_form_field(field_name, field_type, default_value=None):
    match field_type:
        case "bool":
            toga.App.app.widgets[field_name].value = default_value or False  # pyright: ignore[reportOptionalMemberAccess]
        case "datetime":
            toga.App.app.widgets[field_name].value = (  # pyright: ignore[reportOptionalMemberAccess]
                default_value if default_value else None
            )
        case "list":
            toga.App.app.widgets[field_name].value = (  # pyright: ignore[reportOptionalMemberAccess]
                default_value if default_value else ""
            )
        case "text":
            toga.App.app.widgets[field_name].value = (  # pyright: ignore[reportOptionalMemberAccess]
                default_value if default_value else ""
            )
        case "image":
            pass
