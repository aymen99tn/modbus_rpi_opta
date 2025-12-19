"""
RPI#1 - Smart Meter / RTU Server

Modbus TCP server that:
1. Receives PV telemetry from ESP32 (WiFi interface) via Modbus writes
2. Serves telemetry to Arduino Opta (Ethernet interface) via Modbus reads

Architecture:
  ESP32 --[WiFi, Modbus TCP Write:502]--> RPI#1 <--[Ethernet, Modbus TCP Read:502]-- Opta

Network Configuration:
  - Binds to 0.0.0.0:502 (serves both WiFi and Ethernet interfaces)
  - WiFi interface: 192.168.1.100 (for ESP32)
  - Ethernet interface: 192.168.2.100 (for Opta)

Based on system_v1/modbus_bridge_rpi2.py with simplifications:
  - Removed TLS server (plain TCP only)
  - Removed pvlib code (ESP32 handles data generation)
  - Single server instead of dual server

"""

import asyncio
import logging
import ssl
from datetime import datetime, timezone

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusDeviceContext,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTlsServer, StartAsyncTcpServer

# =============================================================================
# CONFIGURATION
# =============================================================================

# TCP Server Configuration (for Opta)
BIND_ADDRESS = "0.0.0.0"  # Bind to all interfaces (WiFi + Ethernet)
BIND_PORT = 502            # Standard Modbus TCP port
UNIT_ID = 1                # Modbus device ID

# TLS Server Configuration (for ESP32)
TLS_BIND_ADDRESS = "0.0.0.0"
TLS_BIND_PORT = 802

# Certificate files (copied from system_v1)
SERVER_CERT = "server.crt"
SERVER_KEY = "server.key"

# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# =============================================================================
# SSL/TLS CONTEXT
# =============================================================================

def build_ssl_context(certfile=SERVER_CERT, keyfile=SERVER_KEY):
    """
    Build SSL context for TLS server

    Based on system_v1/modbus_bridge_rpi2.py (lines 109-119)
    """
    try:
        sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sslctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
        sslctx.minimum_version = ssl.TLSVersion.TLSv1_2
        logger.info(f"SSL context created with cert={certfile}, key={keyfile}")
        return sslctx
    except Exception as e:
        logger.error(f"Failed to create SSL context: {e}")
        raise

# =============================================================================
# SHARED DATA STORAGE
# =============================================================================

class SmartMeterDataBlock(ModbusSequentialDataBlock):
    """
    Smart meter datablock that:
    1. Receives writes from ESP32 (WiFi interface)
    2. Serves reads to Arduino Opta (Ethernet interface)

    Tracks statistics for received (from ESP32) and served (to Opta) data.
    """

    def __init__(self, address, values):
        super().__init__(address, values)
        self.total_received = 0
        self.total_served = 0
        self.last_update = None

    def setValues(self, address, values):
        """
        Called when ESP32 writes data via Modbus TCP

        Intercepts writes to telemetry registers (0-7), decodes for logging,
        and updates statistics.
        """
        super().setValues(address, values)

        # Check if write overlaps telemetry block (registers 0-7)
        start = int(address)
        end = start + len(values) - 1

        if end < 0 or start > 7:
            # Outside our telemetry range, ignore
            return

        # Read back the complete 8-register block for logging
        regs = self.getValues(0, 8)

        # Decode for human-readable logging (apply inverse scaling)
        P_ac = regs[0] * 1.0
        P_dc = regs[1] * 1.0
        V_dc = regs[2] / 10.0        # Decode: V × 10 → V
        I_dc = regs[3] / 100.0       # Decode: A × 100 → A
        G = regs[4] * 1.0
        T_cell = regs[5] / 10.0      # Decode: °C × 10 → °C

        # Reconstruct 32-bit timestamp from two 16-bit registers
        unix_s = ((regs[6] & 0xFFFF) << 16) | (regs[7] & 0xFFFF)
        ts = datetime.fromtimestamp(unix_s, tz=timezone.utc)

        self.total_received += 1
        self.last_update = datetime.now(timezone.utc)

        logger.info(
            f"[RX FROM ESP32 via TLS] {ts.isoformat()} | "
            f"P_ac={P_ac:.1f}W P_dc={P_dc:.1f}W V_dc={V_dc:.2f}V I_dc={I_dc:.2f}A "
            f"G={G:.1f}W/m² T_cell={T_cell:.1f}°C | Total RX: {self.total_received}"
        )

    def getValues(self, address, count=1):
        """
        Called when Opta reads data via Modbus TCP

        Logs read operations for telemetry registers and updates statistics.
        """
        values = super().getValues(address, count)

        # Log only if reading complete telemetry block
        if address == 0 and count == 8:
            self.total_served += 1
            logger.info(
                f"[TX TO OPTA via TCP] Served registers 0-7 | "
                f"Total served: {self.total_served}"
            )

        return values


