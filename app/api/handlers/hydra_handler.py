"""
Prometheus HYDRA Device Handler
Handles HYDRA JBOF controller specific API operations
"""
from typing import Any, Optional
from .base_handler import BaseDeviceHandler, HandlerRegistry
from app.logger import get_logger

logger = get_logger('hydra_handler')


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
        """Get HYDRA system information including NVMe drive data via MCTP"""
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

            slot_info = {
                'slot_number': slot_num,
                'present': False,
                'paddle_card': 'unknown',
                'interposer': 'unknown',
                'edsff_type': 'unknown',
                'power_status': power_status,
                'temperature': temperature,
                'voltage': 0,
                'current': 0,
                'power': 0,
                # NVMe drive info (populated via MCTP if drive present)
                'nvme': None
            }

            if slot_data:
                slot_info.update({
                    'present': slot_data.present or power_status == 'on',
                    'paddle_card': slot_data.paddle_card,
                    'interposer': slot_data.interposer,
                    'edsff_type': slot_data.edsff_type,
                    'temperature': slot_data.temperature or temperature,
                    'voltage': slot_data.voltage,
                    'current': slot_data.current,
                    'power': slot_data.power
                })
            else:
                slot_info['present'] = power_status == 'on'

            # Get NVMe drive info via MCTP for populated slots
            if slot_info['present'] and power_status == 'on':
                nvme_info = self._get_nvme_drive_info(device, slot_num)
                if nvme_info:
                    slot_info['nvme'] = nvme_info

            slots_list.append(slot_info)

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

    def _get_nvme_drive_info(self, device: Any, slot: int) -> Optional[dict]:
        """
        Get NVMe drive information via MCTP for a specific slot.
        Uses Hydra's high-level MCTP methods to get serial number and health status.
        """
        nvme_info = {}

        try:
            # Get drive serial number
            sn_result = device.mctp_get_serial_number(slot=slot, timeout=2.0)
            if sn_result.success:
                nvme_info['serial_number'] = sn_result.serial_number.strip()
            else:
                nvme_info['serial_number'] = None
                nvme_info['serial_error'] = sn_result.error
        except Exception as e:
            logger.debug(f'Failed to get serial number for slot {slot}: {e}')
            nvme_info['serial_number'] = None

        try:
            # Get drive health status
            health_result = device.mctp_get_health_status(slot=slot, timeout=2.0)
            if health_result.success:
                nvme_info['health'] = {
                    'temperature_celsius': health_result.composite_temperature_celsius,
                    'available_spare': health_result.available_spare,
                    'available_spare_threshold': health_result.available_spare_threshold,
                    'percentage_used': health_result.percentage_used,
                    'critical_warning': health_result.critical_warning
                }
            else:
                nvme_info['health'] = None
                nvme_info['health_error'] = health_result.error
        except Exception as e:
            logger.debug(f'Failed to get health status for slot {slot}: {e}')
            nvme_info['health'] = None

        # Only return if we got at least some data
        if nvme_info.get('serial_number') or nvme_info.get('health'):
            return nvme_info
        return None

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

        # NVMe-MI over MCTP commands
        elif command == 'mctp_serial':
            slot = int(params.get('slot'))
            sn_result = device.mctp_get_serial_number(slot=slot, timeout=3.0)
            result = {
                'success': sn_result.success,
                'slot': slot,
                'serial_number': sn_result.serial_number if sn_result.success else None,
                'error': sn_result.error if not sn_result.success else None
            }

        elif command == 'mctp_health':
            slot = int(params.get('slot'))
            health_result = device.mctp_get_health_status(slot=slot, timeout=3.0)
            if health_result.success:
                result = {
                    'success': True,
                    'slot': slot,
                    'temperature_celsius': health_result.composite_temperature_celsius,
                    'available_spare': health_result.available_spare,
                    'available_spare_threshold': health_result.available_spare_threshold,
                    'percentage_used': health_result.percentage_used,
                    'critical_warning': health_result.critical_warning
                }
            else:
                result = {
                    'success': False,
                    'slot': slot,
                    'error': health_result.error
                }

        elif command == 'mctp_pause':
            slot = int(params.get('slot'))
            mctp_result = device.mctp_pause(slot=slot)
            result = {'success': mctp_result.success, 'slot': slot}

        elif command == 'mctp_resume':
            slot = int(params.get('slot'))
            mctp_result = device.mctp_resume(slot=slot)
            result = {'success': mctp_result.success, 'slot': slot}

        elif command == 'mctp_abort':
            slot = int(params.get('slot'))
            mctp_result = device.mctp_abort(slot=slot)
            result = {'success': mctp_result.success, 'slot': slot}

        elif command == 'mctp_status':
            slot = int(params.get('slot'))
            mctp_result = device.mctp_status(slot=slot)
            result = {
                'success': mctp_result.success,
                'slot': slot,
                'raw_response': mctp_result.raw_response
            }

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
            },
            # NVMe-MI over MCTP commands
            {
                'name': 'mctp_serial',
                'description': 'Get NVMe drive serial number via MCTP',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'}
                ]
            },
            {
                'name': 'mctp_health',
                'description': 'Get NVMe drive health status via MCTP',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'}
                ]
            },
            {
                'name': 'mctp_pause',
                'description': 'Pause MCTP transactions for a slot',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'}
                ]
            },
            {
                'name': 'mctp_resume',
                'description': 'Resume MCTP transactions for a slot',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'}
                ]
            },
            {
                'name': 'mctp_abort',
                'description': 'Abort current MCTP transaction for a slot',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'}
                ]
            },
            {
                'name': 'mctp_status',
                'description': 'Get MCTP status for a slot',
                'parameters': [
                    {'name': 'slot', 'type': 'int', 'required': True, 'description': 'Slot number (1-8)'}
                ]
            }
        ]


# Register this handler
HandlerRegistry.register('hydra', HydraHandler)