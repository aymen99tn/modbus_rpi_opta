# Arduino Opta - Microgrid Controller

Dual Modbus TCP client that reads telemetry from RPI#1 and forwards subset to RPI#2.

## Architecture

```
RPI#1 <--[Ethernet, Modbus TCP Read:502]-- Opta --[Ethernet, Modbus TCP Write:502]--> RPI#2
```

## Features

- **Dual Modbus Client**: Maintains two simultaneous Modbus TCP connections
- **Data Processing**: Selects subset of registers for downstream transmission
- **Arduino C++**: Compatible with Arduino IDE and PLC IDE
- **Statistics**: Tracks read/write operations and success rates

## Hardware Requirements

- Arduino Opta (industrial PLC/controller)
- Ethernet connection to RPI#1 and RPI#2
- Power supply (24V DC typical)

## Software Requirements

- Arduino IDE 2.x or Arduino PLC IDE
- ArduinoModbus library

## Installation

### 1. Install Arduino IDE

Download from: https://www.arduino.cc/en/software

### 2. Install Required Libraries

**Arduino IDE:**
1. Open Arduino IDE
2. Go to Sketch → Include Library → Manage Libraries
3. Search and install: **ArduinoModbus** by Arduino

**PLC IDE:**
Libraries are pre-installed.

### 3. Configure Network

Edit the sketch configuration section:

```cpp
// Network Configuration
byte mac[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED };
IPAddress ip(192, 168, 2, 150);       // Opta static IP

// RPI#1 Configuration (Smart Meter)
IPAddress rpi1_ip(192, 168, 2, 100);

// RPI#2 Configuration (Substation Gateway)
IPAddress rpi2_ip(192, 168, 2, 200);
```

### 4. Upload Sketch

1. Connect Opta via USB
2. Select board: Tools → Board → Arduino Opta
3. Select port: Tools → Port → (your port)
4. Click Upload (→)

## Register Mapping

### From RPI#1 (8 registers read)

| Register | Parameter | Encoding |
|----------|-----------|----------|
| 0 | P_ac | W (uint16) |
| 1 | P_dc | W (uint16) |
| 2 | V_dc | V × 10 (uint16) |
| 3 | I_dc | A × 100 (uint16) |
| 4 | G | W/m² (uint16) |
| 5 | T_cell | °C × 10 (uint16) |
| 6 | Timestamp_high | Unix [31:16] |
| 7 | Timestamp_low | Unix [15:0] |

### To RPI#2 (5 registers write)

| Register | Parameter | Source |
|----------|-----------|--------|
| 0 | P_ac | Copy from RPI#1 reg 0 |
| 1 | V_dc (scaled) | Copy from RPI#1 reg 2 |
| 2 | I_dc (scaled) | Copy from RPI#1 reg 3 |
| 3 | G | Copy from RPI#1 reg 4 |
| 4 | Timestamp_low | Copy from RPI#1 reg 7 |

**Why subset?** Focus on critical measurements for SIPROTEC relay, reduce data volume.

## Serial Monitor Output

```
================================================================================
Arduino Opta - Microgrid Controller (Dual Modbus Client)
================================================================================
Initializing Ethernet...
  Opta IP: 192.168.2.150
  Gateway: 192.168.2.1
  Subnet: 255.255.255.0

Modbus Configuration:
  RPI#1 (Read from):  192.168.2.100:502
  RPI#2 (Write to):   192.168.2.200:502

  Poll interval: 1 seconds
================================================================================
Starting dual Modbus client operation...
================================================================================

Connecting to RPI#1... OK
----------------------------------------
[READ FROM RPI#1]
  P_ac:   250.0 W
  P_dc:   260.0 W
  V_dc:   48.50 V
  I_dc:   5.36 A
  G:      850.0 W/m²
  T_cell: 45.6 °C
  Time:   1451606400
[PROCESSED DATA FOR RPI#2]
  Selected 5 registers (P_ac, V_dc, I_dc, G, Timestamp_low)
Connecting to RPI#2... OK
[WRITE TO RPI#2]
  ✓ Sent 5 registers (250, 485, 536, 850, 4660)
```

## Troubleshooting

### Ethernet Not Working

**Check Cable:** Ensure Ethernet cable is connected and LED is lit

**Check IP Configuration:**
```cpp
IPAddress ip(192, 168, 2, 150);  // Must be in same subnet as RPI#1/RPI#2
```

**Ping Test:** From a PC on same network:
```bash
ping 192.168.2.150
```

### Cannot Read from RPI#1

**Error:** `Read from RPI#1 failed`

**Solutions:**
1. Verify RPI#1 is running `smart_meter_server.py`
2. Check RPI#1 IP: `ip addr show eth0` (should be 192.168.2.100)
3. Test with QModMaster from PC
4. Check firewall on RPI#1

### Cannot Write to RPI#2

**Error:** `Write to RPI#2 failed`

**Solutions:**
1. Verify RPI#2 is running `substation_gateway.py`
2. Check RPI#2 IP: `ip addr show eth0` (should be 192.168.2.200)
3. Check RPI#2 Modbus server logs
4. Test with QModMaster from PC

### Upload Failed

**Error:** `Couldn't find a Board on the selected port`

**Solutions:**
1. Install Arduino Opta board support
2. Press reset button twice quickly (bootloader mode)
3. Check USB cable
4. Update Arduino IDE to latest version

## Performance

- **Poll Rate**: 1 Hz (1 sample/second)
- **Network Traffic**: ~30 bytes/second (minimal)
- **CPU Usage**: <5%
- **Memory**: ~40 KB / 256 KB (16%)

## Alternative: PLC IDE Implementation

For industrial PLC programming, use Structured Text (IEC 61131-3):

```
PROGRAM MicrogridController
VAR
    modbusRPI1 : ModbusTCPClient;
    modbusRPI2 : ModbusTCPClient;
    registers_rpi1 : ARRAY[0..7] OF UINT;
    registers_rpi2 : ARRAY[0..4] OF UINT;
END_VAR

(* Read from RPI#1 *)
modbusRPI1.ReadHoldingRegisters(
    SlaveAddress := 1,
    StartAddress := 0,
    Count := 8,
    Data := registers_rpi1
);

(* Process data *)
registers_rpi2[0] := registers_rpi1[0];  (* P_ac *)
registers_rpi2[1] := registers_rpi1[2];  (* V_dc *)
registers_rpi2[2] := registers_rpi1[3];  (* I_dc *)
registers_rpi2[3] := registers_rpi1[4];  (* G *)
registers_rpi2[4] := registers_rpi1[7];  (* Timestamp *)

(* Write to RPI#2 *)
modbusRPI2.WriteMultipleRegisters(
    SlaveAddress := 1,
    StartAddress := 0,
    Count := 5,
    Data := registers_rpi2
);
```

## Next Steps

1. Ensure RPI#1 and RPI#2 servers are running
2. Monitor serial output for data flow
3. Verify SIPROTEC receives data from RPI#2

## References

- [Arduino Opta Documentation](https://docs.arduino.cc/hardware/opta)
- [ArduinoModbus Library](https://www.arduino.cc/reference/en/libraries/arduinomodbus/)
- [Modbus TCP Specification](https://www.modbus.org/docs/Modbus_Messaging_Implementation_Guide_V1_0b.pdf)
