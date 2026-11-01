import time
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException

from backend.models import (
    Building,
    EnergyReading,
    EnergySetting,
    Alert,
    Recommendation,
)
from backend.analytics import (
    floor_hour,
    start_of_day,
    get_hourly_series,
    dense_series,
    compare_rows,
    detect_anomalies,
    HOUR,
    DAY,
)
from backend.peak_reduction import find_windows, fmt_t, fmt_dt
from backend.config import DEFAULT_SETTINGS


def get_or_create_settings(db: Session) -> EnergySetting:
    setting = db.query(EnergySetting).first()
    if not setting:
        setting = EnergySetting(
            campus_name=DEFAULT_SETTINGS.get("campusName", "Riverview Technical College"),
            location=DEFAULT_SETTINGS.get("location", "Riverview"),
            currency=DEFAULT_SETTINGS.get("currency", "$"),
            rate=float(DEFAULT_SETTINGS.get("rate", 0.118)),
            demand_rate=float(DEFAULT_SETTINGS.get("demandRate", 14.5)),
            peak_threshold=float(DEFAULT_SETTINGS.get("peakThreshold", 450.0)),
            ev_charging=bool(DEFAULT_SETTINGS.get("evCharging", True)),
            ev_kw=float(DEFAULT_SETTINGS.get("evKw", 22.0)),
            user_name=DEFAULT_SETTINGS.get("userName", "A. Jordan"),
            role=DEFAULT_SETTINGS.get("role", "Energy Manager"),
            theme=DEFAULT_SETTINGS.get("theme", "light"),
            reduce_motion=bool(DEFAULT_SETTINGS.get("reduceMotion", False)),
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def get_recent_avg_kw(db: Session, bid: str, days: int = 14, now_ts: Optional[int] = None) -> float:
    if now_ts is None:
        max_ts = db.query(func.max(EnergyReading.timestamp)).scalar()
        now_ts = max_ts if max_ts else int(time.time() * 1000)

    from_ts = now_ts - days * DAY
    readings = (
        db.query(func.avg(EnergyReading.kwh))
        .filter(
            EnergyReading.building_id == bid,
            EnergyReading.timestamp >= from_ts,
            EnergyReading.timestamp <= now_ts,
        )
        .scalar()
    )
    return round(float(readings or 0.0), 2)


def parse_when(s: Any) -> Optional[int]:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    s = str(s).strip()
    if not s:
        return None
    # Handle YYYY-MM-DD
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        s += "T00:00"
    s = s.replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
        return int(dt.timestamp() * 1000)
    except Exception:
        # Try custom common formats
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
            try:
                dt = datetime.strptime(s, fmt)
                return int(dt.timestamp() * 1000)
            except Exception:
                pass
    return None


def import_csv_readings(db: Session, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        raise HTTPException(status_code=400, detail="The file contained no data rows.")

    buildings = db.query(Building).all()
    b_map = {}
    for b in buildings:
        b_map[b.id.lower()] = b
        b_map[b.name.lower()] = b

    now_ts = int(time.time() * 1000)
    imported = []
    duplicates = []
    errors = []
    seen = set()

    # Pre-fetch existing building+ts pairs to avoid N query calls
    existing_records = set(
        f"{r[0]}|{r[1]}"
        for r in db.query(EnergyReading.building_id, EnergyReading.timestamp).all()
    )

    for i, row in enumerate(rows):
        rn = i + 2
        bid = str(row.get("building_id") or "").strip()
        bname = str(row.get("building_name") or "").strip()

        target_building = b_map.get(bid.lower()) or b_map.get(bname.lower())
        if not target_building:
            errors.append({
                "row": rn,
                "msg": f'Unknown building "{bid or bname or "—"}". Use a valid building_id or building_name.',
            })
            continue

        raw_ts = row.get("timestamp")
        ts = parse_when(raw_ts)
        if ts is None:
            errors.append({
                "row": rn,
                "msg": f'Invalid timestamp "{raw_ts or ""}". Use YYYY-MM-DD HH:MM.',
            })
            continue

        ts = floor_hour(ts)

        try:
            kwh = float(row.get("kwh", ""))
            if kwh < 0 or not math.isfinite(kwh):
                raise ValueError()
        except Exception:
            errors.append({
                "row": rn,
                "msg": f'Invalid kWh value "{row.get("kwh", "")}" — must be a non-negative number.',
            })
            continue

        if ts > now_ts + HOUR:
            errors.append({
                "row": rn,
                "msg": "Timestamp is in the future.",
            })
            continue

        key = f"{target_building.id}|{ts}"
        if key in existing_records or key in seen:
            duplicates.append({
                "row": rn,
                "msg": f"{target_building.name} at {fmt_dt(ts)} already exists — skipped.",
            })
            continue

        seen.add(key)
        imported.append(
            EnergyReading(
                id=f"r_{uuid.uuid4().hex[:10]}",
                building_id=target_building.id,
                timestamp=ts,
                kwh=round(kwh, 2),
            )
        )

    if imported:
        db.bulk_save_objects(imported)
        db.commit()

    return {
        "imported": len(imported),
        "duplicates": duplicates[:10],
        "dupCount": len(duplicates),
        "errors": errors[:15],
        "errorCount": len(errors),
    }


def get_data_quality(db: Session) -> List[Dict[str, Any]]:
    buildings = db.query(Building).all()
    now_ts = int(time.time() * 1000)
    w0 = floor_hour(now_ts - 7 * DAY)
    w30 = now_ts - 30 * DAY

    out = []
    for b in buildings:
        readings = (
            db.query(EnergyReading.timestamp)
            .filter(EnergyReading.building_id == b.id)
            .all()
        )
        timestamps = set(r[0] for r in readings)
        count = len(timestamps)

        first_ts = min(timestamps) if timestamps else None
        last_ts = max(timestamps) if timestamps else None

        last30 = sum(1 for t in timestamps if t >= w30)
        coverage = min(100, round((last30 / (30 * 24)) * 100)) if count > 0 else 0

        missing = 0
        cur = w0
        while cur < now_ts:
            if cur not in timestamps:
                missing += 1
            cur += HOUR

        out.append({
            "id": b.id,
            "name": b.name,
            "records": count,
            "first": first_ts,
            "last": last_ts,
            "coverage": coverage,
            "missing": missing,
        })

    return out


def scan_alerts_internal(
    db: Session,
    peak_days: int = 7,
    anom_days: int = 14,
    now_ts: Optional[int] = None,
) -> int:
    settings = get_or_create_settings(db)
    if now_ts is None:
        max_ts = db.query(func.max(EnergyReading.timestamp)).scalar()
        now_ts = max_ts if max_ts else int(time.time() * 1000)

    created = 0

    if peak_days > 0:
        hrs = get_hourly_series(db, "*", now_ts - peak_days * DAY, now_ts)
        valid_hrs = [h for h in hrs if h.get("v") is not None]
        windows = find_windows(valid_hrs, settings.peak_threshold)
        for w in windows:
            key = f"peak:{start_of_day(w['start'])}"
            exists = db.query(Alert).filter(Alert.dedupe_key == key).first()
            if not exists:
                severity = "high" if w["peak"] > settings.peak_threshold * 1.08 else "medium"
                msg = f"Campus demand peaked at {round(w['peak'], 1)} kW (threshold {round(settings.peak_threshold, 1)} kW) between {fmt_t(w['start'])} and {fmt_t(w['end'] + HOUR)}."
                alert = Alert(
                    id=f"alt_{uuid.uuid4().hex[:10]}",
                    type="peak",
                    severity=severity,
                    message=msg,
                    timestamp=w["start"],
                    read=False,
                    dedupe_key=key,
                )
                db.add(alert)
                created += 1

    if anom_days > 0:
        anomalies = detect_anomalies(db, None, anom_days, now_ts)
        for a in anomalies:
            dt = datetime.fromtimestamp(a["t"] / 1000)
            key = f"an:{a['bid']}:{start_of_day(a['t'])}:{dt.hour}"
            exists = db.query(Alert).filter(Alert.dedupe_key == key).first()
            if not exists:
                msg = f"Unusual consumption at {a['building']}: {round(a['v'], 1)} kWh at {fmt_dt(a['t'])} (typical {round(a['mean'], 1)} ± {round(a['sd'], 1)})."
                alert = Alert(
                    id=f"alt_{uuid.uuid4().hex[:10]}",
                    type="anomaly",
                    severity="low",
                    message=msg,
                    timestamp=a["t"],
                    read=False,
                    dedupe_key=key,
                )
                db.add(alert)
                created += 1

    if created > 0:
        db.commit()

    return created
