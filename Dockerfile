# Single-stage is fine for a pure-Python app: psycopg[binary] ships its own
# libpq, so there is nothing to compile and no build toolchain to discard.
FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies are copied and installed before the source so that editing code
# does not invalidate the (slow) pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The uid only matters in dev, where the source tree is bind-mounted and files
# written into it (collectstatic, migrations) must stay editable on the host.
# 1000 is the typical first user; set APP_UID in .env where it differs.
ARG APP_UID=1000
RUN useradd --create-home --uid ${APP_UID} app && chown -R app:app /app
USER app

# Static files are baked into the published image, where WhiteNoise serves
# them. collectstatic never reads the key, but settings refuse to load without one.
RUN DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput

# What the page footer and /healthz report. CI passes the release version and
# commit when it publishes; local builds keep "dev". Declared after every
# filesystem step, so a new version never invalidates the cached layers.
ARG APP_VERSION=dev
ARG GIT_COMMIT=
ENV APP_VERSION=${APP_VERSION} \
    GIT_COMMIT=${GIT_COMMIT}

EXPOSE 8000

# The production path. Migrating here rather than in an entrypoint means
# one-off commands (`run web python manage.py test`) skip it. Dev overrides
# this with runserver in compose.override.yaml. createcachetable makes the
# cache table allauth's rate limits live in; it does nothing once it exists.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py createcachetable && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3"]
