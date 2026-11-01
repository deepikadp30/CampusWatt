import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.database import get_db
from backend.models import Building, EnergyReading
from backend.schemas import BuildingCreate, BuildingUpdate

router = APIRouter(prefix="", tags=["Buildings"])


def serialize_building(b: Building) -> Dict[str, Any]:
    return {
        "id": b.id,
        "name": b.name,
        "type": b.type,
        "area": b.area,
        "occupancy": b.occupancy,
        "hvac": b.hvac,
        "controllableKw": b.controllable_kw,
        "equipment": b.equipment or "",
        "notes": b.notes or "",
        "sample": b.is_sample,
    }


@router.get("/buildings/all")
def get_all_buildings_brief(db: Session = Depends(get_db)):
    buildings = db.query(Building.id, Building.name, Building.type).order_by(Building.name.asc()).all()
    return [{"id": b.id, "name": b.name, "type": b.type} for b in buildings]


@router.get("/buildings")
def get_buildings(
    search: Optional[str] = None,
    sort: Optional[str] = "name",
    direction: Optional[str] = Query("asc", alias="dir"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100, alias="pageSize"),
    db: Session = Depends(get_db),
):
    query = db.query(Building)
    if search:
        s = f"%{search.strip().lower()}%"
        query = query.filter(
            func.lower(Building.name).like(s) | func.lower(Building.type).like(s)
        )

    # Dynamic sorting
    sort_attr = getattr(Building, sort, Building.name)
    if sort == "controllableKw":
        sort_attr = Building.controllable_kw

    if direction == "desc":
        query = query.order_by(sort_attr.desc())
    else:
        query = query.order_by(sort_attr.asc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    pages = max(1, (total + page_size - 1) // page_size)

    return {
        "items": [serialize_building(b) for b in items],
        "total": total,
        "page": page,
        "pages": pages,
    }


@router.get("/buildings/{building_id}")
def get_building_by_id(building_id: str, db: Session = Depends(get_db)):
    b = db.query(Building).filter(Building.id == building_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Building not found")
    return serialize_building(b)


@router.post("/buildings")
def create_building(b_in: BuildingCreate, db: Session = Depends(get_db)):
    name = b_in.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Building name is required.")
    if len(name) > 60:
        raise HTTPException(status_code=400, detail="Building name must be 60 characters or fewer.")

    exists = db.query(Building).filter(func.lower(Building.name) == name.lower()).first()
    if exists:
        raise HTTPException(status_code=400, detail="A building with this name already exists.")

    if b_in.area <= 0 or b_in.area > 1_000_000:
        raise HTTPException(status_code=400, detail="Area must be a positive number (m²).")
    if b_in.occupancy < 0:
        raise HTTPException(status_code=400, detail="Occupancy must be a non-negative whole number.")
    if b_in.controllableKw < 0 or b_in.controllableKw > 5000:
        raise HTTPException(status_code=400, detail="Controllable load must be between 0 and 5000 kW.")

    building = Building(
        id=f"b_{uuid.uuid4().hex[:8]}",
        name=name,
        type=b_in.type or "Other",
        area=float(b_in.area),
        occupancy=int(b_in.occupancy),
        hvac=bool(b_in.hvac),
        controllable_kw=float(b_in.controllableKw),
        equipment=(b_in.equipment or "")[:500],
        notes=(b_in.notes or "")[:500],
        is_sample=False,
    )
    db.add(building)
    db.commit()
    db.refresh(building)
    return serialize_building(building)


@router.put("/buildings/{building_id}")
def update_building(
    building_id: str,
    b_in: BuildingUpdate,
    db: Session = Depends(get_db),
):
    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    name = b_in.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Building name is required.")
    if len(name) > 60:
        raise HTTPException(status_code=400, detail="Building name must be 60 characters or fewer.")

    exists = (
        db.query(Building)
        .filter(func.lower(Building.name) == name.lower(), Building.id != building_id)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="A building with this name already exists.")

    if b_in.area <= 0 or b_in.area > 1_000_000:
        raise HTTPException(status_code=400, detail="Area must be a positive number (m²).")
    if b_in.occupancy < 0:
        raise HTTPException(status_code=400, detail="Occupancy must be a non-negative whole number.")
    if b_in.controllableKw < 0 or b_in.controllableKw > 5000:
        raise HTTPException(status_code=400, detail="Controllable load must be between 0 and 5000 kW.")

    building.name = name
    building.type = b_in.type or "Other"
    building.area = float(b_in.area)
    building.occupancy = int(b_in.occupancy)
    building.hvac = bool(b_in.hvac)
    building.controllable_kw = float(b_in.controllableKw)
    building.equipment = (b_in.equipment or "")[:500]
    building.notes = (b_in.notes or "")[:500]

    db.commit()
    db.refresh(building)
    return serialize_building(building)


@router.delete("/buildings/{building_id}")
def delete_building(building_id: str, db: Session = Depends(get_db)):
    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    # Readings will cascade delete due to DB relationship & FK
    db.delete(building)
    db.commit()
    return {"deleted": True}
