# IEC 61850 MMS Protocol Mapping

Complete mapping specification for protocol translation from Modbus TCP to IEC 61850 MMS for SIPROTEC 7SX85 communication.

---

## Overview

**RPI#2 Substation Gateway** translates Modbus registers (from Arduino Opta) to IEC 61850 data objects (for SIPROTEC relay).

**Protocol Translation**: Modbus TCP → IEC 61850 MMS
**Library**: pyiec61850 (Python wrapper for libiec61850)
**Target Device**: Siemens SIPROTEC 7SX85 Protection Relay

---

## 1. IEC 61850 Fundamentals

### 1.1. Information Model Hierarchy

```
IED (Intelligent Electronic Device)
  └── Logical Device (LD0, LD1, ...)
      └── Logical Node (MMXU1, XCBR1, ...)
          └── Data Object (TotW, PhV, A, ...)
              └── Data Attribute (mag.f, q, t, ...)
```

### 1.2. Naming Convention

**Object Reference Format**:
```
LogicalDevice / LogicalNode $ FunctionalConstraint $ DataObject $ DataAttribute
```

**Example**:
```
IEC 61850:  LD0/MMXU1.TotW.mag.f[MX]
MMS:        LD0/MMXU1$MX$TotW$mag$f
```

**Transformations**:
- Replace `.` with `$`
- Insert Functional Constraint (FC) after Logical Node
- FC determines access rights and semantics

---

## 2. SIPROTEC 7SX85 Data Model

### 2.1. Device Information

**Model**: SIPROTEC 7SX85
**Function**: Distance Protection Relay
**IEC 61850 Edition**: 2.0 / 2.1
**Protocol**: MMS (Manufacturing Message Specification)
**Port**: 102 (TCP)

### 2.2. Logical Devices

**Typical Configuration**:
- **LD0**: Primary protection functions
- **LD1**: Secondary protection functions (if configured)

**CRITICAL**: Verify actual Logical Device name using IEDScout or DIGSI!

### 2.3. Logical Nodes

**MMXU (Measurements)** - Primary target for PV telemetry:
- `MMXU1`: Main measurement unit
- `MMXU2`: Secondary measurement unit (optional)

**Other Common LNs** (informational):
- `XCBR1`: Circuit Breaker control
- `CSWI1`: Switch Controller
- `PTOC1`: Overcurrent Protection (time)
- `PDIS1`: Distance Protection

### 2.4. MMXU Data Objects

| Data Object | Description | Type | Typical Use |
|-------------|-------------|------|-------------|
| `TotW` | Total Active Power (3-phase) | MV | Real power measurement |
| `TotVAr` | Total Reactive Power | MV | Reactive power |
| `TotVA` | Total Apparent Power | MV | Apparent power |
| `TotPF` | Total Power Factor | MV | Power factor |
| `Hz` | Frequency | MV | Grid frequency |
| `PPV` | Phase-to-Phase Voltages | WYE | Line voltages |
| `PhV` | Phase Voltages | WYE | Phase voltages |
| `A` | Phase Currents | WYE | Phase currents |

**MV** = Measured Value (single value)
**WYE** = Wye configuration (3-phase values)

---

## 3. Data Attribute Structure

### 3.1. Common Data Class (CDC)

**MV (Measured Value)**:
```
MV
├── mag         (Magnitude)
│   ├── f       (FLOAT32) - Actual value
│   └── i       (INT32)   - Integer value (alternative)
├── q           (Quality) - Bitstring
├── t           (Timestamp) - Timestamp64
├── units       (Units) - Enumeration
└── db          (Deadband) - Deadband configuration
```

**WYE (3-Phase)**:
```
WYE
├── phsA        (Phase A)
│   └── cVal    (Complex Value)
│       ├── mag.f   (Magnitude, FLOAT32)
│       └── ang.f   (Angle, FLOAT32)
├── phsB        (Phase B)
├── phsC        (Phase C)
└── neut        (Neutral)
```

### 3.2. Functional Constraints (FC)

