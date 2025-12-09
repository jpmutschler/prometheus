"""
Prometheus API Routes
REST API endpoints for device management, commands, and data export
"""
from flask import Blueprint, jsonify, request
import serial.tools.list_ports
import threading
from app.logger import get_logger
from app.devices import device_manager
from app.devices.detection import (
    detect_device, DeviceSignatures,
    scan_all_ports_fast, get_cached_devices, start_background_scan
)
from app.api.handlers import get_handler, HandlerRegistry

logger = get_logger('api')

api_bp = Blueprint('api', __name__)

# Store active device connections
_active_devices = {}
# Lock for serializing access to devices
_device_locks = {}


@api_bp.route('/status')
def status():
    """API status endpoint"""
    return jsonify({'status': 'ok', 'api_version': '1.0'})


@api_bp.route('/ports')
def list_ports():
    """Scan and list available COM ports"""
    ports = []
    for port in serial.tools.list_ports.comports():
        port_info = {
            'device': port.device,
            'description': port.description,
            'hwid': port.hwid,
            'manufacturer': port.manufacturer or '',
            'product': port.product or '',
            'serial_number': port.serial_number or ''
        }
        # Include VID/PID if available (useful on Linux where hwid may differ)
        if hasattr(port, 'vid') and port.vid is not None:
            port_info['vid'] = f'{port.vid:04X}'
            port_info['pid'] = f'{port.pid:04X}'
        ports.append(port_info)
    logger.debug(f'COM port scan: found {len(ports)} ports')
    return jsonify({'ports': ports})


@api_bp.route('/devices')
def list_devices():
    """List all connected devices"""
    devices = []
    for device_id, device_info in _active_devices.items():
        devices.append({
            'id': device_id,
            'type': device_info['type'],
            'com_port': device_info['com_port'],
            'connected': device_info['device'].is_connected if hasattr(device_info['device'], 'is_connected') else True
        })
    logger.debug(f'Device list requested: {len(devices)} devices')
    return jsonify({'devices': devices})


@api_bp.route('/device-types')
def list_device_types():
    """List all supported device types"""
    return jsonify({'device_types': HandlerRegistry.get_all_types()})


@api_bp.route('/connect', methods=['POST'])
def connect_device():
    """Connect to a device"""
    data = request.get_json()
    device_type = data.get('device_type')
    com_port = data.get('com_port')

    if not device_type or not com_port:
        return jsonify({'success': False, 'error': 'Missing device_type or com_port'}), 400

    # Get the appropriate handler
    handler = get_handler(device_type)
    if not handler:
        return jsonify({'success': False, 'error': f'Unknown device type: {device_type}'}), 400

    try:
        # Use handler to connect
        device, info = handler.connect(com_port, timeout=10.0)

        # Generate device ID
        device_id = f"{device_type}_{com_port.replace('COM', '').replace('/dev/', '')}"

        # Create a lock for this device
        _device_locks[device_id] = threading.Lock()

        # Store device
        _active_devices[device_id] = {
            'device': device,
            'type': device_type,
            'com_port': com_port,
            'info': info
        }

        logger.info(f'Connected to {device_type} on {com_port} as {device_id}')

        return jsonify({
            'success': True,
            'device_id': device_id,
            'info': info
        })

    except Exception as e:
        logger.error(f'Failed to connect to {device_type} on {com_port}: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/disconnect/<device_id>', methods=['POST'])
def disconnect_device(device_id):
    """Disconnect from a device"""
    if device_id not in _active_devices:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    try:
        device_info = _active_devices[device_id]
        device = device_info['device']

        if hasattr(device, 'disconnect'):
            device.disconnect()

        del _active_devices[device_id]
        if device_id in _device_locks:
            del _device_locks[device_id]
        logger.info(f'Disconnected from {device_id}')

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f'Failed to disconnect from {device_id}: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


def _with_device_lock(device_id, timeout=30):
    """Context manager helper for device lock acquisition"""
    if device_id not in _active_devices:
        return None, None, 'Device not found'

    lock = _device_locks.get(device_id)
    if not lock:
        return None, None, 'Device lock not found'

    if not lock.acquire(timeout=timeout):
        return None, None, 'Device is busy'

    device_info = _active_devices[device_id]
    return device_info, lock, None


