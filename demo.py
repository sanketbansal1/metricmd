"""MetricMD Round 2 demo. One simulated quarter, four stories.

  A  The 18 percent dip     delivery degradation, diagnosed, actioned, VERIFIED healed
  B  The slow bleed         competitor entry, no single-day alarm, caught by trajectory
  C  The win                a lift gets explained too (discount launch)
  D  The honest unknown     no fingerprint fits, engine refuses to guess and asks a human

Plus: RBAC block, analyst vs executive narratives, feedback capture, telemetry.
Run:  python demo.py
"""
import datetime as dt, sys
sys.path.insert(0, ".")
from metricmd import datagen
from metricmd.engine import (load_contract, detect, localize, diagnose, falsify,
                             verify, confidence, Telemetry)
from metricmd.narrate import narrate, feedback

E = dt.date(2026, 8, 20)
D = dt.timedelta
BAR = "=" * 76


def run(contract, tel, region, category, end=E, do_verify=False):
    det = detect(contract, "net_revenue", region, category, end, window=14, tel=tel)
    if det["status"] == "MOVEMENT":
        det = localize(contract, det, end, tel=tel)
        det = diagnose(contract, det, end, tel=tel)
        det = falsify(contract, det, end, tel=tel)
        confidence(det)
        if do_verify and det.get("diagnosis") in contract["fingerprints"]:
            days = contract["fingerprints"][det["diagnosis"]].get("expected_recovery_days", 7)
            verify(contract, det, end + D(days=max(days, 7) + 3), tel=tel)
    return det


def main():
    contract = load_contract()
    tel = Telemetry(contract)
    print("building one simulated quarter with four planted realities...")
    datagen.generate(
        days=132, end=E + D(days=12), seed=4242,
        plants=[
            dict(mechanism="delivery_degradation", magnitude=8.0,
                 start=E - D(days=12), length=13, region="North", category="Dairy"),
            dict(mechanism="competitor_entry", magnitude=0.022,
                 start=E - D(days=13), region="West", category="Beverages"),
            dict(mechanism="discount_launch", magnitude=0.2,
                 start=E - D(days=10), length=12, region="East", category="Household"),
            dict(mechanism="unknown_shock", magnitude=0.28,
                 start=E - D(days=9), length=9, region="South", category="Household"),
        ])

    print(f"\n{BAR}\nSTORY A  THE DIP WITH A CAUSE IN NO TABLE  (North / Dairy)\n{BAR}")
    a = run(contract, tel, "North", "Dairy", do_verify=True)
    print(narrate(contract, a, "regional_head", tel)["text"])
    print("\n[Priya taps Accept]", feedback(a, "accept"))

    print(f"\n{BAR}\nSTORY B  THE SLOW BLEED  (West / Beverages)\n{BAR}")
    b = run(contract, tel, "West", "Beverages")
    print(narrate(contract, b, "central_analyst", tel)["text"])

    print(f"\n{BAR}\nSTORY C  THE WIN, EXPLAINED  (East / Household)\n{BAR}")
    c = run(contract, tel, "East", "Household")
    print(narrate(contract, c, "central_analyst", tel)["text"])

    print(f"\n{BAR}\nSTORY D  THE HONEST UNKNOWN  (South / Household)\n{BAR}")
    d = run(contract, tel, "South", "Household")
    print(narrate(contract, d, "central_analyst", tel)["text"])

    print(f"\n{BAR}\nENTITLEMENT CHECK  Priya (scoped North) asks about West\n{BAR}")
    print(narrate(contract, b, "regional_head", tel)["text"])

    print(f"\n{BAR}\nRUNTIME TELEMETRY\n{BAR}")
    s = tel.summary()
    print(f"total engine time {s['total_ms']} ms, llm tokens {s['llm_tokens']}, "
          f"estimated llm cost INR {s['cost_inr']}")
    print("stage timings:", [(r['stage'], r['ms']) for r in s['stages'][:8]], "...")
    print("\nNote: every number above was computed by SQL, statistics or business "
          "rules before any narrative was written. The LLM, when enabled, only "
          "phrases the evidence list. That is the truth boundary.")


if __name__ == "__main__":
    main()