| FC | Name | Access | Description |
|----|------|--------|-------------|
| **MX** | Measured values | Read/Write | Real-time measurements |
| ST | Status | Read | Status information |
| SP | Setpoint | Write | Control setpoints |
| SG | Settings | Read/Write | Configuration |
| DC | Description | Read | Device descriptions |
| CF | Configuration | Read/Write | Configuration data |

**For PV telemetry**: Use **MX** (Measured values)

---

## 4. Modbus to IEC 61850 Mapping

### 4.1. Translation Table

| Modbus Reg | Parameter | Modbus Value (UINT16) | Decoded | IEC 61850 Object | MMS Variable | Data Type | Quality | Notes |
|------------|-----------|----------------------|---------|------------------|--------------|-----------|---------|-------|
| 0 | P_ac | 250 | 250.0 W | `MMXU1.TotW.mag.f` | `LD0/MMXU1$MX$TotW$mag$f` | FLOAT32 | GOOD | Active Power |
| 1 | V_dc | 485 | 48.5 V | `MMXU1.PhV.phsA.cVal.mag.f` | `LD0/MMXU1$MX$PhV$phsA$cVal$mag$f` | FLOAT32 | GOOD | DC Voltage |
| 2 | I_dc | 536 | 5.36 A | `MMXU1.A.phsA.cVal.mag.f` | `LD0/MMXU1$MX$A$phsA$cVal$mag$f` | FLOAT32 | GOOD | DC Current |
| 3 | G | 850 | 850.0 W/m² | *Custom or omit* | - | - | - | Irradiance |
| 4 | Timestamp | 0x1234 | - | `MMXU1.TotW.t` | `LD0/MMXU1$MX$TotW$t` | Timestamp64 | - | Unix → NTP |

**Quality**: Set to GOOD (0x0000) for valid data

### 4.2. Implementation (Python)

```python
import config
from iec61850_client import IEC61850Client

async def translate_and_send(modbus_regs):
    # Read and decode Modbus registers
    P_ac = float(modbus_regs[0])           # W (no scaling)
    V_dc = float(modbus_regs[1]) / 10.0    # Decode: V×10 → V
    I_dc = float(modbus_regs[2]) / 100.0   # Decode: A×100 → A
    G = float(modbus_regs[3])              # W/m² (no scaling)

    # IEC 61850 client
    iec = IEC61850Client()
    await iec.connect()

    # Write to SIPROTEC
    await iec.write_float(
        config.IEC61850_MAPPING["P_ac"],  # "MMXU1$MX$TotW$mag$f"
        P_ac
    )

    await iec.write_float(
        config.IEC61850_MAPPING["V_dc"],  # "MMXU1$MX$PhV$phsA$cVal$mag$f"
        V_dc
    )

    await iec.write_float(
        config.IEC61850_MAPPING["I_dc"],  # "MMXU1$MX$A$phsA$cVal$mag$f"
        I_dc
    )

    # Optional: Write quality flags
    # await iec.write_quality("MMXU1$MX$TotW$q", 0x0000)  # GOOD
```

---

## 5. Data Type Conversions

### 5.1. Numeric Values

**Modbus UINT16 → IEC 61850 FLOAT32**:

```python
# Modbus (integer, scaled)
modbus_value = 485  # V_dc × 10

# Decode scaling
decoded_value = float(modbus_value) / 10.0  # 48.5 V

# IEC 61850 (float)
mms_value = iec61850.MmsValue_newFloat(decoded_value)
iec_client.connection.writeValue("LD0/MMXU1$MX$PhV$phsA$cVal$mag$f", mms_value)
iec61850.MmsValue_delete(mms_value)
```

### 5.2. Timestamp Conversion

**Unix (Modbus) → NTP (IEC 61850)**:

