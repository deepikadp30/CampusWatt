import math
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.models import EnergyReading, Building

HOUR = 3600 * 1000
DAY = 24 * HOUR


def _safe_dt(ts_ms: int) -> datetime:
    # Ensure safe timestamp on Windows (handles small or 0 epoch edge cases)
    sec = max(ts_ms, 86400000) / 1000.0
    try:
        return datetime.fromtimestamp(sec)
    except Exception:
        from datetime import timezone
        return datetime.fromtimestamp(sec, tz=timezone.utc).replace(tzinfo=None)


def floor_hour(ts_ms: int) -> int:
    dt = _safe_dt(ts_ms)
    dt_floor = dt.replace(minute=0, second=0, microsecond=0)
    return int(dt_floor.timestamp() * 1000)


def start_of_day(ts_ms: int) -> int:
    dt = _safe_dt(ts_ms)
    dt_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(dt_start.timestamp() * 1000)


def start_of_week(ts_ms: int) -> int:
    dt = _safe_dt(ts_ms)
    dt_day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    weekday = dt_day.weekday()  # 0 is Monday
    ts_start = int((dt_day.timestamp() - weekday * 86400) * 1000)
    return ts_start


def start_of_month(ts_ms: int) -> int:
    dt = _safe_dt(ts_ms)
    dt_start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return int(dt_start.timestamp() * 1000)


def get_hourly_series(
    db: Session,
    bid: Optional[str],
    from_ts: int,
    to_ts: int,
) -> List[Dict[str, Any]]:
    """
    Returns an hourly time series from from_ts to to_ts.
    If bid is None or '*', returns campus total aggregated demand.
    """
    t0 = floor_hour(from_ts)
    if to_ts <= t0:
        return []

    # Map existing readings from database
    val_map: Dict[int, float] = {}

    if bid and bid != "*":
        readings = (
            db.query(EnergyReading.timestamp, EnergyReading.kwh)
            .filter(
                EnergyReading.building_id == bid,
                EnergyReading.timestamp >= t0,
                EnergyReading.timestamp < to_ts,
            )
            .all()
        )
        for ts, kwh in readings:
            val_map[ts] = round(kwh, 2)
    else:
        sums = (
            db.query(EnergyReading.timestamp, func.sum(EnergyReading.kwh).label("total"))
            .filter(
                EnergyReading.timestamp >= t0,
                EnergyReading.timestamp < to_ts,
            )
            .group_by(EnergyReading.timestamp)
            .all()
        )
        for ts, total in sums:
            val_map[ts] = round(float(total), 2)

    out = []
    # Generate complete sequence of hours
    cur = t0
    while cur < to_ts:
        val = val_map.get(cur)
        out.append({"t": cur, "v": val})
        cur += HOUR

    return out


def bucketize(hourly: List[Dict[str, Any]], bucket: str) -> List[Dict[str, Any]]:
    """
    Buckets hourly time series into hour, day, week, or month.
    """
    if bucket == "hour":
        return [
            {"t": h["t"], "v": round(h["v"], 2) if h["v"] is not None else 0.0}
            for h in hourly
            if h.get("v") is not None
        ]

    bucket_map: Dict[int, float] = {}
    for h in hourly:
        if h.get("v") is None:
            continue
        ts = h["t"]
        if bucket == "day":
            k = start_of_day(ts)
        elif bucket == "week":
            k = start_of_week(ts)
        elif bucket == "month":
            k = start_of_month(ts)
        else:
            k = ts

        bucket_map[k] = bucket_map.get(k, 0.0) + float(h["v"])

    out = [{"t": k, "v": round(v, 2)} for k, v in bucket_map.items()]
    out.sort(key=lambda x: x["t"])
    return out


def dense_series(
    db: Session,
    bid: Optional[str],
    from_ts: int,
    to_ts: int,
    bucket: str = "day",
) -> List[Dict[str, Any]]:
    hourly = get_hourly_series(db, bid, from_ts, to_ts)
    return bucketize(hourly, bucket)


def compare_rows(db: Session, from_ts: int, to_ts: int) -> Dict[str, Dict[str, Any]]:
    """
    Calculates summary stats (sum, count, peak) for every building between from_ts and to_ts.
    """
    stats = (
        db.query(
            EnergyReading.building_id,
            func.sum(EnergyReading.kwh).label("total"),
            func.count(EnergyReading.id).label("cnt"),
            func.max(EnergyReading.kwh).label("peak"),
        )
        .filter(
            EnergyReading.timestamp >= from_ts,
            EnergyReading.timestamp < to_ts,
        )
        .group_by(EnergyReading.building_id)
        .all()
    )

    acc = {}
    for bid, total, cnt, peak in stats:
        acc[bid] = {
            "s": round(float(total or 0.0), 2),
            "n": int(cnt or 0),
            "p": round(float(peak or 0.0), 2),
        }
    return acc


def detect_anomalies(
    db: Session,
    bid: Optional[str] = None,
    days: int = 14,
    now_ts: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Detects unusual energy consumption: z-score > 3 vs baseline same hour-of-week.
    """
    if now_ts is None:
        # Check max timestamp in readings or use current time
        max_ts_db = db.query(func.max(EnergyReading.timestamp)).scalar()
        now_ts = max_ts_db if max_ts_db else int(datetime.now().timestamp() * 1000)

    from_ts = now_ts - (days + 56) * DAY
    cutoff = now_ts - days * DAY

    query = db.query(Building)
    if bid and bid != "*":
        query = query.filter(Building.id == bid)
    buildings = query.all()

    out = []
    for b in buildings:
        readings = (
            db.query(EnergyReading.timestamp, EnergyReading.kwh)
            .filter(
                EnergyReading.building_id == b.id,
                EnergyReading.timestamp >= from_ts,
            )
            .all()
        )
        if not readings:
            continue

        # Group by hour of the week (0 to 167)
        stat: Dict[int, Dict[str, float]] = {}
        for ts, kwh in readings:
            dt = datetime.fromtimestamp(ts / 1000)
            k = dt.weekday() * 24 + dt.hour
            if k not in stat:
                stat[k] = {"n": 0, "s": 0.0, "ss": 0.0}
            stat[k]["n"] += 1
            stat[k]["s"] += float(kwh)
            stat[k]["ss"] += float(kwh * kwh)

        # Check readings in the recent cutoff window
        for ts, kwh in readings:
            if ts < cutoff:
                continue
            dt = datetime.fromtimestamp(ts / 1000)
            k = dt.weekday() * 24 + dt.hour
            st = stat.get(k)
            if not st or st["n"] < 6:
                continue

            mean = st["s"] / st["n"]
            variance = max(0.0, (st["ss"] / st["n"]) - (mean * mean))
            sd = math.sqrt(variance)

            if sd > 2.0 and abs(kwh - mean) > 3.0 * sd:
                z = round((kwh - mean) / sd, 1)
                out.append({
                    "bid": b.id,
                    "building": b.name,
                    "t": ts,
                    "v": round(float(kwh), 1),
                    "mean": round(mean, 1),
                    "sd": round(sd, 1),
                    "z": z,
                })

    out.sort(key=lambda x: x["t"], reverse=True)
    return out
