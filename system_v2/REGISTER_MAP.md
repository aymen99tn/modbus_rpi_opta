# Modbus Register Map Specification

Complete register mapping for all Modbus TCP communications in system_v2.

---

## Overview

The system uses **3 different register maps** at different stages:

1. **ESP32 → RPI#1**: 8 registers (full telemetry)
2. **RPI#1 → Opta**: 8 registers (same as above, pass-through)
3. **Opta → RPI#2**: 5 registers (subset for SIPROTEC)

All communications use **Holding Registers** starting at **address 0**.

---

## 1. ESP32 → RPI#1 (8 Registers)

**Protocol**: Modbus TCP (plain, no TLS)
**Function Code**: FC16 (Write Multiple Registers)
**Unit ID**: 1
**Starting Address**: 0
**Register Count**: 8

### Register Layout

| Address | Register | Parameter | Data Type | Encoding | Scale Factor | Range | Example Raw | Example Decoded |
|---------|----------|-----------|-----------|----------|--------------|-------|-------------|-----------------|
| 0 | 0 | P_ac | UINT16 | Watts | 1:1 | 0-65535 W | 250 | 250 W |
| 1 | 1 | P_dc | UINT16 | Watts | 1:1 | 0-65535 W | 260 | 260 W |
| 2 | 2 | V_dc | UINT16 | Volts × 10 | **×10** | 0-6553.5 V | 485 | **48.5 V** |
| 3 | 3 | I_dc | UINT16 | Amps × 100 | **×100** | 0-655.35 A | 536 | **5.36 A** |
| 4 | 4 | G | UINT16 | W/m² | 1:1 | 0-65535 W/m² | 850 | 850 W/m² |
| 5 | 5 | T_cell | UINT16 | °C × 10 | **×10** | 0-6553.5 °C | 456 | **45.6 °C** |
| 6 | 6 | Timestamp_high | UINT16 | Unix [31:16] | - | - | 0x6580 | - |
| 7 | 7 | Timestamp_low | UINT16 | Unix [15:0] | - | - | 0x1234 | - |

### Encoding Rules (ESP32)

```cpp
// Apply scaling
registers[0] = u16(round(P_ac));           // Direct: 250.0 → 250
registers[1] = u16(round(P_dc));           // Direct: 260.0 → 260
registers[2] = u16(round(V_dc * 10));      // Scale: 48.5 → 485
registers[3] = u16(round(I_dc * 100));     // Scale: 5.36 → 536
registers[4] = u16(round(G));              // Direct: 850.0 → 850
registers[5] = u16(round(T_cell * 10));    // Scale: 45.6 → 456

// Split timestamp into two 16-bit words
uint32_t unix_s = 1451606400;
registers[6] = (unix_s >> 16) & 0xFFFF;    // High word: 0x6580
registers[7] = unix_s & 0xFFFF;             // Low word: 0x1234

// Helper function
uint16_t u16(int32_t value) {
    return max(0, min(65535, (uint16_t)value));
}
```

### Decoding Rules (RPI#1, Opta)

```python
# Inverse scaling
P_ac = registers[0] * 1.0        # Direct: 250 → 250.0 W
P_dc = registers[1] * 1.0        # Direct: 260 → 260.0 W
V_dc = registers[2] / 10.0       # Decode: 485 → 48.5 V
I_dc = registers[3] / 100.0      # Decode: 536 → 5.36 A
G = registers[4] * 1.0           # Direct: 850 → 850.0 W/m²
T_cell = registers[5] / 10.0     # Decode: 456 → 45.6 °C

# Reconstruct 32-bit timestamp
unix_s = ((registers[6] & 0xFFFF) << 16) | (registers[7] & 0xFFFF)
# 0x65801234 = 1702838836 seconds since 1970-01-01
```

### Data Validation

