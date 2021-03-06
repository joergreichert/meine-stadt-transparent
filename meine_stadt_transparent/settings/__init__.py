import logging
import os
import warnings
from importlib.util import find_spec

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

from meine_stadt_transparent.settings.env import *
from meine_stadt_transparent.settings.nested import *
from meine_stadt_transparent.settings.security import *

# Mute an irrelevant warning
warnings.filterwarnings("ignore", message="`django-leaflet` is not available.")
# This comes from PGPy with enigmail keys
warnings.filterwarnings(
    "ignore", message=".*does not have the required usage flag EncryptStorage.*"
)

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REAL_HOST = env.str("REAL_HOST")
PRODUCT_NAME = env.str("PRODUCT_NAME", "Meine Stadt Transparent")
SITE_NAME = env.str("SITE_NAME", PRODUCT_NAME)
ABSOLUTE_URI_BASE = env.str("ABSOLUTE_URI_BASE", "https://" + REAL_HOST)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.11/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env.str("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = [REAL_HOST, "127.0.0.1", "localhost"]

ROOT_URLCONF = "meine_stadt_transparent.urls"

WSGI_APPLICATION = "meine_stadt_transparent.wsgi.application"

# forcing request.build_absolute_uri to return https
os.environ["HTTPS"] = "on"

if env.str("MAIL_PROVIDER", "local").lower() == "mailjet":
    ANYMAIL = {
        "MAILJET_API_KEY": env.str("MAILJET_API_KEY"),
        "MAILJET_SECRET_KEY": env.str("MAILJET_SECRET_KEY"),
    }
    EMAIL_BACKEND = "anymail.backends.mailjet.EmailBackend"

DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", "info@" + REAL_HOST)
DEFAULT_FROM_EMAIL_NAME = env.str("DEFAULT_FROM_EMAIL_NAME", SITE_NAME)

# Encrypted email are currently plaintext only (html is just rendered as plaintext in thunderbird),
# which is why this feature is disabled by default
ENABLE_PGP = env.bool("ENABLE_PGP", False)
# The pgp keyservevr, following the sks protocol
SKS_KEYSERVER = env.str("SKS_KEYSERVER", "gpg.mozilla.org")

# Database
# https://docs.djangoproject.com/en/1.11/ref/settings/#databases

DATABASES = {"default": env.db()}

if TESTING:
    DATABASES["OPTIONS"] = {"timeout": 10}

# Internationalization
# https://docs.djangoproject.com/en/1.11/topics/i18n/

LANGUAGE_CODE = env.str("LANGUAGE_CODE", "de-de")

TIME_ZONE = env.str("TIME_ZONE", "Europe/Berlin")

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Authentication

ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_EMAIL_REQUIRED = True
LOGIN_REDIRECT_URL = "/profile/"
ACCOUNT_EMAIL_CONFIRMATION_ANONYMOUS_REDIRECT_URL = True
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"
ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE = False
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_ADAPTER = "mainapp.account_adapter.AccountAdapter"
SOCIALACCOUNT_EMAIL_VERIFICATION = False
SOCIALACCOUNT_QUERY_EMAIL = True
# Needed by allauth
SITE_ID = 1

# Password validation
# https://docs.djangoproject.com/en/1.11/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = (
    # Needed to login by username in Django admin, regardless of `allauth`
    "django.contrib.auth.backends.ModelBackend",
    # `allauth` specific authentication methods, such as login by e-mail
    "allauth.account.auth_backends.AuthenticationBackend",
)

SOCIALACCOUNT_USE_FACEBOOK = env.bool("SOCIALACCOUNT_USE_FACEBOOK", False)
SOCIALACCOUNT_USE_TWITTER = env.bool("SOCIALACCOUNT_USE_TWITTER", False)

SOCIALACCOUNT_PROVIDERS = {}
if SOCIALACCOUNT_USE_FACEBOOK:
    SOCIALACCOUNT_PROVIDERS["facebook"] = {
        "EXCHANGE_TOKEN": True,
        "VERIFIED_EMAIL": False,
        "CLIENT_ID": env.str("FACEBOOK_CLIENT_ID"),
        "SECRET_KEY": env.str("FACEBOOK_SECRET_KEY"),
    }
    INSTALLED_APPS.append("allauth.socialaccount.providers.facebook")

if SOCIALACCOUNT_USE_TWITTER:
    SOCIALACCOUNT_PROVIDERS["twitter"] = {
        "CLIENT_ID": env.str("TWITTER_CLIENT_ID"),
        "SECRET_KEY": env.str("TWITTER_SECRET_KEY"),
    }
    INSTALLED_APPS.append("allauth.socialaccount.providers.twitter")

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/1.11/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = env.str("STATIC_ROOT", os.path.join(BASE_DIR, "static/"))

