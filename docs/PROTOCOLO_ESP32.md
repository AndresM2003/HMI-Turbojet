# Protocolo de comunicación ESP32 ⇄ HMI (versión 1)

Este documento dice **cómo debe mandar los datos la ESP32** para que el HMI los reciba, y cómo
responder a los comandos del HMI. Todo lo que aquí se afirma lo valida el código del HMI
(`core/telemetry_protocol.py`, `core/commands.py`) y se puede comprobar sin abrir el HMI con
`tools/check_esp32.py` (sección 6).

## 0. Lo mínimo (resumen)

1. Puerto serial, **115200 baud, 8N1**, sin control de flujo.
2. Cada mensaje es **un objeto JSON en una sola línea**, terminada en `\n` (`\r\n` también sirve).
3. La ESP32 manda una **trama de telemetría cada 250 ms (4 Hz)**, siempre, aunque falle un sensor.
4. Un sensor sin lectura válida se manda como **`null`**. Nunca `NaN`, `nan`, `inf` ni un `0` inventado.
5. Las **alarmas las decide la ESP32** y las manda en la lista `alarms` (vacía `[]` si no hay).
6. Cada **comando** del HMI se responde con un **ACK** (`ok: true/false`). Sin ACK el HMI no da el comando por ejecutado.
   El firmware arranca en **modo automático**: solo acepta mover bomba, solenoide, servo y bujía si el HMI pasó antes a **modo manual** (sección 4.3).
7. Por ese puerto **no se manda nada más** (logs de depuración van por otro puerto).

## 1. Conexión serial

| Parámetro | Valor |
|---|---|
| Velocidad | 115200 baud (el HMI ofrece 115200, 57600, 38400, 19200, 9600; lo importante es que coincidan) |
| Formato | 8 bits de datos, sin paridad, 1 bit de parada (8N1) |
| Control de flujo | Ninguno |
| Codificación | UTF-8 (en la práctica, solo ASCII) |

- **El puerto serial es solo para el protocolo.** Si el firmware imprime texto de depuración por el mismo puerto
  (mensajes de arranque, `Serial.println("debug")`), el HMI **ignora** las líneas que no empiezan con `{`, pero
  una línea que empieza con `{` y no es una trama válida se cuenta como error. Mejor: depuración por `Serial1`.
- **Abrir el puerto no debe reiniciar la ESP32.** Muchas placas con puente USB-serial se reinician cuando el
  PC abre el puerto (líneas DTR/RTS). El HMI abre el puerto con DTR y RTS en bajo para evitarlo, pero
  **compruébalo en tu placa**: conecta el HMI con la ESP32 en marcha y mira que `sequence` **no vuelva a 0**.
  Si se reinicia, una solución de hardware conocida es un condensador de ~10 µF entre `EN` y `GND`
  (quítalo para programar la placa).
- **ESP32-S3 con USB nativo (CDC):** verifica que `Serial.write` **no bloquee el lazo de control** cuando el HMI
  no está conectado (en el core de Arduino existe `Serial.setTxTimeoutMs(...)`; confirma en tu versión).
  La seguridad del motor no puede depender de que el HMI esté conectado.

## 2. Formato de las tramas

- Una trama = **un objeto JSON** en **una sola línea**, sin saltos de línea dentro, terminada en `\n`.
- Tamaño máximo: **4096 bytes** por trama (la trama normal ocupa unos 350). Una línea de más de 4096 bytes sin `\n`
  hace que el HMI **cierre la conexión**.
- Los números son números JSON: punto decimal (no coma), sin separador de miles, sin `+` inicial.
- Los campos que el HMI no conoce se **ignoran** (se pueden agregar campos nuevos sin romper nada).
- Tramas de telemetría y ACK pueden alternarse en el mismo puerto; cada una va en su propia línea.
- **Una sola tarea escribe en el puerto** (o protege la escritura con un mutex): si dos tareas de FreeRTOS imprimen
  a la vez, las líneas se mezclan y las dos tramas se pierden.

## 3. Telemetría (ESP32 → HMI)

### 3.1 Ejemplo completo

<!-- test:valid-telemetry -->
```json
{"version":1,"type":"telemetry","sequence":1042,"sensors":{"t1_c":148.2,"t2_c":146.0,"t3_c":748.3,"t4_c":731.5,"t5_c":74.0,"maf_g_s":18.42,"rpm":32450,"mq6_1_ppm":12.0,"mq6_2_ppm":9.5},"alarms":[{"code":"T3_HIGH","severity":"warning","message":"Combustor outlet temperature high"}],"status":{"estop_released":true}}
```

