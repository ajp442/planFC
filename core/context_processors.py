from django.conf import settings


def deployment(request):
    """Which instance this is and what it runs, for every template: the page,
    the manifest and the service worker all pick their icons from here."""
    is_dev = settings.ENVIRONMENT == "development"
    return {
        "is_dev": is_dev,
        "app_name": "planFC Dev" if is_dev else "planFC",
        "icon_dir": "icons/dev/" if is_dev else "icons/",
        "theme_color": "#b45309" if is_dev else "#0b6b3a",
        "app_version": settings.APP_VERSION,
        "git_commit": settings.GIT_COMMIT[:7],
    }
