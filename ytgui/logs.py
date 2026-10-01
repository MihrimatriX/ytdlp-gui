"""Application logging to a rotating file in the user data directory."""

import logging
from logging.handlers import RotatingFileHandler

from .paths import log_file

_configured = False


def get_logger(name: str = "ytgui") -> logging.Logger:
    global _configured
    if not _configured:
        _configured = True
        root = logging.getLogger("ytgui")
        root.setLevel(logging.INFO)
        try:
            handler = RotatingFileHandler(log_file(), maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            root.addHandler(handler)
        except OSError:
            root.addHandler(logging.NullHandler())
    return logging.getLogger(name)
