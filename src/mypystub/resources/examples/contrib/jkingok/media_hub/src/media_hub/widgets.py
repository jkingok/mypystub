import asyncio
from pathlib import Path

import toga


class LabelledDate(toga.Box):
    def __init__(self, label_text, value_text=None, callback=None, id=None):
        super().__init__(
            direction="row",
            align_items="center",
            children=[
                toga.Label(label_text + ": "),
                toga.DateInput(id=id, value=value_text, flex=1, on_change=callback),
            ],
        )


class LabelledNumber(toga.Box):
    def __init__(self, label_text, value_num=0, callback=None, readonly=False, id=None):
        super().__init__(
            direction="row",
            align_items="center",
            children=[
                toga.Label(label_text + ": "),
                toga.NumberInput(
                    id=id,
                    value=value_num,
                    flex=1,
                    on_change=callback,
                    readonly=readonly,
                ),
            ],
        )


class LabelledSelection(toga.Box):
    def __init__(
        self, label_text, value_text="", value_list=None, callback=None, id=None
    ):
        value_list = [] if value_list is None else value_list
        super().__init__(
            direction="row",
            align_items="center",
            children=[
                toga.Label(label_text + ": "),
                toga.Selection(
                    id=id,
                    items=value_list,
                    value=value_text,
                    flex=1,
                    on_change=callback,
                ),
            ],
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
        super().__init__(
            direction="column" if multiline else "row",
            align_items="start" if multiline else "center",
            children=[
                toga.Label(label_text + ": "),
                toga.MultilineTextInput(
                    id=id,
                    value=value_text,
                    flex=1,
                    on_change=callback,
                    readonly=readonly,
                )
                if multiline
                else toga.TextInput(
                    id=id,
                    value=value_text,
                    flex=1,
                    on_change=callback,
                    on_confirm=confirm,
                    readonly=readonly,
                ),
            ],
            **kwargs,
        )


class StackContainer(toga.Box):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stack = []

    def push(self, new_children):
        self.stack.append(list(self.children))
        self.clear()
        self.add(new_children)

    def pop(self):
        if self.stack:
            new_children = self.stack.pop()
            self.clear()
            self.add(*new_children)


class GenericUtils:
    def info_task(w, title, text):
        asyncio.create_task(w.app.main_window.dialog(toga.InfoDialog(title, text)))  # pyright: ignore[reportAttributeAccessIssue]


class PlatformUtils(GenericUtils):
    def close_keyboard(widget):
        pass

    def open_share_sheet(w, html_file_path):
        pass


if toga.platform.current_platform == "iOS":  # pyright: ignore[reportAttributeAccessIssue]
    from rubicon.objc import (  # pyright: ignore[reportMissingImports]
        NSMakeRect,
        ObjCClass,
    )
    from toga_iOS.libs import (  # pyright: ignore[reportMissingImports]
        NSURL,
        NSMutableArray,
    )

    # UIKit constants. A form sheet is full width on iPhone and a centred card on
    # iPad; left to itself, iOS 26 shows the share sheet as a small corner panel.
    UIModalPresentationFormSheet = 2  # UIModalPresentationStyle.formSheet
    UIPopoverArrowDirectionDown = 2  # UIPopoverArrowDirection.down

    # toga_iOS doesn't declare this one
    UIActivityViewController = ObjCClass("UIActivityViewController")

    class IOSUtils(PlatformUtils):
        def close_keyboard(widget):
            """Triggered when the user presses 'Return' or 'Done' on the iPad keyboard."""
            # Dismiss the keyboard by resigning First Responder status
            try:
                # Check if we are running on iOS/iPadOS via the native implementation handle
                if hasattr(widget, "_impl") and hasattr(widget._impl, "native"):  # pyright: ignore[reportAttributeAccessIssue]
                    native_textfield = widget._impl.native  # pyright: ignore[reportAttributeAccessIssue]

                    # Fire the native UIKit selector to lower the keyboard
                    native_textfield.resignFirstResponder()
                    print("[UIKit] Keyboard dismissed via resignFirstResponder.")
            except Exception as e:  # noqa: BLE001 (desktop runners have no UIKit)
                # Graceful fallback for macOS/Windows desktop development runners
                print(f"[Platform Fallback] Could not reach native interface: {e}")

        def open_share_sheet(w, html_file_path: str):
            """
            Opens the iOS native share sheet for a specific HTML file.

            :param w: The active Toga widget instance initiating the share.
            :param html_file_path: Absolute string path to the local HTML file.
            """
            # 1. Ensure the file path exists and convert it into a native file URL
            absolute_path = str(Path(html_file_path).resolve())
            file_url = NSURL.fileURLWithPath_(absolute_path)

            # 2. Add the URL asset into an Objective-C array of items to share
            share_items = NSMutableArray.alloc().init()
            share_items.addObject_(file_url)

            # 3. Initialize the native UIActivityViewController
            # Pass None for custom applicationActivities to use standard system defaults
            activity_vc = UIActivityViewController.alloc().initWithActivityItems(
                share_items, applicationActivities=None
            )

            # 4. Grab the native UIViewController backing your Toga Window
            presenting_vc = w.app.main_window._impl.native.rootViewController  # pyright: ignore[reportAttributeAccessIssue]

            # 5. A form sheet: full width on iPhone, a centred card on iPad.
            # Left to itself, iOS 26 shows a small panel in the corner.
            activity_vc.modalPresentationStyle = UIModalPresentationFormSheet
            # rubicon reads this as a method (UIKit declares it in a category),
            # so call it. If iOS still uses a popover, point it at a small spot
            # at the bottom centre: without a source view an iPad ends the app.
            popover = activity_vc.popoverPresentationController()
            if popover is not None:
                view = presenting_vc.view
                size = view.bounds.size
                popover.sourceView = view
                popover.sourceRect = NSMakeRect(
                    size.width / 2, max(size.height - 1, 0), 0, 0
                )
                popover.permittedArrowDirections = UIPopoverArrowDirectionDown

            # 6. Present the share sheet asynchronously over the top of the interface
            presenting_vc.presentViewController(
                activity_vc, animated=True, completion=None
            )

    Utils = IOSUtils

else:
    Utils = PlatformUtils
