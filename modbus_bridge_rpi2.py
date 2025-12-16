import ssl
import asyncio
import logging
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

# TCP Server Configuration (for Opta to poll)
TCP_BIND_ADDRESS = "0.0.0.0"
TCP_BIND_PORT = 502

# TLS Server Configuration (receives from RPI#1)
TLS_BIND_ADDRESS = "0.0.0.0"
TLS_BIND_PORT = 802
UNIT_ID = 1

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
# SHARED DATA STORAGE
# =============================================================================

class SharedTelemetryDataBlock(ModbusSequentialDataBlock):
    """
    Shared datablock that:
    1. Receives writes from RPI#1 (via TLS server)
    2. Serves reads to Arduino Opta (via TCP server)
    Both servers share the SAME register data
    """

    def __init__(self, address, values):
        super().__init__(address, values)
        self.total_received = 0
        self.total_served = 0
        self.last_update = None

    def setValues(self, address, values):

        super().setValues(address, values)

        # Check if write overlaps telemetry block (registers 0-7)
        start = int(address)
        end = start + len(values) - 1

        if end < 0 or start > 7:
            # Outside our telemetry range, ignore
            return

        # Read back the complete 8-register block
        regs = self.getValues(0, 8)

        # Decode for human-readable logging
        P_ac = regs[0] * 1.0
        P_dc = regs[1] * 1.0
        V_dc = regs[2] / 10.0
        I_dc = regs[3] / 100.0
        G = regs[4] * 1.0
        T_cell = regs[5] / 10.0

        # Reconstruct timestamp
        unix_s = ((regs[6] & 0xFFFF) << 16) | (regs[7] & 0xFFFF)
        ts = datetime.fromtimestamp(unix_s, tz=timezone.utc)

        self.total_received += 1
        self.last_update = datetime.now(timezone.utc)

        logger.info(
            f"[RECEIVED FROM RPI#1 via TLS] {ts.isoformat()} | "
            f"P_ac={P_ac:.1f}W P_dc={P_dc:.1f}W V_dc={V_dc:.2f}V I_dc={I_dc:.2f}A "
            f"G={G:.1f}W/m² T_cell={T_cell:.1f}°C | Total RX: {self.total_received}"
        )

    def getValues(self, address, count=1):
        """Called when Opta reads data via TCP"""
        values = super().getValues(address, count)

        # Log only if reading telemetry registers
        if address == 0 and count == 8:
            self.total_served += 1
            logger.info(
                f"[SERVED TO OPTA via TCP] Registers 0-7 | "
                f"Total served: {self.total_served}"
            )

        return values


def build_ssl_context(certfile=SERVER_CERT, keyfile=SERVER_KEY):
    """Build SSL context for TLS server"""
    try:
        sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sslctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
        sslctx.minimum_version = ssl.TLSVersion.TLSv1_2
        logger.info(f"SSL context created with cert={certfile}, key={keyfile}")
        return sslctx
    except Exception as e:
        logger.error(f"Failed to create SSL context: {e}")
        raise


async def statistics_task(datablock):
    """
    Periodically report statistics
    """
    while True:
        try:
            await asyncio.sleep(60)

            logger.info(
                f"[STATISTICS] "
                f"Total Received (from RPI#1): {datablock.total_received} | "
                f"Total Served (to Opta): {datablock.total_served} | "
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
    Main async function that starts BOTH TLS and TCP servers
    Both servers share the same datablock (registers)
    """
    logger.info("=" * 80)
    logger.info("Modbus Bridge Server Starting (RPI#2) - Dual Server Mode")
    logger.info("=" * 80)
    logger.info(f"Architecture:")
    logger.info(f"  RPI#1 → RPI#2: Wireless, Modbus+TLS (writes data)")
    logger.info(f"  RPI#2 ← Opta: Wired Ethernet, Modbus TCP (polls/reads data)")
    logger.info(f"")
    logger.info(f"Configuration:")
    logger.info(f"  TLS Server (RPI#1 writes): {TLS_BIND_ADDRESS}:{TLS_BIND_PORT}")
    logger.info(f"  TCP Server (Opta reads):   {TCP_BIND_ADDRESS}:{TCP_BIND_PORT}")
    logger.info(f"  Unit ID: {UNIT_ID}")
    logger.info(f"  Certificates: {SERVER_CERT}, {SERVER_KEY}")
    logger.info("=" * 80)

    # Create SHARED datablock for holding registers
    shared_datablock = SharedTelemetryDataBlock(0, [0] * 100)

    # Create device context with shared datablock
    device = ModbusDeviceContext(hr=shared_datablock)

    # Create server context
    context = ModbusServerContext(devices={UNIT_ID: device}, single=False)

    # Build SSL context for TLS server
    sslctx = build_ssl_context()

    # Start statistics task
    stats = asyncio.create_task(statistics_task(shared_datablock))
    logger.info("Statistics task created")

    logger.info(f"Starting Modbus TLS server on {TLS_BIND_ADDRESS}:{TLS_BIND_PORT}...")
    logger.info(f"Starting Modbus TCP server on {TCP_BIND_ADDRESS}:{TCP_BIND_PORT}...")
    logger.info("Waiting for:")
    logger.info("  - RPI#1 to write data via TLS (wireless)")
    logger.info("  - Opta to read data via TCP (wired)")

    try:

        await asyncio.gather(
            StartAsyncTlsServer(
                context=context,
                address=(TLS_BIND_ADDRESS, TLS_BIND_PORT),
                sslctx=sslctx,
            ),
            StartAsyncTcpServer(
                context=context,
                address=(TCP_BIND_ADDRESS, TCP_BIND_PORT),
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
        logger.info("Bridge Server Shutdown")
        logger.info("=" * 80)
        logger.info(f"Final Statistics:")
        logger.info(f"  Total Received (from RPI#1): {shared_datablock.total_received}")
        logger.info(f"  Total Served (to Opta): {shared_datablock.total_served}")
        logger.info(f"  Last Update: {shared_datablock.last_update.isoformat() if shared_datablock.last_update else 'Never'}")
        logger.info("=" * 80)


#-----------main-------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
