import random
import time
from datetime import datetime
from sqlalchemy.orm import Session

from backend.models import (
    Campus,
    Building,
    EnergyReading,
    EnergySetting,
    Alert,
    Recommendation,
    ForecastRecord,
)
from backend.services import get_or_create_settings, scan_alerts_internal
from backend.analytics import floor_hour, HOUR

PROFILES = {
    "Academic": {
        "base": 16,
        "peak": 150,
        "wd": [.05,.05,.05,.05,.05,.05,.15,.45,.75,.9,.9,.62,.66,.85,.85,.86,.7,.45,.3,.2,.13,.09,.07,.05],
        "we": [.05,.05,.05,.05,.05,.05,.07,.1,.16,.22,.24,.2,.14,.12,.1,.1,.08,.07,.06,.05,.05,.05,.05,.05],
    },
    "Laboratory": {
        "base": 22,
        "peak": 130,
        "wd": [.3,.3,.29,.29,.3,.32,.4,.58,.74,.8,.8,.7,.75,.8,.8,.78,.68,.58,.5,.42,.36,.33,.31,.3],
        "we": [.28,.28,.28,.28,.28,.28,.3,.34,.4,.46,.5,.5,.46,.44,.42,.4,.38,.36,.34,.32,.3,.3,.29,.28],
    },
    "Library": {
        "base": 8,
        "peak": 95,
        "wd": [.12,.12,.11,.11,.11,.13,.3,.52,.62,.66,.68,.66,.6,.64,.66,.64,.6,.55,.5,.44,.34,.2,.14,.12],
        "we": [.1,.1,.1,.1,.1,.1,.12,.18,.3,.4,.44,.44,.4,.38,.36,.34,.3,.26,.2,.14,.1,.1,.1,.1],
    },
    "Residence": {
        "base": 20,
        "peak": 170,
        "wd": [.55,.5,.46,.45,.45,.5,.6,.7,.5,.4,.38,.4,.44,.4,.4,.42,.46,.5,.6,.7,.75,.75,.66,.6],
        "we": [.58,.53,.48,.46,.46,.52,.62,.72,.56,.44,.42,.45,.5,.47,.46,.48,.52,.56,.64,.72,.78,.78,.7,.63],
    },
    "Athletic": {
        "base": 7,
        "peak": 110,
        "wd": [.08,.08,.08,.08,.08,.1,.14,.18,.22,.25,.28,.3,.3,.32,.36,.45,.6,.8,.9,.85,.5,.22,.12,.08],
        "we": [.08,.08,.08,.08,.08,.09,.14,.22,.35,.5,.58,.6,.55,.52,.5,.55,.62,.75,.82,.72,.44,.2,.12,.08],
    },
    "Dining": {
        "base": 3,
        "peak": 70,
        "wd": [.08,.06,.05,.05,.06,.15,.6,.85,.7,.3,.55,.95,.9,.45,.25,.25,.5,.9,1,.85,.4,.2,.12,.08],
        "we": [.08,.06,.05,.05,.06,.14,.55,.8,.72,.35,.5,.85,.85,.45,.28,.28,.55,.92,.95,.8,.4,.18,.12,.08],
    },
}

EV_PROFILE = [6,6,6,6,6,6,5,4,10,14,22,22,22,22,22,22,22,14,12,12,12,10,8,6]