```python
# Modbus timestamp (Unix epoch: 1970-01-01)
unix_timestamp = 1451606400  # Seconds

# IEC 61850 uses NTP epoch (1900-01-01)
NTP_UNIX_OFFSET = 2208988800  # 70 years in seconds
ntp_timestamp_ms = (unix_timestamp + NTP_UNIX_OFFSET) * 1000  # Convert to milliseconds

# Create IEC 61850 timestamp
mms_value = iec61850.MmsValue_newUtcTimeByMsTime(ntp_timestamp_ms)
iec_client.connection.writeValue("LD0/MMXU1$MX$TotW$t", mms_value)
iec61850.MmsValue_delete(mms_value)
```

**Calculation**:
```
Unix:  1451606400 seconds since 1970-01-01
Add:   + 2208988800 seconds (1900 to 1970)
NTP:   = 3660595200 seconds since 1900-01-01
IEC:   = 3660595200000 milliseconds
```

### 5.3. Quality Flags

**IEC 61850 Quality** (13-bit bitstring):

| Bit | Name | Description |
|-----|------|-------------|
| 0-1 | Validity | 00=good, 01=invalid, 10=reserved, 11=questionable |
| 2 | Overflow | Value overflow |
| 3 | OutOfRange | Value out of range |
| 4 | BadReference | Bad reference |
| 5 | Oscillatory | Oscillatory condition |
| 6 | Failure | Failure detected |
| 7 | OldData | Data is old/stale |
| 8 | Inconsistent | Inconsistent data |
| 9 | Inaccurate | Inaccurate measurement |
| 10-11 | Source | 00=process, 01=substituted |
| 12 | Test | Test mode active |

**Common values**:
- `0x0000`: GOOD (all bits clear)
- `0x0001`: INVALID
- `0x0003`: QUESTIONABLE

```python
# Set quality to GOOD
quality = 0x0000
mms_value = iec61850.MmsValue_newBitString(quality)
iec_client.connection.writeValue("LD0/MMXU1$MX$TotW$q", mms_value)
iec61850.MmsValue_delete(mms_value)
```

---

## 6. Configuration File

### 6.1. config.py

```python
# IEC 61850 MMS Client Configuration
SIPROTEC_IP = "192.168.3.250"
SIPROTEC_PORT = 102
LOGICAL_DEVICE = "LD0"  # CRITICAL: Verify with DIGSI/IEDScout

# Data Object Mapping
# Format: "MMS Variable Name" (without LD prefix)
IEC61850_MAPPING = {
    "P_ac": "MMXU1$MX$TotW$mag$f",
    "V_dc": "MMXU1$MX$PhV$phsA$cVal$mag$f",
    "I_dc": "MMXU1$MX$A$phsA$cVal$mag$f",
    "G": "MMXU1$MX$TotW$mag$f",  # Placeholder (no standard for irradiance)
    "Timestamp": "MMXU1$MX$TotW$t"
}
```

### 6.2. Customization for Your SIPROTEC

**IMPORTANT**: The default mapping assumes:
- Logical Device: `LD0`
- Logical Node: `MMXU1`
- Data objects are read-write

**Verify with IEDScout**:
1. Connect to SIPROTEC
2. Browse logical device tree
3. Find actual Logical Device name
4. Locate MMXU Logical Node
5. Check which data objects exist
6. Verify access rights (read-only vs. read-write)

**Update config.py accordingly!**

---

## 7. Alternative Mappings

### 7.1. Using MMXU.PPV (Phase-to-Phase Voltage)

If SIPROTEC doesn't have PhV (phase voltage), use PPV:

```python
# config.py
IEC61850_MAPPING = {
    "V_dc": "MMXU1$MX$PPV$phsAB$cVal$mag$f",  # Phase A-B voltage
    # ...
}
```

### 7.2. Custom Logical Node for PV Data

Some SIPROTEC configurations may have custom LNs:

```python
# config.py
LOGICAL_DEVICE = "LD0"
CUSTOM_LN = "MPVS1"  # Custom PV System LN (hypothetical)

IEC61850_MAPPING = {
    "P_ac": f"{CUSTOM_LN}$MX$W$mag$f",        # Active power
    "V_dc": f"{CUSTOM_LN}$MX$Vol$mag$f",      # DC voltage
    "I_dc": f"{CUSTOM_LN}$MX$Amp$mag$f",      # DC current
    "G": f"{CUSTOM_LN}$MX$Irrad$mag$f",       # Irradiance
}
```

