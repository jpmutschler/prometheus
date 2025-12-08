"""
Prometheus Configuration
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Base directory for logs
BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / 'logs'


class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'prometheus-dev-key-change-in-prod')

    # SocketIO settings
    SOCKETIO_ASYNC_MODE = 'threading'

    # Device polling interval (seconds)
    STATUS_POLL_INTERVAL = 1.0
    TEMPERATURE_POLL_INTERVAL = 2.0

    # Export settings
    EXPORT_TIMESTAMP_FORMAT = '%Y%m%d_%H%M%S'

    # Default COM port settings
    DEFAULT_BAUDRATE = 115200
    DEFAULT_TIMEOUT = 1.0

    # Logging settings
    LOG_DIR = LOG_DIR
    LOG_FILE = LOG_DIR / 'prometheus.log'
    LOG_BACKUP_COUNT = 1  # Keep current + 1 previous session


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    LOG_LEVEL = 'INFO'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
