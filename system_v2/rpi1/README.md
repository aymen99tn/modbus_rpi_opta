# RPI#1 - Smart Meter / RTU Server

Modbus TCP server acting as a Field Zone data concentrator that receives PV telemetry from ESP32 (wireless) and serves it to Arduino Opta (wired).

## Architecture

```
ESP32 --[WiFi, Modbus TCP Write:502]--> RPI#1 <--[Ethernet, Modbus TCP Read:502]-- Opta
```

## Features

- **Dual Interface Support**: Serves both WiFi (ESP32) and Ethernet (Opta) on same port
- **Modbus TCP Server**: Single server on port 502, binds to 0.0.0.0
- **Data Logging**: Decodes and logs all received telemetry
- **Statistics Tracking**: Monitors total received (from ESP32) and served (to Opta)
- **Simplified from system_v1**: No TLS, no pvlib (ESP32 handles data generation)

## Network Configuration

| Interface | IP Address | Subnet | Purpose |
|-----------|------------|--------|---------|
| WiFi (wlan0) | 192.168.1.100 | 192.168.1.0/24 | Receives from ESP32 |
| Ethernet (eth0) | 192.168.2.100 | 192.168.2.0/24 | Serves to Opta |

**Note**: Binding to 0.0.0.0:502 allows server to accept connections on both interfaces

## Installation

### 1. Install Python Dependencies

```bash
cd system_v2/rpi1
pip3 install -r requirements.txt
```

### 2. Configure Network Interfaces

**WiFi (for ESP32):**
```bash
# Configure static IP on wlan0
sudo nmcli con mod "YourWiFiConnection" ipv4.addresses 192.168.1.100/24 ipv4.method manual
```

**Ethernet (for Opta):**
```bash
# Configure static IP on eth0
sudo nmcli con mod "Wired connection 1" ipv4.addresses 192.168.2.100/24 ipv4.method manual
```

### 3. Configure Firewall

```bash
# Allow Modbus TCP port 502
sudo ufw allow 502/tcp comment "Modbus TCP"
```

## Usage

### Start Server

```bash
python3 smart_meter_server.py
```

### Expected Output

```
================================================================================
RPI#1 - Smart Meter / RTU Server Starting
================================================================================
Architecture:
  ESP32 → RPI#1: WiFi, Modbus TCP (writes data)
  RPI#1 ← Opta: Ethernet, Modbus TCP (reads data)

Configuration:
  TCP Server: 0.0.0.0:502
  Unit ID: 1
  Interfaces: WiFi (192.168.1.100) + Ethernet (192.168.2.100)
================================================================================
Statistics task created
Starting Modbus TCP server on 0.0.0.0:502...
Waiting for:
  - ESP32 to write data (WiFi interface)
  - Opta to read data (Ethernet interface)
```

### When ESP32 Writes Data

```
[RX FROM ESP32] 2016-01-01T06:00:00+00:00 | P_ac=250.0W P_dc=260.0W V_dc=48.50V I_dc=5.36A G=850.0W/m² T_cell=45.6°C | Total RX: 1
```

### When Opta Reads Data

```
[TX TO OPTA] Served registers 0-7 | Total served: 1
```

## Register Map

The server stores 8 holding registers starting at address 0:

| Register | Parameter | Encoding | Description |
|----------|-----------|----------|-------------|
| 0 | P_ac | W (uint16) | AC Power |
| 1 | P_dc | W (uint16) | DC Power |
| 2 | V_dc | V × 10 (uint16) | DC Voltage (scaled) |
| 3 | I_dc | A × 100 (uint16) | DC Current (scaled) |
| 4 | G | W/m² (uint16) | Irradiance |
| 5 | T_cell | °C × 10 (uint16) | Cell Temperature (scaled) |
| 6 | Timestamp_high | Unix [31:16] | Timestamp upper 16 bits |
| 7 | Timestamp_low | Unix [15:0] | Timestamp lower 16 bits |

**Scaling Factors** (for decoding):
- V_dc: divide by 10 (485 → 48.5V)
- I_dc: divide by 100 (536 → 5.36A)
- T_cell: divide by 10 (456 → 45.6°C)

## Testing

### Test with Modbus Client Tool

**QModMaster** (GUI):
```bash
# Connect to: 192.168.2.100:502
# Function: FC03 (Read Holding Registers)
# Address: 0
# Count: 8
```

**mbpoll** (CLI):
```bash
# Read registers
mbpoll -a 1 -r 0 -c 8 -t 4 192.168.2.100
```

### Test with Python Script

```python
from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("192.168.2.100", port=502)
client.connect()

# Read 8 registers
result = client.read_holding_registers(0, 8, unit=1)
print(result.registers)

client.close()
```

## Troubleshooting

### Server Won't Start

**Port Already in Use:**
```bash
# Check if port 502 is in use
sudo netstat -tulpn | grep 502

# Kill existing process
sudo kill -9 <PID>
```

**Permission Denied (Port < 1024):**
```bash
# Run with sudo (not recommended) OR
# Use authbind (recommended)
sudo apt-get install authbind
sudo touch /etc/authbind/byport/502
sudo chmod 777 /etc/authbind/byport/502
authbind --deep python3 smart_meter_server.py
```

### ESP32 Cannot Connect

**Check WiFi IP:**
```bash
ip addr show wlan0
# Should show: 192.168.1.100
```

**Check Firewall:**
```bash
sudo ufw status
# Should allow port 502
```

**Test Connectivity:**
```bash
# Ping from ESP32 network (if possible)
ping 192.168.1.100
```

### Opta Cannot Connect

**Check Ethernet IP:**
```bash
ip addr show eth0
# Should show: 192.168.2.100
```

**Test Connectivity:**
```bash
# Ping from Opta network
ping 192.168.2.100
```

## Systemd Service (Optional)

Create `/etc/systemd/system/smart-meter.service`:

```ini
[Unit]
Description=RPI#1 Smart Meter Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/RPI_NBP/system_v2/rpi1
ExecStart=/usr/bin/python3 /home/pi/RPI_NBP/system_v2/rpi1/smart_meter_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable smart-meter
sudo systemctl start smart-meter
sudo systemctl status smart-meter
```

## Next Steps

1. Ensure ESP32 is configured with RPI1_IP="192.168.1.100"
2. Configure Arduino Opta to read from 192.168.2.100:502
3. Monitor logs for data flow

## References

- [pymodbus Documentation](https://pymodbus.readthedocs.io/)
- [Modbus TCP Specification](https://www.modbus.org/docs/Modbus_Messaging_Implementation_Guide_V1_0b.pdf)
