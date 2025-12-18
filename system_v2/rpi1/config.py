"""
RPI#1 Smart Meter Server Configuration
"""

# Modbus TCP Server
BIND_ADDRESS = "0.0.0.0"  # Bind to all interfaces (WiFi + Ethernet)
BIND_PORT = 502            # Standard Modbus TCP port
UNIT_ID = 1                # Modbus device ID

# Network Configuration
WIFI_INTERFACE = "wlan0"
ETHERNET_INTERFACE = "eth0"
ETHERNET_IP = "192.168.2.100"

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Statistics
STATS_INTERVAL_SEC = 60  # Report statistics every 60 seconds
