from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import Building
from backend.services import get_or_create_settings
from backend.analytics import (
    dense_series,
    compare_rows,
    detect_anomalies,
)

router = APIRouter(prefix="", tags=["Analytics"])


@router.get("/series")
def get_series(
    building_id: Optional[str] = Query("*", alias="buildingId"),
    from_ts: int = Query(..., alias="from"),
    to_ts: int = Query(..., alias="to"),
    bucket: str = Query("day"),
    db: Session = Depends(get_db),
):
    return dense_series(db, building_id or "*", from_ts, to_ts, bucket)


@router.get("/analytics")
def get_analytics(
    request: Request,
    from_ts: int = Query(..., alias="from"),
    to_ts: int = Query(..., alias="to"),
    bucket: str = Query("day"),
    db: Session = Depends(get_db),
):
    # Support both ?ids=b1&ids=b2 and ?ids[]=b1 or comma-separated
    raw_ids = request.query_params.getlist("ids") or request.query_params.getlist("ids[]")
    ids = []
    for item in raw_ids:
        if "," in item:
            ids.extend(x.strip() for x in item.split(",") if x.strip())
        elif item.strip():
            ids.append(item.strip())

    settings = get_or_create_settings(db)
    rate = settings.rate

    series_data = []
    if not ids:
        series_data.append({
            "bid": "*",
            "points": dense_series(db, "*", from_ts, to_ts, bucket),
        })
    else:
        for bid in ids:
            series_data.append({
                "bid": bid,
                "points": dense_series(db, bid, from_ts, to_ts, bucket),
            })

    want_set = set(ids) if ids else None
    acc = compare_rows(db, from_ts, to_ts)

    buildings_query = db.query(Building)
    if want_set:
        buildings_query = buildings_query.filter(Building.id.in_(want_set))
    buildings = buildings_query.all()

    rows = []
    for b in buildings:
        a = acc.get(b.id, {"s": 0.0, "n": 0, "p": 0.0})
        total = round(a["s"], 1)
        n = a["n"]
        avg = round(total / n, 2) if n > 0 else 0.0
        peak = round(a["p"], 1)
        intensity = round(total / b.area, 2) if b.area and b.area > 0 else 0.0
        cost = round(total * rate, 2)
        rows.append({
            "id": b.id,
            "name": b.name,
            "type": b.type,
            "area": b.area,
            "total": total,
            "avg": avg,
            "peak": peak,
            "intensity": intensity,
            "cost": cost,
        })

    total_all = round(sum(r["total"] for r in rows), 1)
    for r in rows:
        r["share"] = round((r["total"] / total_all * 100.0), 1) if total_all > 0 else 0.0

    anomalies = detect_anomalies(db, None, days=14)

    return {
        "series": series_data,
        "rows": rows,
        "total": total_all,
        "anomalies": anomalies,
    }
