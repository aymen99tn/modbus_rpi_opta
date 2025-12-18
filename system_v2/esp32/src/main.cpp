/**
 * ESP32 Solar Inverter Simulator
 *
 * Simulates a PV solar inverter by reading pre-processed pvlib data and
 * transmitting telemetry to RPI#1 via Modbus TCP.
 *
 * Architecture:
 *   ESP32 (this device) --[WiFi, Modbus TCP Write:502]--> RPI#1 (Smart Meter/RTU)
 *
 * Data Source:
 *   Pre-computed PV simulation data stored in Flash (PROGMEM)
 *   Generated from weather_washingtonDC_2016.xlsx using pvlib ModelChain
 *
 * Register Map (8 registers, starting at address 0):
 *   0: P_ac (W, uint16)
 *   1: P_dc (W, uint16)
 *   2: V_dc (V×10, uint16)
 *   3: I_dc (A×100, uint16)
 *   4: G (W/m², uint16)
 *   5: T_cell (°C×10, uint16)
 *   6: Timestamp_high [31:16]
 *   7: Timestamp_low [15:0]
 */

#include <Arduino.h>
#include <WiFi.h>
#include <ModbusIP_ESP8266.h>
#include "config.h"
#include "pv_data.h"


// Modbus TCP client
ModbusIP modbus;
IPAddress rpi1Ip;
bool rpi1IpValid = false;

// State variables
uint16_t currentSampleIndex = 0;
unsigned long lastSendTime = 0;
bool wifiConnected = false;
bool modbusConnected = false;

// Statistics
unsigned long totalSamplesSent = 0;
unsigned long totalErrors = 0;
unsigned long totalTcpFailures = 0;

/**
 * Helper function: Clamp value to uint16 range
 */
uint16_t u16(int32_t value) {
    if (value < 0) return 0;
    if (value > 65535) return 65535;
    return (uint16_t)value;
}

/**
 * Connect to WiFi network
 */
void connectWiFi() {
    Serial.println("Connecting to WiFi...");
    Serial.print("SSID: ");
    Serial.println(WIFI_SSID);

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        wifiConnected = true;
        Serial.println("\n✓ WiFi connected!");
        Serial.print("  IP address: ");
        Serial.println(WiFi.localIP());
        Serial.print("  Signal strength: ");
        Serial.print(WiFi.RSSI());
        Serial.println(" dBm");
    } else {
        wifiConnected = false;
        Serial.println("\n✗ WiFi connection failed!");
        Serial.println("  Check SSID and password in include/config.h");
    }
}

/**
 * Connect to Modbus TCP server (RPI#1)
 */
void connectModbus() {
    Serial.println("Connecting to RPI#1 Modbus server...");
    Serial.print("  Target: ");
    Serial.print(RPI1_IP);
    Serial.print(":");
    Serial.println(RPI1_PORT);

    // ModbusIP_ESP8266 library auto-connects on first write
    // Just initialize the client
    modbus.client();
    modbus.autoConnect(true);

    rpi1IpValid = rpi1Ip.fromString(RPI1_IP);
    if (!rpi1IpValid) {
        Serial.println("✗ Invalid RPI1_IP format");
        modbusConnected = false;
        return;
    }

    modbusConnected = modbus.connect(rpi1Ip, RPI1_PORT);
    if (modbusConnected) {
        Serial.println("✓ Modbus TCP connected");
    } else {
        Serial.println("✗ Modbus TCP connect failed");
    }

    Serial.println("✓ Modbus client initialized");
}

/**
 * Quick TCP connectivity check to RPI#1
 */
bool testTcpConnection() {
    IPAddress server_ip;
    if (!server_ip.fromString(RPI1_IP)) {
        Serial.println("✗ Invalid RPI1_IP format");
        return false;
    }

    WiFiClient client;
    client.setTimeout(MODBUS_CONNECT_TIMEOUT_MS / 1000);
    bool connected = client.connect(server_ip, RPI1_PORT);
    if (connected) {
        client.stop();
        if (DEBUG_ENABLED) {
            Serial.println("✓ TCP connect OK");
        }
        return true;
    }

    totalTcpFailures++;
    Serial.print("✗ TCP connect failed (Total TCP failures: ");
    Serial.print(totalTcpFailures);
    Serial.println(")");
    return false;
}

/**
 * Send current PV sample to RPI#1 via Modbus TCP
 */
