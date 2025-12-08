"""
Prometheus WebSocket Handlers
Real-time device status updates via Flask-SocketIO
"""
from flask import request
from flask_socketio import emit, join_room, leave_room
import threading
import time

from app import socketio
from app.devices import device_manager
from app.logger import get_logger

logger = get_logger('websocket')

# Background thread for status polling
status_threads = {}
thread_lock = threading.Lock()


def status_polling_thread(device_id: str, interval: float = 1.0):
    """Background thread that polls device status and emits updates"""
    while True:
        device = device_manager.get_device(device_id)
        
        if not device or not device.connected:
            # Device disconnected, stop polling
            break
        
        try:
            status = device.get_status()
            socketio.emit('status_update', {
                'device_id': device_id,
                'status': status.to_dict()
            }, room=device_id)
        except Exception as e:
            socketio.emit('status_error', {
                'device_id': device_id,
                'error': str(e)
            }, room=device_id)
        
        time.sleep(interval)
    
    # Clean up thread reference
    with thread_lock:
        if device_id in status_threads:
            del status_threads[device_id]


# ============================================================================
# Connection Events
# ============================================================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    client_ip = request.remote_addr
    logger.info(f'Client connected: {client_ip}')
    emit('connected', {'message': 'Connected to Prometheus'})


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    client_ip = request.remote_addr
    logger.info(f'Client disconnected: {client_ip}')


# ============================================================================
# Device Subscription Events
# ============================================================================

@socketio.on('subscribe')
def handle_subscribe(data):
    """Subscribe to device updates"""
    device_id = data.get('device_id')
    
    if not device_id:
        emit('error', {'message': 'Missing device_id'})
        return
    
    device = device_manager.get_device(device_id)
    
    if not device:
        emit('error', {'message': f'Device not found: {device_id}'})
        return
    
    # Join the room for this device
    join_room(device_id)
    
    # Start status polling thread if not already running
    with thread_lock:
        if device_id not in status_threads and device.connected:
            thread = threading.Thread(
                target=status_polling_thread,
                args=(device_id, 1.0),
                daemon=True
            )
            status_threads[device_id] = thread
            thread.start()
    
    emit('subscribed', {
        'device_id': device_id,
        'message': f'Subscribed to {device_id} updates'
    })
    
    # Send initial status
    if device.connected:
        emit('status_update', {
            'device_id': device_id,
            'status': device.get_status().to_dict()
        })


@socketio.on('unsubscribe')
def handle_unsubscribe(data):
    """Unsubscribe from device updates"""
    device_id = data.get('device_id')
    
    if device_id:
        leave_room(device_id)
        emit('unsubscribed', {
            'device_id': device_id,
            'message': f'Unsubscribed from {device_id} updates'
        })


# ============================================================================
# Command Events (for real-time command execution)
# ============================================================================

@socketio.on('execute_command')
def handle_execute_command(data):
    """Execute a command and emit result"""
    device_id = data.get('device_id')
    command = data.get('command')
    params = data.get('params', {})

    logger.debug(f'Command request: device={device_id}, cmd={command}, params={params}')

    if not device_id or not command:
        logger.warning('Command rejected: missing device_id or command')
        emit('command_error', {
            'error': 'Missing device_id or command'
        })
        return

    device = device_manager.get_device(device_id)

    if not device:
        logger.warning(f'Command rejected: device not found: {device_id}')
        emit('command_error', {
            'device_id': device_id,
            'error': f'Device not found: {device_id}'
        })
        return

    if not device.connected:
        logger.warning(f'Command rejected: device not connected: {device_id}')
        emit('command_error', {
            'device_id': device_id,
            'error': 'Device not connected'
        })
        return

    result = device.send_command(command, **params)
    logger.info(f'Command executed: device={device_id}, cmd={command}, success={result.success}')

    emit('command_result', {
        'device_id': device_id,
        'result': result.to_dict()
    })


# ============================================================================
# Utility Events
# ============================================================================

@socketio.on('ping')
def handle_ping():
    """Handle ping for connection keepalive"""
    emit('pong', {'timestamp': time.time()})


@socketio.on('get_all_status')
def handle_get_all_status():
    """Get status of all connected devices"""
    devices_status = {}
    
    for device_id, device in device_manager.get_all_devices().items():
        if device.connected:
            devices_status[device_id] = device.get_status().to_dict()
        else:
            devices_status[device_id] = {'connected': False}
    
    emit('all_status', {'devices': devices_status})
