import base64
import collections
import re
import sqlite3
import urllib.parse
from pathlib import Path

import requests

from . import data as d

DB_NAME = "media_manifest.db"

TMDB_URL_REGEX = re.compile(r"themoviedb\.org/(movie|tv)/(\d+)")


class Functions:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            # Create the single instance and cache it on the class
            cls._instance = super().__new__(cls)
            # Initialize flags or containers that only ever happen ONCE
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, paths, settings):
        # __init__ runs EVERY time you call,
        # so guard it to ensure it only initializes once.
        if self._initialized:
            return
        self.settings = settings
        self.data_path = paths.data
        self.this_path = Path(__file__).resolve().parent
        self.db_file = self.data_path / DB_NAME
        self.image_path = self.data_path / "cached_posters"
        self.template_path = self.this_path / "resources" / "templates"
        self.init_db()
        self.image_path.mkdir(exist_ok=True)
        self._initialized = True

    def init_db(self) -> None:
        with sqlite3.connect(self.db_file) as conn:
            # Alter columns smoothly if database already exists
            conn.execute("""
                CREATE TABLE IF NOT EXISTS selection_cache (
                    query_title TEXT PRIMARY KEY, tmdb_id INTEGER, media_type TEXT,
                    title TEXT, release_date TEXT, overview TEXT, poster_path TEXT,
                    subtitle TEXT
                )
            """)
        print("Database ready.")

    def get_cached_selection(self, query_title: str) -> d.MediaMatch | None:
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.execute(
                "SELECT tmdb_id, media_type, title, release_date, overview, poster_path, subtitle FROM selection_cache WHERE query_title = ?",
                (query_title.lower().strip(),),
            )
            row = cursor.fetchone()
        return d.MediaMatch(*row) if row else None

    def save_selection_to_cache(self, query_title: str, media: d.MediaMatch) -> None:
        with sqlite3.connect(self.db_file) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO selection_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    query_title.lower().strip(),
                    media.tmdb_id,
                    media.media_type,
                    media.title,
                    media.release_date,
                    media.overview,
                    media.poster_path,
                    media.subtitle,
                ),
            )

    def delete_selection_from_cache(self, query_title: str) -> None:
        """Deletes a cached selection from the database by its query_title."""
        # Normalise the key exactly how it was saved
        normalised_title = query_title.lower().strip()

        with sqlite3.connect(self.db_file) as conn:
            conn.execute(
                "DELETE FROM selection_cache WHERE query_title = ?", (normalised_title,)
            )

    def map_titles_from_cache(self) -> dict[str, d.MediaMatch]:
        cached_collection = {}
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.execute(
                "SELECT query_title, tmdb_id, media_type, title, release_date, overview, poster_path, subtitle FROM selection_cache"
            )
            for row in cursor.fetchall():
                cached_collection[row[0]] = d.MediaMatch(*row[1:])
        return cached_collection

    def load_titles_from_cache(self) -> list[d.MediaMatch]:
        cached_collection = []
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.execute(
                "SELECT tmdb_id, media_type, title, release_date, overview, poster_path, subtitle FROM selection_cache"
            )
            for row in cursor.fetchall():
                cached_collection.append(d.MediaMatch(*row))
        return cached_collection

    def extract_from_tmdb_url(self, url):
        return self.TMDB_URL_REGEX.search(url)  # pyright: ignore[reportAttributeAccessIssue]

    def fetch_single_tmdb_id(
        self, tmdb_id: int, media_type: str
    ) -> d.MediaMatch | None:
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}"
        tmdb_api_key = self.settings.get("tmdb_api_key")
        if not tmdb_api_key:
            return None
        params = {"api_key": tmdb_api_key, "language": "en-AU"}
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return d.MediaMatch(
                    tmdb_id=data["id"],
                    media_type=media_type,
                    title=data.get("title") or data.get("name") or "Unknown",
                    release_date=data.get("release_date")
                    or data.get("first_air_date")
                    or "",
                    overview=data.get("overview", ""),
                    poster_path=data.get("poster_path"),
                )
        except Exception as error:  # noqa: BLE001 (any failure means no match)
            print(f"TMDB lookup failed: {error}")
        return None

    def get_base64_poster(self, media: d.MediaMatch) -> str:
        """Checks for explicit placeholder flags or encodes binary files into Data URIs."""
        if media.poster_path == "placeholder":
            svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 750" width="100%" height="100%">
                <rect width="100%" height="100%" fill="#2a2a2a"/>
                <text x="50%" y="45%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="32" font-weight="bold" fill="#666666">NO POSTER</text>
                <text x="50%" y="52%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="20" fill="#444444">Click for details</text>
                </svg>"""
            return f"data:image/svg+xml;base64,{base64.b64encode(svg.encode('utf-8')).decode('utf-8')}"

        if not media.poster_path:
            return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

        local_path = self.paths.data / "cached_posters" / f"{media.tmdb_id}.jpg"  # pyright: ignore[reportAttributeAccessIssue]

        if not local_path.exists() and media.poster_url:
            try:
                resp = requests.get(media.poster_url, timeout=10)
                if resp.status_code == 200:
                    local_path.write_bytes(resp.content)
            except Exception as error:  # noqa: BLE001 (a poster is optional)
                print(f"Poster download failed: {error}")

        if local_path.exists():
            return f"data:image/jpeg;base64,{base64.b64encode(local_path.read_bytes()).decode('utf-8')}"

        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

    def standardise_sort_title(self, title_string: str) -> str:
        """
        Normalises titles for accurate natural alphabetical sorting by:
        1. Converting to lowercase.
        2. Stripping leading article prefixes ('the', 'a', 'an').
        3. Removing punctuation symbols, quotes, and brackets so
           alphanumeric characters dictate the true placement order.
        """
        # 1. Force lowercase and clear padding spaces
        t = title_string.lower().strip()

        # 2. Strip leading article prefixes followed by a space
        t = re.sub(r"^(the|a|an)\s+", "", t)

        # 3. Strip out punctuation marks, single/double quotes, and symbols
        # This leaves only alphanumeric characters and standard space characters
        t = re.sub(r"[^\w\s]", "", t)

        return t

    def generate_offline_responsive_html(
        self,
        media_list: list[d.MediaMatch],
        output_path: str = "../movie_catalog_ios.html",
        page_title: str = "Media Grid Dashboard",
        log_to=print,
    ) -> None:
        template_file = self.template_path / "catalog.html"
        if not template_file.exists():
            log_to("Missing template file resource.")
            return

        html_template = template_file.read_text(encoding="utf-8")

        counts = collections.Counter(item.media_type for item in media_list)
        cards, lightboxes = [], []
        sorted_media_list = sorted(
            media_list, key=lambda item: self.standardise_sort_title(item.title)
        )
        current_letter = None

        for idx, item in enumerate(sorted_media_list):
            sort_title = self.standardise_sort_title(item.title)
            first_char = sort_title[0] if sort_title else "#"
            item_letter = first_char.upper() if first_char.isalpha() else "#"

            if item_letter != current_letter:
                current_letter = item_letter
                # Map number blocks to 'num' so it pairs cleanly with the # anchor link
                anchor_id = "num" if current_letter == "#" else current_letter

                cards.append(f"""
                <div class="alphabet-divider" id="letter-{anchor_id}">
                    <div class="alphabet-divider-content">
                        <h2>{current_letter}</h2>
                        <a href="#catalog-top" class="back-to-top" title="Back to top">↑</a>
                    </div>
                </div>
                """)

            year = item.release_date[:4] if item.release_date else "N/A"
            lightbox_id = f"detail-{idx}"
            base64_src = self.get_base64_poster(item)

            if item.media_type == "unknown":
                encoded_title = urllib.parse.quote(item.title)
                tmdb_url = f"https://www.themoviedb.org/search?query={encoded_title}"
                link_text = "Search TMDB Manually"
            else:
                tmdb_url = (
                    f"https://www.themoviedb.org/{item.media_type}/{item.tmdb_id}"
                )
                link_text = "View on TMDB"

            cards.append(f"""
            <a href="#{lightbox_id}" class="card-wrapper" data-type="{item.media_type}">
                <div class="card">
                    <div class="poster-wrapper"><img class="poster" src="{base64_src}" alt="{item.title}"></div>
                    <div class="info">
                        <div class="title">{item.title}</div>
                        <div class="subtitle">{item.subtitle if item.subtitle else ""}</div>
                        <div class="meta"><span>{year}</span><span class="badge">{item.media_type}</span></div>
                    </div>
                </div>
            </a>""")

            # Ensure this lightbox append code matches the structural update inside your loop:
            lightboxes.append(f"""
                <div id="{lightbox_id}" class="lightbox">
                    <div class="lightbox-content">
                       <a href="#close" class="close-btn">&times;</a>
                    
                        <div class="lightbox-poster-side">
                            <img src="{base64_src}" alt="{item.title}">
                        </div>
                    
                        <div class="lightbox-details-side">
                            <div class="lightbox-header">{item.title}</div>
                            <div class="lightbox-subtitle">{item.subtitle if item.subtitle else ""}</div>
                            <div class="lightbox-meta">
                                <span class="badge" style="margin-right:8px;">{item.media_type}</span><span>{year}</span>
                            </div>
                            <div class="lightbox-overview">{item.overview}</div>
                            <div class="lightbox-actions">
                                <a href="{tmdb_url}" target="_blank" class="tmdb-link">{link_text}</a>
                            </div>
                        </div>
                    
                    </div>
                </div>""")

        output_html = html_template.format(
            page_title=page_title,
            count_all=len(media_list),
            count_movie=counts["movie"],
            count_tv=counts["tv"],
            count_unknown=counts["unknown"],
            cards_html="\n".join(cards),
            lightboxes_html="\n".join(lightboxes),
        )

        Path(output_path).write_text(output_html, encoding="utf-8")
        log_to("✓ Offline responsive catalog file compiled successfully.")
