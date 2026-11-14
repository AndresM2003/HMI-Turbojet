# ESP32-S3 serial telemetry protocol

The HMI connects as a serial **receiver**. It sends no bytes to the ESP32 and
does not issue actuator, ignition, shutdown, reset, or acknowledgement commands.
Safety decisions and actuator control remain outside the HMI.

## Link settings

- Default baud rate: `115200` (selectable in the HMI)
- Frame encoding: UTF-8 JSON, one object per line, terminated by `\n`
- Maximum frame size: 4096 bytes, including the line terminator
- Serial settings: 8 data bits, no parity, 1 stop bit

The HMI marks telemetry stale after three seconds without a valid frame. This is
a display-quality indicator only; it is not a safety response.

## Telemetry frame, version 1

Every frame must contain `version`, `type`, `sequence`, `sensors`, and `alarms`.
`sequence` is a non-negative integer that the ESP32 increments for each frame
and does not wrap while connected. The HMI ignores duplicate sequence numbers
for freshness and logging, and reports gaps or a counter restart.
All listed sensor keys are required; a value may be `null` when the measurement
is unavailable or invalid.

```json
{
  "version": 1,
  "type": "telemetry",
  "sequence": 42,
  "sensors": {
    "t1_c": 148.0,
    "t2_c": 146.0,
    "t3_c": 748.0,
    "t4_c": 731.0,
    "t5_c": 74.0,
    "maf_g_s": 18.4,
    "rpm": 32450.0,
    "mq6_1_ppm": 12.0,
    "mq6_2_ppm": 8.0
  },
  "alarms": [
    {
      "code": "GAS_1_HIGH",
      "severity": "warning",
      "message": "Gas sensor 1 above configured limit"
    }
  ],
  "status": {
    "estop_released": true
  }
}
```

Sensor units are encoded in each key: temperatures in °C, MAF in g/s, RPM in
revolutions per minute, and MQ6 readings in ppm. `alarms` is the current alarm
set on every frame; use an empty list when there are no active alarms. `status`
is optional. Each alarm has a stable `code`, a `severity` (`info`, `warning`, or
`critical`), and a display `message`. The HMI displays alarm states reported by
the ESP32; it does not calculate alarm thresholds. `status.estop_released` is
`true`, `false`, or `null` if unknown.

Frames with invalid JSON, unsupported versions, missing required sensor keys,
invalid field types, non-finite numeric values, or malformed alarms are ignored
and reported in the HMI connection status. The HMI never sends an acknowledgement
or a response frame.
