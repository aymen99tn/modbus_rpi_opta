from pyModbusTCP.server import ModbusServer
import time

# --- RPI-2 Configuration (Server/Slave) ---
SERVER_HOST = "0.0.0.0"  # CRITICAL: RPI-2's fixed IP
SERVER_PORT = 502
TEST_POWER_INT = 25552        # Test value: 255.55 kW scaled by 100
TEST_TiME_INT=1234567890   # Test value: Unix time

# 1. Initialize Modbus Server
#    (No need to pass register sizes; v0.3.0 handles this dynamically)
server = ModbusServer(host=SERVER_HOST, port=SERVER_PORT, no_block=True)

# 2. Set the test value using the server's internal data_bank instance
#    This resolves the "missing positional argument" and "AttributeError"
try:
    print(f"Setting initial value {TEST_POWER_INT} to register 40001...")
    server.data_bank.set_holding_registers(0, [TEST_POWER_INT])
    print(f"Setting initial time value {TEST_TiME_INT} to register 40002...")
    server.data_bank.set_holding_registers(1, [TEST_TiME_INT])
except Exception as e:
    print(f"Error setting registers: {e}")

print(f"Modbus TCP Server started on {SERVER_HOST}:{SERVER_PORT}")

try:
    server.start()
    print("Server is listening for Opta reads...")
    
    while True:
        # Optional: Print the current value to confirm it's stored
        current_val = server.data_bank.get_holding_registers(0, 1,2)
        if current_val:
            # print(f"Current Register Value: {current_val[0]}")
            pass
        time.sleep(1)

except KeyboardInterrupt:
    print("Server stopped.")
    server.stop()
