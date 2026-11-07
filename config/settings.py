import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# No fallback value: an app that holds a payment ledger should fail to boot
# rather than quietly run on a default signing key.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

# "development" gives the PWA its own icons, name and colour, so an installed dev
# build can't be mistaken for production. compose.override.yaml sets it; the
# published image defaults to production. Kept apart from DEBUG, which is about
# error pages, not which instance this is.
ENVIRONMENT = os.environ.get("PLANFC_ENVIRONMENT", "production")
if ENVIRONMENT not in ("production", "development"):
    raise ImproperlyConfigured(f"PLANFC_ENVIRONMENT must be production or development, not {ENVIRONMENT!r}")

# Baked into release images by CI (see the Dockerfile); local builds say "dev".
APP_VERSION = os.environ.get("APP_VERSION", "dev")
GIT_COMMIT = os.environ.get("GIT_COMMIT", "")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "http://localhost:8080")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    # Before allauth, so its templates override allauth's (the layout, the
    # form elements and the logout page).
    "accounts",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    # Installed unconditionally; each only appears on the sign-in page once
    # its credentials are set below.
    "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.apple",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Directly after SecurityMiddleware, as WhiteNoise requires.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "accounts.middleware.PrivatePagesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.deployment",
                "accounts.context_processors.member",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "planfc"),
        "USER": os.environ.get("POSTGRES_USER", "planfc"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Chicago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# In the database rather than per process: allauth keeps its login and signup
# rate limits in the cache, and a per-process cache would give every gunicorn
# worker its own allowance. The table comes from `createcachetable`, which
# runs at startup beside `migrate` (the test runner makes its own).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}

# Behind Caddy, so Django learns the original scheme from the proxy rather than
# from the (plain HTTP) connection it actually receives.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Set once the site is served over HTTPS (a real domain, or a tunnel).
# Browsers never send a Secure cookie over plain HTTP, so turning this on for
# http://localhost:8080 makes signing in impossible. Leaving it off on a real
# domain lets a session cookie travel in the clear.
HTTPS = os.environ.get("DJANGO_HTTPS", "0") == "1"
SESSION_COOKIE_SECURE = HTTPS
CSRF_COOKIE_SECURE = HTTPS

# --- Accounts (django-allauth) ---------------------------------------------

AUTHENTICATION_BACKENDS = [
    # Usernames, for /admin/ and the superuser that createsuperuser makes.
    "django.contrib.auth.backends.ModelBackend",
    # Email addresses, Google and Apple, for everyone else.
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "index"

# Members sign in with an email address, which must be real: allauth sends a
# confirmation link and won't sign anyone in until it has been followed.
# Names are asked for at sign-up, since a roster of email addresses is no use.
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_SIGNUP_FORM_CLASS = "accounts.forms.SignupForm"
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = "[planFC] "
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https" if HTTPS else "http"

# Staying signed in. There is no "remember me" box: everyone is remembered,
# because an installed app that asks for a password on every launch is one
# nobody opens. The session lasts 180 days from the last request (saving on
# every request is what makes it roll forward), so only a member who stays
# away for half a year has to sign in again.
ACCOUNT_SESSION_REMEMBER = True
SESSION_COOKIE_AGE = 60 * 60 * 24 * 180
SESSION_SAVE_EVERY_REQUEST = True

# Google and Apple confirm the address they hand over, so signing in with
# either needs no confirmation email, and it joins an existing account with
# the same address instead of failing as a duplicate.
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True


def _social_providers():
    """Each provider is configured from the environment and left out, so its
    button never shows, until its credentials are set. docs/ACCOUNTS.md says
    where each value comes from."""
    providers = {}
    if os.environ.get("GOOGLE_CLIENT_ID"):
        providers["google"] = {
            "APPS": [{
                "client_id": os.environ["GOOGLE_CLIENT_ID"],
                "secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
            }],
            "SCOPE": ["profile", "email"],
        }
    if os.environ.get("APPLE_CLIENT_ID"):
        providers["apple"] = {
            "APPS": [{
                # Apple calls these the Services ID, the Key ID and the Team
                # ID; certificate_key is the contents of the .p8 key file.
                "client_id": os.environ["APPLE_CLIENT_ID"],
                "secret": os.environ.get("APPLE_KEY_ID", ""),
                "key": os.environ.get("APPLE_TEAM_ID", ""),
                "settings": {
                    # A .env value is a single line, so the key's line breaks
                    # are written there as a literal \n and restored here.
                    "certificate_key": os.environ.get("APPLE_PRIVATE_KEY", "").replace("\\n", "\n"),
                },
            }],
        }
    return providers


SOCIALACCOUNT_PROVIDERS = _social_providers()

# --- Email -----------------------------------------------------------------

# Without a provider, mail is printed to the web container's log
# (`docker compose logs web`), which is enough to follow a confirmation link
# in development. Production needs a real one: PLAN.md explains why mail sent
# straight from this host lands in spam.
if os.environ.get("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ["EMAIL_HOST"]
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL") or "planFC <noreply@localhost>"

# --- Push notifications ----------------------------------------------------

# Web Push signs every message with this key pair (VAPID). Browsers reject
# messages to a subscription made under a different public key, so the pair
# must stay the same for the life of a deployment. Generate it once with
# `python manage.py generate_vapid_keys`. Until it is set, push is off and the
# profile page says so.
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
# Push services use this address to contact us if our messages cause trouble.
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT") or "mailto:admin@localhost"

# Profile pictures are re-encoded server-side, but the upload itself is
# capped first so a huge file is turned away before Pillow ever reads it.
PROFILE_PICTURE_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
