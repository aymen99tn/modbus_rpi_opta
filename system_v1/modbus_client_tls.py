import time
import ssl
import pandas as pd
import pvlib
from pvlib import location as pvlocation, modelchain, pvsystem
from pymodbus.client import ModbusTlsClient
from pymodbus.exceptions import ModbusException


<<<<<<< HEAD:system_v1/modbus_client_tls.py
SERVER_IP = "10.9.64.175"   
PORT = 802 
UNIT_ID = 255

SEND_PERIOD_SEC = 10
EXCEL_PATH = "weather_washingtonDC_2016.xlsx"  
=======
SERVER_IP = "172.17.148.129"
PORT = 802
UNIT_ID = 1

SEND_PERIOD_SEC = 10
EXCEL_PATH = "weather_washingtonDC_2016.xlsx"  

def u16(x: int) -> int:
    return max(0, min(65535, int(x)))


def pack_u32_to_2x_u16(u32: int):
    u32 = max(0, min(0xFFFFFFFF, int(u32)))
    hi = (u32 >> 16) & 0xFFFF
    lo = u32 & 0xFFFF
    return hi, lo


# ----------------------------
# PVLIB PIPELINE
# ----------------------------
def build_weather_df(excel_path: str) -> pd.DataFrame:
    weather_df = pd.read_excel(excel_path)

    # drop first row and change header
    weather_df = weather_df.drop(0)
    weather_df.columns = weather_df.iloc[0]
    weather_df = weather_df.drop(1)

    # datetime index
    weather_df["datetime"] = pd.to_datetime(
        weather_df[["Year", "Month", "Day", "Hour", "Minute"]])
    weather_df.set_index("datetime", inplace=True)
    weather_df.index = pd.to_datetime(weather_df.index)

    # resample to hourly mean
    weather_df = weather_df.resample("h").mean()

    # rename columns for pvlib nomenclature
    weather_df = weather_df.rename(
        {
            "Temperature": "temp_air",
            "Wind Speed": "wind_speed",
            "Relative Humidity": "humidity",
            "Precipitable Water": "precipitable_water",
            "GHI": "ghi",
            "DNI": "dni",
            "DHI": "dhi",
        },
        axis=1,
    )

    # convert to float
    cols = ["temp_air", "wind_speed", "humidity",
            "precipitable_water", "ghi", "dni", "dhi"]
    for c in cols:
        weather_df[c] = weather_df[c].astype(float)

    # keep only relevant columns
    weather_df = weather_df[cols]

    return weather_df


def precompute_pv_timeseries(weather_df: pd.DataFrame) -> pd.DataFrame:
    cec_modules = pvlib.pvsystem.retrieve_sam("cecmod")
    cec_inverters = pvlib.pvsystem.retrieve_sam("cecinverter")
    module = cec_modules["Znshine_PV_Tech_ZXP6_72_295_P"]
    inverter = cec_inverters["ABB__MICRO_0_3_I_OUTD_US_208__208V_"]

    temp_params = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_glass"]

    loc = pvlocation.Location(
        latitude=38.9072,
        longitude=-77.0369,
        name="Washington DC",
        altitude=0,
        tz="US/Eastern",
    )

    system = pvsystem.PVSystem(
        surface_tilt=35,
        surface_azimuth=180,
        module_parameters=module,
        inverter_parameters=inverter,
        temperature_model_parameters=temp_params,
    )

    mc = modelchain.ModelChain(system, loc, aoi_model="physical")

    # Run once on the full dataframe
    mc.run_model(weather=weather_df)

    # AC power
    pac = mc.results.ac.fillna(0.0)

    # DC metrics (MPP)
    dc = mc.results.dc.fillna(0.0)
    pdc = dc["p_mp"]
    vdc = dc["v_mp"]
    idc = dc["i_mp"]

    # Irradiance G: use GHI from weather file (your dataset)
    G = weather_df["ghi"].reindex(pac.index).fillna(0.0)

    # Cell temperature (if available)
    if getattr(mc.results, "cell_temperature", None) is not None:
        tcell = mc.results.cell_temperature.fillna(0.0)
    else:
        # fallback if not produced for some reason
        tcell = pd.Series(0.0, index=pac.index)

    out = pd.DataFrame(
        {
            "P_ac": pac.astype(float),
            "P_dc": pdc.astype(float),
            "V_dc": vdc.astype(float),
            "I_dc": idc.astype(float),
            "G": G.astype(float),
            "T_cell": tcell.astype(float),
        },
        index=pac.index,
    )

    return out


def main():
    print("Loading weather file...")
    weather_df = build_weather_df(EXCEL_PATH)

    print("Running pvlib ModelChain (one-time precompute)...")
    series = precompute_pv_timeseries(weather_df)

    print(f"Generated {len(series)} timesteps. Starting Modbus TLS client...")

#    output_filename = 'pvlib_simulation_results.csv'
#    series.to_csv(output_filename, index=True, index_label='Timestamp')

#    print(f"Successfully wrote simulation results to {output_filename}")

    sslctx = ssl.create_default_context()
    sslctx.check_hostname = False
    sslctx.verify_mode = ssl.CERT_NONE 

    client = ModbusTlsClient(host=SERVER_IP, port=PORT, sslctx=sslctx)

    if not client.connect():
        raise ConnectionError("Failed to connect to Modbus TLS server")

    print("Connected to Modbus TLS server")

    # Register map (holding regs starting at 0):
    # 0 P_ac (W)
    # 1 P_dc (W)
    # 2 V_dc (V*10)
    # 3 I_dc (A*100)
    # 4 G (W/m^2)
    # 5 T_cell (C*10)
    # 6 ts_hi (unix seconds high 16 bits)
    # 7 ts_lo (unix seconds low 16 bits)

    try:
        i = 0
        while True:
            row = series.iloc[i]
            ts = series.index[i]  # pandas Timestamp with tz
            unix_s = int(ts.timestamp())

            regs = [0] * 8
            regs[0] = u16(round(row["P_ac"]))
            regs[1] = u16(round(row["P_dc"]))
            regs[2] = u16(round(row["V_dc"] * 10))
            regs[3] = u16(round(row["I_dc"] * 100))
            regs[4] = u16(round(row["G"]))
            regs[5] = u16(round(row["T_cell"] * 10))
            regs[6], regs[7] = pack_u32_to_2x_u16(unix_s)

            print(
                f"{ts} | Pac={row['P_ac']:.1f}W Pdc={row['P_dc']:.1f}W "
                f"Vdc={row['V_dc']:.2f}V Idc={row['I_dc']:.2f}A "
                f"G={row['G']:.1f}W/m2 Tcell={row['T_cell']:.1f}C"
            )

            try:
                wr = client.write_registers(
                    address=0, values=regs, device_id=UNIT_ID)
                if wr.isError():
                    print("Modbus write error:", wr)
                else:
                    print("Sent registers:", regs)
            except ModbusException as e:
                print("Modbus exception:", e)

            # advance timestep
            i = (i + 1) % len(series)

            time.sleep(SEND_PERIOD_SEC)

    except KeyboardInterrupt:
        print("Stopping...")

    finally:
        client.close()
        print("Connection closed")


if __name__ == "__main__":
    main()