async def statistics_task(datablock):
    """
    Periodically report statistics (every 60 seconds)
    """
    while True:
        try:
            await asyncio.sleep(60)

            logger.info(
                f"[STATISTICS] "
                f"Received (from ESP32): {datablock.total_received} | "
                f"Served (to Opta): {datablock.total_served} | "
                f"Last Update: {datablock.last_update.isoformat() if datablock.last_update else 'Never'}"
            )

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in statistics task: {e}")


# =============================================================================
# MAIN ASYNC FUNCTION
# =============================================================================

async def main():
    """
    Main async function that starts Modbus TCP server

    Server binds to 0.0.0.0:502, serving both WiFi (ESP32) and Ethernet (Opta) interfaces
    """
    logger.info("=" * 80)
    logger.info("RPI#1 - Smart Meter / RTU Server Starting - Dual Server Mode")
    logger.info("=" * 80)
    logger.info(f"Architecture:")
    logger.info(f"  ESP32 → RPI#1: WiFi, Modbus+TLS (writes data)")
    logger.info(f"  RPI#1 ← Opta: Ethernet, Modbus TCP (reads data)")
    logger.info(f"")
    logger.info(f"Configuration:")
    logger.info(f"  TLS Server (ESP32 writes): {TLS_BIND_ADDRESS}:{TLS_BIND_PORT}")
    logger.info(f"  TCP Server (Opta reads):   {BIND_ADDRESS}:{BIND_PORT}")
    logger.info(f"  Unit ID: {UNIT_ID}")
    logger.info(f"  Certificates: {SERVER_CERT}, {SERVER_KEY}")
    logger.info("=" * 80)

    # Create shared datablock for holding registers
    datablock = SmartMeterDataBlock(0, [0] * 100)

    # Create device context with datablock
    device = ModbusDeviceContext(hr=datablock)

    # Create server context (single=True accepts any unit-id, standard for Modbus TCP)
    context = ModbusServerContext(devices=device, single=True)

    # Start statistics task
    stats = asyncio.create_task(statistics_task(datablock))
    logger.info("Statistics task created")

    # Build SSL context for TLS server
    sslctx = build_ssl_context()

    logger.info(f"Starting Modbus TLS server on {TLS_BIND_ADDRESS}:{TLS_BIND_PORT}...")
    logger.info(f"Starting Modbus TCP server on {BIND_ADDRESS}:{BIND_PORT}...")
    logger.info("Waiting for:")
    logger.info("  - ESP32 to write data via TLS (WiFi interface)")
    logger.info("  - Opta to read data via TCP (Ethernet interface)")

    try:
        await asyncio.gather(
            StartAsyncTlsServer(
                context=context,
                address=(TLS_BIND_ADDRESS, TLS_BIND_PORT),
                sslctx=sslctx,
            ),
            StartAsyncTcpServer(
                context=context,
                address=(BIND_ADDRESS, BIND_PORT),
            )
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        # Cancel background tasks
        stats.cancel()
        try:
            await stats
        except asyncio.CancelledError:
            pass

        # Report final statistics
        logger.info("=" * 80)
        logger.info("Smart Meter Server Shutdown (Dual Server Mode)")
        logger.info("=" * 80)
        logger.info(f"Final Statistics:")
        logger.info(f"  Total Received (from ESP32): {datablock.total_received}")
        logger.info(f"  Total Served (to Opta): {datablock.total_served}")
        logger.info(f"  Last Update: {datablock.last_update.isoformat() if datablock.last_update else 'Never'}")
        logger.info("=" * 80)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
