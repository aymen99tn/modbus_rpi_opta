"""
RPI#2 Protocol Translator

Maps Modbus registers to IEC 61850 MMS data objects and handles periodic updates.

Translation: Modbus TCP (from Opta) → IEC 61850 MMS (to SIPROTEC)
"""

import asyncio
import logging
from datetime import datetime, timezone

import config

logger = logging.getLogger(__name__)


class ProtocolTranslator:
    """
    Protocol translator that reads Modbus registers and writes to IEC 61850

    Runs as periodic async task, updating SIPROTEC at configured interval.
    """

    def __init__(self, modbus_server, iec_client):
        self.modbus = modbus_server
        self.iec = iec_client
        self.update_interval = config.TRANSLATION_INTERVAL_SEC
        self.running = False
        self.total_updates = 0
        self.total_errors = 0
        self.last_update = None

    async def run(self):
        """
        Main translation loop

        Periodically reads Modbus registers and writes to IEC 61850.
        Runs until stopped.
        """
        logger.info(f"Protocol translator starting (update interval: {self.update_interval}s)")
        self.running = True

        while self.running:
            try:
                await self.translate_and_send()
            except asyncio.CancelledError:
                logger.info("Protocol translator cancelled")
                break
            except Exception as e:
                logger.error(f"Translation error: {e}", exc_info=True)
                self.total_errors += 1

            await asyncio.sleep(self.update_interval)

        logger.info("Protocol translator stopped")

    async def translate_and_send(self):
        """
        Read Modbus registers, decode, and write to IEC 61850

        Register Map (from Opta):
          0: P_ac (W)
          1: V_dc (V×10, scaled)
          2: I_dc (A×100, scaled)
          3: G (W/m²)
          4: Timestamp_low

        IEC 61850 Mapping (to SIPROTEC):
          P_ac   → MMXU1$MX$TotW$mag$f           (Total Active Power)
          V_dc   → MMXU1$MX$PhV$phsA$cVal$mag$f  (Phase A Voltage)
          I_dc   → MMXU1$MX$A$phsA$cVal$mag$f    (Phase A Current)
          (Quality flags set to GOOD: 0x0000)
        """
        if not self.iec.connected:
            logger.warning("IEC 61850 client not connected, skipping update")
            return

        # Read 5 registers from Modbus datablock
        regs = self.modbus.get_registers(0, 5)

        # Decode scaling factors
        P_ac = float(regs[0])            # W (no scaling)
        V_dc = float(regs[1]) / 10.0     # Decode: V × 10 → V
        I_dc = float(regs[2]) / 100.0    # Decode: A × 100 → A
        G = float(regs[3])               # W/m² (no scaling)
        timestamp_low = regs[4]          # 16-bit timestamp (partial)

        # Validate data ranges (sanity check)
        if not self._validate_data(P_ac, V_dc, I_dc, G):
            logger.warning("Data validation failed, skipping update")
            self.total_errors += 1
            return

        # Write to IEC 61850 (using MMS variable names from config)
        success = True

        # Write P_ac (Active Power)
        success &= await self.iec.write_float(
            config.IEC61850_MAPPING["P_ac"],
            P_ac
        )

        # Write V_dc (DC Voltage)
        success &= await self.iec.write_float(
            config.IEC61850_MAPPING["V_dc"],
            V_dc
        )

        # Write I_dc (DC Current)
        success &= await self.iec.write_float(
            config.IEC61850_MAPPING["I_dc"],
            I_dc
        )

        # Optionally write irradiance G (if SIPROTEC supports custom data object)
        # success &= await self.iec.write_float(
        #     config.IEC61850_MAPPING["G"],
        #     G
        # )

        if success:
            self.total_updates += 1
            self.last_update = datetime.now(timezone.utc)

            logger.info(
                f"[IEC 61850 UPDATE] P_ac={P_ac:.1f}W V_dc={V_dc:.2f}V I_dc={I_dc:.2f}A | "
                f"Total updates: {self.total_updates}"
            )
        else:
            self.total_errors += 1
            logger.error(f"IEC 61850 write failed | Total errors: {self.total_errors}")

    def _validate_data(self, P_ac, V_dc, I_dc, G):
        """
        Validate data ranges for sanity checking

        Args:
            P_ac: AC Power (W)
            V_dc: DC Voltage (V)
            I_dc: DC Current (A)
            G: Irradiance (W/m²)

        Returns:
            True if data is valid, False otherwise
        """
        # Define reasonable ranges for PV system
        if P_ac < 0 or P_ac > 10000:  # 0 - 10 kW
            logger.warning(f"P_ac out of range: {P_ac}W")
            return False

        if V_dc < 0 or V_dc > 100:  # 0 - 100V
            logger.warning(f"V_dc out of range: {V_dc}V")
            return False

        if I_dc < 0 or I_dc > 50:  # 0 - 50A
            logger.warning(f"I_dc out of range: {I_dc}A")
            return False

        if G < 0 or G > 1500:  # 0 - 1500 W/m²
            logger.warning(f"G out of range: {G}W/m²")
            return False

        return True

    async def stop(self):
        """Stop the translation loop"""
        logger.info("Stopping protocol translator...")
        self.running = False

    def get_statistics(self):
        """
        Get translator statistics

        Returns:
            dict with statistics
        """
        return {
            "total_updates": self.total_updates,
            "total_errors": self.total_errors,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "update_interval": self.update_interval
        }
