# Prometheus

A Flask-based web dashboard for monitoring and controlling Serial Cables hardware devices. Prometheus provides real-time monitoring, device detection, and advanced control capabilities for Atlas3 PCIe switches and HYDRA JBOF controllers.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Flask](https://img.shields.io/badge/flask-3.0+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## Features

### Device Support
- **Atlas3 PCIe Gen6 Switch** - Gen6 PCIe switch with full monitoring and control
- **HYDRA JBOF Controller** - Just a Bunch of Flash controller with 8 drive bays

### Core Capabilities

- **Auto-Detection** - Automatic device discovery via fast parallel COM port scanning
- **Real-time Monitoring** - Live status updates via WebSocket
- **Temperature Monitoring** - Multi-sensor temperature tracking
- **Error Counters** - PCIe link error tracking (Atlas3)
- **Device Control** - Device-specific control panels with one-click commands
- **Modular Dashboard** - Draggable widget-based interface

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/jpmutschler/prometheus.git
cd prometheus

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### Running

```bash
python run.py
```

The dashboard will be available at:
- Local: http://localhost:5000
- Network: http://\<your-ip\>:5000

## Dashboard Widgets

| Widget | Description |
|--------|-------------|
| **Connection Manager** | Scan for devices and manage connections |
| **System Info** | Device firmware and hardware details |
| **Device Status** | Real-time status overview |
| **Temperature Monitor** | Temperature readings with sensor breakdown |
| **Port Status** | Link status, speed, and width information |
| **Error Counters** | PCIe error tracking (Atlas3 only) |
| **Command Console** | Send raw commands and view responses |
| **Register Explorer** | Read/write device registers |
| **Control Panel** | Device-specific controls |

## Device-Specific Features

### Atlas3 PCIe Switch

- PERST# reset controls per MCIO connector
- PCIe mode selection (Mode 1-4)
- Clock output control with spread spectrum options
- FLIT mode configuration
- Register read/write access
- PCIe error counter monitoring

### HYDRA JBOF Controller

- System power control
- Per-slot SSD power management
- Host and Fault LED control
- Fan PWM speed control
- SMBus reset
- Buzzer control
- Dual-port mode configuration
- PWRDIS# signal control

## API Reference

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | API health check |
| `/api/ports` | GET | List available COM ports |
| `/api/devices` | GET | List connected devices |
| `/api/device-types` | GET | List supported device types |
| `/api/connect` | POST | Connect to a device |
| `/api/disconnect/<id>` | POST | Disconnect from a device |
| `/api/detect/<port>` | GET | Detect device on COM port |
| `/api/detect-all` | POST | Scan all ports |
| `/api/device/<id>/sysinfo` | GET | Get system information |
| `/api/device/<id>/control-status` | GET | Get control settings |
| `/api/device/<id>/control` | POST | Execute control commands |
| `/api/device/<id>/command` | POST | Execute single command |
| `/api/device/<id>/commands` | GET | List available commands |

### WebSocket Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `subscribe` | Client → Server | Subscribe to device updates |
| `unsubscribe` | Client → Server | Stop receiving updates |
| `status_update` | Server → Client | Real-time status broadcast |

## Project Structure

```
prometheus/
├── run.py                    # Application entry point
├── config.py                 # Configuration settings
├── requirements.txt          # Python dependencies
│
├── app/
│   ├── __init__.py           # Flask application factory
│   ├── routes.py             # Main routes
│   ├── logger.py             # Logging utility
│   │
│   ├── devices/              # Device abstraction layer
│   │   ├── base.py           # Base classes and interfaces
│   │   ├── atlas3.py         # Atlas3 implementation
│   │   ├── hydra.py          # HYDRA implementation
│   │   └── detection.py      # Device detection engine
│   │
│   ├── api/                  # REST API and WebSocket
│   │   ├── routes.py         # API endpoints
│   │   ├── websocket.py      # SocketIO handlers
│   │   └── handlers/         # Device-specific handlers
│   │
│   ├── static/               # Frontend assets
│   │   ├── css/
│   │   └── js/
│   │
│   └── templates/            # Jinja2 templates
│       └── widgets/          # Widget templates
│
└── logs/                     # Application logs
```

## Configuration

Configuration is managed via `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `STATUS_POLL_INTERVAL` | 1.0s | Device status polling interval |
| `TEMPERATURE_POLL_INTERVAL` | 2.0s | Temperature polling interval |
| `DEFAULT_BAUDRATE` | 115200 | Serial communication baud rate |
| `DEFAULT_TIMEOUT` | 1.0s | Serial command timeout |

## Dependencies

### Python Packages
- Flask 3.0+
- Flask-SocketIO 5.3+
- Flask-CORS 4.0+
- eventlet 0.35+
- pyserial 3.5
- serialcables-atlas3
- serialcables-hydra

### Frontend Libraries (via CDN)
- Gridstack 10.0.0
- Socket.IO 4.7.2

## Development

### Mock Mode

When hardware APIs are unavailable, Prometheus automatically falls back to mock device implementations for development and testing.

### Adding New Device Types

1. Create device implementation in `app/devices/`
2. Create handler in `app/api/handlers/`
3. Register handler with `HandlerRegistry`
4. Add device-specific UI components

## License

MIT License - See [LICENSE](LICENSE) for details.

## Related Projects

- [serialcables-atlas3](https://pypi.org/project/serialcables-atlas3/) - Atlas3 PCIe Switch Python API
- [serialcables-hydra](https://pypi.org/project/serialcables-hydra/) - HYDRA JBOF Controller Python API
