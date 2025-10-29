#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lighting_control_hue.py
Lee data/metrics_latest.json, calcula intensidad (bri 1..254) y CCT (Hue ct 153..500),
y envía PUT al Bridge de Philips Hue.
"""
import os
import json
import time
import math
import requests
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Tuple

import yaml

BASE_DIR = Path(__file__).resolve().parent
CFG = yaml.safe_load((BASE_DIR / "config.yaml").read_text(encoding="utf-8"))
DATA_JSON = BASE_DIR / "data" / "metrics_latest.json"

HUE_IP = os.environ.get("HUE_BRIDGE_IP", "")
HUE_USER = os.environ.get("HUE_USER_KEY", "")
HUE_LIGHT_ID = os.environ.get("HUE_LIGHT_ID", "1")

def clamp(x, a, b):
    return max(a, min(b, x))

def parse_hhmm(s: str) -> dtime:
    h, m = map(int, s.split(":"))
    return dtime(hour=h, minute=m)

def in_range(now: dtime, start: dtime, end: dtime) -> bool:
    if start <= end:
        return start <= now < end
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
    return c["intensity_night"], c["cct_night"]

def normalize(x, lo, hi) -> float:
    if x is None:
        return 0.0
    if hi == lo:
        return 0.0
    return clamp((x - lo) / float(hi - lo), 0.0, 1.0)

class Smoother:
    def __init__(self, alpha=0.25, hysteresis=0.04):
        self.alpha = alpha
        self.h = hysteresis
        self.i = None
        self.k = None

    def step(self, intensity, cct):
        if self.i is not None and abs(intensity - self.i) < self.h:
            intensity = self.i
        if self.k is not None and abs(cct - self.k) < (self.k * self.h):
            cct = self.k
        self.i = intensity if self.i is None else (self.alpha * intensity + (1 - self.alpha) * self.i)
        self.k = cct if self.k is None else (self.alpha * cct + (1 - self.alpha) * self.k)
        return self.i, self.k

def compute_targets(metrics: dict) -> Tuple[float, float]:
    limits = CFG["limits"]
    thr = CFG["thresholds"]
    w = CFG["weights"]

    now = datetime.now().time()
    base_intensity, base_cct = circadian_base(now)

    hr = metrics.get("latest_hr")
    stress = metrics.get("stress_avg")
    sleep_score = metrics.get("sleep_score")

    act = normalize(hr, thr["hr_rest"], thr["hr_high"])
    stress_norm = normalize(stress, 0, 100)
    if sleep_score is None:
        sleep_debt = 0.0
    else:
        if sleep_score >= thr["sleep_good"]:
            sleep_debt = 0.0
        elif sleep_score <= thr["sleep_poor"]:
            sleep_debt = 1.0
        else:
            sleep_debt = normalize(thr["sleep_good"] - sleep_score, 0, thr["sleep_good"] - thr["sleep_poor"])

    intensity = base_intensity
    intensity *= (1 + w["activity_boost"] * act)
    intensity *= (1 - w["stress_calm"] * stress_norm)
    intensity *= (1 - w["sleep_debt"] * sleep_debt)
    intensity = clamp(intensity, limits["intensity_min"], limits["intensity_max"])

    cct = base_cct + 600*act - 800*stress_norm - 600*sleep_debt
    cct = clamp(cct, limits["cct_min"], limits["cct_max"])

    return float(intensity), float(cct)

def kelvin_to_hue_ct(kelvin: float) -> int:
    # Hue usa 'ct' = 1e6 / Kelvin, rango 153 (6500K) .. 500 (2000K)
    ct = int(round(1_000_000 / kelvin))
    return clamp(ct, 153, 500)

def intensity_to_bri(intensity: float) -> int:
    # Hue 'bri' 1..254
    return int(clamp(round(intensity * 254), 1, 254))

def set_hue_state(on: bool, bri: int, ct: int):
    url = f"http://{HUE_IP}/api/{HUE_USER}/lights/{HUE_LIGHT_ID}/state"
    payload = {"on": on, "bri": bri, "ct": ct}
    r = requests.put(url, json=payload, timeout=3)
    r.raise_for_status()
    return r.json()

def main():
    if not HUE_IP or not HUE_USER:
        raise SystemExit("Configura HUE_BRIDGE_IP y HUE_USER_KEY en variables de entorno.")
    smoother = Smoother(CFG["smoothing"]["alpha"], CFG["smoothing"]["hysteresis"])

    print("[INFO] Control Hue iniciado. Ctrl+C para salir.")
    try:
        while True:
            if not DATA_JSON.exists():
                time.sleep(2)
                continue
            metrics = json.loads(DATA_JSON.read_text(encoding="utf-8"))
            intensity, cct = compute_targets(metrics)
            i_s, k_s = smoother.step(intensity, cct)

            bri = intensity_to_bri(i_s)
            ct = kelvin_to_hue_ct(k_s)

            resp = set_hue_state(on=True, bri=bri, ct=ct)
            print(f"I={i_s:.2f} (bri={bri})  CCT={int(k_s)}K (ct={ct})  resp={resp}")
            time.sleep(5)
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()