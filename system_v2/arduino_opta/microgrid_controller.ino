/**
 * Arduino Opta - Microgrid Controller (Dual Modbus Client)
 *
 * Acts as a Modbus TCP client that:
 * 1. Reads 8 registers from RPI#1 (Smart Meter)
 * 2. Processes and selects subset of data
 * 3. Writes 5 registers to RPI#2 (Substation Gateway)
 *
 * Architecture:
 *   RPI#1 <--[Ethernet, Modbus TCP Read:502]-- Opta --[Ethernet, Modbus TCP Write:502]--> RPI#2
 *
 * Challenge: Opta must maintain TWO simultaneous Modbus TCP client connections
 *
 * Register Mapping:
 *   FROM RPI#1 (8 registers):
 *     0: P_ac, 1: P_dc, 2: V_dc (scaled×10), 3: I_dc (scaled×100),
 *     4: G, 5: T_cell (scaled×10), 6: Timestamp_high, 7: Timestamp_low
 *
 *   TO RPI#2 (5 registers - subset):
 *     0: P_ac, 1: V_dc (scaled), 2: I_dc (scaled), 3: G, 4: Timestamp_low
 *
 * Why subset? Focus on critical measurements for SIPROTEC relay
 */

#include <Ethernet.h>
#include <ArduinoModbus.h>

// =============================================================================
// CONFIGURATION
// =============================================================================

// Network Configuration
byte mac[] = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED };
IPAddress ip(192, 168, 2, 150);       // Opta static IP
IPAddress gateway(192, 168, 2, 1);
IPAddress subnet(255, 255, 255, 0);

// RPI#1 Configuration (Smart Meter)
IPAddress rpi1_ip(192, 168, 2, 100);
const int RPI1_PORT = 502;
const int RPI1_UNIT_ID = 1;

// RPI#2 Configuration (Substation Gateway)
IPAddress rpi2_ip(192, 168, 2, 200);
const int RPI2_PORT = 502;
const int RPI2_UNIT_ID = 1;

// Timing Configuration
const unsigned long POLL_INTERVAL_MS = 1000;  // Poll every 1 second

// =============================================================================
// GLOBAL VARIABLES
// =============================================================================

// Ethernet clients for two Modbus connections
EthernetClient ethClient1;
EthernetClient ethClient2;

// Modbus TCP clients
ModbusTCPClient modbusRPI1(ethClient1);
ModbusTCPClient modbusRPI2(ethClient2);

// Data storage
uint16_t registers_rpi1[8];  // 8 registers from RPI#1
uint16_t registers_rpi2[5];  // 5 registers to RPI#2

// Connection status
bool rpi1_connected = false;
bool rpi2_connected = false;

// Statistics
unsigned long totalReads = 0;
unsigned long totalWrites = 0;
unsigned long totalErrors = 0;
unsigned long lastStatsTime = 0;

// =============================================================================
// SETUP FUNCTION
// =============================================================================

void setup() {
  // Initialize serial communication
  Serial.begin(115200);
  while (!Serial && millis() < 5000) {
    ; // Wait for serial port (max 5 seconds)
  }

  Serial.println("================================================================================");
  Serial.println("Arduino Opta - Microgrid Controller (Dual Modbus Client)");
  Serial.println("================================================================================");

  // Initialize Ethernet
  Serial.println("Initializing Ethernet...");
  Ethernet.begin(mac, ip, gateway, gateway, subnet);

  // Give Ethernet time to initialize
  delay(1000);

  Serial.print("  Opta IP: ");
  Serial.println(Ethernet.localIP());
  Serial.print("  Gateway: ");
  Serial.println(Ethernet.gatewayIP());
  Serial.print("  Subnet: ");
  Serial.println(Ethernet.subnetMask());

  // Print connection targets
  Serial.println("\nModbus Configuration:");
  Serial.print("  RPI#1 (Read from):  ");
  Serial.print(rpi1_ip);
  Serial.print(":");
  Serial.println(RPI1_PORT);

  Serial.print("  RPI#2 (Write to):   ");
  Serial.print(rpi2_ip);
  Serial.print(":");
  Serial.println(RPI2_PORT);

  Serial.print("\n  Poll interval: ");
  Serial.print(POLL_INTERVAL_MS / 1000);
  Serial.println(" seconds");

  Serial.println("================================================================================");
  Serial.println("Starting dual Modbus client operation...");
  Serial.println("================================================================================\n");

  lastStatsTime = millis();
}

// =============================================================================
// MAIN LOOP
// =============================================================================

void loop() {
  // Maintain Ethernet link
  Ethernet.maintain();

  // 1. READ from RPI#1
  if (readFromRPI1()) {
    totalReads++;

    // 2. PROCESS data
    prepareDataForRPI2();

    // 3. WRITE to RPI#2
    if (writeToRPI2()) {
      totalWrites++;
    } else {
      totalErrors++;
    }
  } else {
    totalErrors++;
  }

  // Print statistics every 60 seconds
  if (millis() - lastStatsTime >= 60000) {
    printStatistics();
    lastStatsTime = millis();
  }

  // Wait before next poll
  delay(POLL_INTERVAL_MS);
}

