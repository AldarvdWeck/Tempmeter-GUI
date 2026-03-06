#include <OneWire.h>
#include <DallasTemperature.h>

#define ONE_WIRE_BUS 2

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

DeviceAddress addr;

void printAddress(DeviceAddress deviceAddress) {
  for (uint8_t i = 0; i < 8; i++) {
    if (deviceAddress[i] < 16) Serial.print("0");
    Serial.print(deviceAddress[i], HEX);
    if (i < 7) Serial.print(":");
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("Zoeken naar DS18B20 sensoren...");

  sensors.begin();

  int deviceCount = sensors.getDeviceCount();
  Serial.print("Aantal sensoren gevonden: ");
  Serial.println(deviceCount);

  for (int i = 0; i < deviceCount; i++) {
    if (sensors.getAddress(addr, i)) {
      Serial.print("Sensor ");
      Serial.print(i + 1);
      Serial.print(" adres: ");
      printAddress(addr);
      Serial.println();
    } else {
      Serial.print("Sensor ");
      Serial.print(i + 1);
      Serial.println(" adres niet gevonden");
    }
  }
}

// Aantal sensoren gevonden: 4
// Sensor 1 adres: 28:F0:EA:57:04:E1:3C:67
// Sensor 2 adres: 28:7E:AE:57:04:E1:3C:68
// Sensor 3 adres: 28:65:2C:57:04:E1:3C:83
// Sensor 4 adres: 28:BD:20:57:04:E1:3C:C7

void loop() {
}