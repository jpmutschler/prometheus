/**
 * Prometheus Dashboard
 * Serial Cables Hardware Dashboard - Main JavaScript
 *
 * This is the core dashboard that uses the DeviceRegistry for device-specific operations.
 * Device-specific logic is handled by registered handlers in /devices/*.js
 */

class PrometheusDashboard {
    constructor() {
        this.grid = null;
        this.socket = null;
        this.devices = {};
        this.detectedDevices = [];  // Store detected but not connected devices
        this.widgetCounter = 0;
        this.widgetData = {};  // Store widget-specific data for export
        this.autoRefreshTimers = {};  // Store auto-refresh timers by widget ID

        this.init();
    }

    init() {
        // Initialize GridStack
        this.grid = GridStack.init({
            column: 12,
            cellHeight: 80,
            margin: 8,
            float: true,
            removable: false,
            animate: true
        });

        // Initialize Socket.IO
        this.initSocket();

        // Load saved layout
        this.loadLayout();

        // Auto-scan for devices on startup
        this.scanForDevices();
    }

    // =========================================================================
    // Socket.IO
    // =========================================================================

    initSocket() {
        this.socket = io();

        this.socket.on('connect', () => {
            console.log('Connected to Prometheus server');
            this.updateConnectionStatus(true);
        });

        this.socket.on('disconnect', () => {
            console.log('Disconnected from Prometheus server');
            this.updateConnectionStatus(false);
        });

        this.socket.on('status_update', (data) => {
            this.handleStatusUpdate(data);
        });

        this.socket.on('command_result', (data) => {
            this.handleCommandResult(data);
        });

        this.socket.on('error', (data) => {
            // Only log actual errors, not "device not found" which happens on page reload
            if (data.message && !data.message.includes('Device not found')) {
                console.error('Socket error:', data);
            }
        });
    }

    updateConnectionStatus(connected) {
        const statusEl = document.getElementById('connectionStatus');
        const indicator = statusEl.querySelector('.status-indicator');
        const text = statusEl.querySelector('.status-text');

        if (connected) {
            indicator.classList.remove('disconnected');
            indicator.classList.add('connected');
            text.textContent = 'Connected';
        } else {
            indicator.classList.remove('connected');
            indicator.classList.add('disconnected');
            text.textContent = 'Disconnected';
        }
    }

    handleStatusUpdate(data) {
        const { device_id, status } = data;

        // Update all widgets bound to this device
        document.querySelectorAll(`[data-device-id="${device_id}"]`).forEach(widget => {
            const widgetType = widget.dataset.widgetType;
            this.updateWidgetContent(widget, widgetType, status);
        });
    }

    handleCommandResult(data) {
        // Handle async command results if needed
        console.log('Command result:', data);
    }

    // =========================================================================
    // Widget Management
    // =========================================================================

    showAddWidgetModal() {
        document.getElementById('addWidgetModal').classList.add('active');
    }

    closeModal(modalId) {
        document.getElementById(modalId).classList.remove('active');
    }

    addWidget(type) {
        this.closeModal('addWidgetModal');

        const template = document.getElementById(`widget-${type}`);
        if (!template) {
            console.error(`Widget template not found: widget-${type}`);
            return;
        }

        const widgetId = `widget-${++this.widgetCounter}`;
        const content = template.content.cloneNode(true);

        // Get widget size based on type
        const sizes = {
            'connection': { w: 3, h: 5 },
            'sysinfo': { w: 4, h: 4 },
            'status': { w: 4, h: 4 },
            'temperatures': { w: 4, h: 3 },
            'ports': { w: 4, h: 4 },
            'console': { w: 6, h: 4 },
            'register': { w: 3, h: 3 },
            'control': { w: 4, h: 8 },
            'errors': { w: 5, h: 4 }
        };

        const size = sizes[type] || { w: 3, h: 3 };

        // Create wrapper div
        const wrapper = document.createElement('div');
        wrapper.appendChild(content);

        // Add widget to grid
        const widget = this.grid.addWidget({
            w: size.w,
            h: size.h,
            content: wrapper.innerHTML,
            id: widgetId
        });

        // Store widget metadata
        const gridItem = widget;
        gridItem.dataset.widgetType = type;
        gridItem.dataset.widgetId = widgetId;

        // Initialize widget
        this.initializeWidget(gridItem, type);

        return widgetId;
    }

    initializeWidget(widget, type) {
        // Populate device selectors
        const deviceSelect = widget.querySelector('.widget-device-select');
        if (deviceSelect) {
            this.populateDeviceSelect(deviceSelect);
        }

        // Connection widget: update detected devices list if we have cached data
        if (type === 'connection') {
            this.updateDetectedDevicesList();
            this.updateConnectedDevicesList();
        }

        // Populate command select for console widget
        if (type === 'console') {
            // Will be populated when device is selected
        }
    }

    removeWidget(button) {
        const gridItem = button.closest('.grid-stack-item');
        if (gridItem) {
            const widgetId = gridItem.dataset.widgetId;
            const deviceId = gridItem.dataset.deviceId;

            // Stop any auto-refresh timer
            if (widgetId) {
                this.stopAutoRefresh(widgetId);
            }

            if (deviceId) {
                this.socket.emit('unsubscribe', { device_id: deviceId });
            }
            this.grid.removeWidget(gridItem);
        }
    }

    // =========================================================================
    // Device Connection
    // =========================================================================

    async refreshAllPorts() {
        try {
            const response = await fetch('/api/ports');
            const data = await response.json();

            if (data.ports) {
                this.availablePorts = data.ports;
                // Update all port selects
                document.querySelectorAll('.port-select').forEach(select => {
                    this.populatePortSelect(select, data.ports);
                });
            }
        } catch (error) {
            console.error('Failed to refresh ports:', error);
        }
    }

    refreshPorts(button) {
        this.refreshAllPorts();
    }

    // =========================================================================
    // Device Detection
    // =========================================================================

