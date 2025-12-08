"""
Prometheus Device Abstraction Layer
Base class for all Serial Cables devices
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional, Any
import threading
import json


class DeviceType(Enum):
    """Supported device types"""
    ATLAS3 = "atlas3"
    HYDRA = "hydra"


class ConnectionState(Enum):
    """Device connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class DeviceInfo:
    """Device information structure"""
    device_type: str = ""
    firmware_version: str = ""
    serial_number: str = ""
    hardware_revision: str = ""
    manufacturer: str = "Serial Cables, LLC"
    extra: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DeviceStatus:
    """Real-time device status"""
    connected: bool = False
    state: str = ConnectionState.DISCONNECTED.value
    com_port: str = ""
    temperatures: dict = field(default_factory=dict)
    link_status: dict = field(default_factory=dict)
    error_counters: dict = field(default_factory=dict)
    last_update: str = ""
    extra: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass 
class CommandResult:
    """Result of a device command"""
    success: bool
    command: str
    response: Any
    error: Optional[str] = None
    timestamp: str = ""
    execution_time_ms: float = 0.0
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)
    
    def to_text(self) -> str:
        """Format as human-readable text for export"""
        lines = [
            f"Command: {self.command}",
            f"Timestamp: {self.timestamp}",
            f"Success: {self.success}",
            f"Execution Time: {self.execution_time_ms:.2f} ms",
            "-" * 50,
        ]
        if self.error:
            lines.append(f"Error: {self.error}")
        else:
            if isinstance(self.response, dict):
                for key, value in self.response.items():
                    lines.append(f"{key}: {value}")
            elif isinstance(self.response, list):
                for item in self.response:
                    lines.append(str(item))
            else:
                lines.append(str(self.response))
        return "\n".join(lines)


class BaseDevice(ABC):
    """
    Abstract base class for Serial Cables devices.
    Provides common interface for Atlas3 and HYDRA devices.
    """
    
    def __init__(self, device_type: DeviceType):
        self.device_type = device_type
        self.com_port: Optional[str] = None
        self.baudrate: int = 115200
        self.timeout: float = 1.0
        self._connection_state = ConnectionState.DISCONNECTED
        self._device_info = DeviceInfo(device_type=device_type.value)
        self._status = DeviceStatus()
        self._lock = threading.Lock()
        self._connected = False
    
    @property
    def connected(self) -> bool:
        return self._connected
    
    @property
    def state(self) -> ConnectionState:
        return self._connection_state
    
    @property
    def info(self) -> DeviceInfo:
        return self._device_info
    
    @property
    def status(self) -> DeviceStatus:
        return self._status
    
    @abstractmethod
    def connect(self, com_port: str, baudrate: int = 115200) -> bool:
        """Connect to the device on specified COM port"""
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """Disconnect from the device"""
        pass
    
    @abstractmethod
    def get_sysinfo(self) -> CommandResult:
        """Get system information (common to all devices)"""
        pass
    
    @abstractmethod
    def get_status(self) -> DeviceStatus:
        """Get current device status"""
        pass
    
    @abstractmethod
    def send_command(self, command: str, *args, **kwargs) -> CommandResult:
        """Send a command to the device"""
        pass
    
    @abstractmethod
    def get_available_commands(self) -> list[dict]:
        """Get list of available commands for this device"""
        pass
    
    def _update_state(self, state: ConnectionState):
        """Update connection state"""
        self._connection_state = state
        self._status.state = state.value
        self._status.connected = (state == ConnectionState.CONNECTED)
        self._connected = self._status.connected


class DeviceManager:
    """
    Manages multiple device connections.
    Singleton pattern for global device access.
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._devices = {}
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
    
    def register_device(self, device_id: str, device: BaseDevice) -> None:
        """Register a device instance"""
        self._devices[device_id] = device
    
    def get_device(self, device_id: str) -> Optional[BaseDevice]:
        """Get a device by ID"""
        return self._devices.get(device_id)
    
    def get_all_devices(self) -> dict[str, BaseDevice]:
        """Get all registered devices"""
        return self._devices.copy()
    
    def remove_device(self, device_id: str) -> bool:
        """Remove a device"""
        if device_id in self._devices:
            device = self._devices.pop(device_id)
            if device.connected:
                device.disconnect()
            return True
        return False
    
    def get_connected_devices(self) -> dict[str, BaseDevice]:
        """Get only connected devices"""
        return {k: v for k, v in self._devices.items() if v.connected}


# Global device manager instance
device_manager = DeviceManager()
