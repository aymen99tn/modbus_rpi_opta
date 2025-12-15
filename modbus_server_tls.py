# -*- coding: utf-8 -*-
import ssl
import asyncio
from datetime import datetime, timezone

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusDeviceContext,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTlsServer


class PrintingHoldingRegisterBlock(ModbusSequentialDataBlock):
    def setValues(self, address, values):
        # Store first
        super().setValues(address, values)

        # Print only if this write overlaps our telemetry block 0..7
        start = int(address)
        end = start + len(values) - 1
        if end < 0 or start > 7:
            return

        # Read back the full block 0..7 (ensures we always decode complete message)
        regs = self.getValues(0, 8)

        # Decode (must match your client scaling/map)
        P_ac   = regs[0] * 1.0
        P_dc   = regs[1] * 1.0
        V_dc   = regs[2] / 10.0
        I_dc   = regs[3] / 100.0
        G      = regs[4] * 1.0
        T_cell = regs[5] / 10.0

        unix_s = ((regs[6] & 0xFFFF) << 16) | (regs[7] & 0xFFFF)
        ts = datetime.fromtimestamp(unix_s, tz=timezone.utc)

        print(
            f"[SERVER RECEIVED] {ts.isoformat()} | "
            f"P_ac={P_ac:.1f}W P_dc={P_dc:.1f}W V_dc={V_dc:.2f}V I_dc={I_dc:.2f}A "
            f"G={G:.1f}W/m2 T_cell={T_cell:.1f}C "
            f"(write addr={start}, count={len(values)})",
            flush=True,
        )


def build_ssl_context(certfile="server.crt", keyfile="server.key"):
    sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sslctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
    sslctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return sslctx


async def main():
    hr_block = PrintingHoldingRegisterBlock(0, [0] * 100)
    device = ModbusDeviceContext(hr=hr_block)
    context = ModbusServerContext(devices={1: device}, single=False)

    sslctx = build_ssl_context()

    print("Modbus TLS server listening on 0.0.0.0:802 (unit-id=1)", flush=True)
    await StartAsyncTlsServer(
        context=context,
        address=("0.0.0.0", 802),
        sslctx=sslctx,
    )


if __name__ == "__main__":
    asyncio.run(main())
