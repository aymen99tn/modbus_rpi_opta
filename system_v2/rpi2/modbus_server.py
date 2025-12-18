"""
RPI#2 Modbus TCP Server Component

Receives telemetry from Arduino Opta and triggers protocol translation to IEC 61850.
"""

import asyncio
import logging
from datetime import datetime, timezone

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusDeviceContext,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTcpServer

import config

logger = logging.getLogger(__name__)


class GatewayDataBlock(ModbusSequentialDataBlock):
    """
    Gateway datablock that receives writes from Arduino Opta.

    Triggers callback when new data arrives for protocol translation.
    """

    def __init__(self, address, values):
        super().__init__(address, values)
        self.on_update_callback = None
        self.total_received = 0
        self.last_update = None

    def setValues(self, address, values):
        """
        Called when Opta writes data via Modbus TCP

        Triggers protocol translation callback if registered.
        """
        super().setValues(address, values)

        # Check if write overlaps telemetry block (registers 0-4)
        start = int(address)
        end = start + len(values) - 1

        if end < 0 or start > 4:
            # Outside our telemetry range, ignore
            return

        # Read back the complete 5-register block
        regs = self.getValues(0, 5)

        # Decode for logging
        P_ac = regs[0] * 1.0
        V_dc = regs[1] / 10.0        # Decode: V × 10 → V
        I_dc = regs[2] / 100.0       # Decode: A × 100 → A
        G = regs[3] * 1.0
        timestamp_low = regs[4]

        self.total_received += 1
        self.last_update = datetime.now(timezone.utc)

        logger.info(
            f"[RX FROM OPTA] P_ac={P_ac:.1f}W V_dc={V_dc:.2f}V I_dc={I_dc:.2f}A "
            f"G={G:.1f}W/m² | Total RX: {self.total_received}"
        )

        # Trigger protocol translation callback
        if self.on_update_callback:
            self.on_update_callback(address, values)


class ModbusGatewayServer:
    """
    Modbus TCP server for receiving data from Arduino Opta
    """

    def __init__(self):
        self.datablock = GatewayDataBlock(0, [0] * 100)
        self.context = None
        self.server_task = None

    def set_update_callback(self, callback):
        """Register callback to be called when new data arrives"""
        self.datablock.on_update_callback = callback

    async def start(self):
        """Start the Modbus TCP server"""
        logger.info(f"Starting Modbus TCP server on {config.MODBUS_BIND_ADDRESS}:{config.MODBUS_BIND_PORT}")

        # Create device context
        device = ModbusDeviceContext(hr=self.datablock)

        # Create server context
        self.context = ModbusServerContext(devices={config.MODBUS_UNIT_ID: device}, single=False)

        # Start server (this is a blocking call)
        await StartAsyncTcpServer(
            context=self.context,
            address=(config.MODBUS_BIND_ADDRESS, config.MODBUS_BIND_PORT),
        )

    def get_registers(self, address, count):
        """Read registers from datablock"""
        return self.datablock.getValues(address, count)
