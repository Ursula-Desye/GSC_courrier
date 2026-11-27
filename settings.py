
import os
from pathlib import Path
from dotenv import load_dotenv

# =====================================================
# CONFIGURATION DU PROJET
# =====================================================

BASE_DIR = Path(__file__).resolve().parent.parent

# Chargement des variables d'environnement
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "dev-only-change-this-key"
)

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost"
    ).split(",")
    if h.strip()
]

# =====================================================
# APPLICATIONS DJANGO
# =====================================================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Applications GSC
    "courrier",
    "services",
]

# =====================================================
# MIDDLEWARE
# =====================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# =====================================================
# CONFIGURATION DES TEMPLATES
# =====================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# =====================================================
# CONFIGURATION SQL SERVER
# AUTHENTIFICATION WINDOWS
# =====================================================

DATABASES = {
    "default": {
        "ENGINE": "mssql",

        "NAME": os.getenv(
            "DB_NAME",
            "GESTION_COURRIER"
        ),

        "HOST": os.getenv(
            "DB_HOST",
            r"localhost\GSC"
        ),

        "PORT": os.getenv("DB_PORT", ""),

        # Authentification Windows :
        # Aucun identifiant SQL n'est utilisé.
        "USER": "",
        "PASSWORD": "",

        "OPTIONS": {
            "driver": os.getenv(
                "DB_DRIVER",
                "ODBC Driver 18 for SQL Server"
            ),

            "host_is_server": True,

            # Connexion sécurisée avec authentification Windows
            "extra_params": (
                "Trusted_Connection=yes;"
                "Encrypt=yes;"
                "TrustServerCertificate=yes"
            ),
        },
    }
}

# =====================================================
# VALIDATION DES MOTS DE PASSE
# =====================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]

# =====================================================
# LANGUE ET PARAMETRES REGIONAUX
# =====================================================

LANGUAGE_CODE = "fr-fr"

TIME_ZONE = "Africa/Douala"

USE_I18N = True

USE_TZ = True

# =====================================================
# FICHIERS STATIQUES
# =====================================================

STATIC_URL = "static/"

STATICFILES_DIRS = (
    [BASE_DIR / "static"]
    if (BASE_DIR / "static").exists()
    else []
)

STATIC_ROOT = BASE_DIR / "staticfiles"

# =====================================================
# DOCUMENTS ET FICHIERS JOINTS
# =====================================================

MEDIA_URL = "media/"

MEDIA_ROOT = BASE_DIR / "media"

# =====================================================
# CONFIGURATION GENERALE
# =====================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =====================================================
# AUTHENTIFICATION GSC
# =====================================================

LOGIN_URL = "login"

LOGIN_REDIRECT_URL = "dashboard"

LOGOUT_REDIRECT_URL = "login"