    async scanForDevices(button = null) {
        // Update UI to show scanning state
        document.querySelectorAll('.detected-devices-list').forEach(container => {
            const scanningMsg = container.querySelector('.scanning-message');
            const noDevicesMsg = container.querySelector('.no-devices-message');
            if (scanningMsg) scanningMsg.style.display = 'block';
            if (noDevicesMsg) noDevicesMsg.style.display = 'none';

            // Clear previous detected devices (keep messages)
            container.querySelectorAll('.detected-device-item').forEach(el => el.remove());
        });

        try {
            const response = await fetch('/api/detect-all', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            const data = await response.json();

            if (data.success) {
                // Store detected devices
                this.detectedDevices = [];
                for (const [port, result] of Object.entries(data.results)) {
                    if (result.success) {
                        this.detectedDevices.push({
                            com_port: port,
                            device_type: result.device_type,
                            model: result.model,
                            serial_number: result.serial_number,
                            firmware_version: result.firmware_version
                        });
                    }
                }

                // Update all connection widgets
                this.updateDetectedDevicesList();

                console.log(`Scan complete: ${this.detectedDevices.length} device(s) detected`);
            }
        } catch (error) {
            console.error('Scan error:', error);
        } finally {
            // Hide scanning message
            document.querySelectorAll('.scanning-message').forEach(el => {
                el.style.display = 'none';
            });
        }
    }

    updateDetectedDevicesList() {
        document.querySelectorAll('.detected-devices-list').forEach(container => {
            const scanningMsg = container.querySelector('.scanning-message');
            const noDevicesMsg = container.querySelector('.no-devices-message');

            // Clear previous detected devices (keep messages)
            container.querySelectorAll('.detected-device-item').forEach(el => el.remove());

            // Filter out already connected devices
            const connectedPorts = Object.values(this.devices)
                .filter(d => d.connected)
                .map(d => d.com_port);

            const availableDevices = this.detectedDevices.filter(
                d => !connectedPorts.includes(d.com_port)
            );

            if (availableDevices.length === 0) {
                if (noDevicesMsg) noDevicesMsg.style.display = 'block';
                return;
            }

            if (noDevicesMsg) noDevicesMsg.style.display = 'none';

            // Add detected device items
            for (const device of availableDevices) {
                const typeLabel = device.device_type === 'atlas3' ? 'Atlas3' :
                                  device.device_type === 'hydra' ? 'HYDRA' : device.device_type;

                const item = document.createElement('div');
                item.className = 'detected-device-item';
                item.innerHTML = `
                    <div class="detected-device-info">
                        <span class="detected-device-type">${typeLabel}</span>
                        <span class="detected-device-model">${device.model || 'Unknown'}</span>
                        <span class="detected-device-port">${device.com_port}</span>
                        ${device.serial_number ? `<span class="detected-device-sn">SN: ${device.serial_number}</span>` : ''}
                    </div>
                    <button class="btn btn-sm btn-primary"
                            data-port="${device.com_port}"
                            data-type="${device.device_type}"
                            onclick="dashboard.connectDetectedDevice(this)">Connect</button>
                `;
                container.appendChild(item);
            }
        });
    }

    async connectDetectedDevice(button) {
        const comPort = button.dataset.port;
        const deviceType = button.dataset.type;

        if (!comPort || !deviceType) return;

        button.disabled = true;
        button.textContent = 'Connecting...';

        try {
            const response = await fetch('/api/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    device_type: deviceType,
                    com_port: comPort
                })
            });

            const data = await response.json();

