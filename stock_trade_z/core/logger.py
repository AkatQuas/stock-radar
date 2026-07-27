import logging
import os
import sys
from typing import Literal

from stock_trade_z.core.time import get_today_date

_logger_cache = {}


def get_logger(
    logger_name: Literal["fetch", "select", "check", "noop", "risk", "registry", "quant"],
    log_level: int = logging.INFO,
    log_format: str | None = None,
    file_mode: str = "a",  # Append mode (use "w" to overwrite logs each time)
) -> logging.Logger:
    """
    Create or reuse a logger with a file handler.

    Args:
        logger_name: Unique name for the logger (prevents duplicate loggers)
        log_file: Path to log file (default: {logger_name}.log in current directory)
        log_level: Logging level (e.g., logging.DEBUG, logging.INFO)
        log_format: Format string for log messages (auto-detected in CI)
        file_mode: File open mode ("a" for append, "w" for overwrite)

    Returns:
        Configured logger instance (reused if already exists)
    """
    if log_format is None:
        if os.getenv("GITHUB_ACTIONS"):
            log_format = "%(message)s"
        else:
            log_format = "%(asctime)s [%(levelname)s] %(message)s"

    if logger_name in _logger_cache:
        return _logger_cache[logger_name]

    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)

    # Prevent duplicate handlers (critical for reusability)
    logger.propagate = False

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)

    formatter = logging.Formatter(log_format, datefmt="%H:%M:%S")
    stdout_handler.setFormatter(formatter)

    logger.addHandler(stdout_handler)

    if logger_name != "noop" and logger_name != "fetch":
        log_file = f"log/{get_today_date()}_{logger_name}.log"
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(log_file, mode=file_mode, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _logger_cache[logger_name] = logger

    return logger