STATICFILES_DIRS = (
    os.path.join(BASE_DIR, "mainapp/assets"),
    os.path.join(BASE_DIR, "node_modules/pdfjs-dist/viewer"),  # See desgin.md
)

MINIO_PREFIX = env.str("MINIO_PREFIX", "meine-stadt-transparent-")
MINIO_HOST = env.str("MINIO_HOST", "localhost:9000")
MINIO_ACCESS_KEY = env.str("MINIO_ACCESS_KEY", "meinestadttransparent")
MINIO_SECRET_KEY = env.str("MINIO_SECRET_KEY", "meinestadttransparent")

WEBPACK_LOADER = {
    "DEFAULT": {
        "BUNDLE_DIR_NAME": "bundles/",
        "STATS_FILE": os.path.join(BASE_DIR, "webpack-stats.json"),
    }
}

# Elastic
ELASTICSEARCH_ENABLED = env.bool("ELASTICSEARCH_ENABLED", True)

if ELASTICSEARCH_ENABLED:
    INSTALLED_APPS.append("django_elasticsearch_dsl")

ELASTICSEARCH_URL = env.str("ELASTICSEARCH_URL", "localhost:9200")

ELASTICSEARCH_DSL = {"default": {"hosts": ELASTICSEARCH_URL}}

ELASTICSEARCH_INDEX = env.str(
    "ELASTICSEARCH_INDEX", "meine_stadt_transparent_documents"
)

# Language use for stemming, stop words, etc.
ELASTICSEARCH_LANG = env.str("ELASTICSEARCH_LANG", "german")

# Valid values for GEOEXTRACT_ENGINE: Nominatim, Opencage
GEOEXTRACT_ENGINE = env.str("GEOEXTRACT_ENGINE", "Nominatim")
if GEOEXTRACT_ENGINE.lower() not in ["nominatim", "opencage"]:
    raise ValueError("Unknown Geocoder: " + GEOEXTRACT_ENGINE)

if GEOEXTRACT_ENGINE.lower() == "opencage":
    OPENCAGE_KEY = env.str("OPENCAGE_KEY")

# Settings for Geo-Extraction
GEOEXTRACT_SEARCH_COUNTRY = env.str("GEOEXTRACT_SEARCH_COUNTRY", "Deutschland")
GEOEXTRACT_DEFAULT_CITY = env.str("GEOEXTRACT_DEFAULT_CITY")

CITY_AFFIXES = env.list(
    "CITY_AFFIXES",
    default=["Stadt", "Landeshauptstadt", "Gemeinde", "Kreis", "Landkreis"],
)

OCR_AZURE_KEY = env.str("OCR_AZURE_KEY", None)
OCR_AZURE_LANGUAGE = env.str("OCR_AZURE_LANGUAGE", "de")
OCR_AZURE_API = env.str(
    "OCR_AZURE_API", "https://westcentralus.api.cognitive.microsoft.com"
)

# Configuration regarding the city of choice
SITE_DEFAULT_BODY = env.int("SITE_DEFAULT_BODY", 1)
SITE_DEFAULT_ORGANIZATION = env.int("SITE_DEFAULT_ORGANIZATION", 1)

# Possible values: OSM, Mapbox
MAP_TILES_PROVIDER = env.str("MAP_TILES_PROVIDER", "OSM")
MAP_TILES_URL = env.str("MAP_TILES_URL", None)
MAP_TILES_MAPBOX_TOKEN = env.str("MAP_TILES_MAPBOX_TOKEN", None)

CUSTOM_IMPORT_HOOKS = env.str("CUSTOM_IMPORT_HOOKS", None)

PARLIAMENTARY_GROUPS_TYPE = (1, "parliamentary group")
COMMITTEE_TYPE = (2, "committee")
DEPARTMENT_TYPE = (3, "department")
ORGANIZATION_ORDER = env.list(
    "ORGANIZATION_ORDER",
    int,
    [PARLIAMENTARY_GROUPS_TYPE, COMMITTEE_TYPE, DEPARTMENT_TYPE],
)

# Possible values: month, listYear, listMonth, listDay, basicWeek, basicDay, agendaWeek, agendaDay
CALENDAR_DEFAULT_VIEW = env.str("CALENDAR_DEFAULT_VIEW", "listMonth")
CALENDAR_HIDE_WEEKENDS = env.bool("CALENDAR_HIDE_WEEKENDS", True)
CALENDAR_MIN_TIME = env.bool("CALENDAR_MIN_TIME", "08:00:00")
CALENDAR_MAX_TIME = env.bool("CALENDAR_MAX_TIME", "21:00:00")

# Configuration regarding Search Engine Optimization
SITE_SEO_NOINDEX = env.bool("SITE_SEO_NOINDEX", False)

# Include the plain text of PDFs next to the PDF viewer, visible only for Screenreaders
# On by default to improve accessibility, deactivatable in case there are legal concerns
EMBED_PARSED_TEXT_FOR_SCREENREADERS = env.bool(
    "EMBED_PARSED_TEXT_FOR_SCREENREADERS", True
)

SEARCH_PAGINATION_LENGTH = 20

SENTRY_DSN = env.str("SENTRY_DSN", None)

# SENTRY_HEADER_ENDPOINT is defined in security.py

if SENTRY_DSN:
    sentry_sdk.init(SENTRY_DSN, integrations=[DjangoIntegration()])

DJANGO_LOG_LEVEL = env.str("DJANGO_LOG_LEVEL", None)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "extended": {"format": "%(asctime)s %(levelname)-8s %(name)-12s %(message)s"}
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
        "django": {
            "class": "logging.FileHandler",
            "filename": os.path.join(env.str("LOGGING_DIRECTORY", ""), "django.log"),
            "formatter": "extended",
        },
        "importer": {
            "class": "logging.FileHandler",
            "filename": os.path.join(env.str("LOGGING_DIRECTORY", ""), "importer.log"),
            "formatter": "extended",
        },
    },
    "loggers": {
        "mainapp": {
            "handlers": ["console", "django"],
            "level": DJANGO_LOG_LEVEL or "INFO",
        },
        "mainapp.management.commands": {
            "level": DJANGO_LOG_LEVEL or "DEBUG",
            "propagate": True,
        },
        "importer": {
            "handlers": ["console", "importer"],
            "level": DJANGO_LOG_LEVEL or "INFO",
            "propagate": True,
        },
        "django": {
            "level": DJANGO_LOG_LEVEL or "WARNING",
            "handlers": ["console", "django"],
            "propagate": True,
        },
    },
}

LOGGING.update(env.json("LOGGING", {}))

OPARL_INDEX = env.str("OPARL_INDEX", "https://mirror.oparl.org/bodies")

OPARL_ENDPOINT = env.str("OPARL_ENDPOINT", None)

TEMPLATE_META = {
    "logo_name": env.str("TEMPLATE_LOGO_NAME", "MST"),
    "site_name": SITE_NAME,
    "prototype_fund": "https://prototypefund.de/project/open-source-ratsinformationssystem",
    "github": "https://github.com/meine-stadt-transparent/meine-stadt-transparent",
    "contact_mail": DEFAULT_FROM_EMAIL,
    "main_css": env.str("TEMPLATE_MAIN_CSS", "mainapp"),
    "location_limit_lng": 42,
    "location_limit_lat": 23,
    "sks_keyserver": SKS_KEYSERVER,
    "enable_pgp": ENABLE_PGP,
    "sentry_dsn": SENTRY_DSN,
}

FILE_DISCLAIMER = env.str("FILE_DISCLAIMER", None)
FILE_DISCLAIMER_URL = env.str("FILE_DISCLAIMER_URL", None)

SETTINGS_EXPORT = [
    "TEMPLATE_META",
    "FILE_DISCLAIMER",
    "FILE_DISCLAIMER_URL",
    "ABSOLUTE_URI_BASE",
]

DEBUG_TOOLBAR_ACTIVE = False
DEBUG_TESTING = env.bool("DEBUG_TESTING", False)

if DEBUG and not TESTING:
    if find_spec("debug_toolbar"):
        # Debug Toolbar
        INSTALLED_APPS.append("debug_toolbar")
        MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware")
        DEBUG_TOOLBAR_CONFIG = {"JQUERY_URL": ""}
        DEBUG_TOOLBAR_ACTIVE = True
    else:
        logger = logging.getLogger(__name__)
        logger.warning(
            "This is running in DEBUG mode, however the Django debug toolbar is not installed."
        )
        DEBUG_TOOLBAR_ACTIVE = False

    if env.bool("DEBUG_SHOW_SQL", False):
        LOGGING["logggers"]["django.db.backends"] = {
            "level": "DEBUG",
            "handlers": ["console"],
            "propagate": False,
        }

    INTERNAL_IPS = ["127.0.0.1"]

    # Make debugging css styles in firefox easier
    DEBUG_STYLES = env.bool("DEBUG_STYLES", False)
    if DEBUG_STYLES:
        CSP_STYLE_SRC = ("'self'", "'unsafe-inline'")

    # Just an additional host you might want
    ALLOWED_HOSTS.append("meinestadttransparent.local")
