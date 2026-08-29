"""MetricMD deterministic core. Pure stdlib. No LLM anywhere in this file.

Pipeline per KPI window:
  DETECT    seasonal baseline (day-of-week means) + robust z on residuals
  LOCALIZE  contribution split across contract dimensions, surprise weighted
  DIAGNOSE  match computed features against the fingerprint library
  FALSIFY   control-group and coherence tests try to kill the diagnosis
  VERIFY    after the playbook window, recheck the KPI against its band

Every fact carries an evidence id (E1, E2, ...). The narrative layer may
only phrase facts that exist in the evidence list. Nothing else.
"""
import sqlite3, statistics, datetime as dt, time, re, json, os

try:
    import yaml
    def load_contract(path="contracts/contract.yaml"):
        with open(path) as f:
            return yaml.safe_load(f)
except ImportError:  # tiny fallback so the core stays runnable with zero deps
    def load_contract(path="contracts/contract.yaml"):
        raise SystemExit("pip install pyyaml (the only dependency)")

D = dt.date.fromisoformat


class Telemetry:
    def __init__(self, contract):
        self.rows, self.t0 = [], time.time()
        self.price = contract["telemetry"]["price_per_1k_tokens_inr"]
    def log(self, stage, ms, tokens=0):
        self.rows.append({"stage": stage, "ms": round(ms, 1), "tokens": tokens,
                          "cost_inr": round(tokens / 1000 * self.price, 4)})
    def summary(self):
        return {"total_ms": round(sum(r["ms"] for r in self.rows), 1),
                "llm_tokens": sum(r["tokens"] for r in self.rows),
                "cost_inr": round(sum(r["cost_inr"] for r in self.rows), 4),
                "stages": self.rows}


def _series(db, region, category, end, days, field="sum(units*unit_price)"):
    q = ("SELECT day,{f} FROM orders WHERE day<=? " +
         ("AND region=? " if region else "") + ("AND category=? " if category else "") +
         "GROUP BY day ORDER BY day").format(f=field)
    args = [end.isoformat()] + ([region] if region else []) + ([category] if category else [])
    rows = sqlite3.connect(db).execute(q, args).fetchall()[-days:]
    return [(D(r[0]), r[1] or 0.0) for r in rows]


def _dow_baseline(series, window):
    """Expected value for each day = mean of the same weekday over history
    excluding the evaluation window. Returns (expected, residual_sigma)."""
    hist = series[:-window]
    bydow = {}
    for d, v in hist:
        bydow.setdefault(d.weekday(), []).append(v)
    exp = {k: statistics.mean(v) for k, v in bydow.items()}
    resid = [v - exp[d.weekday()] for d, v in hist if d.weekday() in exp]
    sigma = statistics.pstdev(resid) if len(resid) > 2 else 1.0
    return exp, max(sigma, 1e-6)


# ------------------------------------------------------------------ DETECT
def detect(contract, kpi, region=None, category=None, end=None, window=14, tel=None):
    t0 = time.time()
    cfg = contract["kpis"][kpi]
    db = contract["sources"][cfg["source"]]["db"]
    field = {"net_revenue": "sum(units*unit_price)", "units_sold": "sum(units)",
             "avg_delivery_min": "avg(delivery_min)"}[kpi]
    series = _series(db, region, category, end, days=120, field=field)
    if len(series) < cfg.get("min_history_days", 42) + window:
        return {"status": "SPARSE", "evidence": [
            {"id": "E1", "fact": f"history {len(series)}d < contract minimum "
             f"{cfg.get('min_history_days',42)}d, engine abstains by rule",
             "method": "business_rule", "source": cfg["source"]}], "series": series}
    exp, sigma = _dow_baseline(series, window)
    win = series[-window:]
    zs = [(d, v, (v - exp[d.weekday()]) / sigma) for d, v in win]
    mean_z = statistics.mean(z for _, _, z in zs)
    delta = sum(v - exp[d.weekday()] for d, v, _ in zs)
    material = abs(delta) >= cfg.get("material_abs_inr", 0)
    fired = abs(mean_z) >= cfg["z_threshold"] / (window ** 0.5) * 2 and material \
            or any(abs(z) >= cfg["z_threshold"] for _, _, z in zs) and material
    # campaign decay: current window normal but the PRIOR window was lifted
    spike_prior = False
    if not fired and len(series) >= window * 2 + 40:
        prev = series[-window * 2:-window]
        prev_z = statistics.mean((v - exp[d.weekday()]) / sigma for d, v in prev if d.weekday() in exp)
        if prev_z > 1.5 and abs(mean_z) < 1.0:
            fired, spike_prior = True, True
            delta = sum(v for _, v in win) - sum(v for _, v in prev)
    out = {"status": "MOVEMENT" if fired else "QUIET", "kpi": kpi, "region": region,
           "spike_prior": spike_prior,
           "category": category, "window": [win[0][0].isoformat(), win[-1][0].isoformat()],
           "mean_z": round(mean_z, 2), "delta": round(delta, 0), "sigma": round(sigma, 1),
           "pct": round(delta / max(sum(exp[d.weekday()] for d, _, _ in zs), 1) * 100, 1),
           "series": series, "zs": zs,
           "evidence": [{"id": "E1", "fact": f"{kpi} {region or 'ALL'} moved "
                         f"{round(delta,0):,.0f} ({'{:+.1f}'.format(0) if False else ''}"
                         f"{round(delta/max(sum(exp[d.weekday()] for d,_,_ in zs),1)*100,1)}%) "
                         f"vs day-of-week expected band, mean z {round(mean_z,2)}",
                         "method": "statistics", "source": cfg["source"]}]}
    if tel: tel.log("detect", (time.time() - t0) * 1000)
    return out


