// Arduino Opta WiFi/TLS Modbus client (WPA2-PSK + self-signed TLS helper)

// =============================================================================
// CONNECTION MODE
// =============================================================================
// Uncomment one of these:
// #define USE_PLAIN_TCP
#define USE_TLS

// =============================================================================

#include <WiFi.h>
#include <ArduinoModbus.h>
#include <cstring>
#include <utility>
#include <type_traits>

// =============================================================================
// CONFIGURATION - MODIFY THESE VALUES
// =============================================================================

// WiFi (WPA2-PSK)
const char* WIFI_SSID = "aymen99tn";
const char* WIFI_PASSWORD = "ca1920ca";

// Modbus target
const char* SERVER_IP = "10.21.66.129";

#ifdef USE_PLAIN_TCP
  const int SERVER_PORT = 502;
#else
  const int SERVER_PORT = 802;
#endif

const int UNIT_ID = 255;

const int REGISTER_START = 0;
const int REGISTER_COUNT = 8;

const unsigned long POLL_INTERVAL = 5000;
const unsigned long MONITOR_INTERVAL = 5000;
const unsigned long RECONNECT_DELAY = 10000;
const unsigned long WIFI_CONNECT_TIMEOUT = 30000;

// =============================================================================
// GLOBAL VARIABLES
// =============================================================================

// Network clients
#ifdef USE_PLAIN_TCP
  WiFiClient client;
  ModbusTCPClient modbusClient(client);
#else
  #include <WiFiSSLClient.h>
  static const char SERVER_CA[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDETCCAfmgAwIBAgIUIrVHy4hoIbCn09BCNfRak2+QPR4wDQYJKoZIhvcNAQEL
BQAwGDEWMBQGA1UEAwwNbW9kYnVzLXNlcnZlcjAeFw0yNTEyMTQyMzI3NTBaFw0y
NjEyMTQyMzI3NTBaMBgxFjAUBgNVBAMMDW1vZGJ1cy1zZXJ2ZXIwggEiMA0GCSqG
SIb3DQEBAQUAA4IBDwAwggEKAoIBAQC19+DYYJNPD8vWfN8mmG+BxGw5kYtNsOgZ
w6RKkOIgGrlLJhtCGhzwDzWOYzboRIQD3EXwPa+5TiG8hsva2m2A/5K0xnSZ0Gkn
eI7IEYjEgw3TzlWTuZnxdhHRK6aOkNNnQz2cA015z5LqkmgaIMsgmShYNgmzlnnZ
LKQeCVV4+VSk7XH1ffeBC+5ML2KRPHJ2RBw/GOE35NgTKaw9GgKOnPJawjcvj/Kp
4s3WgJIsw6seJZ3Y3GAvY7kfPytoQ1yvCV8ZnZnZ9zGX0vtl+cLd5f42W2IbZtTn
q4rFK1QyFavMBuYg8hi5Hm37SCQKQ5QiQbF4LV5Vi1MqHCOeH+2rAgMBAAGjUzBR
MB0GA1UdDgQWBBTWUYZX+OkM6klxAwl6Xj3sPVc5gjAfBgNVHSMEGDAWgBTWUYZX
+OkM6klxAwl6Xj3sPVc5gjAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUA
A4IBAQAPV/rJXmKQawv8CEEAn0HIwmwEI7w8dkAbbC8CxtqVc/8uJI1OZaY/IU5L
eDZLzeFzybu2YcTsygtYOH9qu5PZl/KVYyjNRe+jmvXlZUejbBQ7eBrNwhZmQ6bZ
HBy0FqB3uPB2Xou8Rhkutme6JWCr4uVg/RI7S722O/vaPUPFNY1oZIgkFYsRnmaD
Kvx9Nxh/ar5MCt7/qJLViaDRq131MBRMOuWfhKqY4cQEtrupRRgpAb7DfYttzSiD
UpCWgKbHmRagmOHkZsSA8U1R7suFjB6ZZWpv7DrDTct4rLeFY7ek8/VUW5R3yQeg
fmJFS9XBywShm1kKXoYKjESpAheN
-----END CERTIFICATE-----
)EOF";
  WiFiSSLClient sslClient;
  ModbusTCPClient modbusClient(sslClient);
