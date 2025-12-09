"""
Prometheus Device Detection Module
Auto-detects device type by sending 'ver' command via raw serial
"""
import serial
import serial.tools.list_ports
import time
import re
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from app.logger import get_logger

logger = get_logger('detection')


@dataclass
class DetectionResult:
    """Result of device detection attempt"""
    success: bool
    device_type: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    com_port: Optional[str] = None
    raw_response: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'device_type': self.device_type,
            'model': self.model,
            'serial_number': self.serial_number,
            'firmware_version': self.firmware_version,
            'com_port': self.com_port,
            'error': self.error
        }


class DeviceSignatures:
    """
    Manages device signature patterns for identification.
    Signatures are loaded from a JSON configuration file.
    """

    _instance = None
    _signatures: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_signatures()
        return cls._instance

    def _load_signatures(self):
        """Load device signatures from configuration file"""
        config_path = Path(__file__).parent / 'device_signatures.json'

        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    self._signatures = json.load(f)
                logger.info(f'Loaded {len(self._signatures.get("devices", []))} device signatures')
            except Exception as e:
                logger.error(f'Failed to load device signatures: {e}')
                self._signatures = self._get_default_signatures()
        else:
            logger.info('No device signatures file found, using defaults')
            self._signatures = self._get_default_signatures()
            self._save_signatures(config_path)

    def _save_signatures(self, path: Path):
        """Save signatures to file"""
        try:
            with open(path, 'w') as f:
                json.dump(self._signatures, f, indent=2)
            logger.info(f'Saved device signatures to {path}')
        except Exception as e:
            logger.error(f'Failed to save device signatures: {e}')

    def _get_default_signatures(self) -> dict:
        """Return default device signatures"""
        return {
            "version": "1.0",
            "description": "Prometheus device signature definitions",
            "devices": [
                {
                    "device_type": "atlas3",
                    "display_name": "Atlas3 PCIe Switch",
                    "manufacturer": "Serial Cables",
                    "known_models": [
                        "PCI6-AD-X16HI-BG6-144",
                        "PCI6-AD-X16HI-BG6-80"
                    ],
                    "model_patterns": [
                        "PCI6-AD"
                    ],
                    "response_format": {
                        "model_regex": r"(?:Model|Product)[\s:]+(.+?)(?:\r|\n|$)",
                        "serial_regex": r"(?:Serial|SN|S/N)[\s:#]+([A-Z0-9\-]+)",
                        "firmware_regex": r"(?:FW|Firmware|MCU|Version|Ver)[\s:]+v?([0-9]+\.[0-9]+\.?[0-9]*)"
                    }
                },
                {
                    "device_type": "hydra",
                    "display_name": "HYDRA JBOF Controller",
                    "manufacturer": "Serial Cables",
                    "known_models": [
                        "PCI6-ENC8-E3-08",
                        "PCIe Gen6 8bays JBOF",
                        "PCIe Gen6 8Bays JBOF"
                    ],
                    "model_patterns": [
                        "PCI6-ENC8",
                        "JBOF"
                    ],
                    "response_format": {
                        "model_regex": r"(?:Model|Product)[\s:]+(.+?)(?:\r|\n|$)",
                        "serial_regex": r"(?:Serial|SN|S/N)[\s:#]+([A-Z0-9\-]+)",
                        "firmware_regex": r"(?:FW|Firmware|Version|Ver)[\s:]+v?([0-9]+\.[0-9]+\.?[0-9]*)"
                    }
                }
            ],
            "detection_settings": {
                "baudrate": 115200,
                "timeout": 2.0,
                "command": "ver\r\n",
                "retry_count": 2
            }
        }

    def get_signatures(self) -> list[dict]:
        """Get all device signatures"""
        return self._signatures.get('devices', [])

    def get_settings(self) -> dict:
        """Get detection settings"""
        return self._signatures.get('detection_settings', {
            'baudrate': 115200,
            'timeout': 2.0,
            'command': 'ver\r\n',
            'retry_count': 2
        })

    def get_known_models(self, device_type: str) -> list[str]:
        """Get known models for a device type"""
        for sig in self.get_signatures():
            if sig.get('device_type') == device_type:
                return sig.get('known_models', [])
        return []

    def get_known_usb_ids(self) -> list[tuple[str, str, str]]:
        """
        Get list of known USB VID/PID pairs with their device types.
        Returns list of (vid, pid, device_type) tuples.
        """
        result = []
        for sig in self.get_signatures():
            usb_ids = sig.get('usb_ids')
            if usb_ids:
                vid = usb_ids.get('vid', '').upper()
                pid = usb_ids.get('pid', '').upper()
                if vid and pid:
                    result.append((vid, pid, sig['device_type']))
        return result

    def match_usb_id(self, hwid: str) -> Optional[str]:
        """
        Check if a hardware ID matches any known device USB IDs.
        Returns device_type if matched, None otherwise.

        Supports multiple HWID formats:
        - Windows: USB\VID_045B&PID_5300
        - pyserial Windows: USB VID:PID=045B:5300
        - Linux pyserial: USB VID:PID=045b:5300 (lowercase)
        - Linux sysfs style: 045b:5300
        """
        if not hwid:
            return None

        hwid_upper = hwid.upper()
        for vid, pid, device_type in self.get_known_usb_ids():
            vid_upper = vid.upper()
            pid_upper = pid.upper()

            # Match VID_xxxx&PID_xxxx pattern (Windows device manager format)
            if f'VID_{vid_upper}' in hwid_upper and f'PID_{pid_upper}' in hwid_upper:
                return device_type
            # Match VID:PID=xxxx:xxxx pattern (pyserial format - both Windows and Linux)
            if f'VID:PID={vid_upper}:{pid_upper}' in hwid_upper:
                return device_type
            # Match just the VID and PID values separated by colon (Linux lsusb style)
            if f'{vid_upper}:{pid_upper}' in hwid_upper:
                return device_type
        return None

    def match_port_info(self, port_info) -> Optional[str]:
        """
        Check if a port_info object matches any known device.
        Checks both HWID and VID/PID attributes directly.

        Args:
            port_info: pyserial ListPortInfo object

        Returns:
            device_type if matched, None otherwise
        """
        # First try HWID matching (works on Windows)
        if port_info.hwid:
            matched = self.match_usb_id(port_info.hwid)
            if matched:
                return matched

        # On Linux, pyserial provides vid/pid as integer attributes
        if hasattr(port_info, 'vid') and hasattr(port_info, 'pid'):
            vid = port_info.vid
            pid = port_info.pid
            if vid is not None and pid is not None:
                # Convert to hex string for comparison
                vid_hex = f'{vid:04X}'
                pid_hex = f'{pid:04X}'
                for known_vid, known_pid, device_type in self.get_known_usb_ids():
                    if vid_hex == known_vid.upper() and pid_hex == known_pid.upper():
                        return device_type

        return None


