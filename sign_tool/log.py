from __future__ import annotations

import logging

_logger: logging.Logger = None


def setup_logger(level: str = "INFO") -> logging.Logger:
    global _logger
    _logger = logging.getLogger("sign_tool")
    if not _logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        _logger.addHandler(handler)
    _logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return _logger


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger
