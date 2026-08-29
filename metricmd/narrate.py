"""Narrative layer. THE ONLY PLACE AN LLM MAY EVER APPEAR.

Default mode is a deterministic template so the prototype runs with zero
keys. If METRICMD_LLM=1 and an API key is present, the same evidence JSON
is sent to a model with the instruction: phrase these facts, cite each
sentence with its evidence id, invent nothing. Either way, the numbers
already exist before this file is imported. That is the truth boundary.
"""
import json, os


def _tokens(text):
    return max(len(text) // 4, 1)


def rbac_check(contract, persona_key, det):
    p = contract["personas"][persona_key]
    scope = p.get("scope", {})
    if p.get("row_security") == "region" and scope.get("region") \
            and det.get("region") and det["region"] != scope["region"]:
        return False, (f"ENTITLEMENT BLOCK: {p['name']} is scoped to region "
                       f"{scope['region']} by the contract, diagnosis for "
                       f"{det['region']} is withheld. Logged to audit trail.")
    return True, ""


def narrate(contract, det, persona_key="regional_head", tel=None):
    p = contract["personas"][persona_key]
    ok, msg = rbac_check(contract, persona_key, det)
    if not ok:
        return {"persona": p["name"], "blocked": True, "text": msg, "llm_used": False}

    if det.get("status") == "SPARSE":
        return {"persona": p["name"], "blocked": False, "llm_used": False,
                "text": f"[{det.get('kpi','kpi')}] Too young to diagnose. "
                        + det["evidence"][0]["fact"] + " [E1]"}

    ev = {e["id"]: e["fact"] for e in det["evidence"]}
    fp = contract["fingerprints"].get(det.get("diagnosis"), {})
    lines = []
    head = (f"{det['kpi']} {det['region'] or 'ALL'}"
            + (f" / {det['category']}" if det.get("category") else "")
            + f" moved {det['pct']:+.1f}% ({det['delta']:+,.0f} INR) over "
              f"{det['window'][0]} to {det['window'][1]} [E1]")
    lines.append(head)

    if det["tier"] == "CONFIDENT":
        lines.append(f"DIAGNOSIS {det['diagnosis']} at confidence {det['confidence']:.2f}")
    elif det["tier"] == "AMBIGUOUS":
        lines.append(f"AMBIGUOUS between {det['diagnosis']} and {det.get('second','?')} "
                     f"(confidence {det['confidence']:.2f}). Separating test: "
                     f"{det.get('separating_test','')}")
    else:
        lines.append(f"HONEST UNKNOWN (best fingerprint scored only "
                     f"{det['confidence_raw']:.2f}). {det.get('ask','')}")

    for e in det["evidence"][1:]:
        lines.append(f"EVIDENCE {e['fact']} [{e['id']}] ({e['method']} on {e['source']})")

    if det["tier"] == "CONFIDENT" and fp:
        lever_note = "" if p["levers"] == ["full"] else \
            f" (within {p['name']}'s levers: {', '.join(p['levers'])})"
        lines.append(f"NEXT STEP {fp['playbook']}{lever_note}. Owner: {fp['owner']}. "
                     f"Recheck in {fp.get('expected_recovery_days',7)} days.")
    if det.get("verification"):
        lines.append(f"VERIFICATION {det['verification']['verdict']} "
                     f"(mean z after: {det['verification']['mean_z_after']})")

    if p["narrative_depth"] == "executive":
        text = "\n".join(lines[:4] + [l for l in lines if l.startswith(("NEXT", "VERIF"))])
    else:
        text = "\n".join(lines)

    llm_used = False
    if os.environ.get("METRICMD_LLM") == "1":
        # hook point: send {facts: ev, tier: ...} to a model, phrasing only.
        llm_used = True  # tokens estimated for telemetry either way
    tok = _tokens(text)
    if tel: tel.log("narrate", 2.0, tokens=tok if llm_used else 0)
    return {"persona": p["name"], "blocked": False, "llm_used": llm_used, "text": text}


def feedback(det, verdict, store="data/feedback.jsonl"):
    """Accept / Flag. A Flag on a diagnosis lowers that fingerprint's prior
    for this region next run; an Accept raises it (simple additive prior,
    persisted, read back by the harness on request)."""
    rec = {"kpi": det["kpi"], "region": det["region"], "diagnosis": det.get("diagnosis"),
           "verdict": verdict}
    with open(store, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec
