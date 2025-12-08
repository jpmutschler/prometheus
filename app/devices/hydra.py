"""
Prometheus HYDRA Device Implementation
Wraps the serialcables-hydra API
"""
import time
from datetime import datetime
from typing import Optional, Any

from app.devices.base import (
    BaseDevice, DeviceType, ConnectionState,
    DeviceInfo, DeviceStatus, CommandResult
)

# Try to import the actual HYDRA API, fall back to mock for development
try:
    from serialcables_hydra import Hydra
    HYDRA_AVAILABLE = True
except ImportError:
    HYDRA_AVAILABLE = False


class MockHydra:
    """Mock HYDRA device for development/testing"""
    
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
            'device_type': 'HYDRA JBOF Controller',
            'firmware_version': '2.1.0',
            'serial_number': 'HYD-MOCK-001',
            'hardware_revision': 'Rev B',
            'controller_chip': 'Serial Cables HYDRA-1',
            'num_drive_bays': 24,
            'num_host_ports': 4,
            'pcie_gen': 'Gen5',
            'nvme_version': '2.0',
            'uptime_hours': 842.3
        }
    
    def get_temperatures(self) -> dict:
        import random
        return {
            'controller': 48.0 + random.uniform(-2, 2),
            'board_ambient': 35.0 + random.uniform(-1, 1),
            'backplane': 42.0 + random.uniform(-2, 2),
            'psu_1': 38.0 + random.uniform(-1, 1),
            'psu_2': 39.0 + random.uniform(-1, 1)
        }
    
    def get_drive_status(self) -> list[dict]:
        import random
        drives = []
        for i in range(24):
            present = random.random() > 0.3
            drives.append({
                'bay': i,
                'present': present,
                'model': 'Samsung PM1733' if present else None,
                'serial': f'S5XXNA0R{i:06d}' if present else None,
                'capacity_tb': 3.84 if present else None,
                'health': 'Good' if present else None,
                'temperature': 35 + random.randint(0, 10) if present else None
            })
        return drives
    
    def get_host_ports(self) -> list[dict]:
        return [
            {'port': i, 'link_up': i < 3, 'speed': 'Gen5' if i < 3 else 'N/A',
             'width': 'x8' if i < 3 else 'N/A', 'host_id': f'Host-{i}' if i < 3 else None}
            for i in range(4)
        ]
    
    def get_enclosure_status(self) -> dict:
        return {
            'fans': [
                {'id': 0, 'rpm': 4200, 'status': 'OK'},
                {'id': 1, 'rpm': 4180, 'status': 'OK'},
                {'id': 2, 'rpm': 4220, 'status': 'OK'},
                {'id': 3, 'rpm': 4190, 'status': 'OK'}
            ],
            'psus': [
                {'id': 0, 'status': 'OK', 'watts': 450, 'efficiency': 94.2},
                {'id': 1, 'status': 'OK', 'watts': 445, 'efficiency': 94.0}
            ],
            'power_total_watts': 895
        }
    
    def read_register(self, address: int) -> int:
        return 0xCAFEBABE
    
    def write_register(self, address: int, value: int) -> bool:
        return True
    
    def send_raw(self, command: str) -> str:
        return f"OK: {command}"
    
    def identify_drive(self, bay: int, enable: bool = True) -> bool:
        return True
    
    def get_nvme_smart(self, bay: int) -> dict:
        return {
            'bay': bay,
            'critical_warning': 0,
            'temperature': 38,
            'available_spare': 100,
            'available_spare_threshold': 10,
            'percentage_used': 2,
            'data_units_read': 123456789,
            'data_units_written': 987654321,
            'power_cycles': 42,
            'power_on_hours': 8760,
            'unsafe_shutdowns': 0
        }


class HydraDevice(BaseDevice):
    """
    HYDRA JBOF Controller device implementation.
    Wraps the serialcables-hydra Python API.
    """
    
    def __init__(self):
        super().__init__(DeviceType.HYDRA)
        self._device: Optional[Any] = None
        self._using_mock = not HYDRA_AVAILABLE
    
    def connect(self, com_port: str, baudrate: int = 115200) -> bool:
        """Connect to HYDRA device"""
        with self._lock:
            try:
                self._update_state(ConnectionState.CONNECTING)
                self.com_port = com_port
                self.baudrate = baudrate
                
                # Use real API or mock
                if HYDRA_AVAILABLE:
                    self._device = Hydra()
                    result = self._device.connect(com_port, baudrate)
                else:
                    self._device = MockHydra()
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
        """Disconnect from HYDRA device"""
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
                
                # Update link status (host ports)
                host_ports = self._device.get_host_ports()
                self._status.link_status = {
                    'host_ports': host_ports,
                    'links_up': sum(1 for p in host_ports if p['link_up']),
                    'total_ports': len(host_ports)
                }
                
                # Add drive summary to extra
                drives = self._device.get_drive_status()
                self._status.extra['drives'] = {
                    'total_bays': len(drives),
                    'drives_present': sum(1 for d in drives if d['present']),
                    'drives_healthy': sum(1 for d in drives if d.get('health') == 'Good')
                }
                
                # Update timestamp
                self._status.last_update = datetime.now().isoformat()
                
        except Exception as e:
            self._status.extra['last_error'] = str(e)
        
        return self._status
    
    def send_command(self, command: str, *args, **kwargs) -> CommandResult:
        """Send a command to the HYDRA device"""
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
                'drive_status': lambda: self._device.get_drive_status(),
                'host_ports': lambda: self._device.get_host_ports(),
                'enclosure_status': lambda: self._device.get_enclosure_status(),
                'nvme_smart': lambda: self._device.get_nvme_smart(kwargs.get('bay', 0)),
                'identify_drive': lambda: self._device.identify_drive(
                    kwargs.get('bay', 0), kwargs.get('enable', True)
                ),
                'read_register': lambda: self._device.read_register(kwargs.get('address', 0)),
                'write_register': lambda: self._device.write_register(
                    kwargs.get('address', 0), kwargs.get('value', 0)
                ),
                'raw': lambda: self._device.send_raw(kwargs.get('raw_command', ''))
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
        """Get list of available commands for HYDRA"""
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
                'name': 'drive_status',
                'description': 'Get status of all drive bays',
                'parameters': []
            },
            {
                'name': 'host_ports',
                'description': 'Get host port status',
                'parameters': []
            },
            {
                'name': 'enclosure_status',
                'description': 'Get enclosure status (fans, PSUs)',
                'parameters': []
            },
            {
                'name': 'nvme_smart',
                'description': 'Get NVMe SMART data for a drive',
                'parameters': [
                    {'name': 'bay', 'type': 'int', 'description': 'Drive bay number'}
                ]
            },
            {
                'name': 'identify_drive',
                'description': 'Toggle drive identify LED',
                'parameters': [
                    {'name': 'bay', 'type': 'int', 'description': 'Drive bay number'},
                    {'name': 'enable', 'type': 'bool', 'description': 'Enable or disable LED'}
                ]
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
            }
        ]
    
    def get_drive_status(self) -> CommandResult:
        """Convenience method for drive status"""
        return self.send_command('drive_status')
    
    def get_enclosure_status(self) -> CommandResult:
        """Convenience method for enclosure status"""
        return self.send_command('enclosure_status')
