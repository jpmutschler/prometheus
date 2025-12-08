"""
Prometheus Atlas3 Device Handler
Handles Atlas3 PCIe switch specific API operations
"""
from typing import Any
from .base_handler import BaseDeviceHandler, HandlerRegistry


def _clean_string(s: Any) -> Any:
    """Strip trailing box-drawing characters and whitespace from device strings"""
    if not isinstance(s, str):
        return s
    return s.rstrip('║│┃ \t\r\n')


def _serialize_port_list(ports: list) -> list[dict]:
    """Serialize Atlas3 port objects to dicts"""
    result = []
    for port in ports:
        neg_speed = getattr(port, 'negotiated_speed', None)
        max_speed = getattr(port, 'max_speed', None)
        status = getattr(port, 'status', None)
        port_type = getattr(port, 'port_type', None)

        port_dict = {
            'station': getattr(port, 'station', 0),
            'connector': getattr(port, 'connector', ''),
            'port_number': getattr(port, 'port_number', 0),
            'speed': neg_speed.value if neg_speed and hasattr(neg_speed, 'value') else None,
            'width': getattr(port, 'negotiated_width', 0),
            'max_speed': max_speed.value if max_speed and hasattr(max_speed, 'value') else None,
            'max_width': getattr(port, 'max_width', 0),
            'status': status.value if status and hasattr(status, 'value') else 'Unknown',
            'port_type': port_type.value if port_type and hasattr(port_type, 'value') else None,
            'is_linked': getattr(port, 'negotiated_width', 0) > 0
        }
        result.append(port_dict)
    return result


