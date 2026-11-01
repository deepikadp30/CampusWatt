import time
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.database import get_db
from backend.models import Building, EnergyReading, Recommendation, Alert
from backend.services import get_or_create_settings
from backend.analytics import (
    get_hourly_series,
    dense_series,
    compare_rows,
    HOUR,
    DAY,
)
from backend.peak_reduction import find_windows

router = APIRouter(prefix="", tags=["Overview"])


@router.get("/overview")
def get_overview(
    from_ts: int = Query(..., alias="from"),
    to_ts: int = Query(..., alias="to"),
    bucket: str = Query("day"),
    db: Session = Depends(get_db),
):
    settings = get_or_create_settings(db)
    rate = settings.rate

    hrs = get_hourly_series(db, "*", from_ts, to_ts)
    valid_hrs = [h for h in hrs if h.get("v") is not None]

    kwh = round(sum(h["v"] for h in valid_hrs), 1)

    peak_kw = 0.0
    peak_ts = None
    for h in valid_hrs:
        if h["v"] > peak_kw:
            peak_kw = h["v"]
            peak_ts = h["t"]
    peak_kw = round(peak_kw, 1)

    # Prior period comparison
    span = to_ts - from_ts
    prev_hrs = get_hourly_series(db, "*", from_ts - span, from_ts)
    prev_valid = [h for h in prev_hrs if h.get("v") is not None]
    prev_kwh = round(sum(h["v"] for h in prev_valid), 1)
    delta_pct = (
        round(((kwh - prev_kwh) / prev_kwh) * 100.0, 1) if prev_kwh > 0 else None
    )

    # Building comparison
    acc = compare_rows(db, from_ts, to_ts)
    buildings = db.query(Building).all()
    compare = []
    for b in buildings:
        a = acc.get(b.id)
        total = round(a["s"], 1) if a else 0.0
        intensity = round(total / b.area, 2) if b.area and b.area > 0 else 0.0
        if total > 0:
            compare.append({
                "id": b.id,
                "name": b.name,
                "type": b.type,
                "total": total,
                "intensity": intensity,
            })
    compare.sort(key=lambda x: x["total"], reverse=True)
    compare_total = round(sum(c["total"] for c in compare), 1)

    # Recommendations
    acted_recs = (
        db.query(Recommendation)
        .filter(Recommendation.status.in_(["accepted", "completed"]))
        .all()
    )
    savings_est = round(sum(r.est_kwh for r in acted_recs) * rate, 2)
    savings_meas = round(sum(r.measured_kwh or 0.0 for r in acted_recs) * rate, 2)

    # Peak windows
    windows = find_windows(valid_hrs, settings.peak_threshold)
    windows.sort(key=lambda x: x["peak"], reverse=True)

    # Alerts
    alerts_query = db.query(Alert).order_by(Alert.timestamp.desc())
    alerts_all = alerts_query.all()
    recent_alerts = [
        {
            "id": a.id,
            "type": a.type,
            "severity": a.severity,
            "message": a.message,
            "ts": a.timestamp,
            "read": a.read,
            "key": a.dedupe_key,
        }
        for a in alerts_all[:5]
    ]
    unread_count = sum(1 for a in alerts_all if not a.read)

    # Current demand at latest recorded hour
    current_kw = 0.0
    current_ts = None
    max_ts = db.query(func.max(EnergyReading.timestamp)).scalar()
    if max_ts:
        current_ts = max_ts
        latest_sum = (
            db.query(func.sum(EnergyReading.kwh))
            .filter(EnergyReading.timestamp == max_ts)
            .scalar()
        )
        current_kw = round(float(latest_sum or 0.0), 1)

    # Ribbon series (last 48 recorded hours)
    now_ts = int(time.time() * 1000)
    ribbon_end = max(now_ts, current_ts or now_ts)
    ribbon_start = ribbon_end - 48 * HOUR
    ribbon = get_hourly_series(db, "*", ribbon_start, ribbon_end)

    return {
        "summary": {
            "kwh": kwh,
            "cost": round(kwh * rate, 2),
            "peakKw": peak_kw,
            "peakTs": peak_ts,
            "currentKw": current_kw,
            "currentTs": current_ts,
            "prevKwh": prev_kwh,
            "deltaPct": delta_pct,
            "savingsEst": savings_est,
            "savingsMeas": savings_meas,
        },
        "series": dense_series(db, "*", from_ts, to_ts, bucket),
        "ribbon": ribbon,
        "compare": compare,
        "compareTotal": compare_total,
        "windows": windows[:4],
        "alerts": {
            "items": recent_alerts,
            "unread": unread_count,
        },
        "threshold": settings.peak_threshold,
    }
