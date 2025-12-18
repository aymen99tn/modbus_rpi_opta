import math
import pandas as pd
import time
from datetime import datetime
import struct
import pvlib.clearsky
from pvlib import location, modelchain, pvsystem
from pvlib.temperature import TEMPERATURE_MODEL_PARAMETERS


def gen_values():
    cec_modules = pvlib.pvsystem.retrieve_sam("cecmod")
    sapm_inverters = pvlib.pvsystem.retrieve_sam("cecinverter")
    module = cec_modules["Znshine_PV_Tech_ZXP6_72_295_P"]
    inverter = sapm_inverters["ABB__MICRO_0_3_I_OUTD_US_208__208V_"]
    temperature_model_parameters = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS[
        "sapm"
    ]["open_rack_glass_glass"]

    # Create a Location and a PV System
    location = pvlib.location.Location(
        latitude=38.9072,
        longitude=-77.0369,
        name="Washington DC",
        altitude=0,
        tz='US/Eastern',
    )

    system = pvlib.pvsystem.PVSystem(
        surface_tilt=35,
        surface_azimuth=180,
        module_parameters=module,
        inverter_parameters=inverter,
        temperature_model_parameters=temperature_model_parameters,
    )

    weather_df = pd.read_excel('weather_washingtonDC_2016.xlsx')	

    #drop the first row and change the header
    weather_df = weather_df.drop(0)
    weather_df.columns = weather_df.iloc[0]
    weather_df = weather_df.drop(1)

    # create new datetime column using the columns year, month, day, hour, minute
    weather_df['datetime'] = pd.to_datetime(weather_df[['Year', 'Month', 'Day', 'Hour', 'Minute']])
    weather_df.set_index('datetime', inplace=True)
    weather_df.index = pd.to_datetime(weather_df.index)

    # resample to hourly
    weather_df = weather_df.resample('h').mean()

    # rename columns to use the pvlib nomenclature
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

    # convert values to float
    weather_df['temp_air'] = weather_df['temp_air'].astype(float)
    weather_df['wind_speed'] = weather_df['wind_speed'].astype(float)
    weather_df['humidity'] = weather_df['humidity'].astype(float)
    weather_df['precipitable_water'] = weather_df['precipitable_water'].astype(float)
    weather_df['ghi'] = weather_df['ghi'].astype(float)
    weather_df['dni'] = weather_df['dni'].astype(float)
    weather_df['dhi'] = weather_df['dhi'].astype(float)

    # select only relevant columns
    weather_df = weather_df[['temp_air', 'wind_speed', 'humidity', 'precipitable_water', 'ghi', 'dni', 'dhi', ]]

    # resample to hourly
    weather_df = weather_df.resample('h').mean()
    weather_df.head()

    # Create and run PV Model

    mc = modelchain.ModelChain(system, location, aoi_model="physical")
    mc.run_model(weather=weather_df)
    module_energy = mc.results.ac.fillna(0)
    print(mc)

    # Print the generated modelchain arrays
    print(mc.results)
    print()

    # Print summary statistics for DC power
    print("\nDC Power Summary (W):")
    print(mc.results.dc.describe())

if __name__ == "__main__":
    gen_values()
