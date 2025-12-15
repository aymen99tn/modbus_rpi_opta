import time
from datetime import datetime
import struct
import pandas as pd
import pvlib.clearsky
from pymodbus.client import ModbusTlsClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadBuilder

# --- 1. Helper function to generate sample PV data using pvlib ---
def get_sample_pv_values():
    """Generates sample PV data (irradiance, temp_amb, power) using pvlib."""
    # Define a location (e.g., somewhere in Fredericton, NB)
    latitude, longitude = 45.9636, -66.6431
    times = pd.to_datetime(datetime.now()).tz_localize('America/Halifax')

    # Get clear sky data
    cs = pvlib.clearsky.ineichen(times, latitude, longitude)

    # Simplified panel temperature and power calculation
    temp_amb = 25.0
    # Simple power estimate (scaled for example)
    power = cs['ghi'].iloc[0] * 0.5 if not pd.isna(cs['ghi'].iloc[0]) else 0.0
    
    # Return as a dictionary of values
    return {
        "timestamp_unix": int(times.timestamp()),
        "irradiance_ghi": int(cs['ghi'].iloc[0]) if not pd.isna(cs['ghi'].iloc[0]) else 0,
        "ambient_temp": int(temp_amb),
        "power_output": int(power)
    }

# --- 2. Modbus TLS Client Configuration and Data Transmission ---
def run_modbus_tls_client():
    # Configure the Modbus TLS client
    # Replace 'localhost' and port with your server's details
    # Update certfile, keyfile, and server_hostname to match your certificate setup
    client = ModbusTlsClient(
        host='localhost',
        port=802, # Default Modbus TLS port is 802
        certfile='./certificates/pymodbus.crt',
        keyfile='./certificates/pymodbus.key',
        # Optional: use ca_certs to verify server certificate if self-signed
        # ca_certs='./certificates/ca.crt',
        server_hostname='localhost',
        framer=None, # Use default TLS framer
        timeout=10
    )

    print("Attempting to connect to Modbus TLS server...")
    if not client.connect():
        print("Failed to connect to the Modbus server. Check certificates, network, and server status.")
        return

    print("Connection established successfully with TLS.")

    try:
        while True:
            # Get sample PV data
            pv_data = get_sample_pv_values()
            
            # Use a BinaryPayloadBuilder to format the data into registers
            # We use Big Endian byte order (common in Modbus)
            builder = BinaryPayloadBuilder(byteorder=Endian.BIG, wordorder=Endian.BIG)

            # Add timestamp (unix time, usually a 32-bit int) and PV values (e.g., 16-bit ints)
            builder.add_32bit_int(pv_data["timestamp_unix"])
            builder.add_16bit_int(pv_data["irradiance_ghi"])
            builder.add_16bit_int(pv_data["ambient_temp"])
            builder.add_16bit_int(pv_data["power_output"])

            # Get the list of registers (words) to write
            payload = builder.build()
            
            # Define the starting address to write to (e.g., 0)
            start_address = 0

            # Write the multiple registers to the server
            response = client.write_multiple_registers(start_address, payload, slave=1)

            if response.isError():
                print(f"Error writing registers: {response}")
            else:
                current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{current_time_str}] Successfully wrote PV data to registers starting at {start_address}. Values: {pv_data}")

            time.sleep(5) # Send data every 5 seconds

    except KeyboardInterrupt:
        print("Client shutdown requested by user.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        client.close()
        print("Connection closed.")

if __name__ == "__main__":
    run_modbus_tls_client()

