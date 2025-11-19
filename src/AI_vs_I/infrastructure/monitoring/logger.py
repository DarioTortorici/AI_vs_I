import logging


class Logger:
    """
    Logger utility class to configure and provide a logger instance.

    Responsibilities:
    - Configures logging format and level
    """

    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """
        Get a configured logger instance for the given name.

        Args:
            name (str): The name of the logger.

        Returns:
            logging.Logger: Configured logger instance.
        """
        logger = logging.getLogger(name)
        # Only add handler if not already present
        if not logger.hasHandlers():
            logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger
