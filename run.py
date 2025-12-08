#!/usr/bin/env python3
"""
Prometheus - Serial Cables Hardware Dashboard
Application Entry Point
"""
import os
import socket
import logging
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from config import config, LOG_DIR

# Serial Cables libraries to check for updates
SERIALCABLES_PACKAGES = [
    'serialcables-atlas3',
    'serialcables-hydra',
]

def get_local_ip():
    """Get the local IP address for LAN access"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def check_package_updates(packages, logger=None):
    """Check for updates to specified packages and install if available"""
    for package in packages:
        try:
            # Check if update is available using pip
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade', '--dry-run', package],
                capture_output=True,
                text=True,
                timeout=30
            )

            # Check if package would be upgraded
            if 'Would install' in result.stdout or 'Collecting' in result.stdout:
                msg = f'Update available for {package}, installing...'
                print(f' * {msg}')
                if logger:
                    logger.info(msg)

                # Perform the actual upgrade
                upgrade_result = subprocess.run(
                    [sys.executable, '-m', 'pip', 'install', '--upgrade', package],
                    capture_output=True,
                    text=True,
                    timeout=120
                )

                if upgrade_result.returncode == 0:
                    msg = f'Successfully updated {package}'
                    print(f' * {msg}')
                    if logger:
                        logger.info(msg)
                else:
                    msg = f'Failed to update {package}: {upgrade_result.stderr}'
                    print(f' * {msg}')
                    if logger:
                        logger.warning(msg)
            else:
                msg = f'{package} is up to date'
                if logger:
                    logger.debug(msg)

        except subprocess.TimeoutExpired:
            msg = f'Timeout checking updates for {package}'
            print(f' * {msg}')
            if logger:
                logger.warning(msg)
        except Exception as e:
            msg = f'Error checking updates for {package}: {e}'
            if logger:
                logger.warning(msg)

def setup_logging(app_config):
    """Setup file-based logging with rotation (keeps current + 1 previous session)"""
    LOG_DIR.mkdir(exist_ok=True)

    # Rotate on each startup - this creates a new session log
    handler = RotatingFileHandler(
        app_config.LOG_FILE,
        maxBytes=0,  # Don't rotate by size
        backupCount=app_config.LOG_BACKUP_COUNT,
        encoding='utf-8'  # Support Unicode characters from device responses
    )
    # Force rotation on startup to separate sessions
    if app_config.LOG_FILE.exists():
        handler.doRollover()

    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))

    log_level = getattr(logging, app_config.LOG_LEVEL, logging.DEBUG)
    handler.setLevel(log_level)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)

    # Also configure Flask/Werkzeug/SocketIO loggers and serialcables libraries
    for logger_name in ['app', 'werkzeug', 'socketio', 'engineio', 'serialcables_hydra', 'serialcables_atlas3']:
        lib_logger = logging.getLogger(logger_name)
        lib_logger.setLevel(log_level)
        lib_logger.addHandler(handler)

    return logging.getLogger('prometheus')

from app import create_app, socketio

# Create Flask application
env = os.environ.get('FLASK_ENV', 'development')
app_config = config[env]
app = create_app(env)

if __name__ == '__main__':
    logger = setup_logging(app_config)
    logger.info('=' * 60)
    logger.info('Prometheus server starting')
    logger.info('=' * 60)

    # Check for Serial Cables library updates
    print(' * Checking for Serial Cables library updates...')
    logger.info('Checking for Serial Cables library updates')
    check_package_updates(SERIALCABLES_PACKAGES, logger)

    local_ip = get_local_ip()
    port = 5000

    # OSC 8 hyperlink format: \033]8;;URL\033\\TEXT\033]8;;\033\\
    def make_link(url):
        return f"\033]8;;{url}\033\\{url}\033]8;;\033\\"

    local_url = f"http://localhost:{port}"
    network_url = f"http://{local_ip}:{port}"

    print(f" * Prometheus Dashboard")
    print(f" * Local:   {make_link(local_url)}")
    print(f" * Network: {make_link(network_url)}")
    print(f" * Logging to: {app_config.LOG_FILE}")
    print(" * Press Ctrl+C to stop")

    logger.info(f'Server accessible at http://localhost:{port} and http://{local_ip}:{port}')

    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )
