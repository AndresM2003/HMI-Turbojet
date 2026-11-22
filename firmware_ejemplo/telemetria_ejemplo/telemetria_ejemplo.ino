// Ejemplo de referencia del protocolo HMI <-> ESP32 (v1). Ver docs/PROTOCOLO_ESP32.md.
//
// Qué muestra:
//   - Armar y enviar una trama de telemetría JSON por el puerto serial (4 Hz).
//   - Enviar null (nunca NaN) cuando un sensor falla.
//   - Recibir un comando JSON del HMI, validarlo, ejecutarlo y responder con el ACK.
// Qué NO hace: leer los sensores ni mover los actuadores. Reemplaza las funciones marcadas "TODO".
// Los umbrales de alarma son de EJEMPLO: define los reales con el equipo.
//
// Importante: el Serial de este puerto es SOLO para el protocolo. Los mensajes de depuración van
// por otro puerto (Serial1) o se desactivan; el HMI ignora líneas que no empiezan con '{'.

#include <math.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const uint32_t BAUD = 115200;
static const uint32_t SEND_PERIOD_MS = 250;  // 4 Hz: el MAX6675 necesita >= 220 ms entre lecturas
static const int PIN_ESTOP = 4;              // TODO: entrada del botón de emergencia físico

static uint32_t sequenceNumber = 0;
static uint32_t lastSendMs = 0;

// Estado confirmado de los actuadores (lo usa el firmware para sus propios enclavamientos).
// Modo de control: arranca en AUTOMÁTICO (el firmware maneja las salidas solo). El HMI solo puede
// mover bomba, solenoide, servo y bujía mientras el modo sea MANUAL.
static bool manualMode = false;
static bool oilPumpOn = false;
static bool solenoidOpen = false;
static float servoPercent = 0;

// ---------------- lecturas (TODO: reemplazar por las reales; devolver NAN si no es válida) ----------------
float readTemperatureC(int channel) { (void)channel; return NAN; }  // channel 1..5 -> t1_c..t5_c
float readMafGramsPerSecond() { return NAN; }
float readRpm() { return NAN; }
float readMq6Ppm(int sensor) { (void)sensor; return NAN; }          // sensor 1..2

// Estado del E-STOP físico: 1 = liberado, 0 = presionado, -1 = desconocido (se envía null).
int readEstopReleased() { return -1; }  // TODO: p. ej. return digitalRead(PIN_ESTOP) == HIGH ? 1 : 0;

// ---------------- actuadores (TODO: reemplazar por los reales) ----------------
void setOilPump(bool on) { oilPumpOn = on; }
void setSolenoid(bool open) { solenoidOpen = open; }
void setServoPercent(float percent) { servoPercent = percent; }
void pulseSpark() {}
void returnToAutomatic() {}  // TODO: el control automático retoma las salidas
void normalStop() { setSolenoid(false); setServoPercent(0); }                // la bomba sigue hasta enfriar
void emergencyStop() { setSolenoid(false); setServoPercent(0); /* bujía OFF */ }

// ---------------- armado de JSON sin librerías ----------------
struct JsonBuffer {
  char data[640];
  size_t length = 0;
  bool ok = true;

  void add(const char* format, ...) {
    if (!ok) return;
    va_list args;
    va_start(args, format);
    int written = vsnprintf(data + length, sizeof(data) - length, format, args);
    va_end(args);
    if (written < 0 || (size_t)written >= sizeof(data) - length) ok = false;  // no enviar tramas cortadas
    else length += (size_t)written;
  }
  // Un número JSON. NaN/Infinito -> null (printf escribiría "nan", que NO es JSON válido).
  void number(float value, int decimals) {
    if (!isfinite(value)) add("null");
    else add("%.*f", decimals, (double)value);
  }
};

static void sendLine(const JsonBuffer& json) {
  if (!json.ok) return;
  Serial.write((const uint8_t*)json.data, json.length);
  Serial.write('\n');
}

