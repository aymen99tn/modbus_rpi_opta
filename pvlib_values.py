import pvlib
import pandas as pd
import matplotlib.pyplot as plt

# 1. Define location and system components
# Create a Location object for Tucson, AZ
tucson = pvlib.location.Location(
    latitude=32.2, longitude=-111.0, name='Tucson', altitude=700, tz='Etc/GMT+7'
)

# Retrieve module and inverter specifications from SAM library
sandia_modules = pvlib.pvsystem.retrieve_sam('SandiaMod')
sapm_inverters = pvlib.pvsystem.retrieve_sam('cecinverter')

# Select a specific module and inverter
module = sandia_modules['Canadian_Solar_CS5P_220M___2009_']
inverter = sapm_inverters['ABB__MICRO_0_25_I_OUTD_US_208__208V_']

# Define temperature model parameters
temperature_model_parameters = pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS['sapm']['open_rack_glass_glass']

# Create a PVSystem object
system = pvlib.pvsystem.PVSystem(
    module_parameters=module,
    inverter_parameters=inverter,
    temperature_model_parameters=temperature_model_parameters,
    surface_tilt=30,  # Example fixed tilt
    surface_azimuth=180, # South-facing
)

# 2. Get meteorological data (e.g., TMY data from PVGIS)
# Note: This requires an internet connection to fetch data from PVGIS
weather_data, _ = pvlib.iotools.get_pvgis_tmy(
    latitude=tucson.latitude, longitude=tucson.longitude, map_variables=True
)

# 3. Create and run the ModelChain
mc = pvlib.modelchain.ModelChain(system, tucson)
mc.run_model(weather_data)

# 4. Access and visualize results
# The ModelChain stores results in its results attribute
print("First few rows of DC power output:")
print(mc.results.dc.head())

print("\nFirst few rows of AC power output:")
print(mc.results.ac.head())

# Plot daily AC power output
mc.results.ac.plot(title='Daily AC Power Output')
plt.ylabel('AC Power (W)')
plt.show()
