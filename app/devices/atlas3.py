"""
Prometheus Atlas3 Device Implementation
Wraps the serialcables-atlas3 API
"""
import time
from datetime import datetime
from typing import Optional, Any

from app.devices.base import (
    BaseDevice, DeviceType, ConnectionState,
    DeviceInfo, DeviceStatus, CommandResult
)

# Try to import the actual Atlas3 API, fall back to mock for development
try:
    from serialcables_atlas3 import Atlas3
    ATLAS3_AVAILABLE = True
except ImportError:
    ATLAS3_AVAILABLE = False


class MockAtlas3:
    """Mock Atlas3 device for development/testing"""
    
    def __init__(self):
        self._connected = False
        self._port = None
    
    def connect(self, port: str, baudrate: int = 115200) -> bool:
        self._connected = True
        self._port = port
        return True
    
    def disconnect(self) -> bool:
        self._connected = False
        self._port = None
        return True
    
    def sysinfo(self) -> dict:
        return {
            'device_type': 'Atlas3 PCIe Gen6 Switch',
            'firmware_version': '1.2.3',
            'serial_number': 'ATL3-MOCK-001',
            'hardware_revision': 'Rev C',
            'switch_chip': 'Broadcom PEX89000',
            'num_ports': 16,
            'pcie_gen': 'Gen6',
            'max_lanes': 64,
            'temperature_sensors': 3,
            'uptime_hours': 127.5
        }
    
    def get_temperatures(self) -> dict:
        import random
        return {
            'switch_core': 45.0 + random.uniform(-2, 2),
            'board_ambient': 32.0 + random.uniform(-1, 1),
            'vrm': 52.0 + random.uniform(-3, 3)
        }
    
    def get_port_status(self) -> list[dict]:
        return [
            {'port': i, 'link_up': i % 3 != 0, 'speed': 'Gen6' if i % 3 != 0 else 'N/A',
             'width': f'x{4 if i < 8 else 8}' if i % 3 != 0 else 'N/A'}
            for i in range(16)
        ]
    
    def get_link_status(self, port: int = None) -> dict:
        return {
            'total_ports': 16,
            'links_up': 11,
            'links_down': 5,
            'ports': self.get_port_status()
        }
    
    def read_register(self, address: int) -> int:
        return 0xDEADBEEF
    
    def write_register(self, address: int, value: int) -> bool:
        return True
    
    def send_raw(self, command: str) -> str:
        return f"OK: {command}"

    def get_error_counters(self) -> dict:
        """Get error counters for all ports"""
        import random
        port_status = self.get_port_status()
        error_counters = {}

        for port_info in port_status:
            port_num = port_info['port']
            link_up = port_info['link_up']

            if link_up:
                # Generate mock error counts for active ports
                # Most counters should be 0, with occasional non-zero values
                error_counters[f'port_{port_num}'] = {
                    'port': port_num,
                    'link_up': True,
                    'bad_tlp': random.choice([0, 0, 0, 0, 0, 1, 2, 5]),
                    'bad_dllp': random.choice([0, 0, 0, 0, 0, 0, 1, 3]),
                    'receiver_error': random.choice([0, 0, 0, 0, 0, 0, 0, 1, 2]),
                    'replay_timeout': random.choice([0, 0, 0, 0, 0, 0, 1]),
                    'replay_num_rollover': random.choice([0, 0, 0, 0, 0, 0, 0, 0, 1]),
                    'correctable_error': random.choice([0, 0, 0, 0, 1, 2, 3, 8]),
                    'uncorrectable_error': random.choice([0, 0, 0, 0, 0, 0, 0, 0, 0, 1]),
                }

        return error_counters

    def clear_error_counters(self, port: int = None) -> bool:
        """Clear error counters for specified port or all ports"""
        # In mock, just return success
        return True


