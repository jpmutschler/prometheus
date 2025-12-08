/**
 * Prometheus Atlas3 Device Handler
 * Frontend handler for Atlas3 PCIe switch devices
 */

const Atlas3Handler = {
    deviceType: 'atlas3',

    /**
     * Get control panel template ID
     */
    getControlTemplateId() {
        return 'control-panel-atlas3';
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
            if (sysinfo.version.mcu_version) {
                flat['MCU Version'] = sysinfo.version.mcu_version;
            }
            if (sysinfo.version.cpld_version) {
                flat['CPLD Version'] = sysinfo.version.cpld_version;
            }
            if (sysinfo.version.sbr_version) {
                flat['SBR Version'] = sysinfo.version.sbr_version;
            }
        }

        // Thermal info
        if (sysinfo.thermal && sysinfo.thermal.switch_temp !== undefined) {
            flat['Switch Temp'] = `${(sysinfo.thermal.switch_temp || 0).toFixed(1)}°C`;
        }

        // Fan info
        if (sysinfo.fan && sysinfo.fan.switch_fan_rpm) {
            flat['Fan Speed'] = `${sysinfo.fan.switch_fan_rpm} RPM`;
        }

        // Power info
        if (sysinfo.power) {
            if (sysinfo.power.voltage !== undefined) {
                flat['Voltage'] = `${(sysinfo.power.voltage || 0).toFixed(2)}V`;
            }
            if (sysinfo.power.current !== undefined) {
                flat['Current'] = `${(sysinfo.power.current || 0).toFixed(2)}A`;
            }
            if (sysinfo.power.power !== undefined) {
                flat['Power'] = `${(sysinfo.power.power || 0).toFixed(1)}W`;
            }
        }

        // Ports info
        if (sysinfo.ports) {
            const countLinked = (ports) => ports ? ports.filter(p => p.is_linked).length : 0;
            if (sysinfo.ports.upstream) {
                flat['Upstream Ports'] = `${countLinked(sysinfo.ports.upstream)} linked`;
            }
            const extMcio = sysinfo.ports.ext_mcio || [];
            const intMcio = sysinfo.ports.int_mcio || [];
            const mcioLinked = countLinked(extMcio) + countLinked(intMcio);
            flat['MCIO Ports'] = `${mcioLinked} linked`;
        }

        return flat;
    },

    /**
     * Extract temperatures from sysinfo for temperature widget
     */
    extractTemperatures(sysinfo) {
        const temperatures = {};
        if (sysinfo.thermal?.switch_temp) {
            temperatures['Switch'] = sysinfo.thermal.switch_temp;
        }
        return temperatures;
    },

    /**
     * Render ports in the ports widget
     */
    renderPorts(container, sysinfo) {
        if (!sysinfo.ports) {
            container.innerHTML = '<div class="placeholder-message">No port data available</div>';
            return;
        }

        let html = '';

        // Helper to get status class based on port status
        const getStatusClass = (port) => {
            if (!port.is_linked) return 'link-down';
            if (port.status === 'Degraded') return 'link-degraded';
            return 'link-up';
        };

        // Helper to format link info
        const formatLinkInfo = (port) => {
            if (!port.is_linked) return `Max: ${port.max_speed || '--'} x${port.max_width || '--'}`;
            return `${port.speed || '--'} x${port.width || 0} / ${port.max_speed || '--'} x${port.max_width || '--'}`;
        };

        // Chip version header if available
        if (sysinfo.ports.chip_version) {
            html += `<div class="chip-version">Atlas3 ${sysinfo.ports.chip_version}</div>`;
        }

        // Upstream ports
        if (sysinfo.ports.upstream && sysinfo.ports.upstream.length > 0) {
            html += '<div class="port-section"><div class="port-section-header">Upstream Ports</div><div class="ports-grid">';
            for (const port of sysinfo.ports.upstream) {
                const statusClass = getStatusClass(port);
                html += `
                    <div class="port-item ${statusClass}">
                        <span class="port-name">${port.connector || 'USP'}</span>
                        <span class="port-number">Port ${port.port_number}</span>
                        <span class="port-status">${port.status || (port.is_linked ? 'Linked' : 'Idle')}</span>
                        <span class="port-detail">${formatLinkInfo(port)}</span>
                    </div>
                `;
            }
            html += '</div></div>';
        }

        // EXT MCIO ports
        if (sysinfo.ports.ext_mcio && sysinfo.ports.ext_mcio.length > 0) {
            html += '<div class="port-section"><div class="port-section-header">EXT MCIO Ports</div><div class="ports-grid">';
            for (const port of sysinfo.ports.ext_mcio) {
                const statusClass = getStatusClass(port);
                html += `
                    <div class="port-item ${statusClass}">
                        <span class="port-name">${port.connector || 'MCIO'}</span>
                        <span class="port-number">Port ${port.port_number}</span>
                        <span class="port-status">${port.status || (port.is_linked ? 'Linked' : 'Idle')}</span>
                        <span class="port-detail">${formatLinkInfo(port)}</span>
                    </div>
                `;
            }
            html += '</div></div>';
        }

        // INT MCIO ports
        if (sysinfo.ports.int_mcio && sysinfo.ports.int_mcio.length > 0) {
            html += '<div class="port-section"><div class="port-section-header">INT MCIO Ports</div><div class="ports-grid">';
            for (const port of sysinfo.ports.int_mcio) {
                const statusClass = getStatusClass(port);
                html += `
                    <div class="port-item ${statusClass}">
                        <span class="port-name">${port.connector || 'MCIO'}</span>
                        <span class="port-number">Port ${port.port_number}</span>
                        <span class="port-status">${port.status || (port.is_linked ? 'Linked' : 'Idle')}</span>
                        <span class="port-detail">${formatLinkInfo(port)}</span>
                    </div>
                `;
            }
            html += '</div></div>';
        }

        // Straddle ports
        if (sysinfo.ports.straddle && sysinfo.ports.straddle.length > 0) {
            html += '<div class="port-section"><div class="port-section-header">Straddle Ports</div><div class="ports-grid">';
            for (const port of sysinfo.ports.straddle) {
                const statusClass = getStatusClass(port);
                html += `
                    <div class="port-item ${statusClass}">
                        <span class="port-name">${port.connector || 'Straddle'}</span>
                        <span class="port-number">Port ${port.port_number}</span>
                        <span class="port-status">${port.status || (port.is_linked ? 'Linked' : 'Idle')}</span>
                        <span class="port-detail">${formatLinkInfo(port)}</span>
                    </div>
                `;
            }
            html += '</div></div>';
        }

        if (!html) {
            html = '<div class="placeholder-message">No ports configured</div>';
        }

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
                            <span class="status-item-label">MCU Version</span>
                            <span class="status-item-value">${sysinfo.version.mcu_version || 'N/A'}</span>
                        </div>
                        <div class="status-item">
                            <span class="status-item-label">SBR Version</span>
                            <span class="status-item-value">${sysinfo.version.sbr_version || 'N/A'}</span>
                        </div>
                    </div>
                </div>
            `;
        }

        // Thermal section
        if (sysinfo.thermal) {
            const switchTemp = sysinfo.thermal.switch_temp || 0;
            const tempClass = (temp) => temp < 50 ? 'success' : temp < 70 ? 'warning' : 'error';

            html += `
                <div class="status-section">
                    <div class="status-section-header">Thermal</div>
                    <div class="status-grid">
                        <div class="status-item">
                            <span class="status-item-label">Switch Temp</span>
                            <span class="status-item-value ${tempClass(switchTemp)}">${switchTemp.toFixed(1)}°C</span>
                        </div>
            `;

            // Add fan info if available
            if (sysinfo.fan && sysinfo.fan.switch_fan_rpm) {
                html += `
                        <div class="status-item">
                            <span class="status-item-label">Fan Speed</span>
                            <span class="status-item-value">${sysinfo.fan.switch_fan_rpm} RPM</span>
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
                            <span class="status-item-label">Voltage</span>
                            <span class="status-item-value">${(sysinfo.power.voltage || 0).toFixed(2)}V</span>
                        </div>
                        <div class="status-item">
                            <span class="status-item-label">Current</span>
                            <span class="status-item-value">${(sysinfo.power.current || 0).toFixed(2)}A</span>
                        </div>
                        <div class="status-item">
                            <span class="status-item-label">Power</span>
                            <span class="status-item-value highlight">${(sysinfo.power.power || 0).toFixed(1)}W</span>
                        </div>
                    </div>
                </div>
            `;
        }

        // Ports section
        if (sysinfo.ports) {
            const countLinked = (ports) => ports ? ports.filter(p => p.is_linked).length : 0;
            const upstreamLinked = countLinked(sysinfo.ports.upstream);
            const mcioLinked = countLinked(sysinfo.ports.ext_mcio) + countLinked(sysinfo.ports.int_mcio);
            const straddleLinked = countLinked(sysinfo.ports.straddle);

            html += `
                <div class="status-section">
                    <div class="status-section-header">Port Status</div>
                    <div class="status-grid">
                        <div class="status-item">
                            <span class="status-item-label">Upstream</span>
                            <span class="status-item-value ${upstreamLinked > 0 ? 'success' : ''}">${upstreamLinked} linked</span>
                        </div>
                        <div class="status-item">
                            <span class="status-item-label">MCIO</span>
                            <span class="status-item-value ${mcioLinked > 0 ? 'success' : ''}">${mcioLinked} linked</span>
                        </div>
                        <div class="status-item">
                            <span class="status-item-label">Straddle</span>
                            <span class="status-item-value ${straddleLinked > 0 ? 'success' : ''}">${straddleLinked} linked</span>
                        </div>
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
            case 'setmode':
                return params.mode !== undefined;
            case 'clk':
                return params.enable !== undefined;
            case 'spread':
                return params.mode !== undefined;
            case 'flit':
                return params.station !== undefined && params.disable !== undefined;
            case 'conrst':
                return params.connector !== undefined;
            default:
                return false;
        }
    },

    /**
     * Update control panel with current values from device
     */
    updateControlValues(widget, status) {
        // Update Mode display
        if (status.mode !== undefined) {
            const modeEl = widget.querySelector('.mode-current');
            if (modeEl) modeEl.textContent = `Mode ${status.mode}`;
            const modeSelect = widget.querySelector('[data-command="setmode"][data-param="mode"]');
            if (modeSelect) modeSelect.value = status.mode;
        }

        // Update Clock display
        if (status.clock !== undefined) {
            const clockEl = widget.querySelector('.clock-current');
            const clockEnabled = status.clock.straddle_enabled || status.clock.ext_mcio_enabled || status.clock.int_mcio_enabled;
            if (clockEl) clockEl.textContent = clockEnabled ? 'Enabled' : 'Disabled';
            const clkSelect = widget.querySelector('[data-command="clk"][data-param="enable"]');
            if (clkSelect) clkSelect.value = clockEnabled ? 'true' : 'false';
        }

        // Update Spread display
        if (status.spread !== undefined) {
            const spreadSelect = widget.querySelector('[data-command="spread"][data-param="mode"]');
            if (spreadSelect && status.spread.mode) {
                spreadSelect.value = status.spread.mode;
            }
        }

        // Update FLIT display
        if (status.flit !== undefined) {
            const flitEl = widget.querySelector('.flit-current');
            const anyDisabled = status.flit.station2 || status.flit.station5 || status.flit.station7 || status.flit.station8;
            if (flitEl) flitEl.textContent = anyDisabled ? 'Some Disabled' : 'All Enabled';
        }
    }
};

// Register with DeviceRegistry
if (window.DeviceRegistry) {
    DeviceRegistry.register('atlas3', Atlas3Handler);
}