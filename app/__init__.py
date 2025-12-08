"""
Prometheus - Serial Cables Hardware Dashboard
Flask Application Factory
"""
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS

socketio = SocketIO()


def create_app(config_name='default'):
    """Create and configure the Flask application"""
    from config import config

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Initialize extensions
    CORS(app)
    socketio.init_app(app,
                      async_mode=app.config.get('SOCKETIO_ASYNC_MODE', 'eventlet'),
                      cors_allowed_origins="*")

    # Register blueprints
    from app.api.routes import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    # Register WebSocket handlers
    from app.api import websocket  # noqa: F401

    # Register main routes
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    # Start background device detection scan
    # This pre-caches device info so the first client request is fast
    with app.app_context():
        from app.devices.detection import start_background_scan
        start_background_scan()

    return app
