#ifndef CONFIG_H
#define CONFIG_H

/**
 * ESP32 Solar Inverter Simulator Configuration
 *
 * IMPORTANT: Update these values for your network setup
 * Add this file to .gitignore to protect WiFi credentials
 */

// WiFi Configuration
#define WIFI_SSID "Aymen99tn"
#define WIFI_PASSWORD "ca1920ca"

// RPI#1 Smart Meter Server Configuration
#define RPI1_IP "10.21.66.250"      // RPI#1 WiFi IP address (Field zone)
#define RPI1_PORT 502               // Modbus TCP port (plain TCP, no TLS)
#define MODBUS_UNIT_ID 1            // Modbus device ID (RPI#1 uses unit-id 1)

// Data Transmission Configuration
#define SEND_INTERVAL_MS 10000        // 10 seconds between samples
#define PV_DATA_LOOP true             // Loop through data when reaching end

// Connection Configuration
#define WIFI_RETRY_DELAY_MS 5000      // Delay between WiFi reconnection attempts
#define MODBUS_CONNECT_TIMEOUT_MS 10000  // Modbus connection timeout
#define MODBUS_RETRY_COUNT 3          // Number of retries for Modbus writes

// Debug Configuration
#define DEBUG_ENABLED true            // Enable serial debug output
#define DEBUG_BAUD_RATE 115200        // Serial monitor baud rate

#endif // CONFIG_H