class Atlas3Handler(BaseDeviceHandler):
    """Handler for Atlas3 PCIe switch devices"""

    device_type = "atlas3"

    def connect(self, com_port: str, timeout: float = 10.0) -> tuple[Any, dict]:
        """Connect to an Atlas3 device"""
        from serialcables_atlas3 import Atlas3

        device = Atlas3(com_port, auto_connect=True, timeout=timeout)
        version_info = device.get_version()

        info = {
            'device_type': 'Atlas3 PCIe Switch',
            'model': version_info.model,
            'serial_number': version_info.serial_number,
            'firmware_version': version_info.mcu_version,
            'company': version_info.company
        }

        return device, info

    def prepare_for_commands(self, device: Any) -> None:
        """Clear serial buffers before sending commands"""
        if device._serial:
            device._serial.reset_input_buffer()
            device._serial.reset_output_buffer()

    def check_connection(self, device: Any) -> bool:
        """Check connection and reconnect if needed"""
        if not device.is_connected:
            device.connect()
            return device.is_connected
        return True

    def get_sysinfo(self, device: Any) -> dict:
        """Get Atlas3 system information"""
        # Get version info
        version = device.get_version()
        # Get host card info (temperatures, power, etc.)
        host_info = device.get_host_card_info()
        # Get port status
        port_status = device.get_port_status()

        return {
            'version': {
                'company': version.company,
                'model': version.model,
                'serial_number': version.serial_number,
                'mcu_version': version.mcu_version,
                'cpld_version': getattr(version, 'cpld_version', ''),
                'sbr_version': getattr(version, 'sbr_version', '')
            },
            'thermal': {
                'switch_temp': getattr(host_info.thermal, 'switch_temperature_celsius', 0)
            },
            'fan': {
                'switch_fan_rpm': getattr(host_info.fan, 'switch_fan_rpm', 0) if hasattr(host_info, 'fan') else 0
            },
            'power': {
                'voltage': getattr(host_info.power, 'power_voltage', 0),
                'current': getattr(host_info.power, 'load_current', 0),
                'power': getattr(host_info.power, 'load_power', 0)
            },
            'ports': {
                'chip_version': getattr(port_status, 'chip_version', ''),
                'upstream': _serialize_port_list(getattr(port_status, 'upstream_ports', [])),
                'ext_mcio': _serialize_port_list(getattr(port_status, 'ext_mcio_ports', [])),
                'int_mcio': _serialize_port_list(getattr(port_status, 'int_mcio_ports', [])),
                'straddle': _serialize_port_list(getattr(port_status, 'straddle_ports', []))
            }
        }

    def get_control_status(self, device: Any) -> dict:
        """Get Atlas3 current control settings"""
        status = {}

        # Get mode
        mode = device.get_mode()
        status['mode'] = mode.value if hasattr(mode, 'value') else mode

        # Get clock status
        clock = device.get_clock_status()
        status['clock'] = {
            'straddle_enabled': clock.straddle_enabled,
            'ext_mcio_enabled': clock.ext_mcio_enabled,
            'int_mcio_enabled': clock.int_mcio_enabled
        }

        # Get spread status
        spread = device.get_spread_status()
        status['spread'] = {
            'enabled': spread.enabled,
            'mode': spread.mode.value if spread.mode and hasattr(spread.mode, 'value') else 'off'
        }

        # Get FLIT status
        flit = device.get_flit_status()
        status['flit'] = {
            'station2': flit.station2,
            'station5': flit.station5,
            'station7': flit.station7,
            'station8': flit.station8
        }

        return status

    def execute_command(self, device: Any, command: str, params: dict) -> tuple[Any, bool]:
        """
        Execute an Atlas3 control command.

        Returns:
            Tuple of (result, requires_disconnect)
        """
        requires_disconnect = False

        if command == 'setmode':
            mode = int(params.get('mode', 1))
            from serialcables_atlas3.models import OperationMode
            result = device.set_mode(OperationMode(mode))
            requires_disconnect = True

        elif command == 'clk':
            enable = params.get('enable')
            if isinstance(enable, str):
                enable = enable.lower() == 'true'
            result = device.set_clock_output(enable)

        elif command == 'spread':
            mode = params.get('mode', 'off')
            from serialcables_atlas3.models import SpreadMode
            if mode == 'off':
                spread_mode = SpreadMode.OFF
            elif mode == '1':
                spread_mode = SpreadMode.DOWN_2500PPM
            elif mode == '2':
                spread_mode = SpreadMode.DOWN_5000PPM
            else:
                spread_mode = SpreadMode.OFF
            result = device.set_spread(spread_mode)

        elif command == 'flit':
            station = params.get('station')
            disable = params.get('disable')
            if isinstance(disable, str):
                disable = disable.lower() == 'true'
            result = device.set_flit_mode(station, disable)

        elif command == 'conrst':
            connector = params.get('connector')
            result = device.reset_connector(connector)

        elif command == 'error_counters':
            # Get port status to find active ports and their connectors
            port_status = device.get_port_status()
            active_ports = {}

            # Build map of active ports (negotiated_width > 0) with their connectors
            for port_list in [port_status.upstream_ports, port_status.ext_mcio_ports,
                              port_status.int_mcio_ports, port_status.straddle_ports]:
                if port_list:
                    for port in port_list:
                        port_num = getattr(port, 'port_number', 0)
                        neg_width = getattr(port, 'negotiated_width', 0)
                        if neg_width > 0:
                            active_ports[port_num] = getattr(port, 'connector', '')

            # Get error counters from the serialized API
            counters = device.get_error_counters()

            # Build response with only active ports
            error_data = {}
            for c in counters.counters:
                port_num = c.port_number
                if port_num in active_ports:
                    error_data[f'port_{port_num}'] = {
                        'port': port_num,
                        'connector': active_ports[port_num],
                        'link_up': True,
                        'port_rx': c.port_rx,
                        'bad_tlp': c.bad_tlp,
                        'bad_dllp': c.bad_dllp,
                        'rec_diag': c.rec_diag,
                        'link_down': c.link_down,
                        'flit_error': c.flit_error,
                        'total_errors': c.total_errors,
                        'has_errors': c.has_errors,
                    }

            result = {'success': True, 'response': error_data}

        elif command == 'clear_error_counters':
            try:
                device.clear_error_counters()
                result = {'success': True, 'response': None}
            except Exception as e:
                result = {'success': False, 'error': str(e)}

        else:
            raise ValueError(f'Unknown Atlas3 command: {command}')

        return result, requires_disconnect

    def get_available_commands(self) -> list[dict]:
        """Get list of available Atlas3 commands"""
        return [
            {
                'name': 'setmode',
                'description': 'Set operation mode (requires power cycle)',
                'parameters': [
                    {'name': 'mode', 'type': 'int', 'required': True, 'description': 'Mode number (1-4)'}
                ],
                'dangerous': True
            },
            {
                'name': 'clk',
                'description': 'Enable/disable clock output',
                'parameters': [
                    {'name': 'enable', 'type': 'bool', 'required': True, 'description': 'Enable clock output'}
                ]
            },
            {
                'name': 'spread',
                'description': 'Set spread spectrum mode',
                'parameters': [
                    {'name': 'mode', 'type': 'string', 'required': True, 'description': 'off, 1 (-0.25%), or 2 (-0.5%)'}
                ]
            },
            {
                'name': 'flit',
                'description': 'Enable/disable FLIT mode for a station',
                'parameters': [
                    {'name': 'station', 'type': 'string', 'required': True, 'description': 'Station identifier'},
                    {'name': 'disable', 'type': 'bool', 'required': True, 'description': 'Disable FLIT mode'}
                ]
            },
            {
                'name': 'conrst',
                'description': 'Reset a connector',
                'parameters': [
                    {'name': 'connector', 'type': 'string', 'required': True, 'description': 'Connector name'}
                ]
            },
            {
                'name': 'error_counters',
                'description': 'Get error counters for all active ports',
                'parameters': []
            },
            {
                'name': 'clear_error_counters',
                'description': 'Clear error counters',
                'parameters': [
                    {'name': 'port', 'type': 'int', 'required': False, 'description': 'Port number (optional, clears all if not specified)'}
                ]
            }
        ]


# Register this handler
HandlerRegistry.register('atlas3', Atlas3Handler)