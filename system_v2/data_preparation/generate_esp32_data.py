"""
Generate pre-processed PV data for ESP32 from weather data and pvlib simulation.

This script:
1. Loads weather data from Excel file
2. Runs pvlib ModelChain to simulate PV system
3. Generates C header file with PV data array for ESP32

Output: pv_data.h containing struct array stored in PROGMEM (Flash memory)
"""

import pandas as pd
import pvlib
from pvlib import location as pvlocation, modelchain, pvsystem
import os

# Configuration
EXCEL_PATH = "../../weather_washingtonDC_2016.xlsx"
OUTPUT_PATH = "output/pv_data.h"

# Encoding functions (same as system_v1)
def u16(x: int) -> int:
    """Clamp value to uint16 range [0, 65535]"""
    return max(0, min(65535, int(x)))

def pack_u32_to_2x_u16(u32: int):
    """Split 32-bit value into high and low 16-bit words"""
    u32 = max(0, min(0xFFFFFFFF, int(u32)))
    hi = (u32 >> 16) & 0xFFFF
    lo = u32 & 0xFFFF
    return hi, lo


def build_weather_df(excel_path: str) -> pd.DataFrame:
    """
    Load and preprocess weather data from Excel file.

    Copied from system_v1/modbus_client_tls.py:31-69
    """
    weather_df = pd.read_excel(excel_path)

    # drop first row and change header
    weather_df = weather_df.drop(0)
    weather_df.columns = weather_df.iloc[0]
    weather_df = weather_df.drop(1)

    # datetime index
    weather_df["datetime"] = pd.to_datetime(weather_df[["Year", "Month", "Day", "Hour", "Minute"]])
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
    cols = ["temp_air", "wind_speed", "humidity", "precipitable_water", "ghi", "dni", "dhi"]
    for c in cols:
        weather_df[c] = weather_df[c].astype(float)

    # keep only relevant columns
    weather_df = weather_df[cols]

    return weather_df


def precompute_pv_timeseries(weather_df: pd.DataFrame) -> pd.DataFrame:
    """
    Run pvlib ModelChain to simulate PV system output.

    Copied from system_v1/modbus_client_tls.py:72-132
    """
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

    # Irradiance G: use GHI from weather file
    G = weather_df["ghi"].reindex(pac.index).fillna(0.0)

    # Cell temperature
    if getattr(mc.results, "cell_temperature", None) is not None:
        tcell = mc.results.cell_temperature.fillna(0.0)
    else:
        # fallback if not produced
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