### 7.3. Multiple Measurement Units

If tracking multiple PV strings:

```python
# String 1
await iec.write_float("MMXU1$MX$TotW$mag$f", P_ac_1)

# String 2
await iec.write_float("MMXU2$MX$TotW$mag$f", P_ac_2)

# Total (aggregate)
await iec.write_float("MMXU3$MX$TotW$mag$f", P_ac_1 + P_ac_2)
```

---

## 8. MMS Protocol Details

### 8.1. MMS Services Used

| Service | Purpose | Used For |
|---------|---------|----------|
| **Write** | Write variable | Sending PV telemetry to SIPROTEC |
| Read | Read variable | Verification, health checks |
| GetNameList | Browse variables | Discovery (IEDScout) |
| GetVariableAccessAttributes | Get data type info | Discovery |

**RPI#2 primarily uses**: **Write** service

### 8.2. MMS Write Request Structure

**Simplified**:
```
MMS-PDU
├── InvokeID: 123
├── Service: Write
├── VariableName: "LD0/MMXU1$MX$TotW$mag$f"
└── VariableValue: 250.0 (FLOAT32)
```

**pyiec61850 abstracts this**:
```python
connection.writeValue(variable_name, mms_value)
```

### 8.3. Error Codes

| Code | Name | Description |
|------|------|-------------|
| 0 | OK | Success |
| 1 | ACCESS_DENIED | No write permission |
| 2 | OBJECT_UNDEFINED | Variable doesn't exist |
| 3 | TYPE_INCONSISTENT | Wrong data type |
| 10 | CONNECTION_LOST | Network disconnected |

**Handle in code**:
```python
error = connection.writeValue(var_name, value)

if error == iec61850.IedConnectionError.IED_ERROR_OK:
    logging.info("Write successful")
elif error == iec61850.IedConnectionError.IED_ERROR_OBJECT_REFERENCE_INVALID:
    logging.error(f"Variable {var_name} doesn't exist")
elif error == iec61850.IedConnectionError.IED_ERROR_ACCESS_DENIED:
    logging.error(f"No write permission for {var_name}")
```

---

## 9. Verification & Testing

### 9.1. Using IEDScout

**Connect**:
1. Launch IEDScout
2. File → New Client
3. Enter SIPROTEC IP: 192.168.3.250
4. Port: 102
5. Click Connect

**Browse Data Model**:
1. Expand tree: LD0 → MMXU1
2. Locate data objects (TotW, PhV, A)
3. Double-click to view attributes

**Manual Write Test**:
1. Right-click: MMXU1.TotW.mag.f
2. Select "Write Value"
3. Enter: 250.0
4. Click OK
5. Verify value updates in SIPROTEC display

**Read Back**:
1. Right-click: MMXU1.TotW.mag.f
2. Select "Read Value"
3. Confirm: 250.0

### 9.2. Python Verification Script

```python
#!/usr/bin/env python3
import iec61850

# Connect to SIPROTEC
connection = iec61850.IedConnection()
error = connection.connect("192.168.3.250", 102)

if error != iec61850.IedConnectionError.IED_ERROR_OK:
    print(f"Connection failed: {error}")
    exit(1)

print("Connected to SIPROTEC")

# Write test value
test_value = 250.0
mms_value = iec61850.MmsValue_newFloat(test_value)
error = connection.writeValue("LD0/MMXU1$MX$TotW$mag$f", mms_value)
iec61850.MmsValue_delete(mms_value)

if error == iec61850.IedConnectionError.IED_ERROR_OK:
    print(f"✓ Wrote {test_value} to MMXU1.TotW.mag.f")
else:
    print(f"✗ Write failed: {error}")

# Read back
mms_value = connection.readValue("LD0/MMXU1$MX$TotW$mag$f")
if mms_value:
    read_value = iec61850.MmsValue_toFloat(mms_value)
    print(f"✓ Read back: {read_value}")
    iec61850.MmsValue_delete(mms_value)

# Disconnect
connection.close()
print("Disconnected")
```

