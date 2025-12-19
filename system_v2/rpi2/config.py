"""
RPI#2 Substation Gateway Configuration
"""

# Modbus TCP Server Configuration
MODBUS_BIND_ADDRESS = "0.0.0.0"
MODBUS_BIND_PORT = 502
MODBUS_UNIT_ID = 1

# IEC 61850 MMS Client Configuration
SIPROTEC_IP = "192.168.1.21"
SIPROTEC_PORT = 102  # Standard IEC 61850 MMS port
LOGICAL_DEVICE = "LD0"  # Verify with DIGSI/IEDScout

# Protocol Translator Configuration
TRANSLATION_INTERVAL_SEC = 1.0  # Update rate to SIPROTEC

# Network Configuration
STATION_ZONE_IP = "192.168.1.50"  # Receives from Opta
PROCESS_ZONE_IP = "192.168.1.21"  # Connects to SIPROTEC

# IEC 61850 Data Object Mapping
# Verify these with SIPROTEC ICD file or IEDScout
IEC61850_MAPPING = {
    "P_ac": "MMXU1$MX$TotW$mag$f",           # Total Active Power
    "V_dc": "MMXU1$MX$PhV$phsA$cVal$mag$f",  # Phase A Voltage
    "I_dc": "MMXU1$MX$A$phsA$cVal$mag$f",    # Phase A Current
    "G": "MMXU1$MX$TotW$mag$f",              # Use same as P_ac or custom
    "Timestamp": "MMXU1$MX$TotW$t"            # Timestamp
}

# Logging Configuration
LOG_LEVEL = "INFO"
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Error Handling
CONNECTION_RETRY_DELAY_SEC = 5
MAX_RETRY_ATTEMPTS = 3
QUEUE_MAX_SIZE = 100  # Buffer updates during disconnection