            if (data.success) {
                // Store device info
                this.devices[data.device_id] = {
                    type: deviceType,
                    com_port: comPort,
                    connected: true,
                    info: data.info,
                    status: data.status
                };

                // Subscribe to updates
                this.socket.emit('subscribe', { device_id: data.device_id });

                // Update UI
                this.updateDetectedDevicesList();
                this.updateConnectedDevicesList();

                // Update all device selectors in other widgets
                document.querySelectorAll('.widget-device-select').forEach(select => {
                    this.populateDeviceSelect(select);
                });
            } else {
                alert(`Connection failed: ${data.error}`);
                button.disabled = false;
                button.textContent = 'Connect';
            }
        } catch (error) {
            alert(`Connection error: ${error.message}`);
            button.disabled = false;
            button.textContent = 'Connect';
        }
    }

    populatePortSelect(select, ports) {
        const currentValue = select.value;
        select.innerHTML = '<option value="">Select port...</option>';

        if (!ports || ports.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No ports found';
            option.disabled = true;
            select.appendChild(option);
            return;
        }

        ports.forEach(port => {
            const option = document.createElement('option');
            option.value = port.device;
            option.textContent = `${port.device} - ${port.description}`;
            select.appendChild(option);
        });

        if (currentValue) {
            select.value = currentValue;
        }
    }

    populateDeviceSelect(select) {
        const currentValue = select.value;
        const filterDeviceType = select.dataset.deviceType; // Optional filter
        select.innerHTML = '<option value="">Select device...</option>';

        Object.entries(this.devices).forEach(([deviceId, device]) => {
            if (device.connected) {
                // Filter by device type if specified
                if (filterDeviceType && device.type !== filterDeviceType) {
                    return;
                }
                const option = document.createElement('option');
                option.value = deviceId;
                option.textContent = `${device.type.toUpperCase()} (${device.com_port})`;
                select.appendChild(option);
            }
        });

        if (currentValue && this.devices[currentValue]) {
            select.value = currentValue;
        }
    }

    async connectDevice(button) {
        const widget = button.closest('.widget-content');
        const deviceType = widget.querySelector('.device-type-select').value;
        const comPort = widget.querySelector('.port-select').value;

        if (!comPort) {
            alert('Please select a COM port');
            return;
        }

        // Check if this port is already connected
        for (const [id, device] of Object.entries(this.devices)) {
            if (device.com_port === comPort && device.connected) {
                alert(`Port ${comPort} is already connected as ${id}`);
                return;
            }
        }

        button.disabled = true;
        button.textContent = 'Connecting...';

        try {
            const response = await fetch('/api/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    device_type: deviceType,
                    com_port: comPort
                })
            });

            const data = await response.json();

            if (data.success) {
                // Store device info
                this.devices[data.device_id] = {
                    type: deviceType,
                    com_port: comPort,
                    connected: true,
                    info: data.info,
                    status: data.status
                };

                // Subscribe to updates
                this.socket.emit('subscribe', { device_id: data.device_id });

                // Update the connected devices list in all connection widgets
                this.updateConnectedDevicesList();

                // Update all device selectors in other widgets
                document.querySelectorAll('.widget-device-select').forEach(select => {
                    this.populateDeviceSelect(select);
                });
            } else {
                alert(`Connection failed: ${data.error}`);
            }
        } catch (error) {
            alert(`Connection error: ${error.message}`);
        } finally {
            button.disabled = false;
            button.textContent = 'Connect';
        }
    }

    async disconnectDevice(button) {
        const deviceId = button.dataset.deviceId;

        if (!deviceId) return;

        button.disabled = true;

        try {
            const response = await fetch(`/api/disconnect/${deviceId}`, {
                method: 'POST'
            });

            const data = await response.json();

            if (data.success) {
                // Unsubscribe from updates
                this.socket.emit('unsubscribe', { device_id: deviceId });

                // Remove from devices
                delete this.devices[deviceId];

                // Update the connected devices list in all connection widgets
                this.updateConnectedDevicesList();

                // Update all device selectors in other widgets
                document.querySelectorAll('.widget-device-select').forEach(select => {
                    this.populateDeviceSelect(select);
                });
            } else {
                alert(`Disconnect failed: ${data.error}`);
            }
        } catch (error) {
            alert(`Disconnect error: ${error.message}`);
        }
    }

    updateConnectedDevicesList() {
        // Update all connection widgets with the current list of connected devices
        document.querySelectorAll('.connected-devices-items').forEach(container => {
            const connectedDevices = Object.entries(this.devices).filter(([id, d]) => d.connected);

            if (connectedDevices.length === 0) {
                container.innerHTML = '<div class="placeholder-message">No devices connected</div>';
                return;
            }

            let html = '';
            for (const [deviceId, device] of connectedDevices) {
                const typeLabel = device.type === 'atlas3' ? 'Atlas3' : 'HYDRA';
                const serialNumber = device.info?.serial_number || 'N/A';
                const fwVersion = device.info?.firmware_version || device.info?.mcu_version || 'N/A';
                html += `
                    <div class="connected-device-item">
                        <div class="connected-device-info">
                            <span class="connected-device-type">${typeLabel}</span>
                            <span class="connected-device-port">${device.com_port}</span>
                            <span class="connected-device-sn">SN: ${serialNumber}</span>
                            <span class="connected-device-fw">FW: ${fwVersion}</span>
                        </div>
                        <button class="btn btn-sm btn-danger" data-device-id="${deviceId}" onclick="dashboard.disconnectDevice(this)">Disconnect</button>
                    </div>
                `;
            }
            container.innerHTML = html;
        });
    }

    // =========================================================================
    // Widget Device Binding
    // =========================================================================

    onWidgetDeviceChange(select) {
        const widget = select.closest('.grid-stack-item');
        const deviceId = select.value;
        const widgetType = widget.dataset.widgetType;

        // Unsubscribe from previous device
        const prevDeviceId = widget.dataset.deviceId;
        if (prevDeviceId) {
            // We don't fully unsubscribe as other widgets might need it
        }

        // Bind to new device
        widget.dataset.deviceId = deviceId;

        if (deviceId) {
            // Subscribe to device updates
            this.socket.emit('subscribe', { device_id: deviceId });

            // Fetch initial data
            this.fetchWidgetData(widget, widgetType, deviceId);
        } else {
            // Clear widget content
            this.clearWidgetContent(widget, widgetType);
        }
    }

    async fetchWidgetData(widget, widgetType, deviceId) {
        switch (widgetType) {
            case 'sysinfo':
                await this.fetchSysinfo(widget, deviceId);
                break;
            case 'status':
                await this.fetchStatusData(widget, deviceId);
                break;
            case 'temperatures':
                await this.fetchStatus(widget, deviceId);
                break;
            case 'ports':
                await this.fetchPorts(widget, deviceId);
                break;
            case 'console':
                await this.fetchCommands(widget, deviceId);
                break;
            case 'errors':
                await this.fetchErrors(widget, deviceId);
                break;
        }
    }

    async fetchSysinfo(widget, deviceId) {
        try {
            const response = await fetch(`/api/device/${deviceId}/sysinfo`);
            const data = await response.json();

            if (data.success && data.sysinfo) {
                const content = widget.querySelector('.sysinfo-content');
                const sysinfo = data.sysinfo;
                const deviceType = this.devices[deviceId]?.type;

                // Store for export
                const widgetId = widget.dataset.widgetId;
                this.widgetData[widgetId] = {
                    type: 'sysinfo',
                    deviceId: deviceId,
                    data: sysinfo
                };

                // Use DeviceRegistry to flatten sysinfo
                const flatInfo = DeviceRegistry.flattenSysinfo(sysinfo, deviceType);
                content.innerHTML = Object.entries(flatInfo)
                    .map(([key, value]) => `
                        <div class="sysinfo-item">
                            <span class="sysinfo-key">${key}</span>
                            <span class="sysinfo-value">${value}</span>
                        </div>
                    `).join('');
            } else if (data.error) {
                console.error('Sysinfo API error:', data.error);
            }
        } catch (error) {
            console.error('Failed to fetch sysinfo:', error);
        }
    }

    refreshSysinfo(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget.dataset.deviceId;
        if (deviceId) {
            this.fetchSysinfo(widget, deviceId);
        }
    }

    async fetchStatus(widget, deviceId) {
        try {
            const response = await fetch(`/api/device/${deviceId}/sysinfo`);
            const data = await response.json();

            if (data.success && data.sysinfo) {
                const sysinfo = data.sysinfo;
                const deviceType = this.devices[deviceId]?.type;

                // Use DeviceRegistry to extract temperatures
                const temperatures = DeviceRegistry.extractTemperatures(sysinfo, deviceType);

                this.updateWidgetContent(widget, widget.dataset.widgetType, { temperatures });
            }
        } catch (error) {
            console.error('Failed to fetch status:', error);
        }
    }

    async fetchPorts(widget, deviceId) {
        try {
            const response = await fetch(`/api/device/${deviceId}/sysinfo`);
            const data = await response.json();

            if (data.success && data.sysinfo) {
                const content = widget.querySelector('.ports-content');
                const deviceType = this.devices[deviceId]?.type;

                // Use DeviceRegistry to render ports
                DeviceRegistry.renderPorts(content, data.sysinfo, deviceType);

                // Store for export
                const widgetId = widget.dataset.widgetId;
                this.widgetData[widgetId] = {
                    type: 'ports',
                    deviceId: deviceId,
                    data: data.sysinfo
                };
            }
        } catch (error) {
            console.error('Failed to fetch port status:', error);
        }
    }

    async refreshPorts(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget.dataset.deviceId;
        if (deviceId) {
            await this.fetchPorts(widget, deviceId);
        }
    }

    async fetchCommands(widget, deviceId) {
        try {
            const response = await fetch(`/api/device/${deviceId}/commands`);
            const data = await response.json();

            if (data.success) {
                const commandSelect = widget.querySelector('.command-select');
                commandSelect.innerHTML = '<option value="">Select command...</option>';

                data.commands.forEach(cmd => {
                    const option = document.createElement('option');
                    option.value = cmd.name;
                    option.textContent = `${cmd.name} - ${cmd.description}`;
                    option.dataset.params = JSON.stringify(cmd.parameters);
                    commandSelect.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Failed to fetch commands:', error);
        }
    }

    updateWidgetContent(widget, widgetType, status) {
        switch (widgetType) {
            case 'status':
                this.updateStatusWidget(widget, status);
                break;
            case 'temperatures':
                this.updateTemperatureWidget(widget, status);
                break;
        }
    }

    updateStatusWidget(widget, sysinfo) {
        const content = widget.querySelector('.status-content');
        if (!sysinfo) return;

        const deviceId = widget.dataset.deviceId;
        const deviceType = this.devices[deviceId]?.type || 'unknown';

        // Use DeviceRegistry to render status
        let html = DeviceRegistry.renderStatus(sysinfo, deviceType);

        // Add last updated timestamp
        html += `
            <div class="status-section">
                <div class="status-item" style="background: transparent;">
                    <span class="status-item-label">Last Updated</span>
                    <span class="status-item-value">${new Date().toLocaleTimeString()}</span>
                </div>
            </div>
        `;

        content.innerHTML = html;
    }

    async refreshStatus(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget.dataset.deviceId;
        if (deviceId) {
            await this.fetchStatusData(widget, deviceId);
        }
    }

    async fetchStatusData(widget, deviceId) {
        try {
            const response = await fetch(`/api/device/${deviceId}/sysinfo`);
            const data = await response.json();

            if (data.success) {
                this.updateStatusWidget(widget, data.sysinfo);

                // Store for export
                const widgetId = widget.dataset.widgetId;
                this.widgetData[widgetId] = {
                    type: 'status',
                    deviceId: deviceId,
                    data: data.sysinfo
                };
            } else {
                console.error('Failed to fetch status:', data.error);
            }
        } catch (error) {
            console.error('Failed to fetch status:', error);
        }
    }

    toggleAutoRefresh(checkbox) {
        const widget = checkbox.closest('.grid-stack-item');
        const widgetId = widget.dataset.widgetId;
        const deviceId = widget.dataset.deviceId;
        const intervalSelect = widget.querySelector('.auto-refresh-interval');
        const interval = parseInt(intervalSelect.value);

        if (checkbox.checked && deviceId) {
            // Start auto-refresh
            this.startAutoRefresh(widget, widgetId, deviceId, interval);
        } else {
            // Stop auto-refresh
            this.stopAutoRefresh(widgetId);
        }
    }

    updateRefreshInterval(select) {
        const widget = select.closest('.grid-stack-item');
        const widgetId = widget.dataset.widgetId;
        const deviceId = widget.dataset.deviceId;
        const checkbox = widget.querySelector('.auto-refresh-toggle');
        const interval = parseInt(select.value);

        if (checkbox.checked && deviceId) {
            // Restart with new interval
            this.stopAutoRefresh(widgetId);
            this.startAutoRefresh(widget, widgetId, deviceId, interval);
        }
    }

    startAutoRefresh(widget, widgetId, deviceId, interval) {
        // Clear any existing timer
        this.stopAutoRefresh(widgetId);

        // Determine which fetch function to use based on widget type
        const widgetType = widget.dataset.widgetType;
        const fetchFn = () => {
            switch (widgetType) {
                case 'status':
                    this.fetchStatusData(widget, deviceId);
                    break;
                case 'temperatures':
                    this.fetchStatus(widget, deviceId);
                    break;
                case 'sysinfo':
                    this.fetchSysinfo(widget, deviceId);
                    break;
                case 'ports':
                    this.fetchPorts(widget, deviceId);
                    break;
                case 'errors':
                    this.fetchErrors(widget, deviceId);
                    break;
                default:
                    this.fetchStatusData(widget, deviceId);
            }
        };

        // Start new timer
        this.autoRefreshTimers[widgetId] = setInterval(fetchFn, interval);

        console.log(`Started auto-refresh for ${widgetId} (${widgetType}) at ${interval}ms interval`);
    }

    async refreshTemperatures(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget.dataset.deviceId;
        if (deviceId) {
            await this.fetchStatus(widget, deviceId);
        }
    }

    // =========================================================================
    // Error Counters Widget (Atlas3 only)
    // =========================================================================

    async fetchErrors(widget, deviceId) {
        const device = this.devices[deviceId];
        if (!device || device.type !== 'atlas3') {
            const content = widget.querySelector('.errors-content');
            if (content) {
                content.innerHTML = '<div class="placeholder-message">Error counters are only available for Atlas3 devices</div>';
            }
            return;
        }

        try {
            const response = await fetch(`/api/device/${deviceId}/command`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'error_counters', params: {} })
            });

            const data = await response.json();

            if (data.result && data.result.success) {
                this.updateErrorsWidget(widget, data.result.response);

                // Store for export
                const widgetId = widget.dataset.widgetId;
                this.widgetData[widgetId] = {
                    type: 'errors',
                    deviceId: deviceId,
                    data: data.result.response
                };
            } else {
                const content = widget.querySelector('.errors-content');
                if (content) {
                    content.innerHTML = `<div class="placeholder-message error">Error: ${data.result?.error || 'Failed to fetch error counters'}</div>`;
                }
            }
        } catch (error) {
            console.error('Failed to fetch error counters:', error);
            const content = widget.querySelector('.errors-content');
            if (content) {
                content.innerHTML = `<div class="placeholder-message error">Error: ${error.message}</div>`;
            }
        }
    }

    async refreshErrors(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget.dataset.deviceId;
        if (deviceId) {
            await this.fetchErrors(widget, deviceId);
        }
    }

    async clearErrorCounters(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget.dataset.deviceId;

        if (!deviceId) {
            alert('Please select a device first');
            return;
        }

        const device = this.devices[deviceId];
        if (!device || device.type !== 'atlas3') {
            alert('Error counters are only available for Atlas3 devices');
            return;
        }

        if (!confirm('Clear all error counters? This action cannot be undone.')) {
            return;
        }

        try {
            const response = await fetch(`/api/device/${deviceId}/command`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: 'clear_error_counters', params: {} })
            });

            const data = await response.json();

            if (data.result && data.result.success) {
                // Refresh the display
                await this.fetchErrors(widget, deviceId);
            } else {
                alert(`Failed to clear counters: ${data.result?.error || 'Unknown error'}`);
            }
        } catch (error) {
            alert(`Error: ${error.message}`);
        }
    }

    updateErrorsWidget(widget, errorData) {
        const content = widget.querySelector('.errors-content');
        if (!content || !errorData) return;

        const ports = Object.values(errorData);
        if (ports.length === 0) {
            content.innerHTML = '<div class="placeholder-message">No active ports with error counters</div>';
            return;
        }

        // Error types to display with PCIe 6.x specification descriptions
        // Fields match Atlas3 counters output: PortRx, BadTLP, BadDLLP, RecDiag, LinkDown, FlitError
        const errorTypes = [
            {
                key: 'port_rx',
                label: 'Port Rx',
                color: 'blue',
                tooltip: 'Port Receive Errors - Total receive errors detected on this port. Indicates general PHY layer reception issues.'
            },
            {
                key: 'bad_tlp',
                label: 'Bad TLP',
                color: 'red',
                tooltip: 'Bad Transaction Layer Packet - A TLP failed CRC check or had malformed header/payload. Common causes: signal integrity issues, cable damage, or connector problems.'
            },
            {
                key: 'bad_dllp',
                label: 'Bad DLLP',
                color: 'orange',
                tooltip: 'Bad Data Link Layer Packet - A DLLP failed CRC verification. Common causes: electrical noise, marginal signal quality, or link instability.'
            },
            {
                key: 'rec_diag',
                label: 'Receiver Diag',
                color: 'yellow',
                tooltip: 'Receiver Diagnostic Errors - PHY layer receiver detected invalid data patterns. Common causes: clock recovery issues, signal attenuation, or impedance mismatches.'
            },
            {
                key: 'link_down',
                label: 'Link Down',
                color: 'purple',
                tooltip: 'Link Down Events - Number of times the link transitioned to down state. Common causes: hot-plug events, power issues, or severe signal degradation.'
            },
            {
                key: 'flit_error',
                label: 'FLIT Error',
                color: 'teal',
                tooltip: 'FLIT Mode Errors - Errors in PCIe 6.x FLIT (Flow Control Unit) mode transmission. Specific to 64 GT/s operation with 256b/256b encoding.'
            }
        ];

        // Find the max value for scaling bars
        let maxCount = 1;
        ports.forEach(port => {
            errorTypes.forEach(({ key }) => {
                if (port[key] > maxCount) maxCount = port[key];
            });
        });

        let html = '<div class="errors-grid">';

        // Sort ports by port number
        const sortedPorts = ports.sort((a, b) => a.port - b.port);

        for (const port of sortedPorts) {
            const totalErrors = errorTypes.reduce((sum, { key }) => sum + (port[key] || 0), 0);
            const hasErrors = totalErrors > 0;
            const portLabel = port.connector ? `${port.connector} (Port ${port.port})` : `Port ${port.port}`;

            html += `
                <div class="error-port-section ${hasErrors ? 'has-errors' : ''}">
                    <div class="error-port-header">
                        <span class="error-port-label">${portLabel}</span>
                        <span class="error-port-total ${hasErrors ? 'error' : 'success'}">${totalErrors} errors</span>
                    </div>
                    <div class="error-bars">
            `;

            for (const { key, label, color, tooltip } of errorTypes) {
                const count = port[key] || 0;
                const percent = maxCount > 0 ? (count / maxCount) * 100 : 0;
                const barColorClass = count > 0 ? `error-${color}` : 'ok';

                html += `
                    <div class="error-bar-item" title="${tooltip}">
                        <span class="error-bar-label">${label}</span>
                        <div class="error-bar-container">
                            <div class="error-bar-fill ${barColorClass}" style="width: ${percent}%"></div>
                        </div>
                        <span class="error-bar-count ${count > 0 ? `has-errors error-text-${color}` : ''}">${count}</span>
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        html += '</div>';

        // Add last updated timestamp
        html += `
            <div class="errors-footer">
                <span class="errors-timestamp">Last updated: ${new Date().toLocaleTimeString()}</span>
            </div>
        `;

        content.innerHTML = html;
    }

    stopAutoRefresh(widgetId) {
        if (this.autoRefreshTimers[widgetId]) {
            clearInterval(this.autoRefreshTimers[widgetId]);
            delete this.autoRefreshTimers[widgetId];
            console.log(`Stopped auto-refresh for ${widgetId}`);
        }
    }

    updateTemperatureWidget(widget, status) {
        const content = widget.querySelector('.temperature-content');
        if (!status || !status.temperatures) return;

        content.innerHTML = Object.entries(status.temperatures)
            .map(([name, temp]) => {
                const tempNum = parseFloat(temp);
                const percent = Math.min((tempNum / 80) * 100, 100);
                const tempClass = tempNum < 50 ? 'cool' : tempNum < 65 ? 'warm' : 'hot';

                return `
                    <div class="temp-item">
                        <span class="temp-label">${this.formatKey(name)}</span>
                        <div class="temp-bar">
                            <div class="temp-bar-fill ${tempClass}" style="width: ${percent}%"></div>
                        </div>
                        <span class="temp-value">${tempNum.toFixed(1)}°C</span>
                    </div>
                `;
            }).join('');
    }

    clearWidgetContent(widget, widgetType) {
        const contentSelectors = {
            'sysinfo': '.sysinfo-content',
            'status': '.status-content',
            'temperatures': '.temperature-content',
            'ports': '.ports-content',
            'errors': '.errors-content'
        };

        const selector = contentSelectors[widgetType];
        if (selector) {
            const content = widget.querySelector(selector);
            if (content) {
                content.innerHTML = '<div class="placeholder-message">Select a device</div>';
            }
        }
    }

    // =========================================================================
    // Console Widget
    // =========================================================================

    async executeCommand(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget.dataset.deviceId;
        const commandSelect = widget.querySelector('.command-select');
        const paramsInput = widget.querySelector('.command-params');
        const output = widget.querySelector('.console-output');

        if (!deviceId) {
            alert('Please select a device first');
            return;
        }

        const command = commandSelect.value;
        if (!command) {
            alert('Please select a command');
            return;
        }

        let params = {};
        if (paramsInput.value.trim()) {
            try {
                params = JSON.parse(paramsInput.value);
            } catch (e) {
                alert('Invalid JSON parameters');
                return;
            }
        }

        // Add command to output
        const timestamp = new Date().toLocaleTimeString();
        output.innerHTML += `
            <div class="console-line timestamp">[${timestamp}]</div>
            <div class="console-line command">&gt; ${command} ${JSON.stringify(params)}</div>
        `;

        try {
            const response = await fetch(`/api/device/${deviceId}/command`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command, params })
            });

            const data = await response.json();

            if (data.result.success) {
                output.innerHTML += `
                    <div class="console-line response">${JSON.stringify(data.result.response, null, 2)}</div>
                `;
            } else {
                output.innerHTML += `
                    <div class="console-line error">Error: ${data.result.error}</div>
                `;
            }

            // Store for export
            const widgetId = widget.dataset.widgetId;
            if (!this.widgetData[widgetId]) {
                this.widgetData[widgetId] = { type: 'console', history: [] };
            }
            this.widgetData[widgetId].history.push({
                timestamp,
                command,
                params,
                result: data.result
            });

        } catch (error) {
            output.innerHTML += `
                <div class="console-line error">Error: ${error.message}</div>
            `;
        }

        output.scrollTop = output.scrollHeight;
    }

    clearConsole(button) {
        const widget = button.closest('.grid-stack-item');
        const output = widget.querySelector('.console-output');
        output.innerHTML = '';

        const widgetId = widget.dataset.widgetId;
        if (this.widgetData[widgetId]) {
            this.widgetData[widgetId].history = [];
        }
    }

    // =========================================================================
    // Register Widget
    // =========================================================================

    async readRegister(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget.dataset.deviceId;
        const addressInput = widget.querySelector('.register-address');
        const result = widget.querySelector('.register-result');

        if (!deviceId) {
            alert('Please select a device first');
            return;
        }

        const address = parseInt(addressInput.value, 16);
        if (isNaN(address)) {
            alert('Invalid address');
            return;
        }

        try {
            const response = await fetch(`/api/device/${deviceId}/command`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    command: 'read_register',
                    params: { address }
                })
            });

            const data = await response.json();

            if (data.result.success) {
                result.innerHTML = `
                    <strong>Address:</strong> 0x${address.toString(16).toUpperCase()}<br>
                    <strong>Value:</strong> 0x${data.result.response.toString(16).toUpperCase()}
                `;
            } else {
                result.innerHTML = `<span style="color: var(--error)">Error: ${data.result.error}</span>`;
            }
        } catch (error) {
            result.innerHTML = `<span style="color: var(--error)">Error: ${error.message}</span>`;
        }
    }

    async writeRegister(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget.dataset.deviceId;
        const addressInput = widget.querySelector('.register-address');
        const valueInput = widget.querySelector('.register-value');
        const result = widget.querySelector('.register-result');

        if (!deviceId) {
            alert('Please select a device first');
            return;
        }

        const address = parseInt(addressInput.value, 16);
        const value = parseInt(valueInput.value, 16);

        if (isNaN(address) || isNaN(value)) {
            alert('Invalid address or value');
            return;
        }

        try {
            const response = await fetch(`/api/device/${deviceId}/command`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    command: 'write_register',
                    params: { address, value }
                })
            });

            const data = await response.json();

            if (data.result.success) {
                result.innerHTML = `
                    <strong>Written:</strong> 0x${value.toString(16).toUpperCase()} to 0x${address.toString(16).toUpperCase()}<br>
                    <span style="color: var(--success)">Success</span>
                `;
            } else {
                result.innerHTML = `<span style="color: var(--error)">Error: ${data.result.error}</span>`;
            }
        } catch (error) {
            result.innerHTML = `<span style="color: var(--error)">Error: ${error.message}</span>`;
        }
    }

    // =========================================================================
    // Export Functions
    // =========================================================================

    exportWidgetData(button, format) {
        const widget = button.closest('.grid-stack-item');
        const widgetId = widget.dataset.widgetId;
        const widgetType = widget.dataset.widgetType;
        const deviceId = widget.dataset.deviceId;

        let data = this.widgetData[widgetId];

        if (!data && widgetType === 'console') {
            const output = widget.querySelector('.console-output');
            data = { type: 'console', content: output.innerText };
        }

        if (!data) {
            alert('No data to export');
            return;
        }

        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        let filename, content, mimeType;

        if (format === 'json') {
            filename = `prometheus_${widgetType}_${timestamp}.json`;
            content = JSON.stringify(data, null, 2);
            mimeType = 'application/json';
        } else {
            filename = `prometheus_${widgetType}_${timestamp}.txt`;
            content = this.formatDataAsText(data, widgetType);
            mimeType = 'text/plain';
        }

        this.downloadFile(filename, content, mimeType);
    }

    formatDataAsText(data, widgetType) {
        let lines = [
            `Prometheus Export - ${widgetType}`,
            `Timestamp: ${new Date().toISOString()}`,
            '='.repeat(50),
            ''
        ];

        if ((widgetType === 'sysinfo' || widgetType === 'status') && data.data) {
            lines.push('SYSTEM INFORMATION');
            lines.push('-'.repeat(30));
            const sysinfo = data.data;

            // Handle nested sysinfo structure
            if (sysinfo.version) {
                lines.push('');
                lines.push('VERSION INFO:');
                for (const [key, value] of Object.entries(sysinfo.version)) {
                    if (value) lines.push(`  ${this.formatKey(key)}: ${value}`);
                }
            }
            if (sysinfo.thermal) {
                lines.push('');
                lines.push('THERMAL:');
                for (const [key, value] of Object.entries(sysinfo.thermal)) {
                    const temp = typeof value === 'number' ? `${value.toFixed(1)}°C` : value;
                    lines.push(`  ${this.formatKey(key)}: ${temp}`);
                }
            }
            if (sysinfo.power) {
                lines.push('');
                lines.push('POWER:');
                for (const [key, value] of Object.entries(sysinfo.power)) {
                    let formatted = value;
                    if (typeof value === 'number') {
                        if (key.includes('voltage')) formatted = `${value.toFixed(2)}V`;
                        else if (key.includes('current')) formatted = `${value.toFixed(2)}A`;
                        else if (key.includes('power')) formatted = `${value.toFixed(1)}W`;
                        else formatted = value.toFixed(2);
                    }
                    lines.push(`  ${this.formatKey(key)}: ${formatted}`);
                }
            }
            if (sysinfo.ports) {
                lines.push('');
                lines.push('PORTS:');
                for (const [portType, ports] of Object.entries(sysinfo.ports)) {
                    if (Array.isArray(ports)) {
                        const linked = ports.filter(p => p.is_linked).length;
                        lines.push(`  ${this.formatKey(portType)}: ${linked}/${ports.length} linked`);
                    }
                }
            }
            if (sysinfo.fans) {
                lines.push('');
                lines.push('FANS:');
                for (const [key, value] of Object.entries(sysinfo.fans)) {
                    lines.push(`  ${this.formatKey(key)}: ${value} RPM`);
                }
            }
            if (sysinfo.slots) {
                lines.push('');
                lines.push('SLOTS:');
                for (const slot of sysinfo.slots) {
                    const status = slot.present ? (slot.power_status || 'present') : 'empty';
                    lines.push(`  Slot ${slot.slot_number}: ${status}`);
                }
            }
        } else if (widgetType === 'console' && data.history) {
            lines.push('COMMAND HISTORY');
            lines.push('-'.repeat(30));
            data.history.forEach(entry => {
                lines.push(`[${entry.timestamp}] ${entry.command}`);
                if (entry.result.success) {
                    lines.push(JSON.stringify(entry.result.response, null, 2));
                } else {
                    lines.push(`Error: ${entry.result.error}`);
                }
                lines.push('');
            });
        } else if (data.content) {
            lines.push(data.content);
        }

        return lines.join('\n');
    }

    async exportAllSysinfo() {
        const connectedDevices = Object.keys(this.devices).filter(id => this.devices[id].connected);

        if (connectedDevices.length === 0) {
            alert('No connected devices');
            return;
        }

        try {
            const response = await fetch('/api/export/all-sysinfo?format=txt');
            const text = await response.text();

            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            this.downloadFile(`prometheus_all_sysinfo_${timestamp}.txt`, text, 'text/plain');
        } catch (error) {
            alert(`Export failed: ${error.message}`);
        }
    }

    downloadFile(filename, content, mimeType) {
        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // =========================================================================
    // Layout Persistence
    // =========================================================================

    saveLayout() {
        const layout = this.grid.save(true, true);
        localStorage.setItem('prometheus_layout', JSON.stringify(layout));

        // Also save widget bindings
        const bindings = {};
        document.querySelectorAll('.grid-stack-item').forEach(widget => {
            const id = widget.dataset.widgetId;
            bindings[id] = {
                type: widget.dataset.widgetType,
                deviceId: widget.dataset.deviceId
            };
        });
        localStorage.setItem('prometheus_bindings', JSON.stringify(bindings));

        alert('Layout saved!');
    }

    loadLayout() {
        const layoutJson = localStorage.getItem('prometheus_layout');

        if (!layoutJson) {
            // Add default widgets for first-time users
            this.addWidget('connection');
            return;
        }

        try {
            const layout = JSON.parse(layoutJson);

            // Validate layout is an array (GridStack expects this)
            if (!Array.isArray(layout)) {
                console.warn('Invalid layout format, clearing and using defaults');
                localStorage.removeItem('prometheus_layout');
                localStorage.removeItem('prometheus_bindings');
                this.addWidget('connection');
                return;
            }

            this.grid.load(layout);

            // Restore widget bindings
            const bindingsJson = localStorage.getItem('prometheus_bindings');
            if (bindingsJson) {
                const bindings = JSON.parse(bindingsJson);

                document.querySelectorAll('.grid-stack-item').forEach(widget => {
                    const id = widget.getAttribute('gs-id');
                    if (bindings[id]) {
                        widget.dataset.widgetType = bindings[id].type;
                        widget.dataset.widgetId = id;

                        // Update widget counter
                        const num = parseInt(id.replace('widget-', ''));
                        if (num > this.widgetCounter) {
                            this.widgetCounter = num;
                        }

                        // Initialize the widget (but don't restore device bindings - they need reconnection)
                        this.initializeWidget(widget, bindings[id].type);
                    }
                });
            }
        } catch (error) {
            console.error('Failed to load layout:', error);
            // Clear corrupt layout data
            localStorage.removeItem('prometheus_layout');
            localStorage.removeItem('prometheus_bindings');
            this.addWidget('connection');
        }
    }

    clearLayout() {
        localStorage.removeItem('prometheus_layout');
        localStorage.removeItem('prometheus_bindings');
        location.reload();
    }

    // =========================================================================
    // Utility Functions
    // =========================================================================

    formatKey(key) {
        return key
            .replace(/_/g, ' ')
            .replace(/([A-Z])/g, ' $1')
            .replace(/^./, str => str.toUpperCase())
            .trim();
    }

    // =========================================================================
    // Control Panel Widget
    // =========================================================================

    onControlDeviceChange(select) {
        const widget = select.closest('.grid-stack-item');
        const deviceId = select.value;
        const container = widget.querySelector('.control-panels-container');

        if (!deviceId) {
            container.innerHTML = '<div class="placeholder-message">Select a device to view controls</div>';
            return;
        }

        const device = this.devices[deviceId];
        if (!device) {
            container.innerHTML = '<div class="placeholder-message">Device not found</div>';
            return;
        }

        // Use DeviceRegistry to get template ID
        const templateId = DeviceRegistry.getControlTemplateId(device.type);
        const template = document.getElementById(templateId);

        if (!template) {
            container.innerHTML = '<div class="placeholder-message">Control panel template not found</div>';
            return;
        }

        container.innerHTML = '';
        container.appendChild(template.content.cloneNode(true));

        // Store device reference
        widget.dataset.deviceId = deviceId;
        widget.dataset.deviceType = device.type;

        // Load saved configs for this device type
        this.loadControlConfigList(widget, device.type);

        // Fetch current device settings
        this.fetchControlSettings(widget, deviceId);
    }

    async fetchControlSettings(widget, deviceId) {
        const device = this.devices[deviceId];
        if (!device) return;

        try {
            const response = await fetch(`/api/device/${deviceId}/control-status`);
            const data = await response.json();

            if (data.success && data.status) {
                // Use DeviceRegistry to update control values
                DeviceRegistry.updateControlValues(widget, data.status, device.type);
            }
        } catch (error) {
            console.error('Failed to fetch control settings:', error);
        }
    }

    loadControlConfigList(widget, deviceType) {
        const configSelect = widget.querySelector('.config-load-select');
        if (!configSelect) return;

        const configs = JSON.parse(localStorage.getItem(`prometheus_control_configs_${deviceType}`) || '{}');

        configSelect.innerHTML = '<option value="">Load config...</option>';
        for (const name of Object.keys(configs)) {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name;
            configSelect.appendChild(option);
        }
    }

    saveControlConfig(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceType = widget.dataset.deviceType;
        const nameInput = widget.querySelector('.config-name-input');
        const configName = nameInput?.value?.trim();

        if (!configName) {
            alert('Please enter a configuration name');
            return;
        }

        // Collect all control values
        const config = {};
        widget.querySelectorAll('.control-input').forEach(input => {
            const command = input.dataset.command;
            const param = input.dataset.param;
            const value = input.value;

            if (!config[command]) config[command] = {};
            config[command][param] = value;
        });

        // Save to localStorage
        const configKey = `prometheus_control_configs_${deviceType}`;
        const configs = JSON.parse(localStorage.getItem(configKey) || '{}');
        configs[configName] = config;
        localStorage.setItem(configKey, JSON.stringify(configs));

        // Update dropdown
        this.loadControlConfigList(widget, deviceType);
        nameInput.value = '';

        alert(`Configuration "${configName}" saved`);
    }

    loadControlConfig(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceType = widget.dataset.deviceType;
        const configSelect = widget.querySelector('.config-load-select');
        const configName = configSelect?.value;

        if (!configName) {
            alert('Please select a configuration to load');
            return;
        }

        const configKey = `prometheus_control_configs_${deviceType}`;
        const configs = JSON.parse(localStorage.getItem(configKey) || '{}');
        const config = configs[configName];

        if (!config) {
            alert('Configuration not found');
            return;
        }

        // Apply config values to inputs
        for (const [command, params] of Object.entries(config)) {
            for (const [param, value] of Object.entries(params)) {
                const input = widget.querySelector(`[data-command="${command}"][data-param="${param}"]`);
                if (input) input.value = value;
            }
        }

        alert(`Configuration "${configName}" loaded`);
    }

    async runControlCommands(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget.dataset.deviceId;
        const deviceType = widget.dataset.deviceType;

        if (!deviceId) {
            alert('No device selected');
            return;
        }

        // Collect commands to run
        const commands = this.collectControlCommands(widget, deviceType);

        if (commands.length === 0) {
            alert('No commands to run. Change some settings first.');
            return;
        }

        // Check for dangerous commands
        const dangerousCommands = commands.filter(c =>
            (c.command === 'setmode') ||
            (c.command === 'syspwr' && c.params.state === 'off')
        );

        if (dangerousCommands.length > 0) {
            const warnings = dangerousCommands.map(c => {
                if (c.command === 'setmode') {
                    return '- Changing mode requires a power cycle of the Atlas3 device. The device will be disconnected.';
                }
                if (c.command === 'syspwr') {
                    return '- System power off will shut down the Hydra. The device will be disconnected.';
                }
                return '';
            }).join('\n');

            if (!confirm(`Warning:\n${warnings}\n\nDo you want to proceed?`)) {
                return;
            }
        }

        // Disable button and show running state
        button.disabled = true;
        button.textContent = 'Running...';

        // Remove any existing result display
        const existingResult = widget.querySelector('.control-result');
        if (existingResult) existingResult.remove();

        // Create result display
        const resultDiv = document.createElement('div');
        resultDiv.className = 'control-result running';
        resultDiv.textContent = 'Executing commands...';
        widget.querySelector('.control-actions').appendChild(resultDiv);

        try {
            const response = await fetch(`/api/device/${deviceId}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ commands })
            });

            const data = await response.json();

            if (data.success) {
                resultDiv.className = 'control-result success';
                resultDiv.textContent = `${data.results.length} command(s) executed successfully`;

                // Check if we need to disconnect
                if (data.disconnect) {
                    await this.handleControlDisconnect(deviceId, widget);
                } else {
                    // Refresh current settings
                    await this.fetchControlSettings(widget, deviceId);
                }
            } else {
                resultDiv.className = 'control-result error';
                resultDiv.textContent = `Error: ${data.error || 'Unknown error'}`;
            }
        } catch (error) {
            resultDiv.className = 'control-result error';
            resultDiv.textContent = `Error: ${error.message}`;
        } finally {
            button.disabled = false;
            button.textContent = 'Run';

            // Auto-hide result after 5 seconds
            setTimeout(() => {
                if (resultDiv.parentNode) resultDiv.remove();
            }, 5000);
        }
    }

    collectControlCommands(widget, deviceType) {
        const commands = [];
        const commandGroups = {};

        // Group inputs by command
        widget.querySelectorAll('.control-input').forEach(input => {
            const command = input.dataset.command;
            const param = input.dataset.param;
            let value = input.value;

            // Skip empty values (no change selections)
            if (value === '' || value === undefined) return;

            // Convert string booleans
            if (value === 'true') value = true;
            if (value === 'false') value = false;

            if (!commandGroups[command]) {
                commandGroups[command] = {};
            }
            commandGroups[command][param] = value;
        });

        // Build command list, filtering out incomplete commands
        for (const [command, params] of Object.entries(commandGroups)) {
            // Use DeviceRegistry to validate command
            if (DeviceRegistry.isValidCommand(command, params, deviceType)) {
                commands.push({ command, params });
            }
        }

        return commands;
    }

    async handleControlDisconnect(deviceId, widget) {
        // Disconnect the device
        try {
            await fetch(`/api/disconnect/${deviceId}`, { method: 'POST' });

            // Update local state
            if (this.devices[deviceId]) {
                this.devices[deviceId].connected = false;
                delete this.devices[deviceId];
            }

            // Reset the control panel
            const container = widget.querySelector('.control-panels-container');
            container.innerHTML = '<div class="placeholder-message">Device disconnected. Please reconnect.</div>';

            const select = widget.querySelector('.widget-device-select');
            if (select) select.value = '';

            widget.dataset.deviceId = '';

            // Update connection widget and device selectors
            this.updateConnectedDevicesList();
            document.querySelectorAll('.widget-device-select').forEach(s => {
                this.populateDeviceSelect(s);
            });
        } catch (error) {
            console.error('Failed to disconnect:', error);
        }
    }

    // =========================================================================
    // Modern Control Panel - On-Click Command Execution
    // =========================================================================

    /**
     * Execute an Atlas3 command immediately on button click
     */
    async executeAtlas3Command(button, command, params) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget?.dataset.deviceId;

        if (!deviceId) {
            alert('No device selected');
            return;
        }

        // Add executing state to button
        button.classList.add('executing');

        try {
            const response = await fetch(`/api/device/${deviceId}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    commands: [{ command, params }]
                })
            });

            const data = await response.json();

            if (data.success) {
                // Flash success state
                button.classList.remove('executing');
                button.classList.add('btn-success');
                setTimeout(() => button.classList.remove('btn-success'), 1000);

                // Update active state for button groups (spread, mode)
                this.updateButtonGroupState(button);
            } else {
                button.classList.remove('executing');
                button.classList.add('btn-danger');
                setTimeout(() => button.classList.remove('btn-danger'), 2000);
                console.error('Command failed:', data.error);
            }
        } catch (error) {
            button.classList.remove('executing');
            button.classList.add('btn-danger');
            setTimeout(() => button.classList.remove('btn-danger'), 2000);
            console.error('Command error:', error);
        }
    }

    /**
     * Execute Atlas3 mode change with confirmation and disconnect
     */
    async executeAtlas3ModeChange(button, mode) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget?.dataset.deviceId;

        if (!deviceId) {
            alert('No device selected');
            return;
        }

        // Confirm mode change
        const confirmed = confirm(
            `Changing to Mode ${mode} requires a power cycle of the Atlas3 device.\n\n` +
            `The device will be disconnected after this command.\n\n` +
            `Do you want to proceed?`
        );

        if (!confirmed) return;

        button.classList.add('executing');

        try {
            const response = await fetch(`/api/device/${deviceId}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    commands: [{ command: 'setmode', params: { mode: mode } }]
                })
            });

            const data = await response.json();

            if (data.success) {
                // Update button state
                this.updateButtonGroupState(button);

                // Disconnect the device
                await this.handleControlDisconnect(deviceId, widget);

                alert('Mode changed successfully. Please power cycle the Atlas3 device and reconnect.');
            } else {
                button.classList.remove('executing');
                button.classList.add('btn-danger');
                setTimeout(() => button.classList.remove('btn-danger'), 2000);
                alert(`Mode change failed: ${data.error || 'Unknown error'}`);
            }
        } catch (error) {
            button.classList.remove('executing');
            button.classList.add('btn-danger');
            setTimeout(() => button.classList.remove('btn-danger'), 2000);
            alert(`Mode change error: ${error.message}`);
        }
    }

    /**
     * Execute Atlas3 clock toggle
     */
    async executeAtlas3ClockToggle(toggleLabel) {
        // Prevent the default toggle behavior - we'll handle it manually
        event.preventDefault();

        const widget = toggleLabel.closest('.grid-stack-item');
        const deviceId = widget?.dataset.deviceId;
        const checkbox = toggleLabel.querySelector('input[type="checkbox"]');
        const label = toggleLabel.querySelector('.toggle-label');

        if (!deviceId) {
            alert('No device selected');
            return;
        }

        // Toggle to the opposite state
        const newState = !checkbox.checked;

        toggleLabel.classList.add('disabled');

        try {
            const response = await fetch(`/api/device/${deviceId}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    commands: [{ command: 'clk', params: { enable: newState } }]
                })
            });

            const data = await response.json();

            if (data.success) {
                // Update checkbox and label
                checkbox.checked = newState;
                label.textContent = newState ? 'Enabled' : 'Disabled';
                label.classList.toggle('active', newState);
            } else {
                console.error('Clock toggle failed:', data.error);
            }
        } catch (error) {
            console.error('Clock toggle error:', error);
        } finally {
            toggleLabel.classList.remove('disabled');
        }
    }

    /**
     * Update button group state (mark active button)
     */
    updateButtonGroupState(activeButton) {
        const group = activeButton.closest('.control-btn-group');
        if (group) {
            // Remove active from all buttons in group
            group.querySelectorAll('.control-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            // Add active to clicked button
            activeButton.classList.add('active');
        }
        activeButton.classList.remove('executing');
    }

    // =========================================================================
    // Hydra Control Panel - On-Click Command Execution
    // =========================================================================

    /**
     * Execute a Hydra command immediately on button click
     */
    async executeHydraCommand(button, command, params) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget?.dataset.deviceId;

        if (!deviceId) {
            alert('No device selected');
            return;
        }

        // Check for dangerous commands
        if (command === 'syspwr' && params.state === 'off') {
            const confirmed = confirm(
                'System power off will shut down the Hydra.\n\n' +
                'The device will be disconnected.\n\n' +
                'Do you want to proceed?'
            );
            if (!confirmed) return;
        }

        button.classList.add('executing');

        try {
            const response = await fetch(`/api/device/${deviceId}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    commands: [{ command, params }]
                })
            });

            const data = await response.json();

            if (data.success) {
                button.classList.remove('executing');

                // Check if this is a rocker button
                const rockerSwitch = button.closest('.rocker-switch');
                if (rockerSwitch) {
                    // Update rocker switch state
                    rockerSwitch.querySelectorAll('.rocker-btn').forEach(btn => {
                        btn.classList.remove('active');
                    });
                    button.classList.add('active');
                } else {
                    // Standard button feedback
                    button.classList.add('btn-success');
                    setTimeout(() => button.classList.remove('btn-success'), 1000);

                    // Update active state for button groups
                    this.updateButtonGroupState(button);
                }

                // Handle disconnect for power off
                if (command === 'syspwr' && params.state === 'off') {
                    await this.handleControlDisconnect(deviceId, widget);
                }
            } else {
                button.classList.remove('executing');
                button.classList.add('btn-danger');
                setTimeout(() => button.classList.remove('btn-danger'), 2000);
                console.error('Command failed:', data.error);
            }
        } catch (error) {
            button.classList.remove('executing');
            button.classList.add('btn-danger');
            setTimeout(() => button.classList.remove('btn-danger'), 2000);
            console.error('Command error:', error);
        }
    }

    /**
     * Execute Hydra buzzer on with auto-enable
     * Sends enable first, then on, to ensure buzzer sounds
     */
    async executeHydraBuzzerOn(button) {
        const widget = button.closest('.grid-stack-item');
        const deviceId = widget?.dataset.deviceId;

        if (!deviceId) {
            alert('No device selected');
            return;
        }

        button.classList.add('executing');

        try {
            // Send both enable and on commands
            const response = await fetch(`/api/device/${deviceId}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    commands: [
                        { command: 'buz', params: { state: 'enable' } },
                        { command: 'buz', params: { state: 'on' } }
                    ]
                })
            });

            const data = await response.json();
            console.log('Hydra buzzer on response:', data);

            if (data.success) {
                button.classList.remove('executing');

                // Update rocker switch state
                const rockerSwitch = button.closest('.rocker-switch');
                if (rockerSwitch) {
                    rockerSwitch.querySelectorAll('.rocker-btn').forEach(btn => {
                        btn.classList.remove('active');
                    });
                    button.classList.add('active');
                }

                // Also update the enable rocker to show it's enabled
                const section = button.closest('.control-section-body');
                const enableRocker = section?.querySelector('.rocker-switch:first-of-type');
                if (enableRocker) {
                    enableRocker.querySelectorAll('.rocker-btn').forEach(btn => {
                        btn.classList.remove('active');
                    });
                    enableRocker.querySelector('.rocker-right')?.classList.add('active');
                }
            } else {
                button.classList.remove('executing');
                button.classList.add('btn-danger');
                setTimeout(() => button.classList.remove('btn-danger'), 2000);
                console.error('Buzzer command failed:', data.error);
            }
        } catch (error) {
            button.classList.remove('executing');
            button.classList.add('btn-danger');
            setTimeout(() => button.classList.remove('btn-danger'), 2000);
            console.error('Buzzer command error:', error);
        }
    }

    /**
     * Execute Hydra toggle command (for LED, power toggles)
     */
    async executeHydraToggle(toggleLabel, command, paramName, slot = null) {
        event.preventDefault();

        const widget = toggleLabel.closest('.grid-stack-item');
        const deviceId = widget?.dataset.deviceId;
        const checkbox = toggleLabel.querySelector('input[type="checkbox"]');
        const label = toggleLabel.querySelector('.toggle-label');

        if (!deviceId) {
            alert('No device selected');
            return;
        }

        const newState = !checkbox.checked;
        const params = { [paramName]: newState ? 'on' : 'off' };
        if (slot !== null) {
            params.slot = slot;
        }

        toggleLabel.classList.add('disabled');

        try {
            const response = await fetch(`/api/device/${deviceId}/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    commands: [{ command, params }]
                })
            });

            const data = await response.json();

            if (data.success) {
                checkbox.checked = newState;
                if (label) {
                    label.textContent = newState ? 'On' : 'Off';
                    label.classList.toggle('active', newState);
                }
            } else {
                console.error('Toggle failed:', data.error);
            }
        } catch (error) {
            console.error('Toggle error:', error);
        } finally {
            toggleLabel.classList.remove('disabled');
        }
    }
}

// Initialize dashboard
const dashboard = new PrometheusDashboard();