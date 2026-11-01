from typing import Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Alert
from backend.schemas import AlertUpdate
from backend.services import scan_alerts_internal

router = APIRouter(prefix="", tags=["Alerts"])


def serialize_alert(a: Alert) -> Dict[str, Any]:
    return {
        "id": a.id,
        "type": a.type,
        "severity": a.severity,
        "message": a.message,
        "ts": a.timestamp,
        "read": a.read,
        "key": a.dedupe_key,
    }


@router.get("/alerts")
def get_alerts(db: Session = Depends(get_db)):
    alerts = db.query(Alert).order_by(Alert.timestamp.desc()).all()
    unread_count = sum(1 for a in alerts if not a.read)
    return {
        "items": [serialize_alert(a) for a in alerts],
        "unread": unread_count,
    }


@router.post("/alerts/scan")
def scan_alerts(
    peak_days: int = Query(7, alias="peakDays"),
    anom_days: int = Query(14, alias="anomDays"),
    db: Session = Depends(get_db),
):
    created = scan_alerts_internal(db, peak_days, anom_days)
    return {"created": created}


@router.patch("/alerts/{alert_id}")
def update_alert(
    alert_id: str,
    update: AlertUpdate = Body(...),
    db: Session = Depends(get_db),
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if update.read is not None:
        alert.read = bool(update.read)
    db.commit()
    db.refresh(alert)
    return serialize_alert(alert)


@router.post("/alerts/read-all")
def mark_all_alerts_read(db: Session = Depends(get_db)):
    db.query(Alert).update({Alert.read: True})
    db.commit()
    return {"ok": True}


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()
    return {"deleted": True}
