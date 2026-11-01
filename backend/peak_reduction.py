import uuid
import time
from datetime import datetime
from typing import List, Dict, Any, Callable

HOUR = 3600 * 1000


def find_windows(hours: List[Dict[str, Any]], threshold: float) -> List[Dict[str, Any]]:
    """
    Finds contiguous windows of time where energy demand exceeds peak threshold.
    """
    out = []
    cur = None

    def finish(c):
        c["end"] = c["hours"][-1]["t"]
        c["peak"] = round(max(x["v"] for x in c["hours"]), 1)
        excess = sum(max(0.0, x["v"] - threshold) for x in c["hours"])
        c["excess"] = round(excess, 1)
        c["h"] = len(c["hours"])
        out.append(c)

    for h in hours:
        val = h.get("v")
        if val is not None and val > threshold:
            if cur is None:
                cur = {"start": h["t"], "hours": []}
            cur["hours"].append(h)
        elif cur is not None:
            finish(cur)
            cur = None

    if cur is not None:
        finish(cur)

    return out


def _safe_dt(ts_ms: int) -> datetime:
    sec = max(ts_ms, 86400000) / 1000.0
    try:
        return datetime.fromtimestamp(sec)
    except Exception:
        from datetime import timezone
        return datetime.fromtimestamp(sec, tz=timezone.utc).replace(tzinfo=None)


def fmt_t(ts_ms: int) -> str:
    dt = _safe_dt(ts_ms)
    return dt.strftime("%I:%M %p").lstrip("0")


def fmt_d(ts_ms: int) -> str:
    dt = _safe_dt(ts_ms)
    return dt.strftime("%b %d, %Y")
    dt = datetime.fromtimestamp(ts_ms / 1000)
    return dt.strftime("%b %d, %Y")


def fmt_dt(ts_ms: int) -> str:
    return f"{fmt_d(ts_ms)} · {fmt_t(ts_ms)}"


def build_recommendations(
    windows: List[Dict[str, Any]],
    source_label: str,
    settings: Any,
    buildings: List[Any],
    recent_avg_kw_fn: Callable[[str, int], float],
) -> List[Dict[str, Any]]:
    """
    Rule-based transparent peak reduction recommendation engine.
    """
    labs = [b for b in buildings if getattr(b, "type", "") == "Laboratory" and getattr(b, "controllable_kw", 0) > 0]
    hvac_buildings = [b for b in buildings if getattr(b, "hvac", True)]
    lit_buildings = [b for b in buildings if getattr(b, "type", "") in ["Academic", "Library", "Athletic"]]

    recs = []

    def priority_for(w):
        ratio = w["peak"] / settings.peak_threshold
        if ratio >= 1.1:
            return "High"
        if ratio >= 1.03:
            return "Medium"
        return "Low"

    for wi, w in enumerate(windows[:6]):
        pri = priority_for(w)
        base = {
            "source": source_label,
            "windowStart": w["start"],
            "windowEnd": w["end"],
            "hours": w["h"],
            "priority": pri,
            "windowPeak": round(float(w["peak"]), 1),
            "status": "pending",
            "measuredKwh": None,
            "createdAt": int(time.time() * 1000),
        }

        # 1. EV Charging Shift
        if getattr(settings, "ev_charging", True):
            ev_kw = getattr(settings, "ev_kw", 22.0)
            shifted_kw = round(ev_kw * 0.6, 1)
            recs.append({
                "id": f"rec_{uuid.uuid4().hex[:10]}",
                "type": "ev",
                **base,
                "title": "Shift EV charging to overnight",
                "detail": f"Move ~{round(shifted_kw)} kW of EV charging (parking garage) from the peak window to 00:00–06:00 via the charger scheduler.",
                "buildingLabel": "Central parking (metered under North Residence)",
                "estKwh": round(shifted_kw * w["h"], 1),
                "kwRed": shifted_kw,
                "difficulty": "Easy",
            })

        # 2. Laboratory Equipment Deferral
        if labs and wi < 3:
            total_ck = sum(getattr(b, "controllable_kw", 0) for b in labs)
            lab_kw = round(total_ck * 0.7, 1)
            lab_names = ", ".join(getattr(b, "name", "") for b in labs)
            recs.append({
                "id": f"rec_{uuid.uuid4().hex[:10]}",
                "type": "lab",
                **base,
                "title": "Schedule non-critical lab equipment off-peak",
                "detail": f"Pre-run or defer ~{lab_kw} kW of schedulable lab load (drying ovens, test rigs, non-essential fume hoods) outside {fmt_t(w['start'])}–{fmt_t(w['end'] + HOUR)}.",
                "buildingLabel": lab_names,
                "estKwh": round(lab_kw * w["h"], 1),
                "kwRed": lab_kw,
                "difficulty": "Medium",
            })

        # 3. HVAC Optimisation
        if hvac_buildings:
            hvac_kw_est = sum(recent_avg_kw_fn(getattr(b, "id", ""), 14) * 0.45 for b in hvac_buildings)
            hvac_kw = round(hvac_kw_est * 0.12, 1)
            hvac_label = ", ".join(getattr(b, "name", "") for b in hvac_buildings[:3])
            if len(hvac_buildings) > 3:
                hvac_label += f" +{len(hvac_buildings) - 3}"
            recs.append({
                "id": f"rec_{uuid.uuid4().hex[:10]}",
                "type": "hvac",
                **base,
                "title": "Optimise HVAC: pre-cool + set-point +1–2 °C",
                "detail": f"Assuming HVAC ≈ 45% of building load, a 12% reduction during the window via pre-cooling before {fmt_t(w['start'])} and higher set-points during it.",
                "buildingLabel": hvac_label,
                "estKwh": round(hvac_kw * w["h"], 1),
                "kwRed": hvac_kw,
                "difficulty": "Medium",
            })

        # 4. Low-occupancy Zone Lighting Trim
        dt_start = datetime.fromtimestamp(w["start"] / 1000)
        if 8 <= dt_start.hour <= 18 and lit_buildings:
            lit_kw_est = sum(recent_avg_kw_fn(getattr(b, "id", ""), 14) for b in lit_buildings)
            lit_kw = round(lit_kw_est * 0.04, 1)
            lit_label = ", ".join(getattr(b, "name", "") for b in lit_buildings[:3])
            recs.append({
                "id": f"rec_{uuid.uuid4().hex[:10]}",
                "type": "lighting",
                **base,
                "title": "Trim non-essential lighting in low-occupancy zones",
                "detail": "~4% lighting reduction in corridors, stairwells and low-occupancy areas during the window (daylight harvesting + occupancy sensors).",
                "buildingLabel": lit_label,
                "estKwh": round(lit_kw * w["h"], 1),
                "kwRed": lit_kw,
                "difficulty": "Easy",
            })

    return recs