@api_bp.route('/device/<device_id>/sysinfo')
def get_device_sysinfo(device_id):
    """Get system information for a device"""
    device_info, lock, error = _with_device_lock(device_id)
    if error:
        status_code = 404 if error == 'Device not found' else 503 if error == 'Device is busy' else 500
        return jsonify({'success': False, 'error': error}), status_code

    try:
        device = device_info['device']
        device_type = device_info['type']

        logger.debug(f'Getting sysinfo for {device_id}')

        # Get the appropriate handler
        handler = get_handler(device_type)
        if not handler:
            lock.release()
            return jsonify({'success': False, 'error': 'Unknown device type'}), 400

        # Prepare device for commands (reconnect if needed, clear buffers)
        if not handler.check_connection(device):
            logger.warning(f'Device {device_id} disconnected, reconnecting...')

        handler.prepare_for_commands(device)

        # Use handler to get sysinfo
        sysinfo = handler.get_sysinfo(device)

        logger.debug(f'Successfully got sysinfo for {device_id}')
        lock.release()
        return jsonify({'success': True, 'sysinfo': sysinfo})

    except Exception as e:
        logger.error(f'Failed to get sysinfo for {device_id}: {e}')
        lock.release()
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/device/<device_id>/control-status')
def get_control_status(device_id):
    """Get current control settings for a device"""
    device_info, lock, error = _with_device_lock(device_id)
    if error:
        status_code = 404 if error == 'Device not found' else 503 if error == 'Device is busy' else 500
        return jsonify({'success': False, 'error': error}), status_code

    try:
        device = device_info['device']
        device_type = device_info['type']

        # Get the appropriate handler
        handler = get_handler(device_type)
        if not handler:
            lock.release()
            return jsonify({'success': False, 'error': 'Unknown device type'}), 400

        # Use handler to get control status
        status = handler.get_control_status(device)

        lock.release()
        return jsonify({'success': True, 'status': status})

    except Exception as e:
        lock.release()
        logger.error(f'Failed to get control status for {device_id}: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/device/<device_id>/control', methods=['POST'])
