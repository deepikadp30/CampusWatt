from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import EnergySetting
from backend.schemas import SettingsUpdateSchema
from backend.services import get_or_create_settings

router = APIRouter(prefix="", tags=["Settings"])


def serialize_settings(s: EnergySetting) -> Dict[str, Any]:
    return {
        "campusName": s.campus_name,
        "location": s.location,
        "currency": s.currency,
        "rate": s.rate,
        "demandRate": s.demand_rate,
        "peakThreshold": s.peak_threshold,
        "evCharging": s.ev_charging,
        "evKw": s.ev_kw,
        "userName": s.user_name,
        "role": s.role,
        "theme": s.theme,
        "reduceMotion": s.reduce_motion,
    }


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    setting = get_or_create_settings(db)
    return serialize_settings(setting)


@router.put("/settings")
def update_settings(
    update: SettingsUpdateSchema = Body(...),
    db: Session = Depends(get_db),
):
    setting = get_or_create_settings(db)

    if update.rate is not None:
        if update.rate < 0 or update.rate > 5:
            raise HTTPException(status_code=400, detail="Energy rate must be between 0 and 5.")
        setting.rate = float(update.rate)

    if update.demandRate is not None:
        if update.demandRate < 0 or update.demandRate > 500:
            raise HTTPException(status_code=400, detail="Demand rate must be between 0 and 500.")
        setting.demand_rate = float(update.demandRate)

    if update.peakThreshold is not None:
        if update.peakThreshold <= 0 or update.peakThreshold > 10000:
            raise HTTPException(status_code=400, detail="Peak threshold must be a positive number (kW).")
        setting.peak_threshold = float(update.peakThreshold)

    if update.campusName is not None:
        setting.campus_name = str(update.campusName)[:80]
    if update.location is not None:
        setting.location = str(update.location)[:80]
    if update.currency is not None:
        setting.currency = str(update.currency)[:10]
    if update.userName is not None:
        setting.user_name = str(update.userName)[:80]
    if update.role is not None:
        setting.role = str(update.role)[:80]

    if update.evCharging is not None:
        setting.ev_charging = bool(update.evCharging)
    if update.evKw is not None:
        if update.evKw < 0 or update.evKw > 1000:
            raise HTTPException(status_code=400, detail="EV load must be between 0 and 1000 kW.")
        setting.ev_kw = float(update.evKw)

    if update.theme is not None:
        setting.theme = "dark" if update.theme == "dark" else "light"
    if update.reduceMotion is not None:
        setting.reduce_motion = bool(update.reduceMotion)

    db.commit()
    db.refresh(setting)
    return serialize_settings(setting)
