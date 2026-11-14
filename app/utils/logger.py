import logging
import warnings

from django.conf import settings


def configure_logger() -> None:
    logger = get_logger()

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(getattr(settings, "LOGLEVEL", logging.INFO))

    warnings.simplefilter(action="ignore", category=FutureWarning)


def get_logger() -> logging.Logger:
    return logging.getLogger(__name__)