class DeviceDetector:
    """
    Detects device type by sending 'ver' command via raw serial connection.
    Matches extracted model against known models for reliable identification.
    """

    def __init__(self):
        self.signatures = DeviceSignatures()

    def detect(self, com_port: str) -> DetectionResult:
        """
        Detect device type on the specified COM port.

        Args:
            com_port: COM port to probe (e.g., 'COM3' or '/dev/ttyUSB0')

        Returns:
            DetectionResult with device information if successful
        """
        settings = self.signatures.get_settings()

        logger.info(f'Starting device detection on {com_port}')

        # Try to get response from device
        response = self._send_ver_command(
            com_port,
            baudrate=settings.get('baudrate', 115200),
            timeout=settings.get('timeout', 2.0),
            retry_count=settings.get('retry_count', 2),
            command=settings.get('command', 'ver\r\n')
        )

        if response is None:
            return DetectionResult(
                success=False,
                com_port=com_port,
                error='No response from device'
            )

        logger.debug(f'Received response from {com_port}: {response[:200]}...')

        # Match against known device signatures
        result = self._match_device(response, com_port)
        result.raw_response = response

        return result

    def _send_ver_command(
        self,
        com_port: str,
        baudrate: int = 115200,
        timeout: float = 2.0,
        retry_count: int = 2,
        command: str = 'ver\r\n'
    ) -> Optional[str]:
        """
        Send 'ver' command and collect response.

        Returns:
            Response string or None if failed
        """
        for attempt in range(retry_count):
            try:
                with serial.Serial(
                    port=com_port,
                    baudrate=baudrate,
                    timeout=timeout,
                    write_timeout=timeout
                ) as ser:
                    # Clear any pending data
                    ser.reset_input_buffer()
                    ser.reset_output_buffer()

                    # Small delay for device to be ready
                    time.sleep(0.1)

                    # Send command
                    ser.write(command.encode('utf-8'))
                    ser.flush()

                    # Wait for response
                    time.sleep(0.3)

                    # Read all available data
                    response_bytes = b''
                    end_time = time.time() + timeout

                    while time.time() < end_time:
                        if ser.in_waiting > 0:
                            chunk = ser.read(ser.in_waiting)
                            response_bytes += chunk
                            time.sleep(0.05)
                        else:
                            if response_bytes:
                                break
                            time.sleep(0.1)

                    if response_bytes:
                        try:
                            response = response_bytes.decode('utf-8', errors='replace')
                        except Exception:
                            response = response_bytes.decode('latin-1', errors='replace')

                        response = self._clean_response(response)

                        if response:
                            return response

            except serial.SerialException as e:
                logger.warning(f'Serial error on {com_port} (attempt {attempt + 1}): {e}')
                if attempt < retry_count - 1:
                    time.sleep(0.5)
            except Exception as e:
                logger.error(f'Unexpected error detecting device on {com_port}: {e}')
                break

        return None

    def _clean_response(self, response: str) -> str:
        """Clean up device response string"""
        cleaned = ''.join(
            c for c in response
            if c.isprintable() or c in '\r\n\t'
        )
        cleaned = cleaned.replace('\r\n', '\n').replace('\r', '\n')
        lines = [line.strip() for line in cleaned.split('\n') if line.strip()]
        return '\n'.join(lines)

    def _match_device(self, response: str, com_port: str) -> DetectionResult:
        """
        Match response against known device models.
        Uses direct model matching for reliable identification.
        """
        for signature in self.signatures.get_signatures():
            # Extract model from response
            model = self._extract_field(response, signature, 'model_regex')

            if not model:
                continue

            # Check if model matches known models (exact match)
            known_models = signature.get('known_models', [])
            for known in known_models:
                if known.lower() == model.lower() or known.lower() in model.lower():
                    # Found exact or substring match
                    serial_number = self._extract_field(response, signature, 'serial_regex')
                    firmware = self._extract_field(response, signature, 'firmware_regex')

                    logger.info(f'Detected {signature["device_type"]} on {com_port}: {model}')

                    return DetectionResult(
                        success=True,
                        device_type=signature['device_type'],
                        model=model,
                        serial_number=serial_number,
                        firmware_version=firmware,
                        com_port=com_port
                    )

            # Check model patterns (fallback for unknown variants)
            model_patterns = signature.get('model_patterns', [])
            for pattern in model_patterns:
                if pattern.lower() in model.lower():
                    serial_number = self._extract_field(response, signature, 'serial_regex')
                    firmware = self._extract_field(response, signature, 'firmware_regex')

                    logger.info(f'Detected {signature["device_type"]} on {com_port} via pattern: {model}')

                    return DetectionResult(
                        success=True,
                        device_type=signature['device_type'],
                        model=model,
                        serial_number=serial_number,
                        firmware_version=firmware,
                        com_port=com_port
                    )

        return DetectionResult(
            success=False,
            com_port=com_port,
            error='Unknown device type'
        )

    def _extract_field(self, response: str, signature: dict, field: str) -> Optional[str]:
        """Extract a field from response using signature's regex pattern"""
        response_format = signature.get('response_format', {})
        pattern = response_format.get(field)

        if not pattern:
            return None

        try:
            match = re.search(pattern, response, re.IGNORECASE | re.MULTILINE)
            if match:
                value = match.group(1).strip()
                # Remove any trailing box-drawing characters and whitespace
                value = value.rstrip('║│┃┆┇┊┋╎╏ \t')
                return value
        except (re.error, IndexError):
            pass

        return None


