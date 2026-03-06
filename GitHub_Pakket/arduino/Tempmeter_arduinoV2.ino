#include <OneWire.h>
#include <DallasTemperature.h>
#include <LiquidCrystal.h>

#define ONE_WIRE_BUS 2
#define MAX_SENSORS 4

LiquidCrystal lcd(8, 9, 4, 5, 6, 7);
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature ds(&oneWire);

// Vaste sensor adressen
DeviceAddress addr[MAX_SENSORS] = {
  {0x28, 0xF0, 0xEA, 0x57, 0x04, 0xE1, 0x3C, 0x67}, // Sensor 1
  {0x28, 0x7E, 0xAE, 0x57, 0x04, 0xE1, 0x3C, 0x68}, // Sensor 2
  {0x28, 0x65, 0x2C, 0x57, 0x04, 0xE1, 0x3C, 0x83}, // Sensor 3
  {0x28, 0xBD, 0x20, 0x57, 0x04, 0xE1, 0x3C, 0xC7}  // Sensor 4
};

int n = MAX_SENSORS;

// Alleen bovengrenscorrectie: Tcorr = gain * Traw
const float gain[MAX_SENSORS] = {
  0.99305, // Sensor 1
  0.99900, // Sensor 2
  0.99206, // Sensor 3
  0.99900  // Sensor 4
};

float correctTemp(uint8_t idx, float tRaw) {
  if (tRaw == DEVICE_DISCONNECTED_C || tRaw < -100 || tRaw > 150) {
    return DEVICE_DISCONNECTED_C;
  }
  return tRaw * gain[idx];
}

void setup() {
  Serial.begin(115200);

  lcd.begin(16, 2);
  lcd.clear();
  lcd.print("Init sensors...");

  ds.begin();
  ds.setResolution(12);

  lcd.clear();
  lcd.print("Sensors: ");
  lcd.print(n);
  delay(800);
  lcd.clear();
}

static void printTempCell(uint8_t col, uint8_t row, uint8_t idx, float t) {
  lcd.setCursor(col, row);
  lcd.print(idx + 1);
  lcd.print(":");

  if (t == DEVICE_DISCONNECTED_C || t < -100 || t > 150) {
    lcd.print("--.-");
    return;
  }

  char buf[8];
  dtostrf(t, 4, 1, buf);
  lcd.print(buf);
}

void loop() {
  ds.requestTemperatures();

  float t[MAX_SENSORS];

  for (int i = 0; i < MAX_SENSORS; i++) {
    float raw = ds.getTempC(addr[i]);
    t[i] = correctTemp(i, raw);
  }

  // LCD: 1&2 boven, 3&4 onder
  printTempCell(0, 0, 0, t[0]);
  lcd.setCursor(6, 0); lcd.print(" ");
  printTempCell(8, 0, 1, t[1]);

  printTempCell(0, 1, 2, t[2]);
  lcd.setCursor(6, 1); lcd.print(" ");
  printTempCell(8, 1, 3, t[3]);

  // Serial: T,<t1>,<t2>,<t3>,<t4>
  Serial.print("T,");
  for (int i = 0; i < MAX_SENSORS; i++) {
    if (t[i] == DEVICE_DISCONNECTED_C) Serial.print("NaN");
    else Serial.print(t[i], 2);

    if (i < MAX_SENSORS - 1) Serial.print(",");
  }
  Serial.println();

  delay(200);
}