**Valid Ranges** (after decoding):
- P_ac: 0 - 10,000 W (0 - 10 kW)
- P_dc: 0 - 10,000 W
- V_dc: 0 - 100 V (typical PV string)
- I_dc: 0 - 50 A
- G: 0 - 1,500 W/m² (max solar irradiance)
- T_cell: -20 - 80 °C
- Timestamp: Valid Unix timestamp (> 0)

**Out-of-range values should trigger warnings/errors.**

---

## 2. RPI#1 → Opta (8 Registers)

**Protocol**: Modbus TCP
**Function Code**: FC03 (Read Holding Registers)
**Unit ID**: 1
**Starting Address**: 0
**Register Count**: 8

### Register Layout

**Identical to ESP32 → RPI#1** (RPI#1 stores as-is, no transformation)

### Opta Read Operation

```cpp
// Arduino Opta code
if (modbusRPI1.requestFrom(RPI1_UNIT_ID, HOLDING_REGISTERS, 0, 8)) {
    for (int i = 0; i < 8; i++) {
        registers_rpi1[i] = modbusRPI1.read();
    }

    // Decode for display/processing
    float P_ac = registers_rpi1[0] * 1.0;
    float V_dc = registers_rpi1[2] / 10.0;
    float I_dc = registers_rpi1[3] / 100.0;
    // ... etc
}
```

---

## 3. Opta → RPI#2 (5 Registers - Subset)

**Protocol**: Modbus TCP
**Function Code**: FC16 (Write Multiple Registers)
**Unit ID**: 1
**Starting Address**: 0
**Register Count**: 5

### Register Layout

