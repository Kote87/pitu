#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lighting_control_serial.py
Lee data/metrics_latest.json, calcula intensidad (0..1) y CCT (Kelvin), y envía
un color RGB a un Arduino con tira WS2812B por Serial (protocolo: 'RGB,r,g,b\n').
"""
import os
import json
import time
import math
import serial
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Tuple

import yaml

BASE_DIR = Path(__file__).resolve().parent
CFG = yaml.safe_load((BASE_DIR / "config.yaml").read_text(encoding="utf-8"))
DATA_JSON = BASE_DIR / "data" / "metrics_latest.json"

def clamp(x, a, b):
    return max(a, min(b, x))

def parse_hhmm(s: str) -> dtime:
    h, m = map(int, s.split(":"))
    return dtime(hour=h, minute=m)

def in_range(now: dtime, start: dtime, end: dtime) -> bool:
    if start <= end:
        return start <= now < end
    # rango que cruza medianoche
    return now >= start or now < end

def circadian_base(now: dtime):
    c = CFG["circadian"]
    t_morn = parse_hhmm(c["morning_start"])
    t_day  = parse_hhmm(c["day_start"])
    t_eve  = parse_hhmm(c["evening_start"])
    t_nit  = parse_hhmm(c["night_start"])

    if in_range(now, t_morn, t_day):
        return c["intensity_morning"], c["cct_morning"]
    if in_range(now, t_day, t_eve):
        return c["intensity_day"], c["cct_day"]
    if in_range(now, t_eve, t_nit):
        return c["intensity_evening"], c["cct_evening"]
    # noche
    return c["intensity_night"], c["cct_night"]

def normalize(x, lo, hi) -> float:
    if x is None:
        return 0.0
    if hi == lo:
        return 0.0
    return clamp((x - lo) / float(hi - lo), 0.0, 1.0)

def cct_to_rgb(kelvin: float) -> Tuple[int, int, int]:
    """Conversión aproximada CCT(K) -> RGB (0..255)."""
    # Adaptado de fórmulas conocidas (Tanner Helland / Neil Bartlett), 1000K..40000K
    T = kelvin / 100.0
    # Red
    if T <= 66:
        R = 255
    else:
        R = 329.698727446 * ((T - 60) ** -0.1332047592)
        R = clamp(R, 0, 255)
    # Green
    if T <= 66:
        G = 99.4708025861 * math.log(T) - 161.1195681661
        G = clamp(G, 0, 255)
    else:
        G = 288.1221695283 * ((T - 60) ** -0.0755148492)
        G = clamp(G, 0, 255)
    # Blue
    if T >= 66:
        B = 255
    elif T <= 19:
        B = 0
    else:
        B = 138.5177312231 * math.log(T - 10) - 305.0447927307
        B = clamp(B, 0, 255)
    return int(R), int(G), int(B)

class Smoother:
    def __init__(self, alpha=0.25, hysteresis=0.04):
        self.alpha = alpha
        self.h = hysteresis
        self.i = None
        self.k = None

    def step(self, intensity, cct):
        # histéresis
        if self.i is not None and abs(intensity - self.i) < self.h:
            intensity = self.i
        if self.k is not None and abs(cct - self.k) < (self.k * self.h):
            cct = self.k
        # suavizado exponencial
        self.i = intensity if self.i is None else (self.alpha * intensity + (1 - self.alpha) * self.i)
        self.k = cct if self.k is None else (self.alpha * cct + (1 - self.alpha) * self.k)
        return self.i, self.k

def compute_targets(metrics: dict) -> Tuple[float, float]:
    """Devuelve (intensidad 0..1, cct en Kelvin)."""
    limits = CFG["limits"]
    thr = CFG["thresholds"]
    w = CFG["weights"]

    now = datetime.now().time()
    base_intensity, base_cct = circadian_base(now)

    hr = metrics.get("latest_hr")
    stress = metrics.get("stress_avg")
    sleep_score = metrics.get("sleep_score")

    # Normalizaciones
    act = normalize(hr, thr["hr_rest"], thr["hr_high"])            # 0 reposo .. 1 ejercicio
    stress_norm = normalize(stress, 0, 100)
    sleep_debt = 0.0
    if sleep_score is not None:
        if sleep_score >= thr["sleep_good"]:
            sleep_debt = 0.0
        elif sleep_score <= thr["sleep_poor"]:
            sleep_debt = 1.0
        else:
            sleep_debt = normalize(thr["sleep_good"] - sleep_score, 0, thr["sleep_good"] - thr["sleep_poor"])

    # Intensidad
    intensity = base_intensity
    intensity *= (1 + w["activity_boost"] * act)          # subir con actividad
    intensity *= (1 - w["stress_calm"] * stress_norm)     # bajar con estrés
    intensity *= (1 - w["sleep_debt"] * sleep_debt)       # bajar si dormiste mal
    intensity = clamp(intensity, limits["intensity_min"], limits["intensity_max"])

    # CCT (más fría con actividad, más cálida con estrés/ sueño pobre)
    cct = base_cct
    cct += 600 * act
    cct -= 800 * stress_norm
    cct -= 600 * sleep_debt
    cct = clamp(cct, limits["cct_min"], limits["cct_max"])

    return float(intensity), float(cct)

def main():
    ser_cfg = CFG["serial"]
    port = ser_cfg["port"]
    baud = ser_cfg["baudrate"]
    smoother = Smoother(CFG["smoothing"]["alpha"], CFG["smoothing"]["hysteresis"])

    # Abrir Serial
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=1)
        time.sleep(2)  # tiempo para que Arduino reinicie
    except Exception as e:
        print(f"[ERROR] No se pudo abrir el puerto serial {port}: {e}")
        return

    print("[INFO] Control de luces iniciado. Ctrl+C para salir.")
    try:
        while True:
            if not DATA_JSON.exists():
                time.sleep(2)
                continue
            with open(DATA_JSON, "r", encoding="utf-8") as f:
                metrics = json.load(f)

            intensity, cct = compute_targets(metrics)
            i_s, cct_s = smoother.step(intensity, cct)

            # Convertir a RGB según CCT, luego escalar por intensidad
            r, g, b = cct_to_rgb(cct_s)
            r = int(r * i_s)
            g = int(g * i_s)
            b = int(b * i_s)

            cmd = f"RGB,{r},{g},{b}\n"
            try:
                ser.write(cmd.encode("utf-8"))
            except Exception as e:
                print(f"[WARN] Fallo al escribir en Serial: {e}")

            # Debug
            print(f"I={i_s:.2f} CCT={int(cct_s)}K  RGB=({r},{g},{b})  HR={metrics.get('latest_hr')} Stress={metrics.get('stress_avg')} SleepScore={metrics.get('sleep_score')}")

            time.sleep(5)  # ajusta frecuencia de actualización
    except KeyboardInterrupt:
        pass
    finally:
        try:
            ser.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()