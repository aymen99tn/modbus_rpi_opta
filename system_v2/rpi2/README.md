# RPI#2 - Substation Gateway

**CRITICAL COMPONENT**: Protocol translation gateway that converts Modbus TCP to IEC 61850 MMS for communication with SIPROTEC 7SX85 protection relay.

## Architecture

```
Opta --[Ethernet, Modbus TCP:502]--> RPI#2 --[Ethernet, IEC 61850 MMS:102]--> SIPROTEC 7SX85
```

## Components

1. **Modbus TCP Server** (`modbus_server.py`): Receives telemetry from Arduino Opta
2. **IEC 61850 MMS Client** (`iec61850_client.py`): Communicates with SIPROTEC relay
3. **Protocol Translator** (`protocol_translator.py`): Maps Modbus registers → IEC 61850 data objects
4. **Main Orchestrator** (`substation_gateway.py`): Coordinates all components

## Prerequisites

### 1. SIPROTEC Configuration (CRITICAL)

**BEFORE running this gateway**, verify SIPROTEC settings:

```bash
# Use IEDScout or DIGSI to:
1. Connect to SIPROTEC at 192.168.3.250:102
2. Verify Logical Device name (LD0, LD1, or custom)
3. Verify MMXU1 Logical Node exists
4. Check data objects are read-write:
   - MMXU1.TotW.mag.f (Active Power)
   - MMXU1.PhV.phsA.cVal.mag.f (Voltage)
   - MMXU1.A.phsA.cVal.mag.f (Current)
5. Export ICD file for reference
6. Test manual MMS write with IEDScout
```

**Action Item**: Update `config.py` with actual Logical Device name from SIPROTEC.

### 2. Install Python Dependencies

```bash
cd system_v2/rpi2
pip3 install -r requirements.txt
```

**pyiec61850 Installation:**

If pip install fails, build from source:

```bash
git clone https://github.com/mz-automation/libiec61850.git
cd libiec61850
mkdir build && cd build
cmake -DBUILD_PYTHON_BINDINGS=ON ..
make
sudo make install
```

## Configuration

Edit `config.py`:

```python
# IEC 61850 MMS Client Configuration
SIPROTEC_IP = "192.168.1.21"  # SIPROTEC IP address
SIPROTEC_PORT = 102            # Standard IEC 61850 MMS port
LOGICAL_DEVICE = "LD0"        # Verify with DIGSI/IEDScout

# IEC 61850 Data Object Mapping
IEC61850_MAPPING = {
    "P_ac": "MMXU1$MX$TotW$mag$f",           # Total Active Power
    "V_dc": "MMXU1$MX$PhV$phsA$cVal$mag$f",  # Phase A Voltage
    "I_dc": "MMXU1$MX$A$phsA$cVal$mag$f",    # Phase A Current
}
```

## Usage

### Test IEC 61850 Connection

Before running gateway, test connection:

```bash
python3 substation_gateway.py --test-connection
```

Expected output:
```
Testing IEC 61850 connection to SIPROTEC...
Connecting to SIPROTEC at 192.168.3.250:102...
✓ Connected to SIPROTEC at 192.168.3.250:102
  Logical Device: LD0
✓ Connection successful!
✓ Health check passed
```

### Start Gateway

```bash
python3 substation_gateway.py
```

With custom SIPROTEC IP:
```bash
python3 substation_gateway.py --siprotec-ip 192.168.3.250
```

### Expected Output

```
================================================================================
RPI#2 - Substation Gateway Starting
================================================================================
Architecture:
  Opta → RPI#2: Ethernet, Modbus TCP (writes data)
  RPI#2 → SIPROTEC: Ethernet, IEC 61850 MMS (protocol translation)

Configuration:
  Modbus Server: 0.0.0.0:502
  SIPROTEC IP: 192.168.3.250:102
  Logical Device: LD0
  Update Interval: 1.0s
================================================================================
1. Initializing Modbus TCP server...
2. Initializing IEC 61850 MMS client...
3. Connecting to SIPROTEC...
✓ Connected to SIPROTEC at 192.168.3.250:102
  Logical Device: LD0
4. Initializing protocol translator...
5. Starting protocol translator...
================================================================================
✓ Gateway components initialized
Starting Modbus TCP server...
Waiting for:
  - Opta to write data via Modbus TCP
  - Protocol translator to send data to SIPROTEC
================================================================================

[RX FROM OPTA] P_ac=250.0W V_dc=48.50V I_dc=5.36A G=850.0W/m² | Total RX: 1
[IEC 61850 UPDATE] P_ac=250.0W V_dc=48.50V I_dc=5.36A | Total updates: 1
```

## Protocol Translation Mapping

### Modbus Register Map (from Opta)

| Register | Parameter | Encoding |
|----------|-----------|----------|
| 0 | P_ac | W (uint16) |
| 1 | V_dc | V × 10 (uint16) |
| 2 | I_dc | A × 100 (uint16) |
| 3 | G | W/m² (uint16) |
| 4 | Timestamp_low | Unix [15:0] |

