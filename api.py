"""MetricMD JSON API. Pure Python standard library, zero dependencies.
Serves the engine's exported state to any frontend (Lovable, React, curl).

    python export_frontend.py     # run the engine, produce the state
    python api.py                 # serve on http://localhost:8000

Endpoints
  GET  /api/state?persona=regional_head|central_analyst
        full payload, ENTITLED: rows outside the persona's contract scope are
        withheld server side (the frontend never receives them) and analyst
        only evidence is masked for executives. Adds a blocked_notice so the
        UI can render the entitlement wall.
  GET  /api/harness             all 73 scored runs + aggregates
  GET  /api/telemetry           latest engine timings, tokens, cost
  POST /api/feedback            {"case_id","verdict":"accept"|"flag","note"?}
        persists to data/feedback.json: events, mechanism priors
        (accept +0.05, flag -0.10) and, for flags with a note or UNKNOWN
        cases, a draft fingerprint entry: the library compounding, made real.
"""
import json, datetime as dt
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

STATE = "data/frontend_data.json"
FEEDBACK = "data/feedback.json"
MASK_METHODS_FOR_EXEC = {"business_rules"}   # analyst internals masked for execs


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def entitle(state, persona_key):
    p = state["personas"].get(persona_key) or state["personas"]["central_analyst"]
    scope_region = p.get("scope", {}).get("region")
    out, blocked = [], []
    for c in state["cases"]:
        if scope_region and c["region"] != scope_region:
            blocked.append({"case_id": c["case_id"], "region": c["region"],
                            "notice": f"{p['name']} is scoped to {scope_region} by the "
                                      f"contract. Diagnosis for {c['region']} is withheld "
                                      "server side and this access attempt is audit logged."})
            continue
        c = json.loads(json.dumps(c))
        if p["depth"] == "executive":
            kept = [e for e in c["evidence"] if e["method"] not in MASK_METHODS_FOR_EXEC]
            c["masked_evidence"] = len(c["evidence"]) - len(kept)
            c["evidence"] = kept
            c["candidates"] = c["candidates"][:1]
        out.append(c)
    fb = load(FEEDBACK, {"events": [], "mechanism_priors": {}, "draft_fingerprints": []})
    return {**state, "cases": out, "blocked": blocked, "persona": persona_key,
            "feedback_summary": {"events": len(fb["events"]),
                                 "mechanism_priors": fb["mechanism_priors"],
                                 "draft_fingerprints": fb["draft_fingerprints"]}}


class H(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(200, {})

    def do_GET(self):
        u = urlparse(self.path)
        state = load(STATE, {})
        if u.path == "/api/state":
            persona = parse_qs(u.query).get("persona", ["central_analyst"])[0]
            return self._send(200, entitle(state, persona))
        if u.path == "/api/harness":
            return self._send(200, {"scorecard": state.get("scorecard"),
                                    "cases": state.get("harness_cases", [])})
        if u.path == "/api/telemetry":
            return self._send(200, state.get("telemetry", {}))
        return self._send(404, {"error": "unknown endpoint"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/feedback":
            return self._send(404, {"error": "unknown endpoint"})
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "bad json"})
        state = load(STATE, {})
        case = next((c for c in state.get("cases", [])
                     if c["case_id"] == req.get("case_id")), None)
        if not case:
            return self._send(400, {"error": "unknown case_id"})
        fb = load(FEEDBACK, {"events": [], "mechanism_priors": {}, "draft_fingerprints": []})
        verdict = req.get("verdict", "accept")
        mech = case.get("diagnosis")
        fb["events"].append({"at": dt.datetime.now().isoformat(timespec="seconds"),
                             "case_id": case["case_id"], "verdict": verdict,
                             "mechanism": mech, "note": req.get("note", "")})
        key = f"{case['region']}:{mech}"
        fb["mechanism_priors"][key] = round(
            fb["mechanism_priors"].get(key, 0) + (0.05 if verdict == "accept" else -0.10), 2)
        if (verdict == "flag" and req.get("note")) or mech == "UNKNOWN":
            fb["draft_fingerprints"].append({
                "from_case": case["case_id"], "region": case["region"],
                "human_note": req.get("note", ""), "status": "draft",
                "next": "analyst reviews, names the shape and corroborators, "
                        "and it joins contract.yaml as a new fingerprint"})
        json.dump(fb, open(FEEDBACK, "w"), indent=1)
        return self._send(200, {"ok": True, "priors": fb["mechanism_priors"],
                                "draft_fingerprints": len(fb["draft_fingerprints"])})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("MetricMD API on http://localhost:8000  (GET /api/state, /api/harness, "
          "/api/telemetry, POST /api/feedback)")
    HTTPServer(("0.0.0.0", 8000), H).serve_forever()