### 9.3. Wireshark Capture

**Filter**: `mms`

**Expected MMS Write**:
```
MMS
├── InvokeID: 1
├── ConfirmedServiceRequest
│   └── Write
│       ├── VariableAccessSpecification
│       │   └── ObjectName: "LD0/MMXU1$MX$TotW$mag$f"
│       └── Data
│           └── float: 250.0
```

---

## 10. Troubleshooting

### 10.1. Connection Fails

**Error**: `IED_ERROR_CONNECT_FAILED`

**Check**:
1. SIPROTEC IP reachable: `ping 192.168.3.250`
2. Port 102 open (not blocked by firewall)
3. MMS server enabled in DIGSI
4. SIPROTEC in correct operating mode

### 10.2. Write Fails (OBJECT_UNDEFINED)

**Error**: `IED_ERROR_OBJECT_REFERENCE_INVALID`

**Cause**: Variable name doesn't exist

**Solutions**:
1. Verify Logical Device name (LD0 vs. LD1)
2. Check MMXU1 exists (may be MMXU2)
3. Verify data object spelling
4. Use IEDScout to browse actual data model

### 10.3. Write Fails (ACCESS_DENIED)

**Error**: `IED_ERROR_ACCESS_DENIED`

**Cause**: No write permission

**Solutions**:
1. Check SIPROTEC is in "Remote Control" mode
2. Verify MMS write access enabled in DIGSI
3. Check if object is read-only
4. May need to write to control model first (GOOSE)

### 10.4. Data Not Updating

**Check**:
1. RPI#2 logs show successful writes
2. IEDScout shows value updates
3. SIPROTEC display reflects changes
4. Check timestamp is recent

**Possible issues**:
- Cached values in SIPROTEC
- Quality flag set to INVALID
- SIPROTEC in test mode
- Data object mapped incorrectly

---

## 11. Advanced Topics

### 11.1. GOOSE Publishing (Future)

**GOOSE** (Generic Object Oriented Substation Event):
- Faster than MMS (multicast, <4 ms)
- For time-critical events
- Requires GOOSE configuration in SIPROTEC
- Not implemented in current system_v2

### 11.2. IEC 62351 Security

**IEC 62351-6** (MMS Security):
- TLS encryption for MMS
- X.509 certificates
- Mutual authentication

**Implementation** (if SIPROTEC supports):
```python
# Enable TLS in connection
sslctx = ssl.create_default_context()
sslctx.load_cert_chain("client.crt", "client.key")
sslctx.load_verify_locations("ca.crt")

# Configure libiec61850 for TLS (requires custom build)
```

### 11.3. Sampled Values (SV)

**For high-speed data** (4-80 samples/cycle):
- Not applicable to PV telemetry (too slow)
- Used for power quality monitoring
- Requires dedicated SV streams

---

## 12. References

### 12.1. Standards

- **IEC 61850-7-2**: Abstract communication service interface (ACSI)
- **IEC 61850-7-3**: Common data classes (CDC)
- **IEC 61850-7-4**: Compatible logical node classes and data object classes
- **IEC 61850-8-1**: Specific communication service mapping (SCSM) - MMS
- **IEC 62351-6**: Security for IEC 61850 (MMS with TLS)

### 12.2. Documentation

- [IEC 61850 Official](https://webstore.iec.ch/publication/6028)
- [libiec61850 Documentation](https://libiec61850.com/documentation/)
- [pyiec61850 on PyPI](https://pypi.org/project/pyiec61850/)
- [SIPROTEC 7SX85 Manual](https://support.industry.siemens.com/)

### 12.3. Tools

- **IEDScout** (Omicron): IEC 61850 client and browser
- **DIGSI** (Siemens): SIPROTEC configuration
- **Wireshark**: Protocol analyzer (MMS dissector)
- **61850 Analyzer**: Commercial IEC 61850 testing tool

---

**Document Version**: 1.0
**Last Updated**: 2025-12-18
