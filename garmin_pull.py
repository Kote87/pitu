#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, json, time, argparse, datetime as dt, subprocess, shlex
from pathlib import Path
from typing import Any, Dict
import pandas as pd

try:
    from garminconnect import Garmin
except Exception as e:
    raise SystemExit("Falta 'garminconnect'. Activa el venv e instala requirements.txt") from e

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SNAP_DIR = DATA_DIR / "snapshots"
LATEST_JSON = DATA_DIR / "metrics_latest.json"
LOG_CSV = DATA_DIR / "metrics_log.csv"

def _env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"Variable requerida: {name}")
    return v

def login_client() -> Garmin:
    g = Garmin(_env("GARMIN_USER"), _env("GARMIN_PASS"))
    g.login()
    return g

def safe_get(fn, default=None):
    try: return fn()
    except Exception: return default

def extract_fields(hr, sleep, stress, summary):
    sleep_score = None
    if isinstance(sleep, dict):
        sleep_score = sleep.get("sleepScore") or sleep.get("overallScore")
    latest_hr = None
    try:
        values = (hr or {}).get("heartRateValues") or (hr or {}).get("values", [])
        if values:
            last = values[-1]
            latest_hr = int(last[1]) if isinstance(last, list) and len(last) >= 2 else None
    except Exception:
        pass
    stress_avg = None
    try:
        arr = (stress or {}).get("stressValuesArray", [])
        vals = [x[1] for x in arr if isinstance(x, list) and len(x) >= 2 and isinstance(x[1], (int,float))]
        if vals:
            n = min(len(vals), 30)
            stress_avg = sum(vals[-n:]) / n
    except Exception:
        pass
    body_battery = None
    try:
        if isinstance(summary, dict):
            bb = summary.get("bodyBatteryMostRecentValue")
            if bb is None:
                bb = (summary.get("bodyBattery") or {}).get("value")
            body_battery = bb
    except Exception:
        pass
    return latest_hr, sleep_score, stress_avg, body_battery

def day_data(g: Garmin, date_str: str) -> Dict[str, Any]:
    hr      = safe_get(lambda: g.get_heart_rates(date_str), {})
    sleep   = safe_get(lambda: g.get_sleep_data(date_str), {})
    stress  = safe_get(lambda: g.get_stress_data(date_str), {})
    summary = safe_get(lambda: g.get_user_summary(date_str), {})
    latest_hr, sleep_score, stress_avg, body_battery = extract_fields(hr, sleep, stress, summary)
    return {
        "date": date_str,
        "latest_hr": latest_hr,
        "sleep_score": sleep_score,
        "stress_avg": stress_avg,
        "body_battery": body_battery,
        "raw": {"summary": summary},
    }

def has_any_data(d: Dict[str, Any]) -> bool:
    if any([d.get("latest_hr"), d.get("sleep_score"), d.get("stress_avg"), d.get("body_battery")]):
        return True
    summary = (d.get("raw") or {}).get("summary") or {}
    return bool(summary.get("includesWellnessData") or summary.get("minHeartRate") or summary.get("restingHeartRate"))

def fetch_with_optional_lookback(g: Garmin, lookback_days: int) -> Dict[str, Any]:
    today = dt.date.today()
    for delta in range(0, max(0, lookback_days) + 1):
        day = (today - dt.timedelta(days=delta)).isoformat()
        d = day_data(g, day)
        if has_any_data(d):
            d["source_date"] = day
            return d
    d = day_data(g, today.isoformat())
    d["source_date"] = today.isoformat()
    return d

def write_latest(obj: Dict[str, Any]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def write_snapshot(obj: Dict[str, Any]) -> Path:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now()
    snap_name = f"metrics_{now.strftime('%Y-%m-%d_%H-%M')}.json"
    p = SNAP_DIR / snap_name
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return p

def append_csv(obj: Dict[str, Any]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "ts_iso": obj.get("timestamp"),
        "label": obj.get("label"),
        "source_date": obj.get("source_date"),
        "latest_hr": obj.get("latest_hr"),
        "sleep_score": obj.get("sleep_score"),
        "stress_avg": obj.get("stress_avg"),
        "body_battery": obj.get("body_battery"),
    }
    df = pd.DataFrame([row])
    if LOG_CSV.exists():
        df.to_csv(LOG_CSV, mode="a", header=False, index=False)
    else:
        df.to_csv(LOG_CSV, index=False)

def run(cmd, check=False):
    return subprocess.run(shlex.split(cmd), cwd=str(BASE_DIR), capture_output=True, text=True, check=check)

def git_autopush(files, branch="data-stream"):
    # Intenta preparar rama y subir cambios; tolera "no hay cambios"
    run(f"git pull --rebase origin {branch}")
    run(f"git add {' '.join(str(f) for f in files)}")
    msg = dt.datetime.now().strftime("data: %Y-%m-%d %H:%M snapshot")
    commit = run(f"git commit -m {shlex.quote(msg)}")
    if "nothing to commit" in commit.stdout.lower() + commit.stderr.lower():
        return
    run(f"git push origin {branch}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true", help="Ejecutar en bucle")
    ap.add_argument("--interval", type=int, default=600, help="Segundos entre lecturas")
    ap.add_argument("--lookback", type=int, default=0, help="Días hacia atrás si hoy está vacío")
    ap.add_argument("--git-autopush", action="store_true", help="Añadir/commit/push de datos tras cada lectura")
    ap.add_argument("--git-branch", default="data-stream", help="Rama a la que empujar los datos")
    args = ap.parse_args()

    g = login_client()
    while True:
        now = dt.datetime.now()
        label = now.strftime("%d/%m/%y-%H:%M")
        d = fetch_with_optional_lookback(g, args.lookback)
        out = {"timestamp": now.isoformat(), "label": label, **d}

        write_latest(out)
        snap = write_snapshot(out)
        append_csv(out)

        print(f"[OK] {out['timestamp']} src={out.get('source_date')} "
              f"HR={out.get('latest_hr')} Stress={out.get('stress_avg')} "
              f"SleepScore={out.get('sleep_score')} BB={out.get('body_battery')} "
              f"snap={snap.name}")

        if args.git_autopush:
            try:
                files = [snap, LATEST_JSON, LOG_CSV]
                git_autopush(files, branch=args.git_branch)
            except Exception as e:
                print("[WARN] git autopush falló:", e)

        if not args.loop:
            break
        time.sleep(max(30, args.interval))

if __name__ == "__main__":
    main()