// ---------------- alarmas (EJEMPLO: la ESP32 es quien decide qué alarmas existen) ----------------
struct Alarm { const char* code; const char* severity; const char* message; bool active; };

static void addAlarm(JsonBuffer& json, bool& first, const Alarm& alarm) {
  if (!alarm.active) return;
  json.add("%s{\"code\":\"%s\",\"severity\":\"%s\",\"message\":\"%s\"}", first ? "" : ",",
           alarm.code, alarm.severity, alarm.message);  // sin comillas dentro de los textos
  first = false;
}

void sendTelemetry() {
  const float t1 = readTemperatureC(1), t2 = readTemperatureC(2), t3 = readTemperatureC(3);
  const float t4 = readTemperatureC(4), t5 = readTemperatureC(5);
  const float maf = readMafGramsPerSecond(), rpm = readRpm();
  const float gas1 = readMq6Ppm(1), gas2 = readMq6Ppm(2);
  const int estop = readEstopReleased();

  JsonBuffer json;
  json.add("{\"version\":1,\"type\":\"telemetry\",\"sequence\":%lu,\"sensors\":{", (unsigned long)sequenceNumber++);
  json.add("\"t1_c\":");  json.number(t1, 1);
  json.add(",\"t2_c\":"); json.number(t2, 1);
  json.add(",\"t3_c\":"); json.number(t3, 1);
  json.add(",\"t4_c\":"); json.number(t4, 1);
  json.add(",\"t5_c\":"); json.number(t5, 1);
  json.add(",\"maf_g_s\":"); json.number(maf, 2);
  json.add(",\"rpm\":"); json.number(rpm, 0);
  json.add(",\"mq6_1_ppm\":"); json.number(gas1, 1);
  json.add(",\"mq6_2_ppm\":"); json.number(gas2, 1);
  json.add("},\"alarms\":[");

  bool first = true;
  // Umbrales de EJEMPLO. Un sensor sin lectura (NaN) no activa la alarma de valor; considera una
  // alarma "SENSOR_FAULT" propia si un sensor crítico lleva demasiado tiempo en null.
  addAlarm(json, first, {"T3_HIGH", "warning", "Combustor outlet temperature high", isfinite(t3) && t3 > 700.0f});
  addAlarm(json, first, {"GAS_1_HIGH", "critical", "Gas 1 above limit", isfinite(gas1) && gas1 > 300.0f});
  addAlarm(json, first, {"GAS_2_HIGH", "critical", "Gas 2 above limit", isfinite(gas2) && gas2 > 300.0f});

  json.add("],\"status\":{\"estop_released\":%s}}", estop < 0 ? "null" : (estop ? "true" : "false"));
  sendLine(json);
}

// ---------------- comandos del HMI ----------------
// El HMI siempre manda: {"version":1,"type":"command","id":12,"command":"oil_pump","value":"on"}
// (compacto, sin espacios). Este lector mínimo depende de esa forma; con ArduinoJson es más robusto.
static const char* findKey(const char* line, const char* key) {
  char pattern[40];
  snprintf(pattern, sizeof(pattern), "\"%s\":", key);
  const char* at = strstr(line, pattern);
  return at ? at + strlen(pattern) : nullptr;
}
static bool readLong(const char* line, const char* key, long* out) {
  const char* at = findKey(line, key);
  if (!at) return false;
  char* end;
  *out = strtol(at, &end, 10);
  return end != at;
}
static bool readNumber(const char* line, const char* key, double* out) {
  const char* at = findKey(line, key);
  if (!at) return false;
  char* end;
  *out = strtod(at, &end);
  return end != at;
}
static bool readString(const char* line, const char* key, char* out, size_t capacity) {
  const char* at = findKey(line, key);
  if (!at || *at != '"') return false;
  const char* end = strchr(at + 1, '"');
  if (!end || (size_t)(end - at - 1) >= capacity) return false;
  memcpy(out, at + 1, (size_t)(end - at - 1));
  out[end - at - 1] = '\0';
  return true;
}