Mismo mensaje, con un sensor que falla (T3 sin lectura) y sin alarmas:

<!-- test:valid-telemetry -->
```json
{"version":1,"type":"telemetry","sequence":1043,"sensors":{"t1_c":148.3,"t2_c":146.1,"t3_c":null,"t4_c":731.0,"t5_c":74.0,"maf_g_s":18.40,"rpm":32440,"mq6_1_ppm":12.0,"mq6_2_ppm":9.5},"alarms":[],"status":{"estop_released":true}}
```

### 3.2 Campos de primer nivel

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `version` | entero | sí | Siempre `1`. Debe ser entero (`1`, no `1.0`). |
| `type` | texto | sí | Siempre `"telemetry"`. |
| `sequence` | entero ≥ 0 | sí | Contador que **sube de 1 en 1** con cada trama enviada. Entero, sin punto decimal. |
| `sensors` | objeto | sí | Las 9 claves de la tabla 3.3, **todas presentes** (usa `null` si no hay dato). |
| `alarms` | lista | sí | Lista de alarmas activas; `[]` si no hay ninguna. Debe existir siempre. |
| `status` | objeto | no | Ver 3.6. Si falta, el HMI toma el E-STOP como desconocido. |

Si falta un campo obligatorio, o alguno tiene tipo incorrecto, **se rechaza la trama completa** (el HMI muestra el
error y sigue esperando la siguiente).

### 3.3 `sensors` (las 9 claves son obligatorias)

| Clave | Qué es | Unidad | Observación |
|---|---|---|---|
| `t1_c` | T1 — salida del compresor | °C | Termocupla + MAX6675 |
| `t2_c` | T2 — entrada de la cámara de combustión | °C | |
| `t3_c` | T3 — salida de la cámara de combustión | °C | |
| `t4_c` | T4 — entrada a la turbina | °C | |
| `t5_c` | T5 — quinta termocupla (aceite, por confirmar) | °C | |
| `maf_g_s` | Flujo másico de aire (MAF) | g/s | Ya convertido a g/s por el firmware |
| `rpm` | Velocidad del turbo | rpm | La fuente del RPM está por definir |
| `mq6_1_ppm` | Sensor de gas MQ6 n.º 1 | ppm | Valor referencial (el MQ6 no está calibrado) |
| `mq6_2_ppm` | Sensor de gas MQ6 n.º 2 | ppm | |

El HMI **no convierte unidades**: la ESP32 manda los valores ya en las unidades de la tabla.
Los decimales son libres; con 1 decimal en temperaturas y 2 en MAF sobra.

### 3.4 Valores no disponibles → `null`

Cuando un sensor no tiene una lectura válida, la ESP32 manda **`null`** en esa clave:

- Termocupla desconectada (el MAX6675 lo indica con el bit D2 de su lectura), lectura fuera de rango, error de SPI.
- Sensor aún sin calentar (MQ6), RPM sin pulsos, etc.

**Nunca** mandar `NaN`, `nan`, `inf`, `-1`, `999` ni `0` para indicar un fallo: `NaN` e `inf` **no son JSON válido** y
la trama completa se rechaza (con `printf("%f", NAN)` sale `nan`); un `0` falso se confunde con una medición real y
el HMI lo dibujaría y lo registraría como dato bueno. Con `null` el HMI muestra «—», deja un hueco en la gráfica y
las verificaciones de arranque no lo dan por válido.

### 3.5 `alarms`

Cada elemento de la lista es un objeto con tres textos **no vacíos**:

| Campo | Regla |
|---|---|
| `code` | Identificador estable, en mayúsculas, p. ej. `GAS_1_HIGH`. **Único** dentro de la trama (un código repetido rechaza la trama). |
| `severity` | `"info"`, `"warning"` o `"critical"`. |
| `message` | Texto corto para el operador, ASCII, **sin comillas ni barras invertidas**. |

Reglas de comportamiento:

- La ESP32 es la **autoridad de las alarmas**: en operación el HMI no las recalcula, solo muestra lo que llega.
  (Solo las listas de verificación de arranque y apagado comparan valores contra `core/limits.py`, y únicamente si el
  equipo configura esos umbrales.)
- Una alarma **está en la lista mientras la condición esté activa** y desaparece de la lista cuando se despeja.
  El HMI detecta los cambios por `code` y los registra en el historial como ACTIVE / CLEARED.
