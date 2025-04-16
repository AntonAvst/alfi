import logging
from logging.handlers import RotatingFileHandler

def get_logger(name="alfi"):
    logger = logging.getLogger(name)

    if not logger.hasHandlers():  # Ensure it's only configured once
        logger.setLevel(logging.DEBUG)

        # File handler
        handler = RotatingFileHandler("app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)

        # Console handler (optional)
        console = logging.StreamHandler()
        console.setFormatter(formatter)

        logger.addHandler(handler)
        logger.addHandler(console)

    return logger