static void sendAck(long id, bool ok, const char* message) {
  JsonBuffer json;
  json.add("{\"version\":1,\"type\":\"command_ack\",\"id\":%ld,\"ok\":%s,\"message\":\"%s\"}", id,
           ok ? "true" : "false", message);
  sendLine(json);
}

void handleCommand(const char* line) {
  long id;
  char command[24], text[16];
  if (!readLong(line, "id", &id) || !readString(line, "command", command, sizeof(command))) return;  // no es un comando
  const bool hasText = readString(line, "value", text, sizeof(text));

  // stop, emergency_stop y control_mode se aceptan siempre. El resto solo en modo manual.
  const bool isManualCommand = !strcmp(command, "oil_pump") || !strcmp(command, "fuel_solenoid") ||
                               !strcmp(command, "fuel_servo") || !strcmp(command, "spark_pulse");
  if (isManualCommand && !manualMode) { sendAck(id, false, "automatic mode"); return; }

  if (!strcmp(command, "control_mode") && hasText && (!strcmp(text, "auto") || !strcmp(text, "manual"))) {
    manualMode = !strcmp(text, "manual");
    if (!manualMode) returnToAutomatic();
    sendAck(id, true, "");
  } else if (!strcmp(command, "oil_pump") && hasText && (!strcmp(text, "on") || !strcmp(text, "off"))) {
    setOilPump(!strcmp(text, "on"));
    sendAck(id, true, "");
  } else if (!strcmp(command, "fuel_solenoid") && hasText && (!strcmp(text, "open") || !strcmp(text, "close"))) {
    const bool open = !strcmp(text, "open");
    if (open && !oilPumpOn) { sendAck(id, false, "oil pump is off"); return; }  // enclavamiento propio
    if (open && readEstopReleased() != 1) { sendAck(id, false, "estop not released"); return; }
    setSolenoid(open);
    sendAck(id, true, "");
  } else if (!strcmp(command, "fuel_servo")) {
    double percent;
    if (!readNumber(line, "value", &percent) || percent < 0 || percent > 100) { sendAck(id, false, "value out of range"); return; }
    if (percent > 0 && readEstopReleased() != 1) { sendAck(id, false, "estop not released"); return; }
    setServoPercent((float)percent);
    sendAck(id, true, "");
  } else if (!strcmp(command, "spark_pulse")) {
    if (!oilPumpOn || !solenoidOpen) { sendAck(id, false, "oil pump and solenoid required"); return; }
    if (readEstopReleased() != 1) { sendAck(id, false, "estop not released"); return; }
    pulseSpark();  // la duración del pulso la decide el firmware
    sendAck(id, true, "");
  } else if (!strcmp(command, "stop")) {
    normalStop();
    sendAck(id, true, "");
  } else if (!strcmp(command, "emergency_stop")) {
    emergencyStop();
    sendAck(id, true, "");
  } else {
    sendAck(id, false, "unknown command or bad value");
  }
}

static void pollCommands() {
  static char line[256];
  static size_t length = 0;
  while (Serial.available() > 0) {
    const int c = Serial.read();
    if (c == '\n') {
      line[length] = '\0';
      if (length > 0) handleCommand(line);
      length = 0;
    } else if (c != '\r') {
      if (length < sizeof(line) - 1) line[length++] = (char)c;
      else length = 0;  // línea demasiado larga: descartar
    }
  }
}

void setup() {
  Serial.begin(BAUD);
  pinMode(PIN_ESTOP, INPUT_PULLUP);
}

void loop() {
  pollCommands();
  const uint32_t now = millis();
  if (now - lastSendMs >= SEND_PERIOD_MS) {
    lastSendMs = now;
    sendTelemetry();
  }
}
