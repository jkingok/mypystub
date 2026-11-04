# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "toga",
#     "certifi",
# ]
# ///
# RSS / Atom reader for MyPyStub.
#
# Flow: enter a feed URL -> list of items -> tap an item -> WebView of its content.
# Stacks onto the running MyPyStub window and holds the script open with a
# threading.Event until Back returns to the launcher. Standard library for
# fetching and parsing; certifi supplies the CA bundle that iOS lacks.
import ssl
import threading
import urllib.request
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import toga
from toga.style import Pack

ATOM = "{http://www.w3.org/2005/Atom}"


def make_ssl_context():
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def text_of(element, *names):
    """Return the text of the first matching child tag, trying each name."""
    for name in names:
        child = element.find(name)
        if child is not None and child.text:
            return child.text.strip()
    return ""


def parse_feed(xml_bytes):
    """Return a list of SimpleNamespace items from an RSS 2.0 or Atom feed."""
    root = ET.fromstring(xml_bytes)
    items = []

    # RSS 2.0: <rss><channel><item>...
    for item in root.iter("item"):
        items.append(
            SimpleNamespace(
                title=text_of(item, "title") or "(untitled)",
                subtitle=text_of(item, "pubDate"),
                link=text_of(item, "link"),
                html=text_of(item, "description")
                or text_of(item, "{http://purl.org/rss/1.0/modules/content/}encoded"),
            )
        )

    # Atom: <feed><entry>...
    for entry in root.iter(ATOM + "entry"):
        link_el = entry.find(ATOM + "link")
        items.append(
            SimpleNamespace(
                title=text_of(entry, ATOM + "title") or "(untitled)",
                subtitle=text_of(entry, ATOM + "updated", ATOM + "published"),
                link=link_el.get("href", "") if link_el is not None else "",
                html=text_of(entry, ATOM + "content", ATOM + "summary"),
            )
        )

    return items


def fetch_feed(url):
    request = urllib.request.Request(url, headers={"User-Agent": "MyPyStub-RSS/1.0"})
    with urllib.request.urlopen(
        request, timeout=15, context=make_ssl_context()
    ) as response:
        return parse_feed(response.read())


def build_url_view(on_load, on_back):
    """First view: ask for the feed URL. on_back returns to the launcher."""
    url_input = toga.TextInput(
        placeholder="https://example.com/feed.xml",
        value="https://pythoninsider.blogspot.com/feeds/posts/default",
        style=Pack(flex=1),
    )
    status = toga.Label("Enter a feed URL", style=Pack(padding_top=10))
    load = toga.Button("Load feed", on_press=lambda w: on_load(url_input.value, status))
    back = toga.Button("Back", on_press=lambda w: on_back(), style=Pack(padding_top=10))
    return toga.Box(
        children=[
            toga.Label("RSS reader", style=Pack(font_weight="bold", padding_bottom=10)),
            url_input,
            load,
            status,
            back,
        ],
        style=Pack(direction="column", padding=20, flex=1),
    )


def build_list_view(items, on_select, on_back):
    """Second view: the items as a DetailedList."""

    # DetailedList gives back its own Row wrapper on selection, not the object
    # we passed in, so match the selection back to our item by title and date.
    def handle_select(widget):
        row = widget.selection
        if row is None:
            return
        match = next(
            (i for i in items if i.title == row.title and i.subtitle == row.subtitle),
            None,
        )
        if match is not None:
            on_select(match)

    detailed = toga.DetailedList(
        data=[{"title": i.title, "subtitle": i.subtitle} for i in items],
        on_select=handle_select,
        style=Pack(flex=1),
    )
    back = toga.Button("Back", on_press=lambda w: on_back(), style=Pack(padding_top=10))
    return toga.Box(
        children=[detailed, back],
        style=Pack(direction="column", padding=10, flex=1),
    )


def build_detail_view(item, on_back):
    """Third view: one item's content in a WebView."""
    web = toga.WebView(style=Pack(flex=1))
    body = item.html or "<p>No content in this feed item.</p>"
    if item.link:
        body += f'<p><a href="{item.link}">Open original</a></p>'
    web.set_content(
        "",
        f"<html><body style='font-family:-apple-system'>"
        f"<h2>{item.title}</h2><p>{item.subtitle}</p>{body}</body></html>",
    )
    back = toga.Button(
        "Back to list", on_press=lambda w: on_back(), style=Pack(padding_top=10)
    )
    return toga.Box(
        children=[web, back],
        style=Pack(direction="column", padding=10, flex=1),
    )


def startup_into(app, ev):
    """Runs on the app's loop: push the reader onto the main window."""
    window = app.main_window
    if window.content:
        if not hasattr(window, "content_stack"):
            window.content_stack = []
        window.content_stack.append((window.title, window.content))
    window.title = "RSS Reader"

    items_cache = {"items": []}

    def back_to_launcher():
        type(app).unstack_from(app)
        ev.set()

    def show_url():
        window.content = build_url_view(on_load, on_back=back_to_launcher)

    def show_list(items):
        items_cache["items"] = items
        window.content = build_list_view(items, on_select=show_detail, on_back=show_url)

    def show_detail(item):
        window.content = build_detail_view(
            item, on_back=lambda: show_list(items_cache["items"])
        )

    def on_load(url, status):
        status.text = "Loading..."

        def worker():
            try:
                items = fetch_feed(url.strip())
                if not items:
                    raise ValueError("No items found. Is this an RSS or Atom feed?")
                app.loop.call_soon_threadsafe(show_list, items)
            except Exception as err:  # noqa: BLE001
                message = f"Failed: {err}"
                app.loop.call_soon_threadsafe(lambda: setattr(status, "text", message))

        threading.Thread(target=worker, daemon=True).start()

    show_url()
    if not window.visible:
        window.show()


def main():
    app = toga.App.app
    if app:
        # Running inside MyPyStub: stack onto its loop, then hold this script
        # open until Back returns to the launcher.
        ev = threading.Event()
        if app.loop:
            app.loop.call_soon(lambda: startup_into(app, ev))
        else:
            startup_into(app, ev)
        ev.wait()
    else:
        print(
            "RSS reader: run this from MyPyStub, or add a standalone start-up like mpg_to_l100km.py."
        )


# Do NOT call main() at module level: MyPyStub's launcher calls main() itself.
if __name__ == "__main__":
    main()
