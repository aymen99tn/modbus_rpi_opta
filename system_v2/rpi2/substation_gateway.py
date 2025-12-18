"""
RPI#2 - Substation Gateway

Main orchestrator for protocol translation gateway:
  1. Modbus TCP server (receives from Opta)
  2. IEC 61850 MMS client (sends to SIPROTEC)
  3. Protocol translator (maps Modbus → IEC 61850)

Architecture:
  Opta --[Modbus TCP:502]--> RPI#2 --[IEC 61850 MMS:102]--> SIPROTEC 7SX85

CRITICAL: Verify SIPROTEC configuration before running:
  - Connect with IEDScout/DIGSI
  - Verify Logical Device name (LD0, LD1, etc.)
  - Verify MMXU Logical Node exists
  - Export ICD file for reference
  - Test manual MMS write

Usage:
  python3 substation_gateway.py

  Or with custom SIPROTEC IP:
  python3 substation_gateway.py --siprotec-ip 192.168.3.250
"""

import asyncio
import logging
import argparse
import signal
import sys

import config
from modbus_server import ModbusGatewayServer
from iec61850_client import IEC61850Client
from protocol_translator import ProtocolTranslator

# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT,
    datefmt=config.LOG_DATE_FORMAT
)
logger = logging.getLogger(__name__)

# =============================================================================
# GLOBAL STATE
# =============================================================================

shutdown_event = asyncio.Event()


def signal_handler(sig, frame):
    """Handle SIGINT (Ctrl+C) and SIGTERM"""
    logger.info(f"Received signal {sig}, initiating shutdown...")
    shutdown_event.set()


# =============================================================================
# MAIN GATEWAY
# =============================================================================

