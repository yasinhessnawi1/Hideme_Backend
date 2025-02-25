import os
import logging

class AppLogger:
    """
    A helper class to create and configure a logger for the application.
    """
    def __init__(self, name: str = __name__):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        # Only add handlers if they haven't been added yet.
        if not self.logger.handlers:
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            # Create logs directory relative to this file
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../logs")
            os.makedirs(log_dir, exist_ok=True)
            file_handler = logging.FileHandler(os.path.join(log_dir, "app.log"), encoding="utf-8")
            file_handler.setFormatter(formatter)
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            self.logger.addHandler(stream_handler)

    def get_logger(self):
        return self.logger

# Create a default logger instance that other modules can import
default_logger = AppLogger().get_logger()