# Singleton instance
_detector = None


def get_detector() -> DeviceDetector:
    """Get the singleton DeviceDetector instance"""
    global _detector
    if _detector is None:
        _detector = DeviceDetector()
    return _detector


def detect_device(com_port: str) -> DetectionResult:
    """Convenience function to detect device on a COM port"""
    return get_detector().detect(com_port)


# =============================================================================
# Fast Parallel Detection with Caching
# =============================================================================

class DetectionCache:
    """
    Caches device detection results for fast retrieval.
    Supports background scanning and parallel port detection.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}
            cls._instance._lock = threading.Lock()
            cls._instance._scan_in_progress = False
            cls._instance._last_scan_time = 0
        return cls._instance

    def get_cached_results(self) -> dict[str, DetectionResult]:
        """Get all cached detection results"""
        with self._lock:
            return dict(self._cache)

    def get_cached_result(self, com_port: str) -> Optional[DetectionResult]:
        """Get cached result for a specific port"""
        with self._lock:
            return self._cache.get(com_port)

    def is_scan_in_progress(self) -> bool:
        """Check if a background scan is currently running"""
        return self._scan_in_progress

    def get_last_scan_time(self) -> float:
        """Get timestamp of last completed scan"""
        return self._last_scan_time

    def invalidate(self, com_port: str = None):
        """Invalidate cache for a specific port or all ports"""
        with self._lock:
            if com_port:
                self._cache.pop(com_port, None)
            else:
                self._cache.clear()

    def scan_all_ports_fast(
        self,
        exclude_ports: set[str] = None,
        timeout: float = 0.5,
        max_workers: int = 4,
        filter_by_usb_id: bool = True
    ) -> dict[str, DetectionResult]:
        """
        Scan all available COM ports in parallel with short timeout.

        Args:
            exclude_ports: Set of ports to skip (e.g., already connected)
            timeout: Timeout per port (default 0.5s for fast detection)
            max_workers: Number of parallel workers
            filter_by_usb_id: If True, only scan ports with known USB VID/PID

        Returns:
            Dict mapping port name to DetectionResult
        """
        if self._scan_in_progress:
            logger.debug('Scan already in progress, returning cached results')
            return self.get_cached_results()

        self._scan_in_progress = True
        exclude_ports = exclude_ports or set()
        signatures = DeviceSignatures()

        try:
            # Get available ports with their hardware IDs
            all_port_info = list(serial.tools.list_ports.comports())

            # Filter by USB VID/PID if enabled
            if filter_by_usb_id:
                ports_to_scan = []
                for port_info in all_port_info:
                    if port_info.device in exclude_ports:
                        continue
                    # Check if this port matches a known device (supports both Windows and Linux)
                    matched_type = signatures.match_port_info(port_info)
                    if matched_type:
                        ports_to_scan.append(port_info.device)
                        # Log with available info (vid/pid on Linux, hwid on Windows)
                        vid_pid_info = ''
                        if hasattr(port_info, 'vid') and port_info.vid is not None:
                            vid_pid_info = f'VID={port_info.vid:04X} PID={port_info.pid:04X}'
                        else:
                            vid_pid_info = f'HWID: {port_info.hwid}'
                        logger.debug(f'Port {port_info.device} matches {matched_type} ({vid_pid_info})')
                    else:
                        vid_pid_info = ''
                        if hasattr(port_info, 'vid') and port_info.vid is not None:
                            vid_pid_info = f'VID={port_info.vid:04X} PID={port_info.pid:04X}'
                        else:
                            vid_pid_info = f'HWID: {port_info.hwid}'
                        logger.debug(f'Skipping {port_info.device} - unknown USB ID ({vid_pid_info})')
            else:
                ports_to_scan = [p.device for p in all_port_info
                               if p.device not in exclude_ports]

            logger.info(f'Fast scanning {len(ports_to_scan)} ports '
                       f'(filtered from {len(all_port_info)} total)')

            results = {}

            # Scan in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_port = {
                    executor.submit(self._detect_fast, port, timeout): port
                    for port in ports_to_scan
                }

                for future in as_completed(future_to_port):
                    port = future_to_port[future]
                    try:
                        result = future.result()
                        results[port] = result

                        # Update cache
                        with self._lock:
                            self._cache[port] = result

                    except Exception as e:
                        logger.error(f'Detection failed for {port}: {e}')
                        results[port] = DetectionResult(
                            success=False,
                            com_port=port,
                            error=str(e)
                        )

            self._last_scan_time = time.time()
            detected_count = sum(1 for r in results.values() if r.success)
            logger.info(f'Fast scan complete: {detected_count}/{len(ports_to_scan)} devices found')

            return results

        finally:
            self._scan_in_progress = False

    def _detect_fast(self, com_port: str, timeout: float = 0.5) -> DetectionResult:
        """
        Fast single-attempt detection with short timeout.
        Optimized for quick scanning - no retries.
        """
        signatures = DeviceSignatures()
        settings = signatures.get_settings()

        logger.debug(f'Starting fast detection on {com_port}')

        try:
            with serial.Serial(
                port=com_port,
                baudrate=settings.get('baudrate', 115200),
                timeout=timeout,
                write_timeout=0.2  # Short write timeout - fail fast on unresponsive ports
            ) as ser:
                logger.debug(f'{com_port}: Port opened successfully')
                # Clear buffers
                ser.reset_input_buffer()
                ser.reset_output_buffer()

                # Minimal delay
                time.sleep(0.02)

                # Send command
                command = settings.get('command', 'ver\r\n')
                ser.write(command.encode('utf-8'))
                ser.flush()

                # Short wait for response to start
                time.sleep(0.1)

                # Read available data with short timeout
                response_bytes = b''
                end_time = time.time() + timeout

                while time.time() < end_time:
                    if ser.in_waiting > 0:
                        chunk = ser.read(ser.in_waiting)
                        response_bytes += chunk
                        time.sleep(0.02)
                    else:
                        if response_bytes:
                            # Got data and no more coming - done
                            break
                        time.sleep(0.03)

                if not response_bytes:
                    logger.debug(f'{com_port}: No response received')
                    return DetectionResult(
                        success=False,
                        com_port=com_port,
                        error='No response from device'
                    )

                logger.debug(f'{com_port}: Received {len(response_bytes)} bytes')

                # Decode response
                try:
                    response = response_bytes.decode('utf-8', errors='replace')
                except Exception:
                    response = response_bytes.decode('latin-1', errors='replace')

                # Clean response
                response = get_detector()._clean_response(response)

                if not response:
                    logger.debug(f'{com_port}: Response was empty after cleaning')
                    return DetectionResult(
                        success=False,
                        com_port=com_port,
                        error='Empty response'
                    )

                logger.debug(f'{com_port}: Cleaned response: {response[:100]}...')

                # Match device
                result = get_detector()._match_device(response, com_port)
                result.raw_response = response

                if result.success:
                    logger.debug(f'{com_port}: Matched as {result.device_type}')
                else:
                    logger.debug(f'{com_port}: No device match found')

                return result

        except serial.SerialException as e:
            logger.debug(f'{com_port}: Serial error: {e}')
            return DetectionResult(
                success=False,
                com_port=com_port,
                error=f'Serial error: {e}'
            )
        except Exception as e:
            logger.debug(f'{com_port}: Exception: {e}')
            return DetectionResult(
                success=False,
                com_port=com_port,
                error=str(e)
            )

    def start_background_scan(self, exclude_ports: set[str] = None):
        """Start a background scan that doesn't block the caller"""
        thread = threading.Thread(
            target=self.scan_all_ports_fast,
            args=(exclude_ports,),
            daemon=True
        )
        thread.start()
        return thread


# Global cache instance
_detection_cache = None


def get_detection_cache() -> DetectionCache:
    """Get the singleton DetectionCache instance"""
    global _detection_cache
    if _detection_cache is None:
        _detection_cache = DetectionCache()
    return _detection_cache


def scan_all_ports_fast(exclude_ports: set[str] = None) -> dict[str, DetectionResult]:
    """Convenience function for fast parallel port scanning"""
    return get_detection_cache().scan_all_ports_fast(exclude_ports)


def start_background_scan(exclude_ports: set[str] = None):
    """Start a background device scan"""
    return get_detection_cache().start_background_scan(exclude_ports)


def get_cached_devices() -> dict[str, DetectionResult]:
    """Get cached detection results"""
    return get_detection_cache().get_cached_results()