"""
Prometheus Logging Utility
Provides easy access to the application logger
"""
import logging


def get_logger(name: str = None) -> logging.Logger:
    """Get a logger instance for the given module name"""
    if name:
        return logging.getLogger(f'app.{name}')
    return logging.getLogger('app')
