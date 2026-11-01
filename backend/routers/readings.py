import time
import uuid
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Building, EnergyReading
from backend.schemas import ReadingCreate, ImportRequest
from backend.services import parse_when, import_csv_readings
from backend.analytics import floor_hour, HOUR, DAY
from backend.peak_reduction import fmt_dt

router = APIRouter(prefix="", tags=["Readings"])


def serialize_reading(r: EnergyReading) -> Dict[str, Any]:
    return {
        "id": r.id,
        "b": r.building_id,
        "ts": r.timestamp,
        "kwh": r.kwh,
    }


@router.get("/readings")
def get_readings(
    building_id: Optional[str] = Query(None, alias="buildingId"),
    from_ts: Optional[int] = Query(None, alias="from"),
    to_ts: Optional[int] = Query(None, alias="to"),
    direction: Optional[str] = Query("desc", alias="dir"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100, alias="pageSize"),
    db: Session = Depends(get_db),
):
    query = db.query(EnergyReading)
    if building_id:
        query = query.filter(EnergyReading.building_id == building_id)
    if from_ts is not None:
        query = query.filter(EnergyReading.timestamp >= from_ts)
    if to_ts is not None:
        query = query.filter(EnergyReading.timestamp < to_ts)

    if direction == "asc":
        query = query.order_by(EnergyReading.timestamp.asc())
    else:
        query = query.order_by(EnergyReading.timestamp.desc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    pages = max(1, (total + page_size - 1) // page_size)

    return {
        "items": [serialize_reading(r) for r in items],
        "total": total,
        "page": page,
        "pages": pages,
    }


@router.post("/readings")
def create_reading(r_in: ReadingCreate, db: Session = Depends(get_db)):
    bid = r_in.buildingId or r_in.b
    if not bid:
        raise HTTPException(status_code=400, detail="Please choose a valid building.")

    building = db.query(Building).filter(Building.id == bid).first()
    if not building:
        raise HTTPException(status_code=400, detail="Please choose a valid building.")

    ts_raw = r_in.timestamp if r_in.timestamp is not None else r_in.ts
    ts = parse_when(ts_raw)
    if ts is None:
        raise HTTPException(status_code=400, detail="Timestamp is invalid. Use YYYY-MM-DD HH:MM.")

    ts = floor_hour(ts)
    now_ts = int(time.time() * 1000)
    if ts > now_ts + 24 * HOUR:
        raise HTTPException(status_code=400, detail="Timestamp cannot be more than 24 hours in the future.")

    if r_in.kwh < 0 or r_in.kwh > 100000:
        raise HTTPException(status_code=400, detail="kWh must be a non-negative number.")

    duplicate = (
        db.query(EnergyReading)
        .filter(EnergyReading.building_id == bid, EnergyReading.timestamp == ts)
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate: {building.name} already has a reading at {fmt_dt(ts)}.",
        )

    reading = EnergyReading(
        id=f"r_{uuid.uuid4().hex[:10]}",
        building_id=bid,
        timestamp=ts,
        kwh=round(float(r_in.kwh), 2),
    )
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return serialize_reading(reading)


@router.put("/readings/{reading_id}")
def update_reading(
    reading_id: str,
    r_in: ReadingCreate,
    db: Session = Depends(get_db),
):
    reading = db.query(EnergyReading).filter(EnergyReading.id == reading_id).first()
    if not reading:
        raise HTTPException(status_code=404, detail="Reading not found")

    bid = r_in.buildingId or r_in.b or reading.building_id
    building = db.query(Building).filter(Building.id == bid).first()
    if not building:
        raise HTTPException(status_code=400, detail="Please choose a valid building.")

    ts_raw = r_in.timestamp if r_in.timestamp is not None else r_in.ts
    ts = parse_when(ts_raw) if ts_raw is not None else reading.timestamp
    if ts is None:
        raise HTTPException(status_code=400, detail="Timestamp is invalid. Use YYYY-MM-DD HH:MM.")

    ts = floor_hour(ts)
    now_ts = int(time.time() * 1000)
    if ts > now_ts + 24 * HOUR:
        raise HTTPException(status_code=400, detail="Timestamp cannot be more than 24 hours in the future.")

    if r_in.kwh < 0 or r_in.kwh > 100000:
        raise HTTPException(status_code=400, detail="kWh must be a non-negative number.")

    duplicate = (
        db.query(EnergyReading)
        .filter(
            EnergyReading.building_id == bid,
            EnergyReading.timestamp == ts,
            EnergyReading.id != reading_id,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"Duplicate: {building.name} already has a reading at {fmt_dt(ts)}.",
        )

    reading.building_id = bid
    reading.timestamp = ts
    reading.kwh = round(float(r_in.kwh), 2)
    db.commit()
    db.refresh(reading)
    return serialize_reading(reading)


@router.delete("/readings/{reading_id}")
def delete_reading(reading_id: str, db: Session = Depends(get_db)):
    reading = db.query(EnergyReading).filter(EnergyReading.id == reading_id).first()
    if not reading:
        raise HTTPException(status_code=404, detail="Reading not found")

    db.delete(reading)
    db.commit()
    return {"deleted": True}


@router.post("/readings/import")
def import_readings(payload: ImportRequest, db: Session = Depends(get_db)):
    return import_csv_readings(db, payload.rows)