bool sendPVSample() {
    // Read sample from PROGMEM
    PVSample sample;
    memcpy_P(&sample, &PV_DATA[currentSampleIndex], sizeof(PVSample));

    // Prepare 8 Modbus registers
    uint16_t registers[8];
    registers[0] = sample.P_ac;
    registers[1] = sample.P_dc;
    registers[2] = sample.V_dc;      // Already scaled (V×10)
    registers[3] = sample.I_dc;      // Already scaled (A×100)
    registers[4] = sample.G;
    registers[5] = sample.T_cell;    // Already scaled (°C×10)
    registers[6] = (sample.timestamp >> 16) & 0xFFFF;  // Timestamp high
    registers[7] = sample.timestamp & 0xFFFF;           // Timestamp low

    // Debug output
    if (DEBUG_ENABLED) {
        Serial.println("----------------------------------------");
        Serial.print("Sample #");
        Serial.print(currentSampleIndex);
        Serial.print(" of ");
        Serial.println(PV_DATA_COUNT);

        // Decode for human-readable display
        float V_dc_decoded = sample.V_dc / 10.0;
        float I_dc_decoded = sample.I_dc / 100.0;
        float T_cell_decoded = sample.T_cell / 10.0;

        Serial.print("  P_ac:   ");
        Serial.print(sample.P_ac);
        Serial.println(" W");

        Serial.print("  P_dc:   ");
        Serial.print(sample.P_dc);
        Serial.println(" W");

        Serial.print("  V_dc:   ");
        Serial.print(V_dc_decoded, 2);
        Serial.println(" V");

        Serial.print("  I_dc:   ");
        Serial.print(I_dc_decoded, 2);
        Serial.println(" A");

        Serial.print("  G:      ");
        Serial.print(sample.G);
        Serial.println(" W/m²");

        Serial.print("  T_cell: ");
        Serial.print(T_cell_decoded, 1);
        Serial.println(" °C");

        Serial.print("  Time:   ");
        Serial.println(sample.timestamp);
    }

    // Write to Modbus server with retries
    bool success = false;
    for (int attempt = 0; attempt < MODBUS_RETRY_COUNT && !success; attempt++) {
        if (attempt > 0) {
            Serial.print("  Retry attempt ");
            Serial.print(attempt + 1);
            Serial.print("/");
            Serial.println(MODBUS_RETRY_COUNT);
            delay(1000);
        }

        if (!modbusConnected || !modbus.isConnected(rpi1Ip)) {
            modbusConnected = modbus.connect(rpi1Ip, RPI1_PORT);
            if (!modbusConnected) {
                Serial.println("✗ Modbus TCP connect failed");
                testTcpConnection();
                continue;
            }
        }

        // Write 8 registers starting at address 0
        // ModbusIP_ESP8266 API: writeMultipleRegisters(serverIP, address, values, count)
        if (modbus.writeHreg(rpi1Ip, 0, registers, 8, nullptr, MODBUS_UNIT_ID)) {
            success = true;
            totalSamplesSent++;

            if (DEBUG_ENABLED) {
                Serial.print("✓ Sent to RPI#1 (Total: ");
                Serial.print(totalSamplesSent);
                Serial.println(")");
            }
        } else {
            Serial.println("✗ Modbus write failed");
            testTcpConnection();
        }
    }

    if (!success) {
        totalErrors++;
        Serial.print("✗ Failed after ");
        Serial.print(MODBUS_RETRY_COUNT);
        Serial.print(" attempts (Total errors: ");
        Serial.print(totalErrors);
        Serial.println(")");
    }

    return success;
}

/**
 * Arduino setup function
 */
void setup() {
    // Initialize serial communication
    Serial.begin(DEBUG_BAUD_RATE);
    delay(1000);

    Serial.println("================================================================================");
    Serial.println("ESP32 Solar Inverter Simulator");
    Serial.println("================================================================================");
    Serial.print("PV Data: ");
    Serial.print(PV_DATA_COUNT);
    Serial.print(" samples (");
    Serial.print((PV_DATA_COUNT * sizeof(PVSample)) / 1024);
    Serial.println(" KB in Flash)");
    Serial.print("Send interval: ");
    Serial.print(SEND_INTERVAL_MS / 1000);
    Serial.println(" seconds");
    Serial.println("================================================================================");

    // Connect to WiFi
    connectWiFi();

    if (wifiConnected) {
        // Initialize Modbus client
        connectModbus();
    }

    Serial.println("================================================================================");
    Serial.println("Starting data transmission...");
    Serial.println("================================================================================");
}

/**
 * Arduino loop function
 */
void loop() {
    // Check WiFi connection
    if (WiFi.status() != WL_CONNECTED) {
        if (wifiConnected) {
            Serial.println("✗ WiFi connection lost! Reconnecting...");
            wifiConnected = false;
        }
        connectWiFi();
        delay(WIFI_RETRY_DELAY_MS);
        return;
    }

    // Check if it's time to send next sample
    unsigned long currentTime = millis();
    if (currentTime - lastSendTime >= SEND_INTERVAL_MS) {
        lastSendTime = currentTime;

        // Send current sample
        bool success = sendPVSample();

        // Move to next sample
        if (success) {
            currentSampleIndex++;

            // Loop back to beginning if enabled
            if (currentSampleIndex >= PV_DATA_COUNT) {
                if (PV_DATA_LOOP) {
                    Serial.println("========================================");
                    Serial.println("Reached end of data, looping back to start");
                    Serial.println("========================================");
                    currentSampleIndex = 0;
                } else {
                    Serial.println("========================================");
                    Serial.println("Reached end of data, stopping");
                    Serial.println("========================================");
                    while (true) {
                        delay(1000);
                    }
                }
            }
        }
    }

    // Keep Modbus client alive
    modbus.task();

    // Small delay to prevent watchdog issues
    delay(10);
}
