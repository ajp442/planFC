# Single-stage is fine for a pure-Python app: psycopg[binary] ships its own
# libpq, so there is nothing to compile and no build toolchain to discard.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies are copied and installed before the source so that editing code
# does not invalidate the (slow) pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# uid 1000 matches the typical host user, so files written into a bind-mounted
# source tree (collectstatic, migrations) stay editable outside the container.
RUN useradd --create-home --uid 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

# Dev overrides this with runserver in compose.yaml; this is the production path.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
