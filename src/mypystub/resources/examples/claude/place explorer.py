# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "toga",
#     "certifi",
# ]
# ///
# Place explorer for MyPyStub. Uses two free services with no API key:
#   - OpenStreetMap Nominatim to search for places by name
#   - Open-Meteo to fetch the current weather at a place
# Shows the place on a native toga.MapView with a pin, and the weather
# in a WebView card. Stacks onto the running MyPyStub window and holds the
# script open until Back returns to the launcher.
#
# Usage policy: Nominatim asks for a meaningful User-Agent and at most one
# request per second. This script makes one request per tap, so that is met.
import html
import json
import ssl
import threading
import urllib.parse
import urllib.request
from types import SimpleNamespace

import toga
from toga.style import Pack

USER_AGENT = "MyPyStub-PlaceExplorer/1.0"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes used by Open-Meteo, reduced to readable text.
WMO_TEXT = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    80: "Rain showers",
    81: "Rain showers",
    82: "Violent showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with hail",
}


def make_ssl_context():
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def get_json(url, params):
    full_url = url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        full_url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(
        request, timeout=15, context=make_ssl_context()
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def search_places(query):
    """Return up to six places matching the query, using Nominatim."""
    data = get_json(NOMINATIM_URL, {"q": query, "format": "json", "limit": 6})
    places = []
    for index, item in enumerate(data, start=1):
        display = item.get("display_name", "")
        name = item.get("name") or display.split(",")[0]
        # The index prefix keeps every title unique, so a DetailedList
        # selection can be matched back to the right place.
        places.append(
            SimpleNamespace(
                title=f"{index}. {name}",
                subtitle=display[:90],
                name=display,
                lat=float(item["lat"]),
                lon=float(item["lon"]),
            )
        )
    return places


def get_weather(lat, lon):
    data = get_json(
        WEATHER_URL,
        {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "current_weather": "true",
        },
    )
    current = data.get("current_weather", {})
    code = current.get("weathercode")
    return SimpleNamespace(
        temperature=current.get("temperature"),
        wind=current.get("windspeed"),
        description=WMO_TEXT.get(code, f"Code {code}"),
        time=current.get("time", ""),
    )


def weather_card(place, weather_text):
    name = html.escape(place.name)
    return (
        "<html><body style='font-family:-apple-system;padding:8px'>"
        f"<h3>{name}</h3>"
        f"<p>{weather_text}</p>"
        f"<p><a href='https://www.openstreetmap.org/?mlat={place.lat}&mlon={place.lon}#map=12/{place.lat}/{place.lon}'>"
        "Open in OpenStreetMap</a></p>"
        "<p style='color:#888;font-size:12px'>Weather: Open-Meteo. Map data: OpenStreetMap contributors.</p>"
        "</body></html>"
    )


def build_search_view(on_search, on_back):
    query_input = toga.TextInput(
        placeholder="Search for a place",
        value="Perth, Australia",
        style=Pack(flex=1),
    )
    status = toga.Label("Enter a place name", style=Pack(padding_top=10))
    search = toga.Button(
        "Search",
        on_press=lambda w: on_search(query_input.value, status),
        style=Pack(padding_top=10),
    )
    back = toga.Button("Back", on_press=lambda w: on_back(), style=Pack(padding_top=10))
    return toga.Box(
        children=[
            toga.Label(
                "Place explorer", style=Pack(font_weight="bold", padding_bottom=10)
            ),
            query_input,
            search,
            status,
            back,
        ],
        style=Pack(direction="column", padding=20, flex=1),
    )


def build_results_view(places, on_select, on_back):
    def handle_select(widget):
        row = widget.selection
        if row is None:
            return
        match = next((p for p in places if p.title == row.title), None)
        if match is not None:
            on_select(match)

    results = toga.DetailedList(
        data=[{"title": p.title, "subtitle": p.subtitle} for p in places],
        on_select=handle_select,
        style=Pack(flex=1),
    )
    back = toga.Button(
        "New search", on_press=lambda w: on_back(), style=Pack(padding_top=10)
    )
    return toga.Box(
        children=[results, back], style=Pack(direction="column", padding=10, flex=1)
    )


def build_place_view(place, on_back_to_results, on_back_to_launcher, loop):
    # Native map with one pin at the place.
    map_view = toga.MapView(
        location=(place.lat, place.lon), zoom=12, style=Pack(flex=3)
    )
    map_view.pins.add(
        toga.MapPin((place.lat, place.lon), title=place.title, subtitle=place.subtitle)
    )

    # Weather card, loaded in the background.
    card = toga.WebView(style=Pack(flex=2))
    card.set_content(
        "",
        "<html><body style='font-family:-apple-system'><p>Loading weather...</p></body></html>",
    )

    def load_weather():
        try:
            weather = get_weather(place.lat, place.lon)
            temp = (
                "unknown"
                if weather.temperature is None
                else f"{weather.temperature} °C"
            )
            wind = "unknown" if weather.wind is None else f"{weather.wind} km/h"
            text = f"<b>{weather.description}</b><br>Temperature: {temp}<br>Wind: {wind}<br>As of {html.escape(weather.time)}"
        except Exception as err:  # noqa: BLE001
            text = f"Weather unavailable: {html.escape(str(err))}"
        content = weather_card(place, text)
        loop.call_soon_threadsafe(card.set_content, "", content)

    threading.Thread(target=load_weather, daemon=True).start()

    back_results = toga.Button(
        "Results", on_press=lambda w: on_back_to_results(), style=Pack(padding_top=5)
    )
    back_launcher = toga.Button(
        "Back", on_press=lambda w: on_back_to_launcher(), style=Pack(padding_top=5)
    )
    buttons = toga.Box(
        children=[back_results, back_launcher], style=Pack(direction="row", padding=5)
    )

    return toga.Box(
        children=[map_view, card, buttons], style=Pack(direction="column", flex=1)
    )


def start_views(window, loop, on_exit):
    """Show the search view and wire up navigation. on_exit leaves the tool."""
    state = {"places": []}

    def show_search():
        window.content = build_search_view(on_search, on_exit)

    def show_results(places):
        state["places"] = places
        window.content = build_results_view(
            places, on_select=show_place, on_back=show_search
        )

    def show_place(place):
        window.content = build_place_view(
            place,
            on_back_to_results=lambda: show_results(state["places"]),
            on_back_to_launcher=on_exit,
            loop=loop,
        )

    def on_search(query, status):
        if not query.strip():
            status.text = "Enter a place name"
            return
        status.text = "Searching..."

        def worker():
            try:
                places = search_places(query.strip())
                if not places:
                    loop.call_soon_threadsafe(
                        setattr, status, "text", "No places found"
                    )
                    return
                loop.call_soon_threadsafe(show_results, places)
            except Exception as err:  # noqa: BLE001
                loop.call_soon_threadsafe(setattr, status, "text", f"Failed: {err}")

        threading.Thread(target=worker, daemon=True).start()

    show_search()


def startup_into(app, ev):
    """Runs on the app's loop: push the explorer onto the main window."""
    window = app.main_window
    if window.content:
        if not hasattr(window, "content_stack"):
            window.content_stack = []
        window.content_stack.append((window.title, window.content))
    window.title = "Place Explorer"

    def leave():
        type(app).unstack_from(app)
        ev.set()

    start_views(window, app.loop, leave)
    if not window.visible:
        window.show()


def standalone_startup(app):
    """Used when there is no host app: this script owns the whole Toga app."""
    app.main_window = toga.MainWindow(title="Place Explorer")
    start_views(app.main_window, app.loop, app.exit)
    app.main_window.show()


def main():
    app = toga.App.app
    if app:
        # Inside MyPyStub: stack onto its loop and hold the script open
        # until Back returns to the launcher.
        ev = threading.Event()
        if app.loop:
            app.loop.call_soon(lambda: startup_into(app, ev))
        else:
            startup_into(app, ev)
        ev.wait()
    else:
        # Standalone (e.g. desktop): start our own Toga App.
        toga.App(
            "Place Explorer",
            "com.example.placeexplorer",
            startup=standalone_startup,  # pyright: ignore[reportArgumentType]
        ).main_loop()


# Do NOT call main() at module level: MyPyStub's launcher calls main() itself.
if __name__ == "__main__":
    main()