### IEC 61850 Data Model Mapping

| Modbus | Parameter | IEC 61850 Object Reference | MMS Variable Name |
|--------|-----------|----------------------------|-------------------|
| Reg 0 | P_ac (W) | `MMXU1.TotW.mag.f` | `LD0/MMXU1$MX$TotW$mag$f` |
| Reg 1 | V_dc (V) | `MMXU1.PhV.phsA.cVal.mag.f` | `LD0/MMXU1$MX$PhV$phsA$cVal$mag$f` |
| Reg 2 | I_dc (A) | `MMXU1.A.phsA.cVal.mag.f` | `LD0/MMXU1$MX$A$phsA$cVal$mag$f` |

**Decoding**: V_dc and I_dc are decoded (÷10, ÷100) before writing to IEC 61850.

**IEC 61850 Data Types**:
- Magnitude values: FLOAT32
- Quality flags: Bitstring (set to GOOD: 0x0000)
- Timestamp: Timestamp64 (NTP epoch)

## Troubleshooting

### Cannot Connect to SIPROTEC

**Error:** `IEC 61850 connection failed`

**Solutions:**
1. Verify SIPROTEC IP: `ping 192.168.3.250`
2. Check SIPROTEC MMS server is enabled (DIGSI/SICAM)
3. Verify firewall allows port 102
4. Test with IEDScout manually
5. Check SIPROTEC is in "Remote Control" mode
6. Verify network cable is connected

### IEC 61850 Write Failed

**Error:** `Write failed for LD0/MMXU1$MX$TotW$mag$f`

**Solutions:**
1. Verify data object exists: Use IEDScout to browse
2. Check object is read-write (not read-only)
3. Verify Logical Device name: May be LD1, LD2, etc.
4. Check Functional Constraint: Should be MX (Measured values)
5. Verify data type: Must be FLOAT32 for magnitude values

### Logical Device Name Incorrect

**Error:** Connection succeeds but writes fail

**Solution:**
1. Use IEDScout to browse SIPROTEC
2. Check actual Logical Device name (LD0, LD1, etc.)
3. Update `config.py` with correct name:
   ```python
   LOGICAL_DEVICE = "LD1"  # Or whatever IEDScout shows
   ```

### pyiec61850 Not Installed

**Error:** `ModuleNotFoundError: No module named 'iec61850'`

**Solution:**
```bash
pip3 install pyiec61850
```

If that fails, build from source (see Prerequisites).

## Network Configuration

| Interface | IP Address | Subnet | Purpose |
|-----------|------------|--------|---------|
| Ethernet (Station Zone) | 192.168.2.200 | 192.168.2.0/24 | Receives from Opta |
| Ethernet (Process Zone) | 192.168.3.200 | 192.168.3.0/24 | Connects to SIPROTEC |

**Note**: RPI#2 may need two Ethernet interfaces or VLAN configuration for proper zone segmentation.

## Performance

- **Update Rate**: 1 Hz (1 update/second to SIPROTEC)
- **Latency**: <100 ms (Modbus RX → IEC 61850 TX)
- **CPU Usage**: <10%
- **Network Traffic**: ~500 bytes/second (minimal)

## Security Considerations

### Zone Segmentation

- **Station Zone** (192.168.2.0/24): Opta → RPI#2 Modbus TCP
- **Process Zone** (192.168.3.0/24): RPI#2 → SIPROTEC IEC 61850 MMS

**Recommendation**: Use separate physical interfaces or VLANs for zone isolation.

### IEC 62351 Security (Optional)

SIPROTEC 7SX85 may support IEC 62351-6 (MMS with TLS):
1. Enable in DIGSI configuration
2. Generate certificates
3. Update `iec61850_client.py` to use TLS

## Testing

### Test with QModMaster

Write test registers to RPI#2:

```bash
# Write 5 registers to RPI#2:502
# Values: [250, 485, 536, 850, 4660]
```

### Verify SIPROTEC Receives Data

Use IEDScout to read back values:
1. Connect to SIPROTEC
2. Navigate to: LD0/MMXU1/TotW/mag.f
3. Verify value matches P_ac sent by Opta

## Systemd Service (Optional)

Create `/etc/systemd/system/substation-gateway.service`:

```ini
[Unit]
Description=RPI#2 Substation Gateway
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/RPI_NBP/system_v2/rpi2
ExecStart=/usr/bin/python3 /home/pi/RPI_NBP/system_v2/rpi2/substation_gateway.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable substation-gateway
sudo systemctl start substation-gateway
sudo systemctl status substation-gateway
```

## References

- [IEC 61850 Standard](https://webstore.iec.ch/publication/6028)
- [SIPROTEC 7SX85 Manual](https://support.industry.siemens.com/)
- [libiec61850 Documentation](https://libiec61850.com/)
- [pyiec61850 on PyPI](https://pypi.org/project/pyiec61850/)
- [IEDScout Download](https://www.omicronenergy.com/en/products/all/secondary-testing-calibration/iedscout/)
