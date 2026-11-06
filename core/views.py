from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render


def index(request):
    return render(request, "core/index.html", {"db_ok": _database_reachable()})


def healthz(request):
    """Liveness probe that proves the database round-trips, not just that
    Python is running. Suitable for a container healthcheck later. Also says
    which release answered, so an upgrade can be confirmed with curl."""
    ok = _database_reachable()
    return JsonResponse({"status": "ok" if ok else "degraded", "database": ok,
                         "version": settings.APP_VERSION, "commit": settings.GIT_COMMIT},
                        status=200 if ok else 503)


def _database_reachable():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    except Exception:
        return False
