import logging
import logging.handlers
import os
from pathlib import Path

def setup_logging(log_level=logging.INFO, log_to_file=True, log_file="app.log"):
    """
    Setup centralized logging configuration for the application.

    Args:
        log_level: The logging level (e.g., logging.DEBUG, logging.INFO)
        log_to_file: Whether to also log to a file
        log_file: The log file name
    """
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(log_level)

    # Clear any existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_to_file:
        # Ensure logs directory exists
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        log_file_path = log_dir / log_file

        # Create rotating file handler (max 5MB per file, keep 3 backup files)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file_path,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

def get_logger(name):
    """
    Get a logger instance for a specific module.

    Args:
        name: The name of the logger (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)

