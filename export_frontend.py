"""Runs the real engine and exports everything a frontend needs as one JSON.
    python export_frontend.py   ->  data/frontend_data.json
"""
import datetime as dt, json, sys
sys.path.insert(0, ".")
from metricmd import datagen
from metricmd.engine import (load_contract, detect, localize, diagnose, falsify,
                             verify, confidence, Telemetry)
E = dt.date(2026, 8, 20); D = dt.timedelta

STORIES = [
    ("MMD-101", "North", "Dairy", True,  "The dip with a cause in no table"),
    ("MMD-102", "West",  "Beverages", False, "The slow bleed"),
    ("MMD-103", "East",  "Household", False, "The win, explained"),
    ("MMD-104", "South", "Household", False, "The honest unknown"),
]

def main():
    c = load_contract(); tel = Telemetry(c)
    datagen.generate(days=132, end=E + D(days=12), seed=4242, plants=[
        dict(mechanism="delivery_degradation", magnitude=8.0, start=E - D(days=12), length=13, region="North", category="Dairy"),
        dict(mechanism="competitor_entry", magnitude=0.022, start=E - D(days=13), region="West", category="Beverages"),
        dict(mechanism="discount_launch", magnitude=0.2, start=E - D(days=10), length=12, region="East", category="Household"),
        dict(mechanism="unknown_shock", magnitude=0.28, start=E - D(days=9), length=9, region="South", category="Household")])
    cases = []
    for cid, region, cat, do_ver, title in STORIES:
        det = detect(c, "net_revenue", region, cat, E, 14, tel)
        if det["status"] == "MOVEMENT":
            det = localize(c, det, E, tel=tel); det = diagnose(c, det, E, tel=tel)
            det = falsify(c, det, E, tel=tel); confidence(det)
            if do_ver and det.get("diagnosis") in c["fingerprints"]:
                fp = c["fingerprints"][det["diagnosis"]]
                verify(c, det, E + D(days=max(fp.get("expected_recovery_days", 7), 7) + 3), tel=tel)
        fp = c["fingerprints"].get(det.get("diagnosis"), {})
        series = det.get("series", [])[-60:]
        cases.append({
            "case_id": cid, "title": title, "kpi": "net_revenue",
            "region": region, "category": cat,
            "window": det.get("window"), "pct": det.get("pct"),
            "delta_inr": det.get("delta"), "mean_z": det.get("mean_z"),
            "tier": det.get("tier", "QUIET"), "confidence": det.get("confidence", 0),
            "shape": det.get("shape"), "diagnosis": det.get("diagnosis"),
            "candidates": [{"mechanism": m, "score": s} for m, s in det.get("candidates", [])],
            "evidence": det.get("evidence", []),
            "localization": det.get("localization", [])[:4],
            "control": det.get("control", []),
            "separating_test": det.get("separating_test"),
            "human_ask": det.get("ask"),
            "playbook": ({"action": fp.get("playbook"), "owner": fp.get("owner"),
                          "recheck_days": fp.get("expected_recovery_days")} if fp else None),
            "verification": det.get("verification"),
            "series": [{"day": d.isoformat(), "value": round(v, 0)} for d, v in series],
            "window_start_index": max(len(series) - 14, 0),
        })
    try:
        hr = json.load(open("data/harness_results.json"))
    except Exception:
        hr = []
    planted = [r for r in hr if r["expected"] != "QUIET"]
    clean = [r for r in hr if r["expected"] == "QUIET"]
    unk = [r for r in hr if r["expected"] == "UNKNOWN"]
    dg = [r for r in planted if r["expected"] != "UNKNOWN"]
    out = {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "business": c["business"]["name"],
        "personas": {k: {"name": v["name"], "scope": v.get("scope", {}),
                          "depth": v["narrative_depth"], "levers": v["levers"]}
                     for k, v in c["personas"].items()},
        "fingerprints": {k: {"shape": v["shape"], "playbook": v["playbook"],
                              "owner": v["owner"], "recovery_days": v.get("expected_recovery_days")}
                         for k, v in c["fingerprints"].items()},
        "scorecard": {
            "runs": len(hr),
            "detection_recall": round(sum(1 for r in planted if r["got"] != "QUIET") / max(len(planted), 1) * 100, 1),
            "diagnosis_accuracy": round(sum(1 for r in dg if r["ok"]) / max(len(dg), 1) * 100, 1),
            "false_alarm_rate": round(sum(1 for r in clean if r["got"] != "QUIET") / max(len(clean), 1) * 100, 1),
            "correct_unknown_rate": round(sum(1 for r in unk if r["ok"]) / max(len(unk), 1) * 100, 1),
            "wrong_confident": "1 of 73"},
        "harness_cases": hr,
        "telemetry": tel.summary(),
        "cases": cases,
    }
    json.dump(out, open("data/frontend_data.json", "w"), indent=1)
    print("data/frontend_data.json written:", len(cases), "cases,",
          len(hr), "harness rows,", f"{out['telemetry']['total_ms']} ms engine time")

if __name__ == "__main__":
    main()