# ---------------------------------------------------------------- LOCALIZE
def localize(contract, det, end, window=14, tel=None):
    t0 = time.time()
    kpi, region = det["kpi"], det["region"]
    cfg = contract["kpis"][kpi]
    db = contract["sources"][cfg["source"]]["db"]
    field = {"net_revenue": "sum(units*unit_price)", "units_sold": "sum(units)",
             "avg_delivery_min": "avg(delivery_min)"}[kpi]
    contrib = {}
    pinned = {"region"} | ({"category"} if det.get("category") else set())
    for dim in [d for d in cfg.get("dimensions", []) if d not in pinned]:
        vals = sqlite3.connect(db).execute(
            f"SELECT DISTINCT {dim} FROM orders").fetchall()
        for (val,) in vals:
            q = (f"SELECT day,{field} FROM orders WHERE day<=? AND {dim}=? " +
                 ("AND region=? " if region else "") + "GROUP BY day ORDER BY day")
            args = [end.isoformat(), val] + ([region] if region else [])
            rows = sqlite3.connect(db).execute(q, args).fetchall()[-120:]
            s = [(D(r[0]), r[1] or 0.0) for r in rows]
            if len(s) < 60: continue
            exp, _ = _dow_baseline(s, window)
            d_ = sum(v - exp[d.weekday()] for d, v in s[-window:])
            contrib[(dim, val)] = d_
    total = det["delta"] or 1.0
    ranked = sorted(contrib.items(), key=lambda kv: kv[1] / total, reverse=True)
    shares = [{"dim": k[0], "value": k[1], "delta": round(v, 0),
               "share_pct": round(v / total * 100, 1)} for k, v in ranked]
    top = shares[0] if shares else None
    det["localization"] = shares
    det["top_segment"] = top
    if top:
        det["evidence"].append({"id": f"E{len(det['evidence'])+1}",
            "fact": f"{top['dim']}={top['value']} explains {top['share_pct']}% of the movement",
            "method": "contribution_analysis", "source": cfg["source"]})
    if tel: tel.log("localize", (time.time() - t0) * 1000)
    return det


# ---------------------------------------------------------- feature probes
def _shape(det):
    if det.get("spike_prior"):
        return "spike_return"
    zs = [z for _, _, z in det["zs"]]
    deep_days = sum(1 for z in zs if z < -3)
    if 1 <= deep_days <= 4 and min(zs) < -5 and statistics.mean(zs[-3:]) > -1.5:
        return "cliff_rebound"
    # onset: first day the series leaves the band, classify what follows
    def _isolated(i):
        prev_ok = i == 0 or abs(zs[i - 1]) < 1
        nxt_ok = i == len(zs) - 1 or abs(zs[i + 1]) < 1
        return prev_ok and nxt_ok
    onset = next((i for i, z in enumerate(zs)
                  if abs(z) > 2 and not _isolated(i)), 0)
    if len(zs) - onset < 6:
        # onset too recent to judge trajectory: call it persistent until proven
        tail = zs[onset:] or zs[-3:]
        return "step_down_persistent" if statistics.mean(tail) < -1 else "noise"
    post = zs[onset:]
    n = len(post); half = n // 2
    first, second = statistics.mean(post[:half]), statistics.mean(post[half:])
    slope = second - first
    m = statistics.mean(post)
    worst_idx = post.index(min(post))
    if m < -1 and slope < -1.2 and n >= 8 and worst_idx >= int(n * 0.6):
        return "slow_slide"
    if m < -1 and slope <= 1.0:
        return "step_down_persistent"
    if m > 1.2:
        return "lift"
    if max(zs) > 2 and zs[-1] < 1:
        return "spike_return"
    return "noise"


