/**
 * Prometheus Device Registry
 * Central registry for device-specific handlers
 *
 * This module provides a plugin architecture for device types.
 * Each device type registers a handler with methods for:
 * - Rendering data (ports, status, sysinfo)
 * - Validating commands
 * - Flattening/transforming data for display
 */

const DeviceRegistry = {
    // Registered device handlers
    _handlers: {},

    /**
     * Register a device handler
     * @param {string} deviceType - Device type identifier (e.g., 'atlas3', 'hydra')
     * @param {Object} handler - Handler object with device-specific methods
     */
    register(deviceType, handler) {
        if (!handler.deviceType) {
            handler.deviceType = deviceType;
        }
        this._handlers[deviceType] = handler;
        console.log(`Registered device handler: ${deviceType}`);
    },

    /**
     * Get a handler for a device type
     * @param {string} deviceType - Device type identifier
     * @returns {Object|null} Handler object or null if not registered
     */
    get(deviceType) {
        return this._handlers[deviceType] || null;
    },

    /**
     * Check if a device type is registered
     * @param {string} deviceType - Device type identifier
     * @returns {boolean}
     */
    isRegistered(deviceType) {
        return deviceType in this._handlers;
    },

    /**
     * Get all registered device types
     * @returns {string[]}
     */
    getAllTypes() {
        return Object.keys(this._handlers);
    },

    /**
     * Get the control panel template ID for a device type
     * @param {string} deviceType - Device type identifier
     * @returns {string|null}
     */
    getControlTemplateId(deviceType) {
        const handler = this.get(deviceType);
        if (handler && handler.getControlTemplateId) {
            return handler.getControlTemplateId();
        }
        return `control-panel-${deviceType}`;
    },

    /**
     * Render ports for a device
     * @param {HTMLElement} container - Container element
     * @param {Object} sysinfo - Sysinfo data from API
     * @param {string} deviceType - Device type identifier
     */
    renderPorts(container, sysinfo, deviceType) {
        const handler = this.get(deviceType);
        if (handler && handler.renderPorts) {
            handler.renderPorts(container, sysinfo);
        } else {
            container.innerHTML = '<div class="placeholder-message">Unknown device type</div>';
        }
    },

    /**
     * Render status for a device
     * @param {Object} sysinfo - Sysinfo data from API
     * @param {string} deviceType - Device type identifier
     * @returns {string} HTML string
     */
    renderStatus(sysinfo, deviceType) {
        const handler = this.get(deviceType);
        if (handler && handler.renderStatus) {
            return handler.renderStatus(sysinfo);
        }
        return '<div class="placeholder-message">Unknown device type</div>';
    },

    /**
     * Flatten sysinfo for display
     * @param {Object} sysinfo - Sysinfo data from API
     * @param {string} deviceType - Device type identifier
     * @returns {Object} Flattened key-value pairs
     */
    flattenSysinfo(sysinfo, deviceType) {
        const handler = this.get(deviceType);
        if (handler && handler.flattenSysinfo) {
            return handler.flattenSysinfo(sysinfo);
        }
        // Fallback: return version info if available
        if (sysinfo.version) {
            return {
                'Model': sysinfo.version.model || 'N/A',
                'Serial Number': sysinfo.version.serial_number || 'N/A'
            };
        }
        return {};
    },

    /**
     * Extract temperatures from sysinfo
     * @param {Object} sysinfo - Sysinfo data from API
     * @param {string} deviceType - Device type identifier
     * @returns {Object} Temperature key-value pairs
     */
    extractTemperatures(sysinfo, deviceType) {
        const handler = this.get(deviceType);
        if (handler && handler.extractTemperatures) {
            return handler.extractTemperatures(sysinfo);
        }
        return {};
    },

    /**
     * Validate a command for a device type
     * @param {string} command - Command name
     * @param {Object} params - Command parameters
     * @param {string} deviceType - Device type identifier
     * @returns {boolean}
     */
    isValidCommand(command, params, deviceType) {
        const handler = this.get(deviceType);
        if (handler && handler.isValidCommand) {
            return handler.isValidCommand(command, params);
        }
        return false;
    },

    /**
     * Update control panel with current values
     * @param {HTMLElement} widget - Widget element
     * @param {Object} status - Control status from API
     * @param {string} deviceType - Device type identifier
     */
    updateControlValues(widget, status, deviceType) {
        const handler = this.get(deviceType);
        if (handler && handler.updateControlValues) {
            handler.updateControlValues(widget, status);
        }
    }
};

// Export for use in other modules
window.DeviceRegistry = DeviceRegistry;