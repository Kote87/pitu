#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
garmin_pull.py
Descarga métricas clave de Garmin Connect (NO oficial) y las guarda en JSON/CSV.

Uso:
  export GARMIN_USER="correo"
  export GARMIN_PASS="password"
  python garmin_pull.py --loop --interval 600
"""
import os
import time
import json
import argparse
import datetime as dt
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

try:
    from garminconnect import Garmin
except Exception as e:
    raise SystemExit("Falta la librería 'garminconnect'. Instala con: pip install garminconnect") from e


DATA_DIR = Path(__file__).resolve().parent / "data"
LATEST_JSON = DATA_DIR / "metrics_latest.json"
LOG_CSV = DATA_DIR / "metrics_log.csv"

def _env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Variable de entorno requerida: {name}")
    return v

def login_client() -> Garmin:
    user = _env("GARMIN_USER")
    pwd  = _env("GARMIN_PASS")
    g = Garmin(user, pwd)
    g.login()
    return g

def safe_get(callable_fn, default=None):
    try:
        return callable_fn()
    except Exception:
        return default

def fetch_metrics(g: Garmin) -> Dict[str, Any]:
    today = dt.date.today().isoformat()

    # Ejemplos de métodos de garminconnect (pueden variar según versión)
    # Usamos 'safe_get' para tolerar endpoints no disponibles.
    hr       = safe_get(lambda: g.get_heart_rates(today), default={})
    sleep    = safe_get(lambda: g.get_sleep_data(today), default={})
    stress   = safe_get(lambda: g.get_stress_data(today), default={})
    summary  = safe_get(lambda: g.get_user_summary(today), default={})
    bodybat  = safe_get(lambda: g.get_body_battery(today), default={})  # puede no existir en algunas versiones

    # Derivados simples
    sleep_score = None
    try:
        # distintas estructuras posibles; intenta encontrar un score
        if isinstance(sleep, dict):
            sleep_score = sleep.get("sleepScore", None) or sleep.get("overallScore", None)
    except Exception:
        pass

    # HR actual aproximado (último valor del día)
    latest_hr = None
    try:
        values = hr.get("heartRateValues") or hr.get("values", [])
        if values:
            # cada ítem puede ser [timestamp, valor] o dict
            last = values[-1]
            latest_hr = int(last[1]) if isinstance(last, list) and len(last) >= 2 else None
    except Exception:
        pass

    # Estrés promedio reciente
    stress_avg = None
    try:
        # stress["stressValuesArray"] puede contener pares [ts, val]
        arr = stress.get("stressValuesArray", [])
        if arr:
            vals = [x[1] for x in arr if isinstance(x, list) and len(x) >= 2 and isinstance(x[1], (int, float))]
            if vals:
                stress_avg = sum(vals[-30:]) / min(len(vals), 30)  # promedio últimas ~30 muestras
    except Exception:
        pass

    body_battery = None
    try:
        # distintos nombres posibles
        if isinstance(bodybat, dict):
            body_battery = bodybat.get("bodyBattery", {}).get("value") or bodybat.get("value")
    except Exception:
        pass

    out = {
        "timestamp": dt.datetime.now().isoformat(),
        "latest_hr": latest_hr,
        "sleep_score": sleep_score,
        "stress_avg": stress_avg,
        "body_battery": body_battery,
        "raw": {
            "summary": summary,
        },
    }
    return out

def append_csv(row: Dict[str, Any]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    if LOG_CSV.exists():
        df.to_csv(LOG_CSV, mode="a", header=False, index=False)
    else:
        df.to_csv(LOG_CSV, index=False)

def write_latest_json(obj: Dict[str, Any]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Ejecutar en bucle")
    parser.add_argument("--interval", type=int, default=600, help="Segundos entre lecturas (def: 600)")
    args = parser.parse_args()

    g = login_client()

    while True:
        try:
            metrics = fetch_metrics(g)
            write_latest_json(metrics)
            # Log 'bonito' al CSV con columnas planas
            flat = {
                "timestamp": metrics.get("timestamp"),
                "latest_hr": metrics.get("latest_hr"),
                "sleep_score": metrics.get("sleep_score"),
                "stress_avg": metrics.get("stress_avg"),
                "body_battery": metrics.get("body_battery"),
            }
            append_csv(flat)
            print(f"[OK] {metrics.get('timestamp')} HR={metrics.get('latest_hr')} Stress={metrics.get('stress_avg')} SleepScore={metrics.get('sleep_score')}")
        except Exception as e:
            print(f"[WARN] Error al obtener/guardar métricas: {e}")

        if not args.loop:
            break
        time.sleep(max(30, args.interval))

if __name__ == "__main__":
    main()