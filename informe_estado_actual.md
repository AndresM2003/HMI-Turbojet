# Informe de estado actual – HMI Turbojet

**Fecha de actualización:** 14 de noviembre de 2026

## Resumen ejecutivo

La interfaz HMI del turborreactor se encuentra en estado funcional de supervisión en tiempo real sobre telemetría serial proveniente de una ESP32-S3. La aplicación ya no depende de generación interna de datos ficticios para operar; en su estado actual actúa como cliente receptor de solo lectura, valida tramas JSON por línea, muestra alarmas reportadas por el origen externo y mantiene un registro de sesión por conexión.

La lógica de control y la protección del sistema siguen fuera del alcance de la HMI. La interfaz no emite comandos de arranque, parada, apagado, reset ni configuración, y no define umbrales de seguridad; exhibe únicamente la información que recibe del equipo de instrumentación/controlador externo.

## Estructura y componentes actuales

El proyecto actual presenta la siguiente organización funcional:

- `main.py`: punto de entrada de la aplicación.
- `com/serial_reader.py`: lector serial en segundo plano con conexión, lectura de líneas y emisión de señales Qt.
- `core/telemetry_protocol.py`: parser, validación de protocolo y normalización de sensores/alarma.
- `core/data_logger.py`: registro CSV por sesión.
- `ui/main_window.py`: interfaz principal, tabs, banner de alarmas, selector de puerto y actualización en tiempo real.
- `widgets/hmi_visuals.py`: widgets visuales del proceso, medidores de RPM y elementos gráficos del HMI.
- `assets/`: imágenes de la interfaz (bienvenida, secuencia de encendido y pantalla principal).
- `logs/`: registros CSV de sesiones del sistema.
- `tests/test_telemetry_protocol.py`: cobertura de validación del protocolo serial.
- `SERIAL_PROTOCOL.md`: especificación del protocolo de comunicación y del formato de trama.

## Estado funcional actual

### 1. Recepción serial

- Se conecta a un puerto COM configurable desde la interfaz.
- El puerto se puede escanear y seleccionar desde la barra superior.
- La lectura usa `pyserial` y acepta tramas JSON UTF-8 terminadas en `\n`.
- La validación incluye:
  - versionado (`version = 1`)
  - tipo (`type = "telemetry"`)
  - secuencia no negativa
  - sensores requeridos (`t1_c`, `t2_c`, `t3_c`, `t4_c`, `t5_c`, `maf_g_s`, `rpm`, `mq6_1_ppm`, `mq6_2_ppm`)
  - lista de alarmas con `code`, `severity` y `message`
  - `status.estop_released` booleano o nulo
  - rechazo de frames corruptos, vacíos, con valores no finitos o con alarmas inválidas

### 2. Interfaz HMI

- La ventana cuenta con cinco pestañas: `OVERVIEW`, `TEMPERATURES`, `FUEL & SAFETY`, `TRENDS` y `ALARMS`.
- Se muestran temperaturas, caudal de aire, RPM, gases y sensores MQ6.
- La interface presenta un banner de estado global de alarmas.
- El estado de conexión se actualiza en tiempo real y se marca como desactualizado si no llega telemetría en 3 segundos.
- Cuando no existe conexión serial, la aplicación indica claramente la ausencia de telemetría y no genera datos artificiales.

### 3. Registro de datos

- El logger crea un archivo CSV por sesión conectada.
- La salida registra secuencia y variables clave: T1–T5, MAF, RPM y MQ6-1/MQ6-2.
- La sesión queda asociada a la conexión activa y se conserva para análisis posterior.

### 4. Alcance de seguridad y control

- La HMI solo recibe y presenta información.
- No envía comandos a actuadores, ignición, combustible, apagado ni reinicio.
- No reemplaza ni simula las protecciones reales del controlador ni del sistema de seguridad.
- Las alarmas son solo informativas según el payload emitido por la ESP32.

## Validación realizada

Se ejecutó la validación disponible del proyecto con la suite de pruebas unitaria existente:

- comando: `C:\Users\Andres\Documents\Proyecto de grado\interfaz\venv\Scripts\python.exe -m unittest discover -s tests -q`
- resultado: `10 tests OK`

## Archivo ZIP generado

Se exportó el conjunto actual del proyecto en:

`C:\Users\Andres\Documents\Proyecto de grado\interfaz_actual.zip`

Este ZIP contiene los documentos y carpetas actuales del proyecto, incluyendo la estructura principal del repositorio, el código de la HMI, el protocolo, tests, activos y registros.

## Referencias

- [SERIAL_PROTOCOL.md](SERIAL_PROTOCOL.md)
- [main.py](main.py)
- [com/serial_reader.py](com/serial_reader.py)
- [core/telemetry_protocol.py](core/telemetry_protocol.py)
- [ui/main_window.py](ui/main_window.py)
- [tests/test_telemetry_protocol.py](tests/test_telemetry_protocol.py)