#endif

// Timing variables
unsigned long lastPollTime = 0;
unsigned long lastMonitorTime = 0;
unsigned long lastReconnectAttempt = 0;

// Connection state tracking
enum ConnectionState {
  STATE_WIFI_DISCONNECTED,
  STATE_WIFI_CONNECTED,
  STATE_TLS_DISCONNECTED,
  STATE_TLS_CONNECTED,
  STATE_MODBUS_READY
};

ConnectionState currentState = STATE_WIFI_DISCONNECTED;

// Data storage
uint16_t registers[REGISTER_COUNT];
bool dataValid = false;

// =============================================================================
// SETUP
// =============================================================================

void setup() {
  // Initialize Serial for monitoring
  Serial.begin(9600);
  while (!Serial && millis() < 3000) {
    ; // Wait up to 3 seconds for serial port to connect
  }

  printHeader();

  connectWiFi();

  #ifndef USE_PLAIN_TCP
    configureTLS();
  #endif

  Serial.println("========================================");
  Serial.println("System Ready");
  Serial.println("========================================");
  Serial.println();
}

// =============================================================================
// MAIN LOOP
// =============================================================================

void loop() {
  unsigned long currentTime = millis();

  // State machine for connection management
  updateConnectionState();

  // Only poll for data when fully connected
  if (currentState == STATE_MODBUS_READY) {
    // Poll for new data at configured interval
    if (currentTime - lastPollTime >= POLL_INTERVAL) {
      lastPollTime = currentTime;
      readRegisters();
    }

    // Display telemetry at configured interval
    if (dataValid && (currentTime - lastMonitorTime >= MONITOR_INTERVAL)) {
      lastMonitorTime = currentTime;
      displayTelemetry();
    }
  }

  // Small delay to prevent tight loop
  delay(100);
}

// =============================================================================
// WIFI CONNECTION FUNCTIONS
// =============================================================================