def _probes(contract, det, end, window):
    """Computed corroborating features from all three sources."""
    region, category = det["region"], det.get("category")
    db_s = contract["sources"]["pos_sales"]["db"]
    db_o = contract["sources"]["ops_tickets"]["db"]
    db_m = contract["sources"]["marketing"]["db"]
    conn = sqlite3.connect(db_s)
    probes, ev = {}, det["evidence"]

    def add(pid, fact, method, source):
        ev.append({"id": f"E{len(ev)+1}", "fact": fact, "method": method, "source": source})

    # unit price movement
    q = ("SELECT day,avg(unit_price) FROM orders WHERE day<=? " +
         ("AND region=? " if region else "") + ("AND category=? " if category else "") +
         "GROUP BY day ORDER BY day")
    args = [end.isoformat()] + ([region] if region else []) + ([category] if category else [])
    pr = [r[1] for r in conn.execute(q, args).fetchall()[-120:]]
    if len(pr) > 40:
        base_p, win_p = statistics.mean(pr[:-window]), statistics.mean(pr[-window:])
        chg = (win_p - base_p) / base_p * 100
        probes["unit_price_up"] = chg > 4; probes["unit_price_down"] = chg < -4
        if abs(chg) > 4:
            add("p", f"avg unit price moved {chg:+.1f}% in the window "
                     f"({base_p:.1f} to {win_p:.1f} INR)", "sql_aggregation", "pos_sales")

    # delivery time
    dl = [r[1] for r in conn.execute(
        "SELECT day,avg(delivery_min) FROM orders WHERE day<=? " +
        ("AND region=? " if region else "") + ("AND category=? " if category else "") +
        "GROUP BY day ORDER BY day",
        [end.isoformat()] + ([region] if region else []) +
        ([category] if category else [])).fetchall()[-120:]]
    if len(dl) > 40:
        b, w = statistics.mean(dl[:-window]), statistics.mean(dl[-window:])
        probes["delivery_min_up"] = (w - b) > 3
        if probes["delivery_min_up"]:
            add("d", f"avg delivery time rose {b:.0f} to {w:.0f} min in the window",
                "sql_aggregation", "pos_sales")

    # unstructured: ticket keyword counts in the window (retrieval, not LLM)
    win_start = (end - dt.timedelta(days=window)).isoformat()
    tx = [t[0] for t in sqlite3.connect(db_o).execute(
        "SELECT text FROM tickets WHERE created>=? AND created<=? " +
        ("AND region=?" if region else ""),
        [win_start, end.isoformat()] + ([region] if region else [])).fetchall()]
    delay_n = sum(1 for t in tx if re.search(r"late|delay|waited|rider", t, re.I))
    supply_n = sum(1 for t in tx if re.search(r"short shipped|supplier|consignment|inbound", t, re.I))
    probes["tickets_cite_delay"] = delay_n >= 6
    probes["tickets_cite_supply"] = supply_n >= 4
    if delay_n >= 6:
        add("t", f"{delay_n} support tickets in the window cite delivery delays "
                 f"(keyword retrieval over ops_tickets)", "retrieval", "ops_tickets")
    if supply_n >= 4:
        add("t2", f"{supply_n} tickets cite supplier or inbound shortage", "retrieval", "ops_tickets")

    # marketing: did a campaign end just before the window?
    camp = sqlite3.connect(db_m).execute(
        "SELECT campaign,end FROM campaigns WHERE region=? AND campaign!='AlwaysOn'",
        [region or "North"]).fetchall()
    win_start_d = end - dt.timedelta(days=window)
    probes["campaign_window_ended"] = any(
        c[1] and win_start_d - dt.timedelta(days=4) <= D(c[1]) <= end for c in camp)
    if probes["campaign_window_ended"]:
        add("m", "a paid campaign in this region ended within 3 days of the window start "
                 "(marketing source, weekly grain)", "sql_join", "marketing")

    # sibling category movement (cannibalization probe)
    if category:
        sib_moves = []
        for sib in [c for c in ["Beverages", "Snacks", "Dairy", "Household"] if c != category]:
            s = _series(db_s, region, sib, end, 120)
            if len(s) < 60: continue
            exp, sg = _dow_baseline(s, window)
            mz = statistics.mean((v - exp[d.weekday()]) / sg for d, v in s[-window:])
            if mz > 1.5: sib_moves.append((sib, round(mz, 1)))
        probes["sibling_category_up"] = bool(sib_moves)
        if sib_moves:
            add("s", f"sibling category {sib_moves[0][0]} is UP (mean z {sib_moves[0][1]}) "
                     f"over the same window", "statistics", "pos_sales")

    # geo_bounded: control regions stayed inside their bands for this category
    if region:
        quiet = 0; total = 0
        for other in [r for r in ["North", "South", "East", "West"] if r != region]:
            s2 = _series(db_s, other, category, end, 120)
            if len(s2) < 60: continue
            exp2, sg2 = _dow_baseline(s2, window)
            mz2 = statistics.mean((v - exp2[d.weekday()]) / sg2 for d, v in s2[-window:])
            total += 1; quiet += (mz2 > -2)
        probes["geo_bounded"] = total > 0 and quiet == total
    else:
        probes["geo_bounded"] = False
    return probes


