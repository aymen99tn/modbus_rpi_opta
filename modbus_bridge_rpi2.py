"""
Modbus Bridge Server (RPI#2) - Store-and-Forward Architecture
Receives PV telemetry from RPI#1 via Modbus+TLS (wireless)
Stores data locally and forwards to Arduino Opta via Modbus TCP (wired Ethernet)
"""
import ssl
import asyncio
import logging
from datetime import datetime, timezone
from collections import deque

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusDeviceContext,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTlsServer
from pymodbus.client import AsyncModbusTcpClient

# =============================================================================
# CONFIGURATION 
# =============================================================================

# Opta Configuration
OPTA_IP = "192.168.1.51"  # Arduino Opta IP address
OPTA_PORT = 502
OPTA_UNIT_ID = 1

# TLS Server Configuration
TLS_BIND_ADDRESS = "0.0.0.0"
TLS_BIND_PORT = 802
UNIT_ID = 1

# Store-and-Forward Settings
BUFFER_MAX_SIZE = 100          # Maximum telemetry records to buffer
FORWARD_INTERVAL = 5.0         # Send to Opta every 5 seconds
CONNECTION_TIMEOUT = 10.0      # seconds

# TLS Certificates
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
# DATA STORAGE 
# =============================================================================

class TelemetryBuffer:
    """
    Thread-safe buffer for storing telemetry data
    Uses deque for efficient FIFO operations
    """
    def __init__(self, maxsize=BUFFER_MAX_SIZE):
        self.buffer = deque(maxlen=maxsize)
        self.lock = asyncio.Lock()
        self.total_received = 0
        self.total_forwarded = 0
        self.total_dropped = 0

    async def add(self, registers, timestamp):
        """Add new telemetry data to buffer"""
        async with self.lock:
            # Check if buffer is full
            if len(self.buffer) >= self.buffer.maxlen:
                self.total_dropped += 1
                logger.warning(
                    f"Buffer full ({len(self.buffer)}/{self.buffer.maxlen}), "
                    f"dropping oldest data"
                )

            # Add to buffer (automatically drops oldest if full)
            self.buffer.append({
                'registers': registers,
                'timestamp': timestamp,
                'received_at': datetime.now(timezone.utc)
            })

            self.total_received += 1

            logger.info(
                f"Stored telemetry in buffer [{len(self.buffer)}/{self.buffer.maxlen}] "
                f"| Total RX: {self.total_received}, Dropped: {self.total_dropped}"
            )

    async def get_latest(self):
        """Get the most recent telemetry data without removing it"""
        async with self.lock:
            if self.buffer:
                return self.buffer[-1]  # Most recent (rightmost)
            return None

    async def get_all_pending(self):
        """Get all pending data and clear buffer"""
        async with self.lock:
            data = list(self.buffer)
            self.buffer.clear()
            return data

    async def get_count(self):
        """Get current buffer count"""
        async with self.lock:
            return len(self.buffer)

    async def mark_forwarded(self, count):
        """Update forwarded counter"""
        self.total_forwarded += count

# Global telemetry buffer
telemetry_buffer = TelemetryBuffer(maxsize=BUFFER_MAX_SIZE)


class StoringHoldingRegisterBlock(ModbusSequentialDataBlock):
    """
    Custom datablock that stores received data from RPI#1 into buffer
    """

    def setValues(self, address, values):
        # Store the values first
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

        logger.info(
            f"[RECEIVED FROM RPI#1] {ts.isoformat()} | "
            f"P_ac={P_ac:.1f}W P_dc={P_dc:.1f}W V_dc={V_dc:.2f}V I_dc={I_dc:.2f}A "
            f"G={G:.1f}W/m² T_cell={T_cell:.1f}°C"
        )

        asyncio.create_task(
            telemetry_buffer.add(list(regs), ts)
        )

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

# =============================================================================
# FORWARDER TASK (Sends stored data to Arduino Opta)
# =============================================================================

