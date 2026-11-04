# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "toga",
#     "certifi",
# ]
# ///
# Place explorer v2 for MyPyStub.
#
# Layout: search box on top, native map in the middle (starts on your current
# location), weather card below. Search results appear as pins on the map,
# the map zooms out to fit them, and tapping a pin updates the weather.
#
# Services (free, no API key):
#   - OpenStreetMap Nominatim: place search (one request per tap)
#   - Open-Meteo: current weather
#
# Stacks onto the running MyPyStub window and holds the script open until
# Back returns to the launcher. Also runs standalone (e.g. desktop).
import html
import json
import math
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

# Used when the device location is unavailable or permission is refused.
DEFAULT_LAT, DEFAULT_LON = -31.9505, 115.8605
DEFAULT_ZOOM = 12

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


# ---------- network helpers (plain Python, no Toga) ----------


def make_ssl_context():
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def get_json(url, params):
    full_url = url + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        full_url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(
        request, timeout=15, context=make_ssl_context()
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def search_places(query):
    """Up to six places matching the query. Titles are numbered so they stay unique."""
    data = get_json(NOMINATIM_URL, {"q": query, "format": "json", "limit": 6})
    places = []
    for index, item in enumerate(data, start=1):
        display = item.get("display_name", "")
        name = item.get("name") or display.split(",")[0]
        places.append(
            SimpleNamespace(
                title=f"{index}. {name}",
                name=display,
                subtitle=display[:90],
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


def weather_html(place, weather=None, error=None, loading=False):
    name = html.escape(place.name)
    if loading:
        body = "<p>Loading weather...</p>"
    elif error:
        body = f"<p>Weather unavailable: {html.escape(str(error))}</p>"
    else:
        temp = "unknown" if weather.temperature is None else f"{weather.temperature} °C"  # pyright: ignore[reportOptionalMemberAccess]
        wind = "unknown" if weather.wind is None else f"{weather.wind} km/h"  # pyright: ignore[reportOptionalMemberAccess]
        body = (
            f"<p><b>{html.escape(weather.description)}</b></p>"  # pyright: ignore[reportOptionalMemberAccess]
            f"<p>Temperature: {temp}<br>Wind: {wind}<br>"
            f"<small>As of {html.escape(weather.time)}</small></p>"  # pyright: ignore[reportOptionalMemberAccess]
        )
    return (
        "<html><body style='font-family:-apple-system;padding:8px'>"
        f"<h3>{name}</h3>{body}"
        f"<p><a href='https://www.openstreetmap.org/?mlat={place.lat}&mlon={place.lon}"
        f"#map=12/{place.lat}/{place.lon}'>Open in OpenStreetMap</a></p>"
        "<p style='color:#888;font-size:12px'>Weather: Open-Meteo. "
        "Map data: OpenStreetMap contributors.</p>"
        "</body></html>"
    )


def fit_view(points):
    """Return (centre_lat, centre_lon, zoom) that should show every point."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    centre = ((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)
    # Visible span at zoom z is roughly 360 / 2**z degrees of longitude.
    # The latitude span is doubled because the map is taller than it is wide,
    # and one extra step out leaves a margin around the outermost pins.
    span = max((max(lats) - min(lats)) * 2, max(lons) - min(lons), 0.005)
    zoom = int(math.log2(360 / span)) - 1
    return centre[0], centre[1], max(2, min(DEFAULT_ZOOM + 1, zoom))


def point_of(latlng):
    """Accept a toga.LatLng (attributes) or a plain (lat, lon) pair."""
    try:
        return latlng.latitude, latlng.longitude
    except AttributeError:
        return latlng[0], latlng[1]


# ---------- the explorer (Toga UI) ----------


class Explorer:
    def __init__(self, app, loop, on_exit):
        self.app = app
        self.loop = loop
        self.on_exit = on_exit
        self.me = None  # SimpleNamespace for the device location, once known
        self.results = []  # search results currently shown as pins
        self.places = {}  # title -> place, for pin lookups
        self.weather_request = 0  # guards against stale weather replies

        fallback = SimpleNamespace(
            title="Default location",
            name="Perth, Western Australia (default)",
            subtitle="",
            lat=DEFAULT_LAT,
            lon=DEFAULT_LON,
        )
        self.fallback = fallback

        self.search_input = toga.TextInput(
            placeholder="Search for a place", style=Pack(flex=1)
        )
        self.search_button = toga.Button(
            "Search", on_press=self.on_search_press, style=Pack(padding_left=5)
        )
        self.status = toga.Label("Finding your location...", style=Pack(padding=5))

        self.map = toga.MapView(
            location=(DEFAULT_LAT, DEFAULT_LON),
            zoom=DEFAULT_ZOOM,
            on_select=self.on_pin_select,
            style=Pack(flex=3),
        )
        self.card = toga.WebView(style=Pack(flex=2))
        self.card.set_content("", weather_html(fallback, loading=True))

        self.my_location_button = toga.Button(
            "My location",
            on_press=self.on_my_location_press,
            style=Pack(flex=1, padding=5),
        )
        self.back_button = toga.Button(
            "Back", on_press=lambda w: self.on_exit(), style=Pack(flex=1, padding=5)
        )

        search_row = toga.Box(
            children=[self.search_input, self.search_button],
            style=Pack(direction="row", padding=5),
        )
        buttons = toga.Box(
            children=[self.my_location_button, self.back_button],
            style=Pack(direction="row", padding=5),
        )
        self.root = toga.Box(
            children=[search_row, self.status, self.map, self.card, buttons],
            style=Pack(direction="column", flex=1),
        )

    # -- helpers that run on the app loop --

    def set_status(self, text):
        self.status.text = text

    def refresh_pins(self):
        self.map.pins.clear()
        if self.me is not None:
            self.map.pins.add(
                toga.MapPin(
                    (self.me.lat, self.me.lon),
                    title=self.me.title,
                    subtitle=self.me.subtitle,
                )
            )
        for place in self.results:
            self.map.pins.add(
                toga.MapPin(
                    (place.lat, place.lon), title=place.title, subtitle=place.subtitle
                )
            )

    def show_weather(self, place):
        """Fetch weather for a place in the background and show it when ready."""
        self.weather_request += 1
        request_id = self.weather_request
        self.card.set_content("", weather_html(place, loading=True))

        def worker():
            try:
                weather = get_weather(place.lat, place.lon)
                content = weather_html(place, weather=weather)
            except Exception as err:  # noqa: BLE001
                content = weather_html(place, error=err)
            self.loop.call_soon_threadsafe(self._apply_weather, request_id, content)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_weather(self, request_id, content):
        # Ignore replies for pins that were tapped before this one.
        if request_id == self.weather_request:
            self.card.set_content("", content)

    def recentre(self, lat, lon, zoom=DEFAULT_ZOOM):
        self.map.location = (lat, lon)
        self.map.zoom = zoom

    # -- location --

    async def locate(self):
        """Ask for the device location. Falls back to the default if unavailable."""
        try:
            location = self.app.location
            if not location.has_permission:
                await location.request_permission()
            if not location.has_permission:
                raise PermissionError("location permission not granted")
            point = await location.current_location()
            lat, lon = point_of(point)
            self.me = SimpleNamespace(
                title="You are here",
                name="Your current location",
                subtitle=f"{lat:.4f}, {lon:.4f}",
                lat=lat,
                lon=lon,
            )
            self.recentre(lat, lon)
            self.set_status("Showing your current location")
        except Exception as err:  # noqa: BLE001
            self.me = None
            self.recentre(self.fallback.lat, self.fallback.lon)
            self.set_status(f"Using default location: {err}")
        self.refresh_pins()
        self.show_weather(self.me or self.fallback)

    def start_locate(self):
        self.app.loop.create_task(self.locate())

    def on_my_location_press(self, widget):
        if self.me is None:
            self.set_status("Finding your location...")
            self.start_locate()
            return
        self.recentre(self.me.lat, self.me.lon)
        self.refresh_pins()
        self.show_weather(self.me)

    # -- search --

    def on_search_press(self, widget):
        query = self.search_input.value.strip()
        if not query:
            self.set_status("Enter a place name")
            return
        self.set_status("Searching...")

        def worker():
            try:
                places = search_places(query)
                if not places:
                    self.loop.call_soon_threadsafe(self.set_status, "No places found")
                    return
                self.loop.call_soon_threadsafe(self.show_results, places)
            except Exception as err:  # noqa: BLE001
                self.loop.call_soon_threadsafe(self.set_status, f"Search failed: {err}")

        threading.Thread(target=worker, daemon=True).start()

    def show_results(self, places):
        self.results = places
        self.places = {p.title: p for p in places}
        if self.me is not None:
            self.places[self.me.title] = self.me
        self.refresh_pins()

        lat, lon, zoom = fit_view([(p.lat, p.lon) for p in places])
        self.recentre(lat, lon, zoom)
        self.set_status(f"{len(places)} places found. Tap a pin for its weather.")
        self.show_weather(places[0])

    def on_pin_select(self, widget, *, pin, **kwargs):
        place = self.places.get(pin.title)
        if place is not None:
            self.show_weather(place)


# ---------- MyPyStub integration ----------


def open_explorer(app, window, on_exit):
    explorer = Explorer(app, app.loop, on_exit)
    window.title = "Place Explorer"
    window.content = explorer.root
    explorer.start_locate()
    return explorer


def startup_into(app, ev):
    """Runs on the app's loop: push the explorer onto the main window."""
    window = app.main_window
    if window.content:
        if not hasattr(window, "content_stack"):
            window.content_stack = []
        window.content_stack.append((window.title, window.content))

    def leave():
        type(app).unstack_from(app)
        ev.set()

    open_explorer(app, window, leave)
    if not window.visible:
        window.show()


def standalone_startup(app):
    """Used when there is no host app: this script owns the whole Toga app."""
    app.main_window = toga.MainWindow(title="Place Explorer")
    open_explorer(app, app.main_window, app.exit)
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
        toga.App(
            "Place Explorer",
            "com.example.placeexplorer",
            startup=standalone_startup,  # pyright: ignore[reportArgumentType]
        ).main_loop()


# Do NOT call main() at module level: MyPyStub's launcher calls main() itself.
if __name__ == "__main__":
    main()
