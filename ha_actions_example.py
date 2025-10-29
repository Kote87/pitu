#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ha_actions_example.py
Ejecuta acciones en Home Assistant (volumen / clima) según métricas Garmin.

Requiere:
  export HASS_URL="http://homeassistant.local:8123"
  export HASS_TOKEN="Bearer eyJ..."
Ajusta las ENTIDADES abajo.
"""
import os
import json
import time
import requests
from pathlib import Path

HASS_URL = os.environ.get("HASS_URL", "")
HASS_TOKEN = os.environ.get("HASS_TOKEN", "")
HEADERS = {"Authorization": HASS_TOKEN, "Content-Type": "application/json"}

# Ajusta entidades
ENTITY_MEDIA = "media_player.salon"
ENTITY_CLIMATE = "climate.dormitorio"

DATA_JSON = Path(__file__).resolve().parent / "data" / "metrics_latest.json"

def call_service(domain, service, data):
    url = f"{HASS_URL}/api/services/{domain}/{service}"
    r = requests.post(url, headers=HEADERS, json=data, timeout=4)
    r.raise_for_status()
    return r.json()

def main():
    if not HASS_URL or not HASS_TOKEN.startswith("Bearer "):
        raise SystemExit("Configura HASS_URL y HASS_TOKEN (Bearer ...)")

    print("[INFO] Acciones HA iniciadas. Ctrl+C para salir.")
    try:
        while True:
            if not DATA_JSON.exists():
                time.sleep(2); continue
            m = json.loads(DATA_JSON.read_text(encoding="utf-8"))
            hr = m.get("latest_hr") or 0
            stress = m.get("stress_avg") or 0
            sleep_score = m.get("sleep_score") or 70

            # Volumen: baja si estrés alto, sube si ejercicio (hr alta).
            vol = 0.3
            if hr >= 120: vol = 0.7
            if stress >= 70: vol = 0.15
            call_service("media_player", "volume_set", {"entity_id": ENTITY_MEDIA, "volume_level": vol})

            # Clima: más fresco si ejercicio, más templado si descanso.
            temp = 21.0
            if hr >= 120: temp = 20.0
            if sleep_score < 60: temp = 20.5  # ligeramente fresco favorece el sueño
            call_service("climate", "set_temperature", {"entity_id": ENTITY_CLIMATE, "temperature": temp})

            print(f"[HA] volume={vol} temp={temp}")
            time.sleep(60)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()