| Address | Register | Parameter | Data Type | Encoding | Source (from RPI#1) | Notes |
|---------|----------|-----------|-----------|----------|---------------------|-------|
| 0 | 0 | P_ac | UINT16 | Watts | Register 0 | Direct copy |
| 1 | 1 | V_dc | UINT16 | Volts × 10 | Register 2 | Keep scaled |
| 2 | 2 | I_dc | UINT16 | Amps × 100 | Register 3 | Keep scaled |
| 3 | 3 | G | UINT16 | W/m² | Register 4 | Direct copy |
| 4 | 4 | Timestamp_low | UINT16 | Unix [15:0] | Register 7 | Lower 16 bits only |

### Why Subset?

**Omitted from RPI#2**:
- **P_dc** (Register 1): Less critical for protection relay
- **T_cell** (Register 5): Not needed for immediate protection decisions
- **Timestamp_high** (Register 6): 16-bit timestamp sufficient for relative timing

**Included for RPI#2** (critical measurements):
- **P_ac**: Active power (primary protection parameter)
- **V_dc**: Voltage (overvoltage/undervoltage protection)
- **I_dc**: Current (overcurrent protection)
- **G**: Irradiance (contextual information)
- **Timestamp_low**: Relative timing for event correlation

### Opta Write Operation

```cpp
// Arduino Opta code
void prepareDataForRPI2() {
    registers_rpi2[0] = registers_rpi1[0];  // P_ac
    registers_rpi2[1] = registers_rpi1[2];  // V_dc (keep scaled)
    registers_rpi2[2] = registers_rpi1[3];  // I_dc (keep scaled)
    registers_rpi2[3] = registers_rpi1[4];  // G
    registers_rpi2[4] = registers_rpi1[7];  // Timestamp_low
}

// Write to RPI#2
modbusRPI2.beginTransmission(RPI2_UNIT_ID, HOLDING_REGISTERS, 0, 5);
for (int i = 0; i < 5; i++) {
    modbusRPI2.write(registers_rpi2[i]);
}
modbusRPI2.endTransmission();
```

### RPI#2 Decoding (for IEC 61850)

```python
# Read from Modbus datablock
regs = modbus_server.get_registers(0, 5)

# Decode scaling (CRITICAL: Must decode before IEC 61850)
P_ac = float(regs[0])           # 250 → 250.0 W
V_dc = float(regs[1]) / 10.0    # 485 → 48.5 V
I_dc = float(regs[2]) / 100.0   # 536 → 5.36 A
G = float(regs[3])              # 850 → 850.0 W/m²
timestamp_low = regs[4]         # 0x1234
```

---

## 4. Scaling Summary

### Why Scaling?

**UINT16 limitations**:
- Range: 0 - 65,535
- No decimal places
- Need to represent values like 48.5 V or 5.36 A

**Solution**: Multiply by scale factor, transmit as integer, divide to decode.

### Scaling Factors Table

| Parameter | Raw Value | Scale Factor | Encoded (UINT16) | Decoded Value | Precision |
|-----------|-----------|--------------|------------------|---------------|-----------|
| P_ac | 250.0 W | ×1 | 250 | 250.0 W | 1 W |
| V_dc | 48.5 V | **×10** | 485 | 48.5 V | 0.1 V |
| I_dc | 5.36 A | **×100** | 536 | 5.36 A | 0.01 A |
| T_cell | 45.6 °C | **×10** | 456 | 45.6 °C | 0.1 °C |
| G | 850.0 W/m² | ×1 | 850 | 850.0 W/m² | 1 W/m² |

**IMPORTANT**: All components must use **identical** scaling factors!

---

## 5. Timestamp Handling

### 32-bit Unix Timestamp

**Format**: Seconds since 1970-01-01 00:00:00 UTC

**Example**: `1451606400` = 2016-01-01 00:00:00 UTC

### Encoding (ESP32)

```cpp
uint32_t unix_s = 1451606400;

// Split into two 16-bit registers
uint16_t timestamp_high = (unix_s >> 16) & 0xFFFF;  // 0x6580 = 25984
uint16_t timestamp_low = unix_s & 0xFFFF;           // 0x1234 = 4660

registers[6] = timestamp_high;
registers[7] = timestamp_low;
```

### Decoding (RPI#1, Opta, RPI#2)

```python
# Reconstruct from two 16-bit registers
unix_s = ((registers[6] & 0xFFFF) << 16) | (registers[7] & 0xFFFF)

# Convert to datetime
from datetime import datetime, timezone
dt = datetime.fromtimestamp(unix_s, tz=timezone.utc)
# Output: 2016-01-01 00:00:00+00:00
```

### Timestamp in RPI#2 (16-bit only)

**Note**: Opta only sends `timestamp_low` (lower 16 bits) to RPI#2.

**Range**: 0 - 65,535 seconds (≈ 18.2 hours)
**Wraps around**: Every 18.2 hours
**Use case**: Relative timing for event correlation, not absolute time

---

## 6. Example Register Values

### Sample PV Data Point

**Scenario**: Sunny day, mid-day, PV system producing power

| Parameter | Real Value | Encoded (UINT16) | Hex | Decimal |
|-----------|------------|------------------|-----|---------|
| P_ac | 250 W | 250 | 0x00FA | 250 |
| P_dc | 260 W | 260 | 0x0104 | 260 |
| V_dc | 48.5 V | 485 | 0x01E5 | 485 |
| I_dc | 5.36 A | 536 | 0x0218 | 536 |
| G | 850 W/m² | 850 | 0x0352 | 850 |
| T_cell | 45.6 °C | 456 | 0x01C8 | 456 |
| Timestamp | 2016-01-01 00:00:00 | - | - | - |
| Timestamp_high | - | 25984 | 0x6580 | 25984 |
| Timestamp_low | - | 4660 | 0x1234 | 4660 |

### Wireshark Capture (Modbus TCP)

**ESP32 → RPI#1 (FC16 Write Multiple Registers)**:
```
Transaction ID: 0x0001
Protocol ID: 0x0000 (Modbus)
Length: 19
Unit ID: 0x01
Function Code: 0x10 (Write Multiple Registers)
Starting Address: 0x0000
Register Count: 0x0008
Byte Count: 0x10 (16 bytes)
Register Data:
  [0] 0x00FA (250)
  [1] 0x0104 (260)
  [2] 0x01E5 (485)
  [3] 0x0218 (536)
  [4] 0x0352 (850)
  [5] 0x01C8 (456)
  [6] 0x6580 (25984)
  [7] 0x1234 (4660)
```

---

## 7. Error Handling

### Invalid Data Detection

**Range Checks** (after decoding):

```python
def validate_pv_data(P_ac, V_dc, I_dc, G, T_cell):
    errors = []

    if not (0 <= P_ac <= 10000):
        errors.append(f"P_ac out of range: {P_ac}W")

    if not (0 <= V_dc <= 100):
        errors.append(f"V_dc out of range: {V_dc}V")

    if not (0 <= I_dc <= 50):
        errors.append(f"I_dc out of range: {I_dc}A")

    if not (0 <= G <= 1500):
        errors.append(f"G out of range: {G}W/m²")

    if not (-20 <= T_cell <= 80):
        errors.append(f"T_cell out of range: {T_cell}°C")

    return len(errors) == 0, errors
```

### Modbus Communication Errors

**Common error codes**:
- `0x01`: Illegal Function
- `0x02`: Illegal Data Address
- `0x03`: Illegal Data Value
- `0x04`: Slave Device Failure

**Retry logic**:
```cpp
// ESP32 example
int retry_count = 0;
const int MAX_RETRIES = 3;

while (retry_count < MAX_RETRIES) {
    if (modbus.write_registers(...)) {
        break;  // Success
    }
    retry_count++;
    delay(1000);  // Wait before retry
}
```

---

## 8. Testing Tools

### QModMaster (GUI)

**Write to RPI#1 (simulate ESP32)**:
1. Connect to: 192.168.1.100:502
2. Function: FC16 (Preset Multiple Registers)
3. Address: 0
4. Count: 8
5. Values: `250, 260, 485, 536, 850, 456, 25984, 4660`

**Read from RPI#1 (simulate Opta)**:
1. Connect to: 192.168.2.100:502
2. Function: FC03 (Read Holding Registers)
3. Address: 0
4. Count: 8

### mbpoll (CLI)

```bash
# Write registers to RPI#1
mbpoll -a 1 -r 0 -c 8 -t 4 192.168.1.100 \
  250 260 485 536 850 456 25984 4660

# Read registers from RPI#1
mbpoll -a 1 -r 0 -c 8 -t 4 192.168.2.100

# Write subset to RPI#2
mbpoll -a 1 -r 0 -c 5 -t 4 192.168.2.200 \
  250 485 536 850 4660
```

### Python Test Script

```python
from pymodbus.client import ModbusTcpClient

# Connect to RPI#1
client = ModbusTcpClient("192.168.1.100", port=502)
client.connect()

# Write test data (simulate ESP32)
registers = [250, 260, 485, 536, 850, 456, 25984, 4660]
result = client.write_registers(0, registers, unit=1)

# Read back (simulate Opta)
result = client.read_holding_registers(0, 8, unit=1)
print(result.registers)

client.close()
```

---

## 9. Consistency Requirements

**CRITICAL**: All components must agree on:

1. **Register addresses**: Start at 0, sequential
2. **Scaling factors**: V_dc×10, I_dc×100, T_cell×10
3. **Byte order**: Big-endian (network byte order)
4. **Data types**: UINT16 (unsigned 16-bit)
5. **Function codes**: FC16 (write), FC03 (read)
6. **Unit ID**: 1 (default)

**Any mismatch will cause data corruption!**

---

## 10. References

- **Modbus Application Protocol**: V1.1b3 (Dec 2006)
- **Modbus TCP/IP**: Modbus Messaging on TCP/IP Implementation Guide V1.0b (Oct 2006)
- **pymodbus Documentation**: https://pymodbus.readthedocs.io/
- **ArduinoModbus Library**: https://www.arduino.cc/reference/en/libraries/arduinomodbus/

---

**Document Version**: 1.0
**Last Updated**: 2025-12-18