async def forwarder_task():
    """
    Background task that periodically forwards buffered data to Arduino Opta
    Uses store-and-forward: data is stored first, then sent when connection available
    """
    logger.info(f"Forwarder task started. Will forward to {OPTA_IP}:{OPTA_PORT} every {FORWARD_INTERVAL}s")

    # Initialize Modbus TCP client for Opta (wired Ethernet)
    client = AsyncModbusTcpClient(
        host=OPTA_IP,
        port=OPTA_PORT,
        timeout=CONNECTION_TIMEOUT
    )

    # Connection state
    connected = False
    consecutive_failures = 0

    while True:
        try:
            
            await asyncio.sleep(FORWARD_INTERVAL)

            buffer_count = await telemetry_buffer.get_count()

            if buffer_count == 0:
                logger.debug("No data in buffer, skipping forward cycle")
                continue

            logger.info(f"Forward cycle: {buffer_count} record(s) in buffer")

            if not connected:
                logger.info(f"Connecting to Opta at {OPTA_IP}:{OPTA_PORT} (wired Ethernet)...")
                connected = await client.connect()

                if not connected:
                    consecutive_failures += 1
                    logger.error(
                        f"Failed to connect to Opta (attempt #{consecutive_failures}). "
                        f"Data remains buffered. Will retry in {FORWARD_INTERVAL}s"
                    )
                    continue
                else:
                    logger.info("Connected to Opta successfully")
                    consecutive_failures = 0

            
            latest = await telemetry_buffer.get_latest()

            if latest is None:
                logger.debug("No data available after check")
                continue

            registers = latest['registers']
            timestamp = latest['timestamp']

            # Send to Opta
            try:
                result = await client.write_registers(
                    address=0,
                    values=registers,
                    slave=OPTA_UNIT_ID
                )

                if not result.isError():
                    logger.info(
                        f"[FORWARDED TO OPTA] {timestamp.isoformat()} | "
                        f"Registers: {registers} | Buffer: {buffer_count} records"
                    )

                    await telemetry_buffer.mark_forwarded(1)
                    consecutive_failures = 0

                else:
                    consecutive_failures += 1
                    logger.warning(
                        f"Modbus error sending to Opta: {result} "
                        f"(failure #{consecutive_failures})"
                    )

            except Exception as e:
                consecutive_failures += 1
                logger.error(
                    f"Exception sending to Opta: {e} (failure #{consecutive_failures})"
                )
                
                connected = False

            if consecutive_failures >= 3:
                logger.warning(
                    f"Too many consecutive failures ({consecutive_failures}), "
                    f"will reconnect on next cycle"
                )
                connected = False
                consecutive_failures = 0

        except asyncio.CancelledError:
            logger.info("Forwarder task cancelled")
            break
        except Exception as e:
            logger.error(f"Unexpected error in forwarder task: {e}", exc_info=True)
            await asyncio.sleep(FORWARD_INTERVAL) 

    
    if connected:
        client.close()
        logger.info("Closed connection to Opta")


async def statistics_task():
    """
    Periodically report buffer statistics
    """
    while True:
        try:
            await asyncio.sleep(60)  

            buffer_count = await telemetry_buffer.get_count()

            logger.info(
                f"[STATISTICS] Buffer: {buffer_count}/{BUFFER_MAX_SIZE} | "
                f"Total Received: {telemetry_buffer.total_received} | "
                f"Total Forwarded: {telemetry_buffer.total_forwarded} | "
                f"Total Dropped: {telemetry_buffer.total_dropped}"
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
    Main async function that starts TLS server and forwarder task
    """
    logger.info("=" * 80)
    logger.info("Modbus Bridge Server Starting (RPI#2) - Store-and-Forward Mode")
    logger.info("=" * 80)
    logger.info(f"Architecture:")
    logger.info(f"  RPI#1 → RPI#2: Wireless, TLS on port {TLS_BIND_PORT}")
    logger.info(f"  RPI#2 → Opta: Wired Ethernet, TCP on port {OPTA_PORT}")
    logger.info(f"")
    logger.info(f"Configuration:")
    logger.info(f"  TLS Server: {TLS_BIND_ADDRESS}:{TLS_BIND_PORT} (unit-id={UNIT_ID})")
    logger.info(f"  Forward to: {OPTA_IP}:{OPTA_PORT} (unit-id={OPTA_UNIT_ID})")
    logger.info(f"  Buffer size: {BUFFER_MAX_SIZE} records")
    logger.info(f"  Forward interval: {FORWARD_INTERVAL}s")
    logger.info(f"  Certificates: {SERVER_CERT}, {SERVER_KEY}")
    logger.info("=" * 80)

    # Create custom datablock for holding registers
    hr_block = StoringHoldingRegisterBlock(0, [0] * 100)

    device = ModbusDeviceContext(hr=hr_block)

    context = ModbusServerContext(devices={UNIT_ID: device}, single=False)

    sslctx = build_ssl_context()

    forwarder = asyncio.create_task(forwarder_task())
    logger.info("Forwarder task created")

    stats = asyncio.create_task(statistics_task())
    logger.info("Statistics task created")

    logger.info(f"Starting Modbus TLS server on {TLS_BIND_ADDRESS}:{TLS_BIND_PORT}...")
    logger.info("Waiting for data from RPI#1 (wireless)...")

    try:
        await StartAsyncTlsServer(
            context=context,
            address=(TLS_BIND_ADDRESS, TLS_BIND_PORT),
            sslctx=sslctx,
        )
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        # Cancel background tasks
        forwarder.cancel()
        stats.cancel()
        try:
            await forwarder
            await stats
        except asyncio.CancelledError:
            pass

        # Report final statistics
        buffer_count = await telemetry_buffer.get_count()
        logger.info("=" * 80)
        logger.info("Bridge Server Shutdown")
        logger.info("=" * 80)
        logger.info(f"Final Statistics:")
        logger.info(f"  Buffer: {buffer_count}/{BUFFER_MAX_SIZE} records")
        logger.info(f"  Total Received: {telemetry_buffer.total_received}")
        logger.info(f"  Total Forwarded: {telemetry_buffer.total_forwarded}")
        logger.info(f"  Total Dropped: {telemetry_buffer.total_dropped}")
        logger.info("=" * 80)


#-----------main-------------
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