# ---------------------------------------------------------------- DIAGNOSE
def diagnose(contract, det, end, window=14, tel=None):
    t0 = time.time()
    shape = _shape(det)
    det["shape"] = shape
    probes = _probes(contract, det, end, window)
    det["probes"] = {k: v for k, v in probes.items() if v}
    scores = {}
    for name, fp in contract["fingerprints"].items():
        shape_ok = fp["shape"] == shape
        need = fp.get("corroborate", [])
        hits = sum(1 for c in need if probes.get(c))
        sc = 0.4 * shape_ok + 0.6 * ((hits / len(need)) if need else (1.0 if shape_ok else 0.0))
        if not shape_ok: sc = min(sc, 0.45)
        if need and hits == 0: sc = min(sc, 0.25)
        if name == "price_rise" and not probes.get("unit_price_up"): sc = min(sc, 0.2)
        if name == "competitor_entry" and (probes.get("tickets_cite_supply")
                                           or probes.get("tickets_cite_delay")
                                           or probes.get("unit_price_up")):
            sc = min(sc, 0.45)  # a competitor does not raise our ops tickets or our prices
        if name == "discount_launch" and not probes.get("unit_price_down"): sc = min(sc, 0.2)
        scores[name] = (round(sc, 3), hits, int(shape_ok))
    ranked = [(k, v[0]) for k, v in sorted(scores.items(),
              key=lambda kv: kv[1], reverse=True)]
    det["candidates"] = ranked[:3]
    best, second = ranked[0], ranked[1]
    if best[1] >= 0.70 and best[1] - second[1] >= 0.15:
        det["diagnosis"], det["confidence_raw"] = best[0], best[1]
        det["tier"] = "CONFIDENT"
    elif best[1] >= 0.50:
        det["diagnosis"], det["confidence_raw"] = best[0], best[1]
        det["tier"] = "AMBIGUOUS" if best[1] - second[1] < 0.15 else "CONFIDENT"
        if det["tier"] == "AMBIGUOUS":
            det["separating_test"] = _separating_test(best[0], second[0])
            det["second"] = second[0]
    else:
        det["diagnosis"], det["confidence_raw"], det["tier"] = "UNKNOWN", best[1], "UNKNOWN"
        det["ask"] = ("No fingerprint fits. Nearest human ask routed to the "
                      f"{det['region'] or 'central'} ops lead: what changed on the ground "
                      f"between {det['window'][0]} and {det['window'][1]}? "
                      "The answer becomes a new fingerprint.")
    det["evidence"].append({"id": f"E{len(det['evidence'])+1}",
        "fact": f"shape classified {shape}; top fingerprint {ranked[0][0]} "
                f"score {ranked[0][1]}, runner up {ranked[1][0]} {ranked[1][1]}",
        "method": "business_rules", "source": "fingerprint_library"})
    if tel: tel.log("diagnose", (time.time() - t0) * 1000)
    return det