- Mantén el `code` constante. Si cambia `severity` o `message` del mismo `code`, el HMI lo registra como una nueva activación.
- Una alarma `critical` **bloquea en el HMI** los comandos que energizan combustible y bujía (ver sección 4).
- Si un sensor crítico lleva tiempo en `null`, conviene levantar una alarma propia (p. ej. `SENSOR_FAULT_T3`):
  un sensor sin lectura **no activa** por sí mismo ninguna alarma de valor.

### 3.6 `status`

| Campo | Tipo | Regla |
|---|---|---|
| `estop_released` | `true` / `false` / `null` | `true` = botón de emergencia físico liberado; `false` = presionado; `null` = no se sabe. |

El HMI solo permite energizar combustible y bujía si recibe `estop_released: true`.
`false` y `null` (o `status` ausente) los bloquea.

### 3.7 Frecuencia y tiempos

- **Recomendado: 4 Hz (cada 250 ms).** Rango aceptable: 0.5–10 Hz. El MAX6675 necesita ≥ 0.22 s entre lecturas
  de cada chip, así que más de ~4 Hz solo repetiría valores.
- **Manda siempre**, aunque todos los sensores estén en `null`: la ausencia de tramas se interpreta como pérdida de
  comunicación.
- Si pasan **más de 3 s sin una trama válida**, el HMI marca la telemetría como obsoleta (`STALE`) y las
  verificaciones de arranque dejan de aprobarse.
- Las tramas **no llevan hora**: el HMI las sella con la hora del PC al recibirlas (así quedan en el CSV).
  Si quieres la hora del dispositivo, agrega un campo extra (p. ej. `"uptime_ms"`): hoy se ignora, no rompe nada.

## 4. Comandos (HMI → ESP32) y ACK

### 4.1 Comando

El HMI manda un objeto por línea, **siempre compacto** (sin espacios) y con este orden:

<!-- test:valid-command -->
```json
{"version":1,"type":"command","id":12,"command":"oil_pump","value":"on"}
```

| `command` | `value` | Qué debe hacer el firmware |
|---|---|---|
| `oil_pump` | `"on"` / `"off"` | Encender / apagar la bomba de aceite (relé). Solo en modo manual. |
| `fuel_solenoid` | `"open"` / `"close"` | Abrir / cerrar la válvula solenoide de combustible (relé). Solo en modo manual. |
| `fuel_servo` | número 0–100 | Apertura del servo de combustible en %. Solo en modo manual. |
| `spark_pulse` | *(sin `value`)* | Un pulso de la bujía. **La duración la decide el firmware.** Solo en modo manual. |
| `control_mode` | `"auto"` / `"manual"` | Cambiar entre control automático (por defecto) y manual. Ver 4.3. |
| `stop` | *(sin `value`)* | Paro normal (ver pendientes, sección 10). Se acepta en cualquier modo. |
| `emergency_stop` | *(sin `value`)* | Paro de emergencia (ver pendientes, sección 10). Se acepta en cualquier modo. |

`id` es un entero ≥ 0 que elige el HMI para cada comando.

Cambio de modo (el HMI lo manda al pulsar el botón MANUAL CONTROL):

<!-- test:valid-command -->
```json
{"version":1,"type":"command","id":13,"command":"control_mode","value":"manual"}
```

### 4.2 ACK (obligatorio)

La ESP32 responde **una línea por comando**, repitiendo el mismo `id`:

<!-- test:valid-ack -->
```json
{"version":1,"type":"command_ack","id":12,"ok":true,"message":""}
```

<!-- test:valid-ack -->
```json
{"version":1,"type":"command_ack","id":13,"ok":false,"message":"oil pump is off"}
```

| Campo | Regla |
|---|---|
| `id` | El mismo `id` del comando, tal cual. |
| `ok` | `true` si lo ejecutó, `false` si lo rechazó. Debe ser booleano (no `"true"` ni `1`). |
| `message` | Texto corto (opcional pero recomendado al rechazar): ASCII, sin comillas ni barras invertidas. |

- **Responde dentro de 3 s.** Pasado ese tiempo el HMI muestra `NO ACK` en el botón (si el ACK llega después, lo acepta).
- El HMI considera un comando **ejecutado solo cuando llega `ok: true`**. Responde `ok: false` si no lo ejecutas.
- Un comando desconocido, con un `value` inválido o fuera de rango se responde con `ok:false` (y se ignora).
- Las líneas que no son comandos válidos (ruido) se ignoran sin responder.

