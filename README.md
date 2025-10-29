# Garmin ➜ Domótica Wellness (Luces, Sonido, Temperatura) — Starter Kit

Este kit te da un **pipeline mínimo** para:
1) **Extraer datos de tu Garmin Fenix 7** (vía *garminconnect* no oficial).
2) **Guardarlos en JSON/CSV** para usarlos libremente.
3) **Aplicar fórmulas** (circadianas + estado fisiológico) para obtener **intensidad** (0–100%), **tono** (CCT en Kelvin) y **encendido/apagado**.
4) **Controlar luces LED** de dos formas:
   - **Arduino + WS2812B (NeoPixel)** por **Serial** (`lighting_control_serial.py` + `led_controller.ino`).
   - **Philips Hue** por **HTTP** (`lighting_control_hue.py`).  
5) (Opcional) **Acciones Home Assistant** para sonido/temperatura (`ha_actions_example.py`).

> ⚠️ **Privacidad y límites**: el script `garmin_pull.py` usa la librería **no oficial** `garminconnect`. Úsalo bajo tu propio criterio y respeta los TOS de Garmin. La API oficial (Garmin Health) suele exigir acuerdos empresariales. Para *casi tiempo real* de pulso, considera **BLE broadcast** del Fenix (script `hr_ble_to_serial.py` como punto de partida).

---

## Requisitos

- Python 3.10+  
- Instalar dependencias:  
  ```bash
  pip install -r requirements.txt
  ```
- Variables de entorno (o `.env` en tu shell):
  ```bash
  export GARMIN_USER="tu_correo@ejemplo.com"
  export GARMIN_PASS="tu_password"
  # Hue (si usas Hue)
  export HUE_BRIDGE_IP="192.168.1.10"
  export HUE_USER_KEY="xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  export HUE_LIGHT_ID="1"
  # Home Assistant (opcional)
  export HASS_URL="http://homeassistant.local:8123"
  export HASS_TOKEN="Bearer eyJ0eXAiOiJKV1QiLCJh..."
  ```

---

## Flujo recomendado

1. Ejecuta **garmin_pull.py** de forma periódica (cada 5–10 min con `cron` o como servicio).  
   - Produce `data/metrics_latest.json` y acumula `data/metrics_log.csv`.
2. Ejecuta **lighting_control_serial.py** (o **lighting_control_hue.py**) en bucle.  
   - Lee `metrics_latest.json`, calcula **intensidad** + **CCT** y aplica su valor a LEDs.
3. (Opcional) Ejecuta **ha_actions_example.py** para ajustar volumen/temperatura según el estado (estrés, sueño, HR).

---

## Fórmulas (resumen)

- **Base circadiana** (mañana brillante fría; noche tenue cálida).
- **Moduladores** por estado:
  - **Ejercicio/actividad (HR alta)** ⇒ +intensidad, +CCT (más fría).
  - **Estrés alto** ⇒ −intensidad, −CCT (más cálida).
  - **“Sleep debt” o sueño pobre** ⇒ −intensidad diurna y **horario de noche** adelantado.
- **Suavizado**: filtro exponencial + histéresis para evitar parpadeos.

> Parámetros ajustables en `config.yaml`.

---

## Arduino (WS2812B)

1. Carga `led_controller.ino` en tu placa (UNO/Nano/Mega). Conecta la tira WS2812B al **pin 6**, 5V y GND común.  
2. Ejecuta `lighting_control_serial.py` (ajusta `SERIAL_PORT`). El script envía líneas tipo:  
   ```text
   RGB,120,180,255\n
   ```

---

## Philips Hue

1. Crea un usuario en el **Hue Bridge**. Guarda `HUE_BRIDGE_IP`, `HUE_USER_KEY` y `HUE_LIGHT_ID`.  
2. Ejecuta `lighting_control_hue.py`.

---

## BLE (Pulso en vivo, opcional)

- Activa **Broadcast HR** en el Fenix 7. Prueba `hr_ble_to_serial.py` (requiere `bleak`) para leer el **Heart Rate Service** y enviar HR al Arduino.

---

## Archivos

- `garmin_pull.py` — descarga datos de Garmin y escribe JSON/CSV.
- `lighting_control_serial.py` — lee métricas y controla **Arduino/WS2812**.
- `led_controller.ino` — firmware Arduino para recibir `RGB,r,g,b` por Serial.
- `lighting_control_hue.py` — controla luces **Philips Hue** con fórmulas.
- `ha_actions_example.py` — ejemplo de acciones en **Home Assistant** (sonido y clima).
- `hr_ble_to_serial.py` — *starter* para leer pulso por **BLE** y reenviarlo por Serial.
- `config.yaml` — umbrales y pesos de la lógica de control.
- `requirements.txt` — dependencias Python.