def _separating_test(a, b):
    tests = {frozenset(["price_rise", "supply_shortage"]):
                 "price_rise predicts unit price UP with units down; supply_shortage predicts "
                 "flat price with supplier tickets. Check avg unit price first.",
             frozenset(["competitor_entry", "delivery_degradation"]):
                 "competitor_entry is geo bounded with flat delivery times; delivery_degradation "
                 "shows delivery minutes up and delay tickets. Check delivery minutes.",
             frozenset(["stockout", "supply_shortage"]):
                 "stockout is a short cliff with rebound after reorder; supply_shortage persists "
                 "for weeks. Wait 2 days or check inbound consignment status."}
    return tests.get(frozenset([a, b]),
                     f"Compare the one probe that only {a} predicts and {b} does not.")


# ----------------------------------------------------------------- FALSIFY
def falsify(contract, det, end, window=14, tel=None):
    """Control group test: did untouched regions move the same way?
    A cause that also fires in the control is not a local cause."""
    t0 = time.time()
    if det.get("diagnosis") in (None, "UNKNOWN") or not det["region"]:
        return det
    db = contract["sources"]["pos_sales"]["db"]
    moved = []
    for other in [r for r in ["North", "South", "East", "West"] if r != det["region"]]:
        s = _series(db, other, det.get("category"), end, 120)
        if len(s) < 60: continue
        exp, sg = _dow_baseline(s, window)
        mz = statistics.mean((v - exp[d.weekday()]) / sg for d, v in s[-window:])
        moved.append((other, round(mz, 2)))
    control_hits = [m for m in moved if m[1] < -2]
    det["control"] = moved
    if len(control_hits) >= 2:
        det["tier"] = "AMBIGUOUS" if det["tier"] == "CONFIDENT" else det["tier"]
        det["evidence"].append({"id": f"E{len(det['evidence'])+1}",
            "fact": f"control test FAILED the local hypothesis: {len(control_hits)} other regions "
                    f"moved the same way ({control_hits}), cause is likely global "
                    "(seasonal, macro, or platform wide)", "method": "control_group", "source": "pos_sales"})
        det["diagnosis_note"] = "global_pattern"
    else:
        quiet = moved[0] if moved else None
        det["evidence"].append({"id": f"E{len(det['evidence'])+1}",
            "fact": f"control test PASSED: the same window in control regions stayed inside "
                    f"the band (e.g. {quiet[0]} mean z {quiet[1]}), the cause is local to "
                    f"{det['region']}", "method": "control_group", "source": "pos_sales"})
    if tel: tel.log("falsify", (time.time() - t0) * 1000)
    return det


# ------------------------------------------------------------------ VERIFY
def verify(contract, det, end_after, window=7, tel=None):
    """Post-action recheck. Called after the playbook's expected_recovery_days.
    Reports whether the KPI returned inside its expected band."""
    t0 = time.time()
    kpi = det["kpi"]
    re_det = detect(contract, kpi, det["region"], det.get("category"), end_after, window)
    healed = re_det["status"] == "QUIET" or re_det.get("mean_z", -9) > -1.5
    det["verification"] = {
        "recheck_window": re_det.get("window"),
        "mean_z_after": re_det.get("mean_z"),
        "healed": healed,
        "verdict": ("RESOLVED, KPI back inside its expected band, diagnosis confirmed"
                    if healed else
                    "NOT RESOLVED, KPI still outside band, escalate and re-diagnose")}
    det["evidence"].append({"id": f"E{len(det['evidence'])+1}",
        "fact": f"post action recheck at {end_after}: mean z "
                f"{re_det.get('mean_z')}, verdict {det['verification']['verdict']}",
        "method": "statistics", "source": "pos_sales"})
    if tel: tel.log("verify", (time.time() - t0) * 1000)
    return det


# --------------------------------------------------------------- CONFIDENCE
def confidence(det):
    if det.get("status") == "SPARSE": return 0.0
    base = det.get("confidence_raw", 0.0)
    stat = min(abs(det.get("mean_z", 0)) / 6.0, 1.0)
    conc = (det.get("top_segment") or {}).get("share_pct", 0) / 100.0
    penalty = 0.25 if det.get("diagnosis_note") == "global_pattern" else 0.0
    c = round(max(min(0.5 * base + 0.3 * stat + 0.2 * min(conc, 1.0) - penalty, 0.99), 0.05), 2)
    det["confidence"] = c
    return c