// =============================================================================
// MODBUS FUNCTIONS
// =============================================================================

/**
 * Read 8 registers from RPI#1 (Smart Meter)
 */
bool readFromRPI1() {
  // Connect if not connected
  if (!rpi1_connected) {
    Serial.print("Connecting to RPI#1... ");
    if (!modbusRPI1.begin(rpi1_ip, RPI1_PORT)) {
      Serial.println("FAILED");
      return false;
    }
    rpi1_connected = true;
    Serial.println("OK");
  }

  // Read 8 holding registers starting at address 0
  if (!modbusRPI1.requestFrom(RPI1_UNIT_ID, HOLDING_REGISTERS, 0, 8)) {
    Serial.print("✗ Read from RPI#1 failed: ");
    Serial.println(modbusRPI1.lastError());
    rpi1_connected = false;
    return false;
  }

  // Store registers
  for (int i = 0; i < 8; i++) {
    registers_rpi1[i] = modbusRPI1.read();
  }

  // Decode and print (for debugging)
  float P_ac = registers_rpi1[0] * 1.0;
  float P_dc = registers_rpi1[1] * 1.0;
  float V_dc = registers_rpi1[2] / 10.0;
  float I_dc = registers_rpi1[3] / 100.0;
  float G = registers_rpi1[4] * 1.0;
  float T_cell = registers_rpi1[5] / 10.0;
  uint32_t timestamp = ((uint32_t)registers_rpi1[6] << 16) | registers_rpi1[7];

  Serial.println("----------------------------------------");
  Serial.println("[READ FROM RPI#1]");
  Serial.print("  P_ac:   "); Serial.print(P_ac, 1); Serial.println(" W");
  Serial.print("  P_dc:   "); Serial.print(P_dc, 1); Serial.println(" W");
  Serial.print("  V_dc:   "); Serial.print(V_dc, 2); Serial.println(" V");
  Serial.print("  I_dc:   "); Serial.print(I_dc, 2); Serial.println(" A");
  Serial.print("  G:      "); Serial.print(G, 1); Serial.println(" W/m²");
  Serial.print("  T_cell: "); Serial.print(T_cell, 1); Serial.println(" °C");
  Serial.print("  Time:   "); Serial.println(timestamp);

  return true;
}

/**
 * Prepare data for RPI#2 (select subset of registers)
 */
void prepareDataForRPI2() {
  // Select critical measurements for SIPROTEC
  registers_rpi2[0] = registers_rpi1[0];  // P_ac
  registers_rpi2[1] = registers_rpi1[2];  // V_dc (keep scaled)
  registers_rpi2[2] = registers_rpi1[3];  // I_dc (keep scaled)
  registers_rpi2[3] = registers_rpi1[4];  // G
  registers_rpi2[4] = registers_rpi1[7];  // Timestamp_low

  Serial.println("[PROCESSED DATA FOR RPI#2]");
  Serial.println("  Selected 5 registers (P_ac, V_dc, I_dc, G, Timestamp_low)");
}

/**
 * Write 5 registers to RPI#2 (Substation Gateway)
 */
bool writeToRPI2() {
  // Connect if not connected
  if (!rpi2_connected) {
    Serial.print("Connecting to RPI#2... ");
    if (!modbusRPI2.begin(rpi2_ip, RPI2_PORT)) {
      Serial.println("FAILED");
      return false;
    }
    rpi2_connected = true;
    Serial.println("OK");
  }

  // Write 5 holding registers starting at address 0
  modbusRPI2.beginTransmission(RPI2_UNIT_ID, HOLDING_REGISTERS, 0, 5);

  for (int i = 0; i < 5; i++) {
    modbusRPI2.write(registers_rpi2[i]);
  }

  if (!modbusRPI2.endTransmission()) {
    Serial.print("✗ Write to RPI#2 failed: ");
    Serial.println(modbusRPI2.lastError());
    rpi2_connected = false;
    return false;
  }

  Serial.println("[WRITE TO RPI#2]");
  Serial.print("  ✓ Sent 5 registers (");
  for (int i = 0; i < 5; i++) {
    Serial.print(registers_rpi2[i]);
    if (i < 4) Serial.print(", ");
  }
  Serial.println(")");

  return true;
}

/**
 * Print statistics summary
 */
void printStatistics() {
  Serial.println("\n========================================");
  Serial.println("STATISTICS (Last 60 seconds)");
  Serial.println("========================================");
  Serial.print("  Total Reads (from RPI#1):  ");
  Serial.println(totalReads);
  Serial.print("  Total Writes (to RPI#2):   ");
  Serial.println(totalWrites);
  Serial.print("  Total Errors:              ");
  Serial.println(totalErrors);

  if (totalReads > 0) {
    float successRate = (float)totalWrites / totalReads * 100.0;
    Serial.print("  Success Rate:              ");
    Serial.print(successRate, 1);
    Serial.println("%");
  }

  Serial.println("========================================\n");
}
