"""
Prometheus Base Device Handler
Abstract interface for device-specific API operations
"""
from abc import ABC, abstractmethod
from typing import Any, Optional
from app.devices.base import CommandResult


class BaseDeviceHandler(ABC):
    """
    Abstract base class for device-specific API handlers.

    Each device type (Atlas3, HYDRA, future devices) implements this interface
    to handle device-specific data extraction, serialization, and command execution.
    """

    # Device type identifier (e.g., 'atlas3', 'hydra')
    device_type: str = ""

    @abstractmethod
    def connect(self, com_port: str, timeout: float = 10.0) -> tuple[Any, dict]:
        """
        Connect to a device and return the device object and info dict.

        Args:
            com_port: COM port to connect to
            timeout: Connection timeout in seconds

        Returns:
            Tuple of (device_object, info_dict)

        Raises:
            Exception on connection failure
        """
        pass

    @abstractmethod
    def get_sysinfo(self, device: Any) -> dict:
        """
        Get system information from the device.

        Args:
            device: The connected device object

        Returns:
            Standardized sysinfo dictionary
        """
        pass

    @abstractmethod
    def get_control_status(self, device: Any) -> dict:
        """
        Get current control settings from the device.

        Args:
            device: The connected device object

        Returns:
            Dictionary of current control settings
        """
        pass

    @abstractmethod
    def execute_command(self, device: Any, command: str, params: dict) -> tuple[Any, bool]:
        """
        Execute a control command on the device.

        Args:
            device: The connected device object
            command: Command name to execute
            params: Command parameters

        Returns:
            Tuple of (result, requires_disconnect)

        Raises:
            ValueError for unknown commands
        """
        pass

    @abstractmethod
    def get_available_commands(self) -> list[dict]:
        """
        Get list of available commands for this device type.

        Returns:
            List of command definitions with name, description, and parameters
        """
        pass

    def prepare_for_commands(self, device: Any) -> None:
        """
        Prepare device for command execution (e.g., clear buffers).
        Override in subclass if needed.

        Args:
            device: The connected device object
        """
        pass

    def check_connection(self, device: Any) -> bool:
        """
        Check if device is still connected, attempt reconnect if needed.
        Override in subclass if needed.

        Args:
            device: The connected device object

        Returns:
            True if connected (or successfully reconnected)
        """
        return True


class HandlerRegistry:
    """
    Registry for device handlers.
    Allows dynamic registration of new device types.
    """
    _handlers: dict[str, type[BaseDeviceHandler]] = {}
    _instances: dict[str, BaseDeviceHandler] = {}

    @classmethod
    def register(cls, device_type: str, handler_class: type[BaseDeviceHandler]) -> None:
        """
        Register a handler class for a device type.

        Args:
            device_type: Device type identifier (e.g., 'atlas3')
            handler_class: Handler class to register
        """
        cls._handlers[device_type] = handler_class

    @classmethod
    def get(cls, device_type: str) -> Optional[BaseDeviceHandler]:
        """
        Get a handler instance for a device type.

        Args:
            device_type: Device type identifier

        Returns:
            Handler instance or None if not registered
        """
        if device_type not in cls._handlers:
            return None

        # Create instance if not cached
        if device_type not in cls._instances:
            cls._instances[device_type] = cls._handlers[device_type]()

        return cls._instances[device_type]

    @classmethod
    def get_all_types(cls) -> list[str]:
        """Get all registered device types."""
        return list(cls._handlers.keys())

    @classmethod
    def is_registered(cls, device_type: str) -> bool:
        """Check if a device type is registered."""
        return device_type in cls._handlers


def get_handler(device_type: str) -> Optional[BaseDeviceHandler]:
    """
    Convenience function to get a handler for a device type.

    Args:
        device_type: Device type identifier

    Returns:
        Handler instance or None if not registered
    """
    return HandlerRegistry.get(device_type)