class SubstationGateway:
    """
    Main gateway orchestrator

    Coordinates Modbus server, IEC 61850 client, and protocol translator.
    """

    def __init__(self, siprotec_ip=None):
        self.siprotec_ip = siprotec_ip or config.SIPROTEC_IP
        self.modbus_server = None
        self.iec_client = None
        self.translator = None

    async def start(self):
        """Start all gateway components"""
        logger.info("=" * 80)
        logger.info("RPI#2 - Substation Gateway Starting")
        logger.info("=" * 80)
        logger.info("Architecture:")
        logger.info("  Opta → RPI#2: Ethernet, Modbus TCP (writes data)")
        logger.info("  RPI#2 → SIPROTEC: Ethernet, IEC 61850 MMS (protocol translation)")
        logger.info("")
        logger.info("Configuration:")
        logger.info(f"  Modbus Server: {config.MODBUS_BIND_ADDRESS}:{config.MODBUS_BIND_PORT}")
        logger.info(f"  SIPROTEC IP: {self.siprotec_ip}:{config.SIPROTEC_PORT}")
        logger.info(f"  Logical Device: {config.LOGICAL_DEVICE}")
        logger.info(f"  Update Interval: {config.TRANSLATION_INTERVAL_SEC}s")
        logger.info("=" * 80)

        # Initialize Modbus server
        logger.info("1. Initializing Modbus TCP server...")
        self.modbus_server = ModbusGatewayServer()

        # Initialize IEC 61850 client
        logger.info("2. Initializing IEC 61850 MMS client...")
        self.iec_client = IEC61850Client(host=self.siprotec_ip)

        # Connect to SIPROTEC
        logger.info("3. Connecting to SIPROTEC...")
        try:
            await self.iec_client.connect()
        except Exception as e:
            logger.error(f"Failed to connect to SIPROTEC: {e}")
            logger.error("=" * 80)
            logger.error("TROUBLESHOOTING:")
            logger.error("  1. Verify SIPROTEC IP address is correct")
            logger.error("  2. Check network connectivity: ping " + self.siprotec_ip)
            logger.error("  3. Verify SIPROTEC MMS server is enabled (DIGSI)")
            logger.error("  4. Check firewall allows port 102")
            logger.error("  5. Use IEDScout to test connection manually")
            logger.error("=" * 80)
            raise

        # Initialize protocol translator
        logger.info("4. Initializing protocol translator...")
        self.translator = ProtocolTranslator(self.modbus_server, self.iec_client)

        # Start protocol translator task
        logger.info("5. Starting protocol translator...")
        translator_task = asyncio.create_task(self.translator.run())

        # Start statistics task
        stats_task = asyncio.create_task(self._statistics_task())

        logger.info("=" * 80)
        logger.info("✓ Gateway components initialized")
        logger.info("Starting Modbus TCP server...")
        logger.info("Waiting for:")
        logger.info("  - Opta to write data via Modbus TCP")
        logger.info("  - Protocol translator to send data to SIPROTEC")
        logger.info("=" * 80)

        try:
            # Start Modbus server (this is blocking)
            await asyncio.gather(
                self.modbus_server.start(),
                translator_task,
                stats_task,
                self._shutdown_handler()
            )
        except asyncio.CancelledError:
            logger.info("Gateway tasks cancelled")
        finally:
            await self.shutdown()

    async def _statistics_task(self):
        """Periodically report statistics"""
        while not shutdown_event.is_set():
            await asyncio.sleep(60)

            stats = self.translator.get_statistics()
            logger.info("=" * 80)
            logger.info("[STATISTICS]")
            logger.info(f"  Modbus RX (from Opta): {self.modbus_server.datablock.total_received}")
            logger.info(f"  IEC 61850 TX (to SIPROTEC): {stats['total_updates']}")
            logger.info(f"  Translation Errors: {stats['total_errors']}")
            logger.info(f"  Last Update: {stats['last_update']}")
            logger.info(f"  IEC 61850 Connected: {'Yes' if self.iec_client.connected else 'No'}")
            logger.info("=" * 80)

    async def _shutdown_handler(self):
        """Wait for shutdown signal"""
        await shutdown_event.wait()
        logger.info("Shutdown signal received")

    async def shutdown(self):
        """Shutdown all gateway components"""
        logger.info("=" * 80)
        logger.info("Substation Gateway Shutdown")
        logger.info("=" * 80)

        # Stop protocol translator
        if self.translator:
            await self.translator.stop()

        # Disconnect from SIPROTEC
        if self.iec_client:
            await self.iec_client.disconnect()

        # Print final statistics
        if self.translator and self.modbus_server:
            stats = self.translator.get_statistics()
            logger.info("Final Statistics:")
            logger.info(f"  Total Modbus RX: {self.modbus_server.datablock.total_received}")
            logger.info(f"  Total IEC 61850 TX: {stats['total_updates']}")
            logger.info(f"  Total Errors: {stats['total_errors']}")

        logger.info("=" * 80)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

async def main():
    """Main entry point"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="RPI#2 Substation Gateway (Modbus → IEC 61850 MMS)"
    )
    parser.add_argument(
        "--siprotec-ip",
        type=str,
        help=f"SIPROTEC IP address (default: {config.SIPROTEC_IP})"
    )
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Test IEC 61850 connection and exit"
    )
    args = parser.parse_args()

    # Test connection mode
    if args.test_connection:
        logger.info("Testing IEC 61850 connection to SIPROTEC...")
        client = IEC61850Client(host=args.siprotec_ip)
        try:
            await client.connect()
            logger.info("✓ Connection successful!")

            # Try health check
            healthy = await client.health_check()
            if healthy:
                logger.info("✓ Health check passed")
            else:
                logger.warning("✗ Health check failed")

            await client.disconnect()
            return
        except Exception as e:
            logger.error(f"✗ Connection failed: {e}")
            sys.exit(1)

    # Normal operation mode
    gateway = SubstationGateway(siprotec_ip=args.siprotec_ip)

    try:
        await gateway.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Gateway error: {e}", exc_info=True)


if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