void connectWiFi() {
  Serial.println("========================================");
  Serial.println("WiFi Connection");
  Serial.println("========================================");

  #ifdef WL_NO_MODULE
    if (WiFi.status() == WL_NO_MODULE) {
      Serial.println("WiFi module not detected.");
      currentState = STATE_WIFI_DISCONNECTED;
      return;
    }
  #elif defined(WL_NO_SHIELD)
    if (WiFi.status() == WL_NO_SHIELD) {
      Serial.println("WiFi shield not detected.");
      currentState = STATE_WIFI_DISCONNECTED;
      return;
    }
  #endif

  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startTime = millis();
  int dots = 0;
  while (WiFi.status() != WL_CONNECTED && (millis() - startTime) < WIFI_CONNECT_TIMEOUT) {
    delay(500);
    Serial.print(".");
    dots++;
    if (dots >= 60) {
      Serial.println();
      dots = 0;
    }
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("WiFi Connected!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("Signal Strength (RSSI): ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
    currentState = STATE_WIFI_CONNECTED;
  } else {
    Serial.println();
    Serial.println("ERROR: WiFi connection failed!");
    currentState = STATE_WIFI_DISCONNECTED;
  }
}

void reconnectWiFi() {
  Serial.println("Attempting WiFi reconnection...");
  WiFi.disconnect();
  delay(1000);
  connectWiFi();
}

// =============================================================================
// TLS CONFIGURATION FUNCTIONS
// =============================================================================

#ifndef USE_PLAIN_TCP
template <typename T>
struct HasSetCaLen {
  template <typename U>
  static auto test(int) -> decltype(std::declval<U>().setCACert((const char*)nullptr, (size_t)0), std::true_type());
  template <typename>
  static std::false_type test(...);
  static const bool value = std::is_same<decltype(test<T>(0)), std::true_type>::value;
};

template <typename T>
struct HasSetCaPtr {
  template <typename U>
  static auto test(int) -> decltype(std::declval<U>().setCACert((const char*)nullptr), std::true_type());
  template <typename>
  static std::false_type test(...);
  static const bool value = std::is_same<decltype(test<T>(0)), std::true_type>::value;
};

template <bool hasPtr>
struct LoadCaPtr {
  template <typename Client>
  static bool load(Client&, const char*) { return false; }
};

template <>
struct LoadCaPtr<true> {
  template <typename Client>
  static bool load(Client& c, const char* ca) { c.setCACert(ca); return true; }
};

template <bool hasLen>
struct LoadCaLen {
  template <typename Client>
  static bool load(Client&, const char*, size_t) { return false; }
};

template <>
struct LoadCaLen<true> {
  template <typename Client>
  static bool load(Client& c, const char* ca, size_t len) { c.setCACert(ca, len); return true; }
};

template <>
struct LoadCaLen<false> {
  template <typename Client>
  static bool load(Client& c, const char* ca, size_t) { return LoadCaPtr<HasSetCaPtr<Client>::value>::load(c, ca); }
};

template <typename Client>
bool loadCaCert(Client& c, const char* ca, size_t len) {
  return LoadCaLen<HasSetCaLen<Client>::value>::load(c, ca, len);
}

void configureTLS() {
  Serial.println("========================================");
  Serial.println("TLS Configuration");
  Serial.println("========================================");

  const size_t ca_len = strlen(SERVER_CA);
  const bool caLoaded = loadCaCert(sslClient, SERVER_CA, ca_len);
  sslClient.setTimeout(15000);

  if (caLoaded) {
    Serial.println("TLS trust anchor loaded (server.crt)");
    Serial.println("Certificate verification: ENABLED");
  } else {
    Serial.println("TLS library missing setCACert; using defaults (verification may fail)");
  }
  Serial.println();
}
#endif

// =============================================================================
// MODBUS CONNECTION FUNCTIONS
// =============================================================================

bool connectModbus() {
  Serial.println("========================================");
  #ifdef USE_PLAIN_TCP
    Serial.println("Modbus TCP Connection");
  #else
    Serial.println("Modbus+TLS Connection");
  #endif
  Serial.println("========================================");
  Serial.print("Connecting to: ");
  Serial.print(SERVER_IP);
  Serial.print(":");
  Serial.println(SERVER_PORT);
  Serial.print("Unit ID: ");
  Serial.println(UNIT_ID);

  if (!modbusClient.begin(SERVER_IP, SERVER_PORT)) {
    #ifdef USE_PLAIN_TCP
      Serial.println("ERROR: Failed to connect to Modbus TCP server");
    #else
      Serial.println("ERROR: Failed to connect to Modbus+TLS server");
    #endif
    return false;
  }

  #ifdef USE_PLAIN_TCP
    Serial.println("Connected to Modbus TCP server!");
  #else
    Serial.println("Connected to Modbus+TLS server!");
  #endif
  Serial.println();
  return true;
}

// =============================================================================
// MODBUS READ FUNCTIONS
// =============================================================================

void readRegisters() {
  if (!modbusClient.requestFrom(UNIT_ID, HOLDING_REGISTERS, REGISTER_START, REGISTER_COUNT)) {
    Serial.print("ERROR: Failed to read registers! Error code: ");
    Serial.println(modbusClient.lastError());
    dataValid = false;
    return;
  }

  for (int i = 0; i < REGISTER_COUNT; i++) {
    registers[i] = modbusClient.read();
  }

  dataValid = true;
}

// =============================================================================
// TELEMETRY DISPLAY FUNCTION
// =============================================================================

void displayTelemetry() {
  if (!dataValid) {
    Serial.println("No valid data to display");
    return;
  }

  float P_ac = (float)registers[0];           // W (no scaling)
  float P_dc = (float)registers[1];           // W (no scaling)
  float V_dc = (float)registers[2] / 10.0;    // V (divide by 10)
  float I_dc = (float)registers[3] / 100.0;   // A (divide by 100)
  float G = (float)registers[4];              // W/m² (no scaling)
  float T_cell = (float)registers[5] / 10.0;  // °C (divide by 10)

  uint32_t unix_timestamp = ((uint32_t)registers[6] << 16) | registers[7];

  Serial.println("========================================");
  #ifdef USE_PLAIN_TCP
    Serial.println("=== PV TELEMETRY DATA (WiFi TCP) ===");
  #else
    Serial.println("=== PV TELEMETRY DATA (WiFi+TLS) ===");
  #endif
  Serial.println("========================================");

  Serial.print("Timestamp (Unix): ");
  Serial.println(unix_timestamp);

  Serial.print("P_ac (AC Power):  ");
  Serial.print(P_ac, 1);
  Serial.println(" W");

  Serial.print("P_dc (DC Power):  ");
  Serial.print(P_dc, 1);
  Serial.println(" W");

  Serial.print("V_dc (DC Voltage): ");
  Serial.print(V_dc, 2);
  Serial.println(" V");

  Serial.print("I_dc (DC Current): ");
  Serial.print(I_dc, 2);
  Serial.println(" A");

  Serial.print("G (Irradiance):   ");
  Serial.print(G, 1);
  Serial.println(" W/m²");

  Serial.print("T_cell (Temp):    ");
  Serial.print(T_cell, 1);
  Serial.println(" °C");

  Serial.println("========================================");
  Serial.println();
}

// =============================================================================
// CONNECTION STATE MANAGEMENT
// =============================================================================

void updateConnectionState() {
  unsigned long currentTime = millis();

  switch (currentState) {
    case STATE_WIFI_DISCONNECTED:
      // Check if enough time has passed since last reconnection attempt
      if (currentTime - lastReconnectAttempt >= RECONNECT_DELAY) {
        lastReconnectAttempt = currentTime;
        reconnectWiFi();
      }
      break;

    case STATE_WIFI_CONNECTED:
      // WiFi connected, now try to establish Modbus+TLS connection
      if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi connection lost!");
        currentState = STATE_WIFI_DISCONNECTED;
      } else {
        currentState = STATE_TLS_DISCONNECTED;
      }
      break;

    case STATE_TLS_DISCONNECTED:
      // Check WiFi still connected
      if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi connection lost!");
        currentState = STATE_WIFI_DISCONNECTED;
        break;
      }

      // Attempt Modbus+TLS connection
      if (currentTime - lastReconnectAttempt >= RECONNECT_DELAY) {
        lastReconnectAttempt = currentTime;
        if (connectModbus()) {
          currentState = STATE_TLS_CONNECTED;
        }
      }
      break;

    case STATE_TLS_CONNECTED:
      // TLS connected, move to ready state
      currentState = STATE_MODBUS_READY;
      break;

    case STATE_MODBUS_READY:
      // Monitor connections
      if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi connection lost!");
        currentState = STATE_WIFI_DISCONNECTED;
        modbusClient.stop();
      }
      #ifdef USE_PLAIN_TCP
        else if (!client.connected()) {
          Serial.println("Modbus TCP connection lost!");
          currentState = STATE_TLS_DISCONNECTED;
          modbusClient.stop();
        }
      #else
        else if (!sslClient.connected()) {
          Serial.println("TLS connection lost!");
          currentState = STATE_TLS_DISCONNECTED;
          modbusClient.stop();
        }
      #endif
      break;
  }
}

// =============================================================================
// UTILITY FUNCTIONS
// =============================================================================

void printHeader() {
  Serial.println();
  Serial.println("========================================");
  Serial.println("Arduino Opta WiFi Modbus Client");
  Serial.println("PV Telemetry Receiver");
  Serial.println("========================================");
  Serial.println("Configuration:");
  Serial.print("  WiFi SSID: ");
  Serial.println(WIFI_SSID);
  Serial.print("  Server IP: ");
  Serial.println(SERVER_IP);
  Serial.print("  Server Port: ");
  Serial.println(SERVER_PORT);
  #ifdef USE_PLAIN_TCP
    Serial.println("  Connection Mode: Plain TCP (no encryption)");
  #else
    Serial.println("  Connection Mode: TLS (encrypted)");
  #endif
  Serial.print("  Unit ID: ");
  Serial.println(UNIT_ID);
  Serial.print("  Poll Interval: ");
  Serial.print(POLL_INTERVAL / 1000);
  Serial.println(" seconds");
  Serial.println("========================================");
  Serial.println();
}