class Atlas3Device(BaseDevice):
    """
    Atlas3 PCIe Gen6 Switch device implementation.
    Wraps the serialcables-atlas3 Python API.
    """
    
    def __init__(self):
        super().__init__(DeviceType.ATLAS3)
        self._device: Optional[Any] = None
        self._using_mock = not ATLAS3_AVAILABLE
    
    def connect(self, com_port: str, baudrate: int = 115200) -> bool:
        """Connect to Atlas3 device"""
        with self._lock:
            try:
                self._update_state(ConnectionState.CONNECTING)
                self.com_port = com_port
                self.baudrate = baudrate
                
                # Use real API or mock
                if ATLAS3_AVAILABLE:
                    self._device = Atlas3()
                    result = self._device.connect(com_port, baudrate)
                else:
                    self._device = MockAtlas3()
                    result = self._device.connect(com_port, baudrate)
                
                if result:
                    self._update_state(ConnectionState.CONNECTED)
                    self._status.com_port = com_port
                    # Fetch initial device info
                    self._refresh_device_info()
                    return True
                else:
                    self._update_state(ConnectionState.ERROR)
                    return False
                    
            except Exception as e:
                self._update_state(ConnectionState.ERROR)
                self._status.extra['last_error'] = str(e)
                return False
    
    def disconnect(self) -> bool:
        """Disconnect from Atlas3 device"""
        with self._lock:
            try:
                if self._device:
                    self._device.disconnect()
                    self._device = None
                self._update_state(ConnectionState.DISCONNECTED)
                self._status.com_port = ""
                return True
            except Exception as e:
                self._status.extra['last_error'] = str(e)
                return False
    
    def _refresh_device_info(self):
        """Refresh device information from sysinfo"""
        try:
            info = self._device.sysinfo()
            self._device_info.firmware_version = info.get('firmware_version', '')
            self._device_info.serial_number = info.get('serial_number', '')
            self._device_info.hardware_revision = info.get('hardware_revision', '')
            self._device_info.extra = {
                k: v for k, v in info.items() 
                if k not in ['firmware_version', 'serial_number', 'hardware_revision']
            }
        except Exception:
            pass
    
    def get_sysinfo(self) -> CommandResult:
        """Get system information"""
        start_time = time.perf_counter()
        try:
            if not self._connected or not self._device:
                return CommandResult(
                    success=False,
                    command='sysinfo',
                    response=None,
                    error='Device not connected'
                )
            
            info = self._device.sysinfo()
            elapsed = (time.perf_counter() - start_time) * 1000
            
            return CommandResult(
                success=True,
                command='sysinfo',
                response=info,
                execution_time_ms=elapsed
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return CommandResult(
                success=False,
                command='sysinfo',
                response=None,
                error=str(e),
                execution_time_ms=elapsed
            )
    
    def get_status(self) -> DeviceStatus:
        """Get current device status"""
        if not self._connected or not self._device:
            return self._status
        
        try:
            with self._lock:
                # Update temperatures
                temps = self._device.get_temperatures()
                self._status.temperatures = temps
                
                # Update link status
                link_status = self._device.get_link_status()
                self._status.link_status = link_status
                
                # Update timestamp
                self._status.last_update = datetime.now().isoformat()
                
        except Exception as e:
            self._status.extra['last_error'] = str(e)
        
        return self._status
    
    def send_command(self, command: str, *args, **kwargs) -> CommandResult:
        """Send a command to the Atlas3 device"""
        start_time = time.perf_counter()
        
        if not self._connected or not self._device:
            return CommandResult(
                success=False,
                command=command,
                response=None,
                error='Device not connected'
            )
        
        try:
            # Map command names to device methods
            command_map = {
                'sysinfo': lambda: self._device.sysinfo(),
                'temperatures': lambda: self._device.get_temperatures(),
                'port_status': lambda: self._device.get_port_status(),
                'link_status': lambda: self._device.get_link_status(),
                'read_register': lambda: self._device.read_register(kwargs.get('address', 0)),
                'write_register': lambda: self._device.write_register(
                    kwargs.get('address', 0), kwargs.get('value', 0)
                ),
                'raw': lambda: self._device.send_raw(kwargs.get('raw_command', '')),
                'error_counters': lambda: self._device.get_error_counters(),
                'clear_error_counters': lambda: self._device.clear_error_counters(
                    kwargs.get('port', None)
                )
            }
            
            if command in command_map:
                response = command_map[command]()
                elapsed = (time.perf_counter() - start_time) * 1000
                return CommandResult(
                    success=True,
                    command=command,
                    response=response,
                    execution_time_ms=elapsed
                )
            else:
                elapsed = (time.perf_counter() - start_time) * 1000
                return CommandResult(
                    success=False,
                    command=command,
                    response=None,
                    error=f'Unknown command: {command}',
                    execution_time_ms=elapsed
                )
                
        except Exception as e:
            elapsed = (time.perf_counter() - start_time) * 1000
            return CommandResult(
                success=False,
                command=command,
                response=None,
                error=str(e),
                execution_time_ms=elapsed
            )
    
    def get_available_commands(self) -> list[dict]:
        """Get list of available commands for Atlas3"""
        return [
            {
                'name': 'sysinfo',
                'description': 'Get system information',
                'parameters': []
            },
            {
                'name': 'temperatures',
                'description': 'Get temperature readings',
                'parameters': []
            },
            {
                'name': 'port_status',
                'description': 'Get status of all ports',
                'parameters': []
            },
            {
                'name': 'link_status',
                'description': 'Get PCIe link status summary',
                'parameters': []
            },
            {
                'name': 'read_register',
                'description': 'Read a register value',
                'parameters': [
                    {'name': 'address', 'type': 'int', 'description': 'Register address (hex)'}
                ]
            },
            {
                'name': 'write_register',
                'description': 'Write a register value',
                'parameters': [
                    {'name': 'address', 'type': 'int', 'description': 'Register address (hex)'},
                    {'name': 'value', 'type': 'int', 'description': 'Value to write (hex)'}
                ]
            },
            {
                'name': 'raw',
                'description': 'Send raw command',
                'parameters': [
                    {'name': 'raw_command', 'type': 'str', 'description': 'Raw command string'}
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
                    {'name': 'port', 'type': 'int', 'description': 'Port number (optional, clears all if not specified)', 'optional': True}
                ]
            }
        ]
    
    def get_temperatures(self) -> CommandResult:
        """Convenience method for temperature readings"""
        return self.send_command('temperatures')
    
    def get_port_status(self) -> CommandResult:
        """Convenience method for port status"""
        return self.send_command('port_status')
