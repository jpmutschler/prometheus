"""
Prometheus HYDRA Device Handler
Handles HYDRA JBOF controller specific API operations
"""
from typing import Any
from .base_handler import BaseDeviceHandler, HandlerRegistry


def _clean_string(s: Any) -> Any:
    """Strip trailing box-drawing characters and whitespace from device strings"""
    if not isinstance(s, str):
        return s
    return s.rstrip('║│┃ \t\r\n')


class HydraHandler(BaseDeviceHandler):
    """Handler for HYDRA JBOF controller devices"""

    device_type = "hydra"

    def connect(self, com_port: str, timeout: float = 10.0) -> tuple[Any, dict]:
        """Connect to a HYDRA device"""
        from serialcables_hydra import JBOFController

        device = JBOFController(com_port, timeout=timeout)
        if not device.connect():
            raise Exception('Failed to connect to HYDRA')

        version_info = device.get_version_info()

        info = {
            'device_type': 'HYDRA JBOF',
            'model': _clean_string(version_info.get('model', 'PCIe Gen6 8Bays JBOF')),
            'serial_number': _clean_string(version_info.get('serial_number', '')),
            'firmware_version': _clean_string(version_info.get('version', '')),
            'company': _clean_string(version_info.get('company', 'Serial Cables'))
        }

        return device, info

    def get_sysinfo(self, device: Any) -> dict:
        """Get HYDRA system information"""
        # Get complete system info
        sys_info = device.get_system_info()
        env_data = device.get_environmental_data()
        slot_power = device.get_slot_power_status()

        # Build slot info - combine sys_info.slots with env_data temperatures and slot_power
        temperatures = env_data.get('temperatures', {})
        slots_list = []

        # Create slots for all 8 bays, using data from sys_info.slots where available
        sys_slots_by_num = {slot.slot_number: slot for slot in sys_info.slots} if sys_info.slots else {}

        for slot_num in range(1, 9):
            slot_data = sys_slots_by_num.get(slot_num)
            power_status = slot_power.get(slot_num, 'unknown')
            temp_key = f'slot_{slot_num}'
            temperature = temperatures.get(temp_key, 0)

            if slot_data:
                slots_list.append({
                    'slot_number': slot_num,
                    'present': slot_data.present or power_status == 'on',
                    'paddle_card': slot_data.paddle_card,
                    'interposer': slot_data.interposer,
                    'edsff_type': slot_data.edsff_type,
                    'power_status': power_status,
                    'temperature': slot_data.temperature or temperature,
                    'voltage': slot_data.voltage,
                    'current': slot_data.current,
                    'power': slot_data.power
                })
            else:
                # Slot not in sys_info.slots - create from power status and env data
                slots_list.append({
                    'slot_number': slot_num,
                    'present': power_status == 'on',
                    'paddle_card': 'unknown',
                    'interposer': 'unknown',
                    'edsff_type': 'unknown',
                    'power_status': power_status,
                    'temperature': temperature,
                    'voltage': 0,
                    'current': 0,
                    'power': 0
                })

        return {
            'version': {
                'company': _clean_string(sys_info.company),
                'model': _clean_string(sys_info.model),
                'serial_number': _clean_string(sys_info.serial_number),
                'firmware_version': _clean_string(sys_info.firmware_version),
                'build_time': _clean_string(sys_info.build_time)
            },
            'thermal': {
                'mcu_temp': temperatures.get('mcu', 0)
            },
            'fans': {
                'fan1_rpm': sys_info.fan1_rpm,
                'fan2_rpm': sys_info.fan2_rpm
            },
            'power': {
                'psu_voltage': sys_info.psu_voltage
            },
            'slots': slots_list
        }

    def get_control_status(self, device: Any) -> dict:
        """Get HYDRA current control settings"""
        # For Hydra, we can get slot power status
        slot_power = device.get_slot_power_status()
        return {'slot_power': slot_power}

    def execute_command(self, device: Any, command: str, params: dict) -> tuple[Any, bool]:
        """
        Execute a HYDRA control command.

        Returns:
            Tuple of (result, requires_disconnect)
        """
        from serialcables_hydra.controller import PowerState, BuzzerState, SignalLevel

        requires_disconnect = False

        if command == 'syspwr':
            state = PowerState.ON if params.get('state') == 'on' else PowerState.OFF
            result = device.system_power(state)
            if params.get('state') == 'off':
                requires_disconnect = True

        elif command == 'ssdpwr':
            slot = params.get('slot')
            state = PowerState.ON if params.get('state') == 'on' else PowerState.OFF
            result = device.slot_power(slot, state)

        elif command == 'ssdrst':
            slot = params.get('slot')
            result = device.ssd_reset(slot)

        elif command == 'smbrst':
            slot = params.get('slot')
            result = device.smbus_reset(slot)

        elif command == 'hled':
            slot = params.get('slot')
            state = PowerState.ON if params.get('state') == 'on' else PowerState.OFF
            result = device.control_host_led(slot, state)

        elif command == 'fled':
            slot = params.get('slot')
            state = PowerState.ON if params.get('state') == 'on' else PowerState.OFF
            result = device.control_fault_led(slot, state)

        elif command == 'buz':
            state_str = params.get('state', '').lower()
            if state_str == 'on':
                state = BuzzerState.ON
            elif state_str == 'off':
                state = BuzzerState.OFF
            elif state_str == 'enable':
                state = BuzzerState.ENABLE
            elif state_str == 'disable':
                state = BuzzerState.DISABLE
            else:
                raise ValueError(f'Invalid buzzer state: {state_str}')
            result = device.control_buzzer(state)

        elif command == 'pwmctrl':
            fan_id = int(params.get('fan_id', 1))
            duty = int(params.get('duty', 50))
            result = device.set_fan_speed(fan_id, duty)

        elif command == 'dual':
            slot = params.get('slot')
            enabled = params.get('enabled')
            if isinstance(enabled, str):
                enabled = enabled.lower() == 'true'
            result = device.set_dual_port(slot, enabled)

        elif command == 'pwrdis':
            slot = params.get('slot')
            level_str = params.get('level', 'high').lower()
            level = SignalLevel.HIGH if level_str == 'high' else SignalLevel.LOW
            result = device.set_pwrdis(slot, level)

        else:
            raise ValueError(f'Unknown Hydra command: {command}')

        return result, requires_disconnect

    def get_available_commands(self) -> list[dict]:
        """Get list of available HYDRA commands"""
        return [
            {
                'name': 'syspwr',
                'description': 'Control system power',
                'parameters': [
                    {'name': 'state', 'type': 'string', 'required': True, 'description': 'on or off'}
                ],
                'dangerous': True
            },
            {
                'name': 'ssdpwr',
                'description': 'Control slot power',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'},
                    {'name': 'state', 'type': 'string', 'required': True, 'description': 'on or off'}
                ]
            },
            {
                'name': 'ssdrst',
                'description': 'Reset SSD in slot',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'}
                ]
            },
            {
                'name': 'smbrst',
                'description': 'Reset SMBus for slot',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'}
                ]
            },
            {
                'name': 'hled',
                'description': 'Control host LED',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'},
                    {'name': 'state', 'type': 'string', 'required': True, 'description': 'on or off'}
                ]
            },
            {
                'name': 'fled',
                'description': 'Control fault LED',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'},
                    {'name': 'state', 'type': 'string', 'required': True, 'description': 'on or off'}
                ]
            },
            {
                'name': 'buz',
                'description': 'Control buzzer',
                'parameters': [
                    {'name': 'state', 'type': 'string', 'required': True, 'description': 'on, off, enable, or disable'}
                ]
            },
            {
                'name': 'pwmctrl',
                'description': 'Set fan speed (PWM duty cycle)',
                'parameters': [
                    {'name': 'fan_id', 'type': 'int', 'required': True, 'description': 'Fan ID (1 or 2)'},
                    {'name': 'duty', 'type': 'int', 'required': True, 'description': 'Duty cycle (0-100)'}
                ]
            },
            {
                'name': 'dual',
                'description': 'Enable/disable dual port mode',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'},
                    {'name': 'enabled', 'type': 'bool', 'required': True, 'description': 'Enable dual port'}
                ]
            },
            {
                'name': 'pwrdis',
                'description': 'Set power disable signal level',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'},
                    {'name': 'level', 'type': 'string', 'required': True, 'description': 'high or low'}
                ]
            }
        ]


# Register this handler
HandlerRegistry.register('hydra', HydraHandler)