### 4.3 Modo automático y manual

- **Por defecto el sistema está en automático**: el firmware maneja bomba de aceite, solenoide, servo y bujía por su
  cuenta, y en el HMI esos controles están **desactivados**.
- El operador pulsa **MANUAL CONTROL** → el HMI manda `control_mode: "manual"`. Solo cuando llega el ACK `ok:true`
  se habilitan los controles manuales. Pulsa **RETURN TO AUTO** → `control_mode: "auto"` y el firmware retoma las salidas.
- **El firmware debe rechazar con `ok:false`** (`"message":"automatic mode"`) cualquier `oil_pump`, `fuel_solenoid`,
  `fuel_servo` o `spark_pulse` que llegue mientras esté en automático, aunque el HMI lo haya enviado.
- `stop`, `emergency_stop` y `control_mode` se aceptan siempre, en cualquier modo.
- Al volver a automático, el HMI olvida lo comandado a mano (el servo vuelve a 0 en pantalla): lo que haga el
  controlador desde ese momento lo decide el firmware.
- Si el HMI se desconecta, el HMI vuelve a mostrar automático. **El firmware debe hacer lo mismo por su cuenta**
  (volver a automático si pierde al operador); para detectarlo hace falta un latido (ver sección 10).

### 4.4 El firmware tiene sus propias protecciones

**El HMI no es la última defensa.** Los enclavamientos del HMI (bomba de aceite → solenoide → bujía; E-STOP liberado;
sin alarma crítica) son una ayuda para el operador; el firmware debe aplicar los suyos y rechazar con `ok:false`
lo que no sea seguro, aunque el HMI lo haya enviado. El ejemplo `firmware_ejemplo/` lo muestra para solenoide,
servo y bujía. Y el botón físico de emergencia debe cortar por hardware, sin pasar por el firmware ni el HMI.

## 5. Qué hace el HMI con lo que recibe

| Situación | Comportamiento del HMI |
|---|---|
| Trama válida | Actualiza pantallas, gráficas y la guarda en el CSV de la sesión. |
| Línea que no empieza con `{` | La ignora (se asume log de depuración). |
| JSON inválido, campo faltante o tipo erróneo | Descarta **esa trama**, muestra el error abajo y sigue con la siguiente. |
| Trama > 4096 bytes sin `\n` | Error y **cierra la conexión**. |
| `sequence` igual al anterior | Trama duplicada: se ignora. |
| `sequence` salta hacia adelante | Avisa `SEQUENCE GAP` (se perdieron tramas). |
| `sequence` retrocede | Avisa `SEQUENCE RESTARTED` (normalmente la ESP32 se reinició). |
| Sin tramas válidas > 3 s | Aviso de telemetría obsoleta; las verificaciones de arranque dejan de aprobarse. |
| Sensor en `null` | Muestra «—»; hueco en las gráficas; no cuenta como válido en las verificaciones. |
| Alarma `critical` activa | Banner rojo y bloqueo de comandos de combustible y bujía. |
| Cable desconectado / puerto cerrado | Muestra desconectado; los comandos se bloquean. |

Cada comando enviado, su ACK, el rechazo o la falta de ACK se ven en el **LOG** de la pantalla principal
(p. ej. `FUEL SERVO: 50 %   SENT` / `ACK ✓`) y quedan en `logs/commands_AAAAMMDD.csv`.

## 6. Probar sin el HMI

```text
python tools/check_esp32.py --list                      # puertos serial disponibles (la ESP32 suele ser 303A:xxxx, 10C4:EA60 o 1A86:7523)
python tools/check_esp32.py COM5 --seconds 15           # escucha en vivo y da un informe
python tools/check_esp32.py --file captura.txt          # analiza texto copiado del monitor serial
```

El informe cuenta tramas válidas e inválidas, líneas ignoradas, ACK, huecos o reinicios de `sequence`, la frecuencia
medida, qué sensores se mandaron como `null` y qué alarmas aparecieron, y termina en `RESULT: PASS` o `CHECK → ...`.
Para ver el HMI completo sin hardware: `python main.py --demo`.

## 7. Lista de verificación para el firmware

