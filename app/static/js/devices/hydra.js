/**
 * Prometheus HYDRA Device Handler
 * Frontend handler for HYDRA JBOF controller devices
 */

const HydraHandler = {
    deviceType: 'hydra',

    /**
     * Get control panel template ID
     */
    getControlTemplateId() {
        return 'control-panel-hydra';
    },

    /**
     * Flatten sysinfo for display in sysinfo widget
     */
    flattenSysinfo(sysinfo) {
        const flat = {};

        // Version info
        if (sysinfo.version) {
            flat['Model'] = sysinfo.version.model || 'N/A';
            flat['Serial Number'] = sysinfo.version.serial_number || 'N/A';
            if (sysinfo.version.firmware_version) {
                flat['Firmware'] = sysinfo.version.firmware_version;
            }
            if (sysinfo.version.build_time) {
                flat['Build Time'] = sysinfo.version.build_time;
            }
        }

        // Thermal info
        if (sysinfo.thermal && sysinfo.thermal.mcu_temp !== undefined) {
            flat['MCU Temp'] = `${(sysinfo.thermal.mcu_temp || 0).toFixed(1)}°C`;
        }

        // Fans info
        if (sysinfo.fans) {
            if (sysinfo.fans.fan1_rpm) {
                flat['Fan 1'] = `${sysinfo.fans.fan1_rpm} RPM`;
            }
            if (sysinfo.fans.fan2_rpm) {
                flat['Fan 2'] = `${sysinfo.fans.fan2_rpm} RPM`;
            }
        }

        // Power info
        if (sysinfo.power && sysinfo.power.psu_voltage !== undefined) {
            flat['PSU Voltage'] = `${(sysinfo.power.psu_voltage || 0).toFixed(2)}V`;
        }

        // Slots info
        if (sysinfo.slots && sysinfo.slots.length > 0) {
            const activeSlots = sysinfo.slots.filter(s => s.power_status === 'on');
            flat['Active Slots'] = `${activeSlots.length}/${sysinfo.slots.length}`;
        }

        return flat;
    },

    /**
     * Extract temperatures from sysinfo for temperature widget
     */
    extractTemperatures(sysinfo) {
        const temperatures = {};

        // MCU temp
        if (sysinfo.thermal?.mcu_temp) {
            temperatures['MCU'] = sysinfo.thermal.mcu_temp;
        }

        // Slot temperatures
        if (sysinfo.slots) {
            for (const slot of sysinfo.slots) {
                if (slot.temperature && slot.temperature > 0) {
                    temperatures[`Slot ${slot.slot_number}`] = slot.temperature;
                }
            }
        }

        return temperatures;
    },

    /**
     * Render ports (slots) in the ports widget
     */
    renderPorts(container, sysinfo) {
        if (!sysinfo.slots || sysinfo.slots.length === 0) {
            container.innerHTML = '<div class="placeholder-message">No slot data available</div>';
            return;
        }

        let html = '<div class="ports-grid hydra-slots">';

        for (const slot of sysinfo.slots) {
            const isOn = slot.power_status === 'on';
            const statusClass = isOn ? 'link-up' : 'link-down';
            const tempStr = slot.temperature ? `${slot.temperature.toFixed(0)}°C` : '--';
            const powerStr = isOn && slot.power ? `${slot.power.toFixed(1)}W` : '--';

            html += `
                <div class="port-item ${statusClass}">
                    <span class="port-number">Slot ${slot.slot_number}</span>
                    <span class="port-status">${isOn ? 'ON' : 'OFF'}</span>
                    <span class="port-detail">${tempStr}</span>
                    <span class="port-detail">${powerStr}</span>
                </div>
            `;
        }

        html += '</div>';
        container.innerHTML = html;
    },

    /**
     * Render status widget content
     */
    renderStatus(sysinfo) {
        let html = '';

        // Version section
        if (sysinfo.version) {
            html += `
                <div class="status-section">
                    <div class="status-section-header">Device Info</div>
                    <div class="status-grid">
                        <div class="status-item">
                            <span class="status-item-label">Model</span>
                            <span class="status-item-value">${sysinfo.version.model || 'N/A'}</span>
                        </div>
                        <div class="status-item">
                            <span class="status-item-label">Serial</span>
                            <span class="status-item-value highlight">${sysinfo.version.serial_number || 'N/A'}</span>
                        </div>
                        <div class="status-item">
                            <span class="status-item-label">Firmware</span>
                            <span class="status-item-value">${sysinfo.version.firmware_version || 'N/A'}</span>
                        </div>
                        <div class="status-item">
                            <span class="status-item-label">Build</span>
                            <span class="status-item-value">${sysinfo.version.build_time || 'N/A'}</span>
                        </div>
                    </div>
                </div>
            `;
        }

        // Thermal & Fans section
        if (sysinfo.fans || sysinfo.thermal) {
            const mcuTemp = sysinfo.thermal?.mcu_temp || 0;
            const tempClass = (temp) => temp < 50 ? 'success' : temp < 70 ? 'warning' : 'error';

            html += `
                <div class="status-section">
                    <div class="status-section-header">Thermal & Fans</div>
                    <div class="status-grid">
            `;

            if (mcuTemp) {
                html += `
                        <div class="status-item">
                            <span class="status-item-label">MCU Temp</span>
                            <span class="status-item-value ${tempClass(mcuTemp)}">${mcuTemp.toFixed(1)}°C</span>
                        </div>
                `;
            }

            if (sysinfo.fans) {
                html += `
                        <div class="status-item">
                            <span class="status-item-label">Fan 1</span>
                            <span class="status-item-value">${sysinfo.fans.fan1_rpm || 0} RPM</span>
                        </div>
                        <div class="status-item">
                            <span class="status-item-label">Fan 2</span>
                            <span class="status-item-value">${sysinfo.fans.fan2_rpm || 0} RPM</span>
                        </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        // Power section
        if (sysinfo.power) {
            html += `
                <div class="status-section">
                    <div class="status-section-header">Power</div>
                    <div class="status-grid">
                        <div class="status-item">
                            <span class="status-item-label">PSU Voltage</span>
                            <span class="status-item-value">${(sysinfo.power.psu_voltage || 0).toFixed(2)}V</span>
                        </div>
                    </div>
                </div>
            `;
        }

        // Slots section
        if (sysinfo.slots && sysinfo.slots.length > 0) {
            const presentCount = sysinfo.slots.filter(s => s.present || s.power_status === 'on').length;
            html += `
                <div class="status-section">
                    <div class="status-section-header">Slots (${presentCount}/${sysinfo.slots.length} in use)</div>
                    <div class="status-grid">
            `;

            for (const slot of sysinfo.slots) {
                const isOn = slot.power_status === 'on';
                const statusClass = isOn ? 'success' : '';
                const tempStr = slot.temperature ? ` ${slot.temperature.toFixed(0)}°C` : '';
                const statusText = isOn ? `ON${tempStr}` : 'off';
                html += `
                    <div class="status-item">
                        <span class="status-item-label">Slot ${slot.slot_number}</span>
                        <span class="status-item-value ${statusClass}">${statusText}</span>
                    </div>
                `;
            }

            html += `
                    </div>
                </div>
            `;
        }

        return html;
    },

    /**
     * Validate a command
     */
    isValidCommand(command, params) {
        switch (command) {
            case 'syspwr':
                return params.state !== undefined && params.state !== '';
            case 'ssdpwr':
                return params.slot !== undefined && params.slot !== '' && params.state !== undefined;
            case 'ssdrst':
            case 'smbrst':
                return params.slot !== undefined && params.slot !== '';
            case 'hled':
            case 'fled':
                return params.slot !== undefined && params.slot !== '' && params.state !== undefined;
            case 'buz':
                return params.state !== undefined && params.state !== '';
            case 'pwmctrl':
                return params.fan_id !== undefined && params.fan_id !== '' && params.duty !== undefined;
            case 'dual':
                return params.slot !== undefined && params.slot !== '' && params.enabled !== undefined;
            case 'pwrdis':
                return params.slot !== undefined && params.slot !== '' && params.level !== undefined;
            default:
                return false;
        }
    },

    /**
     * Update control panel with current values from device
     */
    updateControlValues(widget, status) {
        // Hydra status updates - slot power status could be displayed
        // Currently the control panel doesn't have specific fields to update
        // This can be extended when needed
    }
};

// Register with DeviceRegistry
if (window.DeviceRegistry) {
    DeviceRegistry.register('hydra', HydraHandler);
}