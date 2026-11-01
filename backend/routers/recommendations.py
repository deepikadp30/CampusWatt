import json
import time
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.database import get_db
from backend.models import Recommendation, ForecastRecord, Building, EnergyReading
from backend.schemas import (
    RecommendationResponse,
    RecommendationDetectRequest,
    RecommendationUpdate,
)
from backend.services import get_or_create_settings, get_recent_avg_kw
from backend.analytics import get_hourly_series, DAY
from backend.peak_reduction import find_windows, build_recommendations, fmt_dt

router = APIRouter(prefix="", tags=["Recommendations"])


def serialize_rec(r: Recommendation) -> Dict[str, Any]:
    return {
        "id": r.id,
        "type": r.type,
        "source": r.source,
        "title": r.title,
        "detail": r.detail,
        "buildingLabel": r.building_label,
        "priority": r.priority,
        "status": r.status,
        "difficulty": r.difficulty,
        "windowStart": r.window_start,
        "windowEnd": r.window_end,
        "hours": r.hours,
        "windowPeak": r.window_peak,
        "estKwh": r.est_kwh,
        "kwRed": r.kw_red,
        "measuredKwh": r.measured_kwh,
        "createdAt": r.created_at,
    }


@router.get("/recommendations")
def get_recommendations(db: Session = Depends(get_db)):
    recs = db.query(Recommendation).all()
    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    sorted_recs = sorted(
        recs,
        key=lambda x: (priority_order.get(x.priority, 3), -x.created_at),
    )
    return [serialize_rec(r) for r in sorted_recs]


@router.post("/recommendations/detect")
def detect_recommendations(
    req: RecommendationDetectRequest,
    db: Session = Depends(get_db),
):
    settings = get_or_create_settings(db)
    source = req.source or "recent"

    if source == "forecast":
        fc_rec = (
            db.query(ForecastRecord)
            .filter(
                ForecastRecord.building_id == "*",
                ForecastRecord.grain == "hour",
            )
            .order_by(ForecastRecord.created_at.desc())
            .first()
        )
        if not fc_rec:
            raise HTTPException(
                status_code=400,
                detail="No campus forecast available yet — run a forecast first, or detect from recent actuals.",
            )
        data = json.loads(fc_rec.data_json)
        hours = [{"t": f["t"], "v": f["y"]} for f in data.get("forecast", [])]
        label = f"Forecast · {fmt_dt(fc_rec.created_at)}"
    else:
        max_ts = db.query(func.max(EnergyReading.timestamp)).scalar()
        now_ts = max_ts if max_ts else int(time.time() * 1000)
        hours = get_hourly_series(db, "*", now_ts - 7 * DAY, now_ts)
        label = "Recent actuals · last 7 days"

    windows = find_windows(hours, settings.peak_threshold)
    if not windows:
        raise HTTPException(
            status_code=400,
            detail=f"No demand periods above the {settings.peak_threshold} kW threshold were found in this source.",
        )

    # Delete existing pending recommendations
    db.query(Recommendation).filter(Recommendation.status == "pending").delete()

    buildings = db.query(Building).all()

    def avg_kw_fn(bid: str, days: int = 14) -> float:
        return get_recent_avg_kw(db, bid, days)

    rec_dicts = build_recommendations(windows, label, settings, buildings, avg_kw_fn)

    new_recs = []
    for rd in rec_dicts:
        rec = Recommendation(
            id=rd["id"],
            type=rd["type"],
            source=rd["source"],
            title=rd["title"],
            detail=rd["detail"],
            building_label=rd["buildingLabel"],
            priority=rd["priority"],
            status=rd["status"],
            difficulty=rd["difficulty"],
            window_start=rd["windowStart"],
            window_end=rd["windowEnd"],
            hours=rd["hours"],
            window_peak=rd["windowPeak"],
            est_kwh=rd["estKwh"],
            kw_red=rd["kwRed"],
            measured_kwh=rd["measuredKwh"],
            created_at=rd["createdAt"],
        )
        new_recs.append(rec)
        db.add(rec)

    db.commit()

    return {
        "count": len(new_recs),
        "label": label,
    }


@router.patch("/recommendations/{rec_id}")
def update_recommendation(
    rec_id: str,
    update_data: RecommendationUpdate = Body(...),
    db: Session = Depends(get_db),
):
    rec = db.query(Recommendation).filter(Recommendation.id == rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    if update_data.status is not None:
        rec.status = update_data.status

    if update_data.measuredKwh is not None:
        val = update_data.measuredKwh
        if val == "" or val is None:
            rec.measured_kwh = None
        else:
            rec.measured_kwh = round(float(val), 2)

    db.commit()
    db.refresh(rec)
    return serialize_rec(rec)