def generate_c_header(series: pd.DataFrame, output_path: str):
    """
    Generate C header file with PV data array for ESP32.

    Format:
    - struct PVSample with 7 fields (P_ac, P_dc, V_dc, I_dc, G, T_cell, timestamp)
    - const array stored in PROGMEM (Flash memory)
    - Register encoding applied (V_dc×10, I_dc×100, T_cell×10)
    """
    print(f"Generating C header file: {output_path}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w') as f:
        # Header guard
        f.write("#ifndef PV_DATA_H\n")
        f.write("#define PV_DATA_H\n\n")

        # Includes
        f.write("#include <Arduino.h>\n\n")

        # Documentation
        f.write("/**\n")
        f.write(" * Pre-processed PV simulation data for ESP32 solar inverter simulator\n")
        f.write(" * \n")
        f.write(" * Generated from weather_washingtonDC_2016.xlsx using pvlib ModelChain\n")
        f.write(" * Location: Washington DC (38.9072°N, -77.0369°W)\n")
        f.write(" * Module: Znshine_PV_Tech_ZXP6_72_295_P\n")
        f.write(" * Inverter: ABB MICRO_0_3_I_OUTD_US_208\n")
        f.write(" * Surface tilt: 35°, azimuth: 180° (south-facing)\n")
        f.write(" * \n")
        f.write(" * Data is stored in PROGMEM (Flash) to save RAM\n")
        f.write(" * Total samples: {} (hourly for one year)\n".format(len(series)))
        f.write(" * Memory usage: ~{} KB\n".format(len(series) * 14 // 1024))
        f.write(" */\n\n")

        # Struct definition
        f.write("struct PVSample {\n")
        f.write("    uint16_t P_ac;      // AC Power (W)\n")
        f.write("    uint16_t P_dc;      // DC Power (W)\n")
        f.write("    uint16_t V_dc;      // DC Voltage (V × 10)\n")
        f.write("    uint16_t I_dc;      // DC Current (A × 100)\n")
        f.write("    uint16_t G;         // Irradiance (W/m²)\n")
        f.write("    uint16_t T_cell;    // Cell Temperature (°C × 10)\n")
        f.write("    uint32_t timestamp; // Unix seconds\n")
        f.write("};\n\n")

        # Array size constant
        f.write(f"const uint16_t PV_DATA_COUNT = {len(series)};\n\n")

        # Array declaration with PROGMEM
        f.write("const PVSample PV_DATA[] PROGMEM = {\n")

        # Generate array entries
        for idx, row in series.iterrows():
            unix_s = int(idx.timestamp())

            # Encode registers (same as system_v1)
            P_ac = u16(round(row['P_ac']))
            P_dc = u16(round(row['P_dc']))
            V_dc = u16(round(row['V_dc'] * 10))  # V × 10
            I_dc = u16(round(row['I_dc'] * 100))  # A × 100
            G = u16(round(row['G']))
            T_cell = u16(round(row['T_cell'] * 10))  # °C × 10

            # Write struct initializer
            f.write(f"    {{{P_ac}, {P_dc}, {V_dc}, {I_dc}, {G}, {T_cell}, {unix_s}UL}},\n")

        # Close array
        f.write("};\n\n")

        # End header guard
        f.write("#endif // PV_DATA_H\n")

    print(f"✓ Generated {len(series)} samples")
    print(f"✓ File size: ~{len(series) * 14} bytes ({len(series) * 14 // 1024} KB)")
    print(f"✓ Output: {output_path}")


def main():
    print("=" * 80)
    print("ESP32 PV Data Generator")
    print("=" * 80)

    # Check if weather file exists
    if not os.path.exists(EXCEL_PATH):
        print(f"ERROR: Weather file not found: {EXCEL_PATH}")
        print("Please ensure weather_washingtonDC_2016.xlsx is in the project root")
        return

    print(f"\n1. Loading weather file: {EXCEL_PATH}")
    weather_df = build_weather_df(EXCEL_PATH)
    print(f"   ✓ Loaded {len(weather_df)} hourly weather records")

    print(f"\n2. Running pvlib ModelChain (this may take a minute)...")
    series = precompute_pv_timeseries(weather_df)
    print(f"   ✓ Generated {len(series)} PV samples")

    # Print sample statistics
    print(f"\n3. PV System Statistics:")
    print(f"   P_ac:   {series['P_ac'].min():.1f} - {series['P_ac'].max():.1f} W (mean: {series['P_ac'].mean():.1f} W)")
    print(f"   P_dc:   {series['P_dc'].min():.1f} - {series['P_dc'].max():.1f} W (mean: {series['P_dc'].mean():.1f} W)")
    print(f"   V_dc:   {series['V_dc'].min():.2f} - {series['V_dc'].max():.2f} V (mean: {series['V_dc'].mean():.2f} V)")
    print(f"   I_dc:   {series['I_dc'].min():.2f} - {series['I_dc'].max():.2f} A (mean: {series['I_dc'].mean():.2f} A)")
    print(f"   G:      {series['G'].min():.1f} - {series['G'].max():.1f} W/m² (mean: {series['G'].mean():.1f} W/m²)")
    print(f"   T_cell: {series['T_cell'].min():.1f} - {series['T_cell'].max():.1f} °C (mean: {series['T_cell'].mean():.1f} °C)")

    print(f"\n4. Generating C header file...")
    generate_c_header(series, OUTPUT_PATH)

    print(f"\n5. Next Steps:")
    print(f"   - Copy {OUTPUT_PATH} to system_v2/esp32/include/pv_data.h")
    print(f"   - Use in ESP32 firmware: #include \"pv_data.h\"")
    print(f"   - Access samples: memcpy_P(&sample, &PV_DATA[index], sizeof(PVSample))")

    print("\n" + "=" * 80)
    print("✓ ESP32 PV Data Generation Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()
