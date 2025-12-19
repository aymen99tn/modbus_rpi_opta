from pyModbusTCP.server import ModbusServer
import time

# Create an instance of the ModbusServer
# Listen on all interfaces (0.0.0.0) on standard Modbus port 502
# Note: Running on ports <= 1024 may require administrator/root privileges.
# You can use a higher port like 8000 if needed (e.g., host='0.0.0.0', port=8000).
server = ModbusServer("127.0.0.1", 802)

print("Starting server...")

try:
    # Start the server
    server.start()
    print("Server is running.")
    
    # Keep the main thread alive while the server thread is running
    while server.is_alive():
        # You can add logic here to update data bank values if needed
        # Example: server.data_bank.set_holding_registers(0, [100])
        time.sleep(100)

except KeyboardInterrupt:
    print("Server stopped by user.")
    server.stop()

except Exception as e:
    print(f"An error occurred: {e}")
    server.stop()

