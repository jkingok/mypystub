import toga
from toga.sources import ListSource


class Model:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            # Create the single instance and cache it on the class
            cls._instance = super().__new__(cls)
            # Initialize flags or containers that only ever happen ONCE
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, paths, fns):
        # __init__ runs EVERY time you call,
        # so guard it to ensure it only initializes once.
        if self._initialized:
            return
        self.fns = fns
        self.cache_path = paths.cache
        self.items_list_source = ListSource(
            accessors=["title", "subtitle", "icon", "index"], data=[]
        )
        self.list_count_label = None
        self.reload_items()
        self._initialized = True

    def reload_items(self, widget=None, row=None):
        self.items_list_source.clear()
        for key, value in self.fns.map_titles_from_cache().items():
            # Safely build a toga.Image if an icon path was specified and exists
            self.items_list_source.append(
                {
                    "title": value.title,
                    "subtitle": value.subtitle,
                    "icon": toga.Image(f)
                    if value.tmdb_id
                    and (
                        f := self.cache_path / f"cached_posters/{value.tmdb_id}.jpg"
                    ).exists()
                    else None,
                    "index": key,
                }
            )
        if self.list_count_label:
            self.list_count_label.text = self.item_count_text()

    def item_count_text(self):
        return f"{len(self.items_list_source)} item(s)"

    def set_list_count_label(self, w):
        self.list_count_label = w
        w.text = self.item_count_text()
        return w

    def add_from_url(self, url):
        return (
            self.fns.fetch_single_tmdb_id(int(m.group(2)), m.group(1))
            if (m := self.fns.extract_from_tmdb_url(url))
            else None
        )

    def save(self, key, values):
        self.fns.save_selection_to_cache(key, values)
        self.fns.get_base64_poster(values)
        # TODO Be able to find and update correct item to avoid full reload
        self.reload_items()

    def delete(self, key):
        self.fns.delete_selection_from_cache(key)
        # TODO Be able to find and update correct item to avoid full reload
        self.reload_items()