def execute_control_commands(device_id):
    """Execute control commands on a device"""
    device_info, lock, error = _with_device_lock(device_id)
    if error:
        status_code = 404 if error == 'Device not found' else 503 if error == 'Device is busy' else 500
        return jsonify({'success': False, 'error': error}), status_code

    data = request.get_json()
    commands = data.get('commands', [])

    if not commands:
        lock.release()
        return jsonify({'success': False, 'error': 'No commands provided'}), 400

    try:
        device = device_info['device']
        device_type = device_info['type']

        # Get the appropriate handler
        handler = get_handler(device_type)
        if not handler:
            lock.release()
            return jsonify({'success': False, 'error': 'Unknown device type'}), 400

        results = []
        disconnect = False

        for cmd in commands:
            command = cmd.get('command')
            params = cmd.get('params', {})

            logger.info(f'Executing {command} on {device_id} with params: {params}')

            try:
                result, requires_disconnect = handler.execute_command(device, command, params)
                if requires_disconnect:
                    disconnect = True
                results.append({'command': command, 'success': True, 'result': result})

            except Exception as e:
                logger.error(f'Command {command} failed: {e}')
                lock.release()
                return jsonify({
                    'success': False,
                    'error': f'Command {command} failed: {str(e)}',
                    'results': results
                }), 500

        lock.release()
        return jsonify({'success': True, 'results': results, 'disconnect': disconnect})

    except Exception as e:
        lock.release()
        logger.error(f'Failed to execute commands on {device_id}: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@api_bp.route('/device/<device_id>/commands')
def get_device_commands(device_id):
    """Get available commands for a device"""
    if device_id not in _active_devices:
        return jsonify({'success': False, 'error': 'Device not found'}), 404

    device_info = _active_devices[device_id]
    device_type = device_info['type']

    handler = get_handler(device_type)
    if not handler:
        return jsonify({'success': False, 'error': 'Unknown device type'}), 400

    commands = handler.get_available_commands()
    return jsonify({'success': True, 'commands': commands})


@api_bp.route('/device/<device_id>/command', methods=['POST'])
def execute_device_command(device_id):
    """Execute a single command on a device"""
    device_info, lock, error = _with_device_lock(device_id)
    if error:
        status_code = 404 if error == 'Device not found' else 503 if error == 'Device is busy' else 500
        return jsonify({'success': False, 'error': error}), status_code

    data = request.get_json()
    command = data.get('command')
    params = data.get('params', {})

    if not command:
        lock.release()
        return jsonify({'success': False, 'error': 'No command provided'}), 400

    try:
        device = device_info['device']
        device_type = device_info['type']

        # Get the appropriate handler
        handler = get_handler(device_type)
        if not handler:
            lock.release()
            return jsonify({'success': False, 'error': 'Unknown device type'}), 400

        logger.info(f'Executing {command} on {device_id} with params: {params}')

        result, requires_disconnect = handler.execute_command(device, command, params)

        lock.release()
        return jsonify({
            'success': True,
            'result': result,
            'disconnect': requires_disconnect
        })

    except Exception as e:
        lock.release()
        logger.error(f'Failed to execute command {command} on {device_id}: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# Device Detection Endpoints
# =============================================================================

@api_bp.route('/detect/<path:com_port>')
def detect_device_on_port(com_port):
    """
    Auto-detect device type on a COM port.

    Sends 'ver' command and matches response against known device signatures.
    Returns detected device type, model, serial number, and firmware version.
    """
    # Handle URL-encoded paths (e.g., COM3 or /dev/ttyUSB0)
    if not com_port.startswith('/') and not com_port.startswith('COM'):
        com_port = f'COM{com_port}'

    logger.info(f'Detection requested for {com_port}')

    # Check if port is already in use
    for device_id, device_info in _active_devices.items():
        if device_info['com_port'] == com_port:
            return jsonify({
                'success': False,
                'error': f'Port {com_port} is already connected as {device_id}',
                'already_connected': True,
                'device_id': device_id,
                'device_type': device_info['type']
            }), 409

    try:
        result = detect_device(com_port)

        if result.success:
            logger.info(f'Detected {result.device_type} on {com_port}: {result.model}')
        else:
            logger.warning(f'Detection failed on {com_port}: {result.error}')

        return jsonify(result.to_dict())

    except Exception as e:
        logger.error(f'Detection error on {com_port}: {e}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@api_bp.route('/detect-all', methods=['POST'])
def detect_all_ports():
    """
    Scan all COM ports and detect devices using fast parallel scanning.

    Optionally accepts a list of ports to scan in the request body.
    Returns detection results for each port.
    """
    data = request.get_json() or {}
    use_cache = data.get('use_cache', False)

    # Get already connected ports to exclude
    connected_ports = {info['com_port'] for info in _active_devices.values()}

    # Use fast parallel scanning
    if use_cache:
        # Return cached results if available
        cached = get_cached_devices()
        if cached:
            results = {port: r.to_dict() for port, r in cached.items()
                      if port not in connected_ports}
            detected_count = sum(1 for r in results.values() if r.get('success'))
            return jsonify({
                'success': True,
                'scanned_count': len(results),
                'detected_count': detected_count,
                'skipped_ports': list(connected_ports),
                'results': results,
                'from_cache': True
            })

    # Perform fast parallel scan
    scan_results = scan_all_ports_fast(exclude_ports=connected_ports)

    # Convert to dict format
    results = {port: r.to_dict() for port, r in scan_results.items()}

    # Count successful detections
    detected_count = sum(1 for r in results.values() if r.get('success'))

    return jsonify({
        'success': True,
        'scanned_count': len(results),
        'detected_count': detected_count,
        'skipped_ports': list(connected_ports),
        'results': results,
        'from_cache': False
    })


@api_bp.route('/signatures')
def get_signatures():
    """Get all device signatures for the frontend"""
    signatures = DeviceSignatures()
    return jsonify({
        'success': True,
        'signatures': signatures.get_signatures(),
        'settings': signatures.get_settings()
    })