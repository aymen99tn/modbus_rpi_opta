"""
RPI#2 IEC 61850 MMS Client Component

Connects to SIPROTEC 7SX85 relay and writes data via MMS protocol.

Before running:
1. Connect to SIPROTEC with IEDScout/DIGSI
2. Verify Logical Device name (LD0, LD1, or custom)
3. Verify MMXU Logical Node exists
4. Export ICD file for reference
5. Test manual MMS write with IEDScout
"""

import logging
import asyncio
from typing import Optional

try:
    import iec61850
    IEC61850_AVAILABLE = True
except ImportError:
    IEC61850_AVAILABLE = False
    logging.warning("pyiec61850 not installed. IEC 61850 functionality disabled.")

import config

logger = logging.getLogger(__name__)


class IEC61850Client:
    """
    IEC 61850 MMS client for communication with SIPROTEC relay

    Uses pyiec61850 library (Python wrapper for libiec61850)
    """

    def __init__(self, host=None, port=None, logical_device=None):
        if not IEC61850_AVAILABLE:
            raise ImportError("pyiec61850 library not installed. Run: pip install pyiec61850")

        self.host = host or config.SIPROTEC_IP
        self.port = port or config.SIPROTEC_PORT
        self.ld = logical_device or config.LOGICAL_DEVICE
        self.connection = None
        self.connected = False

    async def connect(self):
        """
        Establish MMS connection to SIPROTEC

        Raises:
            ConnectionError: If connection fails
        """
        logger.info(f"Connecting to SIPROTEC at {self.host}:{self.port}...")

        try:
            # Create IED connection object
            self.connection = iec61850.IedConnection()

            # Connect to SIPROTEC
            error = self.connection.connect(self.host, self.port)

            if error != iec61850.IedConnectionError.IED_ERROR_OK:
                error_msg = f"IEC 61850 connection failed: {error}"
                logger.error(error_msg)
                raise ConnectionError(error_msg)

            self.connected = True
            logger.info(f"✓ Connected to SIPROTEC at {self.host}:{self.port}")
            logger.info(f"  Logical Device: {self.ld}")

            return True

        except Exception as e:
            logger.error(f"Exception during connection: {e}")
            self.connected = False
            raise

    async def disconnect(self):
        """Close MMS connection"""
        if self.connection and self.connected:
            try:
                self.connection.close()
                logger.info("Disconnected from SIPROTEC")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")
            finally:
                self.connected = False

    async def write_float(self, object_ref: str, value: float) -> bool:
        """
        Write float value to IEC 61850 data object

        Args:
            object_ref: MMS variable name (e.g., "MMXU1$MX$TotW$mag$f")
            value: Float value to write

        Returns:
            True if write succeeded, False otherwise
        """
        if not self.connected:
            logger.error("Not connected to SIPROTEC")
            return False

        try:
            # Construct full MMS variable path
            mms_var = f"{self.ld}/{object_ref}"

            # Create MMS value (FLOAT32)
            mms_value = iec61850.MmsValue_newFloat(value)

            # Write to SIPROTEC
            error = self.connection.writeValue(mms_var, mms_value)

            # Clean up MMS value
            iec61850.MmsValue_delete(mms_value)

            if error != iec61850.IedConnectionError.IED_ERROR_OK:
                logger.error(f"Write failed for {mms_var}: {error}")
                return False

            logger.debug(f"✓ Wrote {value} to {mms_var}")
            return True

        except Exception as e:
            logger.error(f"Exception writing float to {object_ref}: {e}")
            return False

    async def write_timestamp(self, object_ref: str, unix_timestamp: int) -> bool:
        """
        Write timestamp to IEC 61850 data object

        IEC 61850 uses Timestamp64 format (NTP epoch: 1900-01-01)
        Unix timestamp uses Unix epoch (1970-01-01)
        Offset: 2208988800 seconds

        Args:
            object_ref: MMS variable name (e.g., "MMXU1$MX$TotW$t")
            unix_timestamp: Unix timestamp (seconds since 1970-01-01)

        Returns:
            True if write succeeded, False otherwise
        """
        if not self.connected:
            logger.error("Not connected to SIPROTEC")
            return False

        try:
            # Convert Unix → NTP epoch
            NTP_UNIX_OFFSET = 2208988800
            ntp_timestamp = (unix_timestamp + NTP_UNIX_OFFSET) * 1000  # Convert to milliseconds

            # Construct full MMS variable path
            mms_var = f"{self.ld}/{object_ref}"

            # Create MMS timestamp value
            mms_value = iec61850.MmsValue_newUtcTimeByMsTime(ntp_timestamp)

            # Write to SIPROTEC
            error = self.connection.writeValue(mms_var, mms_value)

            # Clean up MMS value
            iec61850.MmsValue_delete(mms_value)

            if error != iec61850.IedConnectionError.IED_ERROR_OK:
                logger.error(f"Write timestamp failed for {mms_var}: {error}")
                return False

            logger.debug(f"✓ Wrote timestamp {unix_timestamp} to {mms_var}")
            return True

        except Exception as e:
            logger.error(f"Exception writing timestamp to {object_ref}: {e}")
            return False

    async def write_quality(self, object_ref: str, quality: int = 0x0000) -> bool:
        """
        Write quality flags to IEC 61850 data object

        Args:
            object_ref: MMS variable name (e.g., "MMXU1$MX$TotW$q")
            quality: Quality flags (0x0000 = GOOD)

        Returns:
            True if write succeeded, False otherwise
        """
        if not self.connected:
            logger.error("Not connected to SIPROTEC")
            return False

        try:
            # Construct full MMS variable path
            mms_var = f"{self.ld}/{object_ref}"

            # Create MMS quality value (bit string)
            mms_value = iec61850.MmsValue_newBitString(quality)

            # Write to SIPROTEC
            error = self.connection.writeValue(mms_var, mms_value)

            # Clean up MMS value
            iec61850.MmsValue_delete(mms_value)

            if error != iec61850.IedConnectionError.IED_ERROR_OK:
                logger.error(f"Write quality failed for {mms_var}: {error}")
                return False

            logger.debug(f"✓ Wrote quality {quality} to {mms_var}")
            return True

        except Exception as e:
            logger.error(f"Exception writing quality to {object_ref}: {e}")
            return False

    async def read_string(self, object_ref: str) -> Optional[str]:
        """
        Read string value from IEC 61850 data object (for verification)

        Args:
            object_ref: MMS variable name

        Returns:
            String value or None if read failed
        """
        if not self.connected:
            logger.error("Not connected to SIPROTEC")
            return None

        try:
            # Construct full MMS variable path
            mms_var = f"{self.ld}/{object_ref}"

            # Read from SIPROTEC
            mms_value = self.connection.readValue(mms_var)

            if not mms_value:
                logger.error(f"Read failed for {mms_var}")
                return None

            # Convert to string
            value_str = iec61850.MmsValue_toString(mms_value)

            # Clean up MMS value
            iec61850.MmsValue_delete(mms_value)

            return value_str

        except Exception as e:
            logger.error(f"Exception reading from {object_ref}: {e}")
            return None

    async def health_check(self) -> bool:
        """
        Verify connection is still alive

        Returns:
            True if connection is healthy, False otherwise
        """
        if not self.connected:
            return False

        try:
            # Try to read a standard data object (adjust based on SIPROTEC model)
            # This is just a connectivity check
            result = await self.read_string("MMXU1$MX$TotW$mag$f")
            return result is not None
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