BUILDING_SEED = [
    {"id": "b1", "name": "Engineering Hall", "type": "Academic", "area": 5200.0, "occupancy": 900, "hvac": True, "controllable_kw": 0.0, "equipment": "Lecture theatres, computing labs, projectors, ventilation"},
    {"id": "b2", "name": "Science Block", "type": "Laboratory", "area": 4200.0, "occupancy": 350, "hvac": True, "controllable_kw": 90.0, "equipment": "Fume hoods, chillers, centrifuges, environmental chambers"},
    {"id": "b3", "name": "Main Library", "type": "Library", "area": 3800.0, "occupancy": 600, "hvac": True, "controllable_kw": 0.0, "equipment": "HVAC, lighting, server room split units"},
    {"id": "b4", "name": "North Residence", "type": "Residence", "area": 6100.0, "occupancy": 480, "hvac": True, "controllable_kw": 0.0, "equipment": "Dorm HVAC, laundry room; campus EV chargers metered here"},
    {"id": "b5", "name": "Sports Complex", "type": "Athletic", "area": 3400.0, "occupancy": 300, "hvac": True, "controllable_kw": 0.0, "equipment": "Pool heat pumps, arena lighting, gym ventilation"},
    {"id": "b6", "name": "Central Canteen", "type": "Dining", "area": 1500.0, "occupancy": 250, "hvac": False, "controllable_kw": 0.0, "equipment": "Kitchen, refrigeration, dishwashers, extraction fans"},
]


def seed_database(db: Session, clear_existing: bool = True) -> dict:
    """
    Seeds database with labelled sample dataset.
    """
    if clear_existing:
        db.query(EnergyReading).delete()
        db.query(Recommendation).delete()
        db.query(Alert).delete()
        db.query(ForecastRecord).delete()
        db.query(Building).delete()
        db.commit()

    # Ensure Campus and Settings exist
    campus = db.query(Campus).filter(Campus.id == "c1").first()
    if not campus:
        campus = Campus(
            id="c1",
            name="Riverview Technical College",
            location="Riverview",
            config_details="CampusWatt Core Configuration",
        )
        db.add(campus)
        db.commit()

    get_or_create_settings(db)

    # Insert sample buildings
    buildings = []
    for bs in BUILDING_SEED:
        b = Building(
            id=bs["id"],
            campus_id="c1",
            name=bs["name"],
            type=bs["type"],
            area=bs["area"],
            occupancy=bs["occupancy"],
            hvac=bs["hvac"],
            controllable_kw=bs["controllable_kw"],
            equipment=bs["equipment"],
            notes="",
            is_sample=True,
            created_at=int(time.time() * 1000),
        )
        db.add(b)
        buildings.append(b)
    db.commit()

    # Generate 90 days of hourly readings
    now = floor_hour(int(time.time() * 1000))
    start_ts = now - (90 * 24 - 1) * HOUR

    rng = random.Random(42)  # Deterministic seed for reproducible testing
    readings = []
    rid = 1

    for b in buildings:
        p = PROFILES[b.type]
        hot_days = set()
        for d in range(90):
            if rng.random() < 0.18:
                hot_days.add(d)

        for h in range(90 * 24):
            ts = start_ts + h * HOUR
            dt = datetime.fromtimestamp(ts / 1000)
            wd = dt.weekday()  # Monday is 0, Sunday is 6
            is_we = wd in (5, 6)

            curve = p["we"] if is_we else p["wd"]
            wk = 0.85 if is_we else 1.0

            val = (p["base"] + (p["peak"] - p["base"]) * curve[dt.hour]) * wk
            if b.type == "Residence":
                val += EV_PROFILE[dt.hour]

            day_idx = h // 24
            if day_idx in hot_days and 10 <= dt.hour <= 17:
                val *= 1.10

            val *= 1.0 + 0.055 * rng.gauss(0, 1)
            if rng.random() < 0.002:
                val *= 1.8

            kwh_final = round(max(0.5, val), 1)

            readings.append(
                EnergyReading(
                    id=f"r{rid}",
                    building_id=b.id,
                    timestamp=ts,
                    kwh=kwh_final,
                )
            )
            rid += 1

    db.bulk_save_objects(readings)
    db.commit()

    # Run alert scan on seeded data
    alerts_created = scan_alerts_internal(db, peak_days=7, anom_days=14, now_ts=now)

    # Mark all but the first 3 alerts as read
    all_alerts = db.query(Alert).order_by(Alert.timestamp.desc()).all()
    for idx, a in enumerate(all_alerts):
        if idx > 2:
            a.read = True
    db.commit()

    return {
        "ok": True,
        "sample": True,
        "buildings": len(buildings),
        "readings": len(readings),
        "alerts": alerts_created,
    }
