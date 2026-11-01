import json
import time
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.database import get_db
from backend.models import EnergyReading, ForecastRecord
from backend.schemas import ForecastRequest
from backend.services import get_or_create_settings
from backend.analytics import (
    get_hourly_series,
    dense_series,
    HOUR,
    DAY,
)
from backend.forecasting import run_forecast_model
from backend.peak_reduction import find_windows

router = APIRouter(prefix="", tags=["Forecasting"])


@router.get("/forecast/latest")
def get_latest_forecast(
    building_id: str = Query("*", alias="buildingId"),
    grain: str = Query("hour"),
    db: Session = Depends(get_db),
):
    rec = (
        db.query(ForecastRecord)
        .filter(
            ForecastRecord.building_id == building_id,
            ForecastRecord.grain == grain,
        )
        .order_by(ForecastRecord.created_at.desc())
        .first()
    )
    if not rec:
        return None
    try:
        return json.loads(rec.data_json)
    except Exception:
        return None


@router.post("/forecast")
def create_forecast(
    req: ForecastRequest,
    db: Session = Depends(get_db),
):
    bid = req.buildingId or "*"
    grain = req.grain or "hour"
    settings = get_or_create_settings(db)

    # Use max timestamp in DB if readings exist, or current time
    max_ts = db.query(func.max(EnergyReading.timestamp)).scalar()
    now_ts = max_ts if max_ts else int(time.time() * 1000)

    if grain == "day":
        raw = dense_series(db, bid, now_ts - 120 * DAY, now_ts, "day")
        m = 7
        step = DAY
        unit = "kWh/day"
        horizon = min(req.horizon or 7, 14)
    else:
        raw = get_hourly_series(db, bid, now_ts - 90 * DAY, now_ts)
        m = 168
        step = HOUR
        unit = "kW"
        horizon = min(req.horizon or 48, 168)

    valid_pts = [p for p in raw if p.get("v") is not None]
    if not valid_pts:
        raise HTTPException(
            status_code=400,
            detail="No historical readings available for this selection.",
        )

    result = run_forecast_model(
        raw,
        step_ms=step,
        m=m,
        horizon=horizon,
        peak_threshold=settings.peak_threshold,
    )

    created_at = int(time.time() * 1000)
    result["unit"] = unit
    result["grain"] = grain
    result["horizon"] = horizon
    result["buildingId"] = bid
    result["createdAt"] = created_at
    result["history"] = raw[-30:] if grain == "day" else raw[-336:]
    result["fittedWin"] = result["fitted"][-30:] if grain == "day" else result["fitted"][-336:]

    if grain == "hour":
        forecast_pts = [{"t": f["t"], "v": f["y"]} for f in result["forecast"]]
        windows = find_windows(forecast_pts, settings.peak_threshold)
        peaks = []
        for w in windows:
            hi_upper = max(
                (f["hi"] for f in result["forecast"] if f["t"] in [h["t"] for h in w["hours"]]),
                default=w["peak"],
            )
            peaks.append({
                "start": w["start"],
                "end": w["end"],
                "h": w["h"],
                "peak": w["peak"],
                "excess": w["excess"],
                "hiUpper": round(hi_upper, 1),
            })
        peaks.sort(key=lambda x: x["peak"], reverse=True)
        result["peaks"] = peaks
        result["peakDay"] = None
    else:
        result["peaks"] = []
        peak_day = max(result["forecast"], key=lambda f: f["y"], default=result["forecast"][0])
        result["peakDay"] = peak_day

    # Persist in DB
    record = ForecastRecord(
        building_id=bid,
        grain=grain,
        horizon=horizon,
        unit=unit,
        created_at=created_at,
        data_json=json.dumps(result),
    )
    db.add(record)
    db.commit()

    return result
