import sys
import time
import requests

BASE_URL = "http://127.0.0.1:8000"


def test_all():
    print("=== Testing CampusWatt API Endpoints (Live Server) ===")

    # 1. Health
    res = requests.get(f"{BASE_URL}/api/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print("[OK] GET /api/health passed")

    # 2. Settings
    res = requests.get(f"{BASE_URL}/api/settings")
    assert res.status_code == 200, f"Get settings failed: {res.text}"
    s = res.json()
    assert "campusName" in s and "rate" in s
    print(f"[OK] GET /api/settings passed: campus={s['campusName']}, rate={s['rate']}")

    res = requests.put(f"{BASE_URL}/api/settings", json={"rate": 0.125, "theme": "light"})
    assert res.status_code == 200, f"Put settings failed: {res.text}"
    assert res.json()["rate"] == 0.125
    print("[OK] PUT /api/settings passed")

    # 3. Buildings
    res = requests.get(f"{BASE_URL}/api/buildings/all")
    assert res.status_code == 200
    b_all = res.json()
    assert len(b_all) >= 6
    print(f"[OK] GET /api/buildings/all passed: {len(b_all)} buildings")

    res = requests.get(f"{BASE_URL}/api/buildings?page=1&pageSize=5")
    assert res.status_code == 200
    b_paged = res.json()
    assert b_paged["total"] >= 6 and len(b_paged["items"]) == 5
    print(f"[OK] GET /api/buildings passed: total={b_paged['total']}")

    # Create temporary building
    new_b = {
        "name": "Test Lab Building",
        "type": "Laboratory",
        "area": 2500,
        "occupancy": 150,
        "hvac": True,
        "controllableKw": 45.0,
        "equipment": "Testing instruments",
        "notes": "Automated test",
    }
    res = requests.post(f"{BASE_URL}/api/buildings", json=new_b)
    assert res.status_code == 200, f"Create building failed: {res.text}"
    created_b = res.json()
    b_id = created_b["id"]
    print(f"[OK] POST /api/buildings passed: created id={b_id}")

    # Update building
    res = requests.put(f"{BASE_URL}/api/buildings/{b_id}", json={**new_b, "name": "Updated Lab Building", "area": 2600})
    assert res.status_code == 200
    assert res.json()["name"] == "Updated Lab Building"
    print("[OK] PUT /api/buildings/{id} passed")

    # 4. Readings
    now_ts = int(time.time() * 1000)
    res = requests.post(f"{BASE_URL}/api/readings", json={"buildingId": b_id, "timestamp": now_ts, "kwh": 35.5})
    assert res.status_code == 200, f"Create reading failed: {res.text}"
    created_r = res.json()
    r_id = created_r["id"]
    print(f"[OK] POST /api/readings passed: created reading id={r_id}")

    # Duplicate check on reading
    res_dup = requests.post(f"{BASE_URL}/api/readings", json={"buildingId": b_id, "timestamp": now_ts, "kwh": 40.0})
    assert res_dup.status_code == 409
    print("[OK] POST /api/readings duplicate check passed (returned HTTP 409)")

    # Read readings list
    res = requests.get(f"{BASE_URL}/api/readings?buildingId={b_id}")
    assert res.status_code == 200
    assert res.json()["total"] >= 1
    print("[OK] GET /api/readings passed")

    # Update reading
    res = requests.put(f"{BASE_URL}/api/readings/{r_id}", json={"buildingId": b_id, "timestamp": now_ts, "kwh": 38.0})
    assert res.status_code == 200
    assert res.json()["kwh"] == 38.0
    print("[OK] PUT /api/readings/{id} passed")

    # Delete reading
    res = requests.delete(f"{BASE_URL}/api/readings/{r_id}")
    assert res.status_code == 200
    print("[OK] DELETE /api/readings/{id} passed")

    # Delete building
    res = requests.delete(f"{BASE_URL}/api/buildings/{b_id}")
    assert res.status_code == 200
    print("[OK] DELETE /api/buildings/{id} passed")

    # 5. CSV Import
    import_payload = {
        "rows": [
            {"building_name": "Engineering Hall", "timestamp": "2026-01-10 10:00", "kwh": 75.2},
            {"building_name": "Science Block", "timestamp": "2026-01-10 10:00", "kwh": 62.1},
            {"building_name": "Nonexistent Building", "timestamp": "2026-01-10 10:00", "kwh": 10.0},
        ]
    }
    res = requests.post(f"{BASE_URL}/api/readings/import", json=import_payload)
    assert res.status_code == 200
    imp = res.json()
    assert imp["imported"] >= 0 and imp["errorCount"] >= 1
    print(f"[OK] POST /api/readings/import passed: imported={imp['imported']}, errors={imp['errorCount']}")

    # 6. Data Quality
    res = requests.get(f"{BASE_URL}/api/quality")
    assert res.status_code == 200
    qual = res.json()
    assert len(qual) >= 6
    print(f"[OK] GET /api/quality passed: checked {len(qual)} buildings")

    # 7. Overview
    to_ts = int(time.time() * 1000)
    from_ts = to_ts - 30 * 24 * 3600 * 1000
    res = requests.get(f"{BASE_URL}/api/overview?from={from_ts}&to={to_ts}&bucket=day")
    assert res.status_code == 200, f"Overview failed: {res.text}"
    ov = res.json()
    assert "summary" in ov and "series" in ov and "ribbon" in ov and "compare" in ov
    print(f"[OK] GET /api/overview passed: kwh={ov['summary']['kwh']}, peakKw={ov['summary']['peakKw']}")

    # 8. Series & Analytics
    res = requests.get(f"{BASE_URL}/api/series?buildingId=*&from={from_ts}&to={to_ts}&bucket=day")
    assert res.status_code == 200
    assert len(res.json()) > 0
    print("[OK] GET /api/series passed")

    res = requests.get(f"{BASE_URL}/api/analytics?from={from_ts}&to={to_ts}&bucket=day")
    assert res.status_code == 200
    an = res.json()
    assert "series" in an and "rows" in an and "anomalies" in an
    print(f"[OK] GET /api/analytics passed: total={an['total']}, rows={len(an['rows'])}, anomalies={len(an['anomalies'])}")

    # 9. Load Forecasting
    res = requests.post(f"{BASE_URL}/api/forecast", json={"buildingId": "*", "grain": "hour", "horizon": 48})
    assert res.status_code == 200, f"Forecast failed: {res.text}"
    fc = res.json()
    assert len(fc["forecast"]) == 48
    assert "metrics" in fc and "mae" in fc["metrics"]
    print(f"[OK] POST /api/forecast passed: 48h predicted, MAE={fc['metrics']['mae']} {fc['unit']}, skill={fc['metrics']['skill']}%")

    res = requests.get(f"{BASE_URL}/api/forecast/latest?buildingId=*&grain=hour")
    assert res.status_code == 200
    assert res.json() is not None
    print("[OK] GET /api/forecast/latest passed")

    # 10. Peak Reduction & Recommendations
    res = requests.post(f"{BASE_URL}/api/recommendations/detect", json={"source": "recent"})
    assert res.status_code == 200, f"Detect recommendations failed: {res.text}"
    rec_res = res.json()
    print(f"[OK] POST /api/recommendations/detect passed: {rec_res['count']} recommendations generated")

    res = requests.get(f"{BASE_URL}/api/recommendations")
    assert res.status_code == 200
    recs = res.json()
    assert len(recs) > 0
    rec_id = recs[0]["id"]
    print(f"[OK] GET /api/recommendations passed: found {len(recs)} recommendations")

    # Accept recommendation
    res = requests.patch(f"{BASE_URL}/api/recommendations/{rec_id}", json={"status": "accepted"})
    assert res.status_code == 200
    assert res.json()["status"] == "accepted"
    print("[OK] PATCH /api/recommendations/{id} status=accepted passed")

    # Complete recommendation with measured kWh
    res = requests.patch(f"{BASE_URL}/api/recommendations/{rec_id}", json={"status": "completed", "measuredKwh": 55.4})
    assert res.status_code == 200
    assert res.json()["status"] == "completed"
    assert res.json()["measuredKwh"] == 55.4
    print("[OK] PATCH /api/recommendations/{id} status=completed with measuredKwh passed")

    # 11. Alerts
    res = requests.get(f"{BASE_URL}/api/alerts")
    assert res.status_code == 200
    alerts_data = res.json()
    print(f"[OK] GET /api/alerts passed: {len(alerts_data['items'])} alerts, unread={alerts_data['unread']}")

    res = requests.post(f"{BASE_URL}/api/alerts/scan?peakDays=7&anomDays=14")
    assert res.status_code == 200
    print("[OK] POST /api/alerts/scan passed")

    if alerts_data["items"]:
        alt_id = alerts_data["items"][0]["id"]
        res = requests.patch(f"{BASE_URL}/api/alerts/{alt_id}", json={"read": True})
        assert res.status_code == 200
        print(f"[OK] PATCH /api/alerts/{alt_id} passed")

    res = requests.post(f"{BASE_URL}/api/alerts/read-all")
    assert res.status_code == 200
    print("[OK] POST /api/alerts/read-all passed")

    # 12. Reports
    for p in ["day", "week", "month"]:
        res = requests.get(f"{BASE_URL}/api/report?period={p}&date=2026-01-10")
        assert res.status_code == 200
        rep = res.json()
        assert "campus" in rep and "buildings" in rep
        print(f"[OK] GET /api/report?period={p} passed: label={rep['label']}, campus_kwh={rep['campus']['kwh']}")

    print("\n=========================================")
    print("ALL 12 TEST SUITES PASSED SUCCESSFULLY!")
    print("=========================================")


if __name__ == "__main__":
    test_all()
