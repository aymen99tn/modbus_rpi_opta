#ifndef TLS_CERT_H
#define TLS_CERT_H

/**
 * TLS Certificate for Modbus TLS Connection to RPI#1
 *
 * This certificate is used to establish encrypted communication
 * between ESP32 and RPI#1 over WiFi.
 *
 * Source: system_v1/server.crt
 * Common Name: modbus-server
 * Valid Until: 2026-12-14
 *
 * NOTE: In production, certificates should be validated.
 * For testing, we use skip verification mode on ESP32 client.
 */

// Server certificate (PEM format)
const char* TLS_SERVER_CERT =
"-----BEGIN CERTIFICATE-----\n"
"MIIDETCCAfmgAwIBAgIUIrVHy4hoIbCn09BCNfRak2+QPR4wDQYJKoZIhvcNAQEL\n"
"BQAwGDEWMBQGA1UEAwwNbW9kYnVzLXNlcnZlcjAeFw0yNTEyMTQyMzI3NTBaFw0y\n"
"NjEyMTQyMzI3NTBaMBgxFjAUBgNVBAMMDW1vZGJ1cy1zZXJ2ZXIwggEiMA0GCSqG\n"
"SIb3DQEBAQUAA4IBDwAwggEKAoIBAQC19+DYYJNPD8vWfN8mmG+BxGw5kYtNsOgZ\n"
"w6RKkOIgGrlLJhtCGhzwDzWOYzboRIQD3EXwPa+5TiG8hsva2m2A/5K0xnSZ0Gkn\n"
"eI7IEYjEgw3TzlWTuZnxdhHRK6aOkNNnQz2cA015z5LqkmgaIMsgmShYNgmzlnnZ\n"
"LKQeCVV4+VSk7XH1ffeBC+5ML2KRPHJ2RBw/GOE35NgTKaw9GgKOnPJawjcvj/Kp\n"
"4s3WgJIsw6seJZ3Y3GAvY7kfPytoQ1yvCV8ZnZnZ9zGX0vtl+cLd5f42W2IbZtTn\n"
"q4rFK1QyFavMBuYg8hi5Hm37SCQKQ5QiQbF4LV5Vi1MqHCOeH+2rAgMBAAGjUzBR\n"
"MB0GA1UdDgQWBBTWUYZX+OkM6klxAwl6Xj3sPVc5gjAfBgNVHSMEGDAWgBTWUYZX\n"
"+OkM6klxAwl6Xj3sPVc5gjAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUA\n"
"A4IBAQAPV/rJXmKQawv8CEEAn0HIwmwEI7w8dkAbbC8CxtqVc/8uJI1OZaY/IU5L\n"
"eDZLzeFzybu2YcTsygtYOH9qu5PZl/KVYyjNRe+jmvXlZUejbBQ7eBrNwhZmQ6bZ\n"
"HBy0FqB3uPB2Xou8Rhkutme6JWCr4uVg/RI7S722O/vaPUPFNY1oZIgkFYsRnmaD\n"
"Kvx9Nxh/ar5MCt7/qJLViaDRq131MBRMOuWfhKqY4cQEtrupRRgpAb7DfYttzSiD\n"
"UpCWgKbHmRagmOHkZsSA8U1R7suFjB6ZZWpv7DrDTct4rLeFY7ek8/VUW5R3yQeg\n"
"fmJFS9XBywShm1kKXoYKjESpAheN\n"
"-----END CERTIFICATE-----\n";

#endif // TLS_CERT_H
