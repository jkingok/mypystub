from dataclasses import dataclass

# Optimized to w342 resolution size limits
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w342"


@dataclass
class MediaMatch:
    tmdb_id: int = 0
    media_type: str = "unknown"
    title: str = ""
    release_date: str | None = None
    overview: str = ""
    poster_path: str | None = None
    subtitle: str = ""  # Captures local custom notations (e.g., Season 1)

    @property
    def poster_url(self) -> str | None:
        if self.poster_path and not self.poster_path.startswith("data:"):
            return f"{TMDB_IMAGE_BASE_URL}{self.poster_path}"
        return None
