# ESP32 Solar Inverter Simulator

ESP32-based solar inverter simulator that transmits pre-processed PV telemetry data to RPI#1 via Modbus TCP over WiFi.

## Architecture

```
ESP32 (Solar Inverter) --[WiFi, Modbus TCP Write:502]--> RPI#1 (Smart Meter/RTU)
```

## Features

- **Pre-processed PV Data**: 8760 hourly samples stored in Flash (PROGMEM)
- **Modbus TCP Client**: Writes 8 holding registers to RPI#1
- **WiFi Connectivity**: Auto-reconnection with exponential backoff
- **Error Handling**: Retry logic for Modbus writes
- **Debug Output**: Serial monitor for real-time telemetry display

## Hardware Requirements

- ESP32 development board (ESP32-DevKitC or similar)
- USB cable for programming and serial monitoring
- WiFi network access

## Software Requirements

- **PlatformIO** (VS Code extension or CLI)
- **Python 3** (for platformio and data generation)

## Installation

### 1. Install PlatformIO

**VS Code:**
```bash
# Install VS Code PlatformIO extension
code --install-extension platformio.platformio-ide
```

**CLI:**
```bash
pip install platformio
```

### 2. Configure WiFi Credentials

Edit `include/config.h` and update:

```cpp
#define WIFI_SSID 
#define WIFI_PASSWORD 
#define RPI1_IP   // RPI#1 WiFi IP address
```

**IMPORTANT**: Add `include/config.h` to `.gitignore` to protect credentials!

### 3. Build and Upload

**VS Code:**
1. Open `system_v2/esp32` folder in VS Code
2. PlatformIO will auto-detect the project
3. Click "PlatformIO: Upload" (→) button

**CLI:**
```bash
cd system_v2/esp32
pio run --target upload
```

### 4. Monitor Serial Output

**VS Code:**
- Click "PlatformIO: Serial Monitor" button

**CLI:**
```bash
pio device monitor --baud 115200
```

## Register Map

The ESP32 writes 8 Modbus holding registers to RPI#1 starting at address 0:

| Register | Parameter | Encoding | Example Raw | Decoded |
|----------|-----------|----------|-------------|---------|
| 0 | P_ac | W (uint16) | 250 | 250 W |
| 1 | P_dc | W (uint16) | 260 | 260 W |
| 2 | V_dc | V × 10 (uint16) | 485 | 48.5 V |
| 3 | I_dc | A × 100 (uint16) | 536 | 5.36 A |
| 4 | G | W/m² (uint16) | 850 | 850 W/m² |
| 5 | T_cell | °C × 10 (uint16) | 456 | 45.6 °C |
| 6 | Timestamp_high | Unix [31:16] | 0x6580 | - |
| 7 | Timestamp_low | Unix [15:0] | 0x1234 | 0x65801234 |

**Scaling Factors:**
- V_dc: multiplied by 10 (48.5V → 485)
- I_dc: multiplied by 100 (5.36A → 536)
- T_cell: multiplied by 10 (45.6°C → 456)

## Configuration Options

Edit `include/config.h` to customize:

```cpp
#define SEND_INTERVAL_MS 10000        // 10 seconds between samples
#define PV_DATA_LOOP true             // Loop through data when reaching end
#define MODBUS_RETRY_COUNT 3          // Number of retries for Modbus writes
#define DEBUG_ENABLED true            // Enable serial debug output
```

## PV Data Source

Pre-processed PV simulation data is stored in `include/pv_data.h`:

- **Source**: weather_washingtonDC_2016.xlsx (historical weather data)
- **Location**: Washington DC (38.9072°N, -77.0369°W)
- **Module**: Znshine PV Tech ZXP6 72 295 P
- **Inverter**: ABB MICRO 0.3 I OUTD US 208
- **Samples**: 8760 hourly values (1 year)
- **Memory**: ~120 KB stored in Flash (PROGMEM)

To regenerate data:
```bash
cd system_v2/data_preparation
python3 generate_esp32_data.py
cp output/pv_data.h ../esp32/include/pv_data.h
```

## Troubleshooting

### WiFi Connection Failed

**Symptoms**: Serial output shows "WiFi connection failed"

**Solutions:**
1. Check SSID and password in `include/config.h`
2. Verify ESP32 is in range of WiFi network
3. Check WiFi network supports 2.4 GHz (ESP32 doesn't support 5 GHz)
4. Disable WiFi MAC filtering or add ESP32 MAC address

### Modbus Write Errors

**Symptoms**: Serial output shows "Modbus write failed"

**Solutions:**
1. Verify RPI#1 is running `smart_meter_server.py`
2. Check RPI1_IP is correct in `include/config.h`
3. Ping RPI#1 from another device: `ping 192.168.1.100`
4. Check firewall on RPI#1: `sudo ufw status`
5. Test with Modbus tool (QModMaster) from PC to RPI#1

### Upload Failed

**Symptoms**: PlatformIO shows "Upload failed"

**Solutions:**
1. Check USB cable is connected
2. Press and hold BOOT button during upload
3. Install CH340/CP2102 USB driver (Windows)
4. Check serial port: `pio device list`
5. Try slower upload speed: `upload_speed = 115200` in platformio.ini

## Serial Monitor Output Example

```
================================================================================
ESP32 Solar Inverter Simulator
================================================================================
PV Data: 8760 samples (120 KB in Flash)
Send interval: 10 seconds
================================================================================
Connecting to WiFi...
SSID: YourNetwork
................
✓ WiFi connected!
  IP address: 192.168.1.10
  Signal strength: -45 dBm
Connecting to RPI#1 Modbus server...
  Target: 192.168.1.100:502
✓ Modbus client initialized
================================================================================
Starting data transmission...
================================================================================
----------------------------------------
Sample #0 of 8760
  P_ac:   250 W
  P_dc:   260 W
  V_dc:   48.50 V
  I_dc:   5.36 A
  G:      850 W/m²
  T_cell: 45.6 °C
  Time:   1451606400
✓ Sent to RPI#1 (Total: 1)
```

## Memory Usage

- **Flash**: ~120 KB (PV data) + ~200 KB (code) = **~320 KB** / 4 MB (8%)
- **RAM**: ~50 KB / 520 KB (10%)

## Performance

- **WiFi**: 2.4 GHz 802.11 b/g/n
- **Modbus**: TCP/IP (no TLS encryption)
- **Data Rate**: 8 registers every 10 seconds = 0.8 reg/sec
- **Network Traffic**: ~20 bytes/10 sec = 2 bytes/sec (negligible)

## Next Steps

1. Ensure RPI#1 is running `smart_meter_server.py`
2. Configure Arduino Opta to read from RPI#1
3. Monitor data flow with QModMaster or mbpoll

## References

- [PlatformIO Documentation](https://docs.platformio.org/)
- [ESP32 Arduino Core](https://github.com/espressif/arduino-esp32)
- [ModbusIP_ESP8266 Library](https://github.com/emelianov/modbus-esp8266)
- [Modbus Protocol Specification](https://www.modbus.org/docs/Modbus_Application_Protocol_V1_1b3.pdf)