- [ ] 115200 baud, una trama JSON por línea con `\n`.
- [ ] 4 Hz, `sequence` sube de 1 en 1 y vuelve a 0 solo si la ESP32 se reinicia.
- [ ] Las 9 claves de `sensors` están **siempre**; sensor sin lectura = `null`.
- [ ] Nunca sale `nan` / `inf` (probar desconectando una termocupla).
- [ ] `alarms` existe siempre (`[]` si no hay) y los `code` no se repiten en una trama.
- [ ] `status.estop_released` refleja el botón físico real (`true` / `false`).
- [ ] Ninguna otra salida por ese puerto (depuración por `Serial1`).
- [ ] Una sola tarea escribe en el puerto.
- [ ] Abrir y cerrar el puerto desde el PC no reinicia la ESP32 (`sequence` no vuelve a 0).
- [ ] Todo comando recibe su ACK con el mismo `id`; lo no seguro se rechaza con `ok:false`.
- [ ] Arranca en modo automático y rechaza los comandos manuales hasta recibir `control_mode: "manual"`.
- [ ] `python tools/check_esp32.py COMx --seconds 30` termina en `PASS`.

## 8. Errores frecuentes

| Síntoma | Causa probable |
|---|---|
| El HMI dice `Invalid JSON frame` | `nan`/`inf` en un valor, coma sobrante antes de `}` o `]`, comillas simples en lugar de dobles, texto con comillas sin escapar. |
| `missing required sensor: ...` | Se omitió una clave de `sensors` en lugar de mandarla en `null`. |
| `sequence must be a non-negative integer` | Se mandó `5.0` o `"5"` en lugar de `5`. |
| `Frame is not newline-terminated` | Falta el `\n` final (o la trama se cortó por un búfer pequeño). |
| `SEQUENCE RESTARTED` al conectar el HMI | La ESP32 se reinicia cuando el PC abre el puerto (ver sección 1). |
| Tramas mezcladas / cortadas | Dos tareas escriben a la vez, o hay texto de depuración en el mismo puerto. |
| Todos los botones en `NO ACK` | El firmware no responde ACK, responde con otro `id`, o el JSON del ACK es inválido. |
| Los botones manuales no se habilitan | El firmware no responde ACK `ok:true` a `control_mode: "manual"`. |
| El `ok` del ACK se rechaza | Se mandó `"true"` (texto) o `1` en lugar de `true`. |

## 9. Versionado

Este documento describe la **versión 1**. Agregar campos nuevos opcionales no rompe la compatibilidad (el HMI
ignora lo que no conoce). Un cambio que el HMI actual no pueda interpretar (renombrar o quitar campos
obligatorios, cambiar tipos o unidades) exige subir `version` y actualizar `core/telemetry_protocol.py`.

## 10. Decisiones pendientes del equipo

- **Quinta termocupla (`t5_c`)**: se asumió aceite; confirmar el punto real de medición.
- **Fuente del RPM**: el HMI espera `rpm` pero el sensor está por definir (tipo y método en el eje).
- **`stop` y `emergency_stop`**: definir qué hace exactamente el firmware. Propuesta: `stop` = cerrar solenoide,
  servo a 0 y mantener la bomba de aceite hasta que la turbina se detenga; `emergency_stop` = cerrar solenoide, servo a 0,
  y bujía OFF. **Decidir si en emergencia la bomba de aceite se apaga o sigue** hasta detener la turbina
  (sin aceite, los cojinetes del turbo se dañan mientras gira).
- **Umbrales de alarma** (EGT, gas, temperatura de enfriamiento): los define el equipo; los del ejemplo son ilustrativos.
- **Seguridad si se pierde el HMI**: el firmware debe llevar el motor a un estado seguro por sus propias condiciones.
  Si se quiere que lo haga al perder el HMI, hay que agregar un mensaje de latido (*heartbeat*) al protocolo.
- **Estado real de los actuadores**: la telemetría v1 no lo reporta (el HMI solo muestra lo comandado y confirmado
  con ACK). Se puede añadir un objeto opcional `actuators` en `status` en una versión compatible.

## 11. Archivos relacionados

| Archivo | Para qué sirve |
|---|---|
| `core/telemetry_protocol.py` | Validador de la telemetría (la definición exacta de lo que se acepta). |
| `core/commands.py` | Armado de comandos y validación de ACK. |
| `com/serial_reader.py` | Lectura del puerto serial en el HMI. |
| `tools/check_esp32.py` | Verificador de tramas en vivo o desde un archivo. |
| `firmware_ejemplo/telemetria_ejemplo/` | Sketch de referencia (telemetría, comandos y ACK). |
| `tests/` | Pruebas automáticas del protocolo y del lector. |
