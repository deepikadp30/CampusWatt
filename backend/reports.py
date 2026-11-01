from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.models import Building
from backend.services import get_or_create_settings, parse_when
from backend.analytics import (
    start_of_day,
    start_of_week,
    start_of_month,
    compare_rows,
    get_hourly_series,
    DAY,
)
from backend.peak_reduction import find_windows


def generate_report(db: Session, period: str = "day", date_str: Optional[str] = None) -> Dict[str, Any]:
    ref_ts = parse_when(date_str) or int(datetime.now().timestamp() * 1000)
    settings = get_or_create_settings(db)
    rate = settings.rate

    if period == "week":
        from_ts = start_of_week(ref_ts)
        to_ts = from_ts + 7 * DAY
        label = "Weekly"
    elif period == "month":
        from_ts = start_of_month(ref_ts)
        dt_from = datetime.fromtimestamp(from_ts / 1000)
        # Next month start
        if dt_from.month == 12:
            dt_to = dt_from.replace(year=dt_from.year + 1, month=1, day=1)
        else:
            dt_to = dt_from.replace(month=dt_from.month + 1, day=1)
        to_ts = int(dt_to.timestamp() * 1000)
        label = "Monthly"
    else:
        from_ts = start_of_day(ref_ts)
        to_ts = from_ts + DAY
        label = "Daily"

    acc = compare_rows(db, from_ts, to_ts)
    campus_kwh = sum(v["s"] for v in acc.values())

    buildings = db.query(Building).all()
    b_rows = []
    for b in buildings:
        a = acc.get(b.id, {"s": 0.0, "p": 0.0, "n": 0})
        kwh = round(a["s"], 1)
        peak = round(a["p"], 1)
        cost = round(kwh * rate, 2)
        share = round((kwh / campus_kwh * 100.0), 1) if campus_kwh > 0 else 0.0
        b_rows.append({
            "id": b.id,
            "name": b.name,
            "type": b.type,
            "kwh": kwh,
            "peak": peak,
            "cost": cost,
            "share": share,
        })

    b_rows.sort(key=lambda x: x["kwh"], reverse=True)

    hrs = get_hourly_series(db, "*", from_ts, to_ts)
    valid_hrs = [h for h in hrs if h.get("v") is not None]
    windows = find_windows(valid_hrs, settings.peak_threshold)

    peak_campus = max([v["p"] for v in acc.values()], default=0.0)

    return {
        "period": period,
        "label": label,
        "from": from_ts,
        "to": to_ts,
        "rate": rate,
        "buildings": b_rows,
        "campus": {
            "kwh": round(campus_kwh, 1),
            "cost": round(campus_kwh * rate, 2),
            "peak": round(peak_campus, 1),
            "windows": len(windows),
        },
    }
