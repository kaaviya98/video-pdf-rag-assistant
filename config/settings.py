import environ
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")
SECRET_KEY = env("SECRET_KEY", default="development-only-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "django_multitenant", "app.apps.LearnLensConfig"]
MIDDLEWARE = []
ROOT_URLCONF = "config.urls"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
MIGRATION_MODULES = {"app": None}
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": env("DB_NAME", default="learnlens"), "USER": env("DB_USER", default="learnlens"), "PASSWORD": env("DB_PASSWORD", default=""), "HOST": env("DB_HOST", default="localhost"), "PORT": env("DB_PORT", default="5432"), "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=60)}}
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
ORG_DEFAULT_LLM_MODEL = env("ORG_DEFAULT_LLM_MODEL", default="gpt-4o-mini")
ORG_DEFAULT_LLM_API_KEY = OPENAI_API_KEY
VECTOR_DB_PDF_COLLECTION_NAME = env("VECTOR_DB_PDF_COLLECTION_NAME", default="LearnLensDocuments")
VECTOR_DB_VIDEO_COLLECTION_NAME = env("VECTOR_DB_VIDEO_COLLECTION_NAME", default="LearnLensVideoDocuments")
WEAVIATE_HOST = env("WEAVIATE_HOST", default="localhost")
WEAVIATE_PORT = env("WEAVIATE_PORT", default="8080")
WEAVIATE_API_KEY = env("WEAVIATE_API_KEY", default="")
WEAVIATE_USE_SSL = env.bool("WEAVIATE_USE_SSL", default=False)
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="amqp://guest:guest@localhost:5672//")
CELERY_TASK_DEFAULT_QUEUE = env("CELERY_TASK_DEFAULT_QUEUE", default="learnlens")
CELERY_PDF_QUEUE = env("CELERY_PDF_QUEUE", default="learnlens_pdf")
CELERY_VIDEO_QUEUE = env("CELERY_VIDEO_QUEUE", default="learnlens_video")
VIDEO_NOTES_LOCAL_DIR = BASE_DIR / "var" / "video_notes"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))
