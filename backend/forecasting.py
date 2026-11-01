import math
from typing import List, Dict, Any, Optional, Tuple
from fastapi import HTTPException


def interp_gaps(pts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Linearly interpolate missing values (None / null) in a time series."""
    out = [dict(p) for p in pts]
    n = len(out)
    if n == 0:
        return out

    null_indices = [i for i, p in enumerate(out) if p.get("v") is None]
    for i in null_indices:
        a = i - 1
        b = i + 1
        while a >= 0 and out[a].get("v") is None:
            a -= 1
        while b < n and out[b].get("v") is None:
            b += 1

        if a >= 0 and b < n:
            val_a = out[a]["v"]
            val_b = out[b]["v"]
            interp = val_a + (val_b - val_a) * (i - a) / (b - a)
            out[i]["v"] = round(float(interp), 2)
        elif a >= 0:
            out[i]["v"] = round(float(out[a]["v"]), 2)
        elif b < n:
            out[i]["v"] = round(float(out[b]["v"]), 2)
        else:
            out[i]["v"] = 0.0

    return out


def hw_fit(y: List[float], m: int, al: float, be: float, ga: float) -> Optional[Dict[str, Any]]:
    """
    Fits an Additive Holt-Winters model on series y with seasonality m.
    """
    n = len(y)
    if n < 2 * m + 2:
        return None

    seasons = n // m
    s_m = []
    for s in range(seasons):
        s_sum = sum(y[s * m + i] for i in range(m))
        s_m.append(s_sum / m)

    seas = [0.0] * m
    for i in range(m):
        sum_seas = sum(y[s * m + i] - s_m[s] for s in range(seasons))
        seas[i] = sum_seas / seasons

    lvl = s_m[0]
    tr = (s_m[1] - s_m[0]) / m if seasons > 1 else 0.0
    fitted = [None] * n

    for t in range(n):
        so = seas[t % m]
        pl = lvl
        fitted[t] = lvl + tr + so
        lvl = al * (y[t] - so) + (1.0 - al) * (pl + tr)
        tr = be * (lvl - pl) + (1.0 - be) * tr
        seas[t % m] = ga * (y[t] - lvl) + (1.0 - ga) * so

    return {
        "lvl": lvl,
        "tr": tr,
        "seas": seas,
        "fitted": fitted,
        "n": n,
        "m": m,
    }


def hw_forecast(model: Dict[str, Any], h: int) -> List[float]:
    """Forecasts h steps forward from fitted Holt-Winters model."""
    lvl = model["lvl"]
    tr = model["tr"]
    seas = model["seas"]
    n = model["n"]
    m = model["m"]

    out = []
    for i in range(1, h + 1):
        idx = (n + i - 1) % m
        val = lvl + i * tr + seas[idx]
        out.append(float(val))
    return out


def mae_err(p: List[float], a: List[float]) -> float:
    s = 0.0
    n = 0
    for pred, act in zip(p, a):
        if pred is not None:
            s += abs(pred - act)
            n += 1
    return s / n if n > 0 else float("nan")


def mape_err(p: List[float], a: List[float]) -> float:
    s = 0.0
    n = 0
    for pred, act in zip(p, a):
        if pred is not None and act >= 0.5:
            s += abs((pred - act) / act)
            n += 1
    return (100.0 * s / n) if n > 0 else float("nan")


def run_forecast_model(
    raw: List[Dict[str, Any]],
    step_ms: int,
    m: int,
    horizon: int,
    peak_threshold: float = 450.0,
) -> Dict[str, Any]:
    """
    Executes additive Holt-Winters with parameter grid search and backtesting.
    """
    pts = [p for p in interp_gaps(raw) if p.get("v") is not None]
    y = [float(p["v"]) for p in pts]
    n = len(y)

    if n < 2 * m + 24:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough history for this model ({n} points, need at least {2 * m + 24}) — add more readings or pick a shorter seasonality.",
        )

    train = y[: n - m]
    test = y[n - m :]

    best = None
    alpha_grid = [0.2, 0.35, 0.5]
    beta_grid = [0.02, 0.08, 0.15]
    gamma_grid = [0.1, 0.3, 0.5]

    for al in alpha_grid:
        for be in beta_grid:
            for ga in gamma_grid:
                model = hw_fit(train, m, al, be, ga)
                if not model:
                    continue
                pred = hw_forecast(model, m)
                err = mae_err(pred, test)
                if best is None or err < best["e"]:
                    best = {"e": err, "al": al, "be": be, "ga": ga}

    if not best:
        raise HTTPException(status_code=500, detail="Model fitting failed for this dataset.")

    # Evaluate on held-out test season
    hold_model = hw_fit(train, m, best["al"], best["be"], best["ga"])
    hold_f = hw_forecast(hold_model, m)
    errs = [pred - act for pred, act in zip(hold_f, test)]
    sd = math.sqrt(sum(e * e for e in errs) / len(errs)) if errs else 1.0

    naive_pred = [train[len(train) - m + i] for i in range(len(test))]
    naive_mae = mae_err(naive_pred, test)
    mae = mae_err(hold_f, test)
    rmse = math.sqrt(sum(e * e for e in errs) / len(errs)) if errs else 0.0
    mape = mape_err(hold_f, test)
    skill = ((naive_mae - mae) / naive_mae * 100.0) if naive_mae else 0.0

    # Fit on all y with winning parameters
    full_model = hw_fit(y, m, best["al"], best["be"], best["ga"])
    fc = hw_forecast(full_model, horizon)
    last_t = pts[-1]["t"]

    forecast_pts = []
    for i, val in enumerate(fc):
        t_val = last_t + step_ms * (i + 1)
        y_val = round(val, 2)
        lo_val = round(val - 1.96 * sd, 2)
        hi_val = round(val + 1.96 * sd, 2)
        forecast_pts.append({"t": t_val, "y": y_val, "lo": lo_val, "hi": hi_val})

    fitted_pts = []
    for i, p in enumerate(pts):
        fit_v = full_model["fitted"][i]
        fitted_pts.append({
            "t": p["t"],
            "y": round(fit_v, 2) if fit_v is not None else None,
        })

    metrics = {
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "mape": round(mape, 2) if not math.isnan(mape) else 0.0,
        "naiveMae": round(naive_mae, 2) if not math.isnan(naive_mae) else 0.0,
        "sd": round(sd, 2),
        "skill": round(skill, 1),
        "params": {"al": best["al"], "be": best["be"], "ga": best["ga"]},
        "trainPts": len(train),
        "testPts": len(test),
        "testFrom": pts[n - m]["t"],
    }

    return {
        "forecast": forecast_pts,
        "fitted": fitted_pts,
        "metrics": metrics,
    }
