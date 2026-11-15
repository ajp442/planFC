import os

from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import StaticFilesStorage


class DevStaticFilesStorage(StaticFilesStorage):
    """Development's stand-in for the hashed filenames production gets from
    the manifest storage: each URL carries the file's modification time, so an
    edit changes the URL. Without it /static/js/app.js keeps one URL for ever,
    and the phone's HTTP cache, the service worker's cache and Cloudflare's
    edge (which caches .css and .js for hours on its own initiative) all go
    on serving the copy from before the edit."""

    def url(self, name):
        url = super().url(name)
        path = finders.find(name)
        if not path:
            return url
        try:
            return f"{url}?v={int(os.path.getmtime(path))}"
        except OSError:
            return url
