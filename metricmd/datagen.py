"""Synthetic source-system generator for MetricMD.

Builds three deliberately mismatched sources, matching the contract:
  data/sales.db      daily order lines   (region, category, channel, units, unit_price, delivery_min)
  data/marketing.db  weekly campaign spend (region, campaign, spend, week_start)
  data/ops.db        event-grain tickets with free text (region, created, text)

Every anomaly is INJECTED with a known label so the harness can score the
engine blind. Reproducible from SEED. Pure stdlib.
"""
import os, random, sqlite3, datetime as dt

SEED = 2026
REGIONS = ["North", "South", "East", "West"]
CATEGORIES = ["Beverages", "Snacks", "Dairy", "Household"]
CHANNELS = ["App", "Web", "Store"]

BASE = {("North", "Beverages"): 520, ("North", "Snacks"): 430, ("North", "Dairy"): 610, ("North", "Household"): 300,
        ("South", "Beverages"): 480, ("South", "Snacks"): 520, ("South", "Dairy"): 450, ("South", "Household"): 340,
        ("East", "Beverages"): 300, ("East", "Snacks"): 280, ("East", "Dairy"): 330, ("East", "Household"): 210,
        ("West", "Beverages"): 560, ("West", "Snacks"): 500, ("West", "Dairy"): 520, ("West", "Household"): 380}
PRICE = {"Beverages": 78.0, "Snacks": 52.0, "Dairy": 64.0, "Household": 140.0}
DOW_MULT = [1.00, 0.96, 0.97, 1.01, 1.06, 1.18, 1.14]  # Mon..Sun
CHAN_SHARE = {"App": 0.46, "Web": 0.22, "Store": 0.32}

TICKET_NORMAL = ["Refund processed for order {oid}", "Customer asked for invoice copy, order {oid}",
                 "Address correction on order {oid}", "Coupon question resolved for order {oid}"]
TICKET_DELAY = ["Order {oid} arrived 40 minutes late, rider said route was rerouted",
                "Delivery delayed again in {region}, customer waited over an hour",
                "Late delivery complaint, {region} hub says rider shortage today"]
TICKET_SUPPLY = ["Vendor mail: {category} consignment short shipped this week",
                 "Warehouse flags {category} inbound stuck at supplier, {region}"]


def _conn(path):
    if os.path.exists(path):
        os.remove(path)
    return sqlite3.connect(path)


def generate(days=120, end=dt.date(2026, 8, 20), plants=None, seed=SEED, outdir="data"):
    """plants: list of dicts {mechanism, region, category, start, length, magnitude}"""
    rng = random.Random(seed)
    plants = plants or []
    os.makedirs(outdir, exist_ok=True)
    start = end - dt.timedelta(days=days - 1)

    sales = _conn(os.path.join(outdir, "sales.db"))
    sales.execute("CREATE TABLE orders(day TEXT, region TEXT, category TEXT, channel TEXT,"
                  " units REAL, unit_price REAL, delivery_min REAL)")
    mkt = _conn(os.path.join(outdir, "marketing.db"))
    mkt.execute("CREATE TABLE campaigns(week_start TEXT, region TEXT, campaign TEXT, spend REAL,"
                " start TEXT, end TEXT)")
    ops = _conn(os.path.join(outdir, "ops.db"))
    ops.execute("CREATE TABLE tickets(created TEXT, region TEXT, text TEXT)")

    # one always-on campaign per region per month plus planted campaign windows
    campaign_windows = []
    for p in plants:
        if p["mechanism"] == "campaign_end":
            cs = p["start"] - dt.timedelta(days=p.get("length", 10))
            campaign_windows.append((p["region"], cs, p["start"] - dt.timedelta(days=1)))
            wk = cs - dt.timedelta(days=cs.weekday())
            mkt.execute("INSERT INTO campaigns VALUES(?,?,?,?,?,?)",
                        (wk.isoformat(), p["region"], "FestBlast", 240000, cs.isoformat(),
                         (p["start"] - dt.timedelta(days=1)).isoformat()))

    for d in range(days):
        day = start + dt.timedelta(days=d)
        for region in REGIONS:
            for category in CATEGORIES:
                base = BASE[(region, category)] * DOW_MULT[day.weekday()]
                units = base * rng.gauss(1.0, 0.045)
                price = PRICE[category] * rng.gauss(1.0, 0.008)
                deliv = rng.gauss(11.0, 0.9)

                for p in plants:
                    if p["region"] not in (region, "*") or p.get("category", category) != category:
                        continue
                    t = (day - p["start"]).days
                    L = p.get("length", 14)
                    m = p["mechanism"]
                    if m == "stockout" and 0 <= t < p.get("length", 3):
                        units *= (1 - p.get("magnitude", 0.75))
                    elif m == "price_rise" and t >= 0:
                        price *= (1 + p.get("magnitude", 0.12)); units *= (1 - p.get("magnitude", 0.12) * 2.0)
                    elif m == "competitor_entry" and t >= 0:
                        units *= (1 - min(p.get("magnitude", 0.02) * (t + 1), 0.30))
                    elif m == "campaign_end":
                        if -p.get("length", 10) <= t < 0:
                            units *= (1 + p.get("magnitude", 0.22))
                    elif m == "delivery_degradation" and 0 <= t < L:
                        deliv += p.get("magnitude", 8.0); units *= 0.90
                    elif m == "discount_launch" and 0 <= t < L:
                        price *= (1 - p.get("magnitude", 0.15)); units *= (1 + p.get("magnitude", 0.15) * 1.8)
                    elif m == "cannibalization" and t >= 0:
                        units *= (1 - p.get("magnitude", 0.18))
                    elif m == "cannibal_sibling" and t >= 0:
                        units *= (1 + p.get("magnitude", 0.18) * 0.9)
                    elif m == "supply_shortage" and 0 <= t < L:
                        units *= (1 - p.get("magnitude", 0.35))
                    elif m == "unknown_shock" and 0 <= t < L:
                        units *= (1 - p.get("magnitude", 0.30))

                for ch, share in CHAN_SHARE.items():
                    sales.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?)",
                                  (day.isoformat(), region, category, ch,
                                   round(units * share, 2), round(price, 2), round(deliv, 1)))

            # tickets: ~3 normal per region-day, plus mechanism-specific chatter
            for _ in range(rng.randint(2, 4)):
                ops.execute("INSERT INTO tickets VALUES(?,?,?)",
                            (day.isoformat(), region,
                             rng.choice(TICKET_NORMAL).format(oid=rng.randint(41000, 99000))))
            for p in plants:
                if p["region"] != region:
                    continue
                t = (day - p["start"]).days
                if p["mechanism"] == "delivery_degradation" and -2 <= t < p.get("length", 14):
                    for _ in range(rng.randint(2, 4)):
                        ops.execute("INSERT INTO tickets VALUES(?,?,?)",
                                    (day.isoformat(), region,
                                     rng.choice(TICKET_DELAY).format(region=region, oid=rng.randint(41000,99000))))
                if p["mechanism"] == "supply_shortage" and -1 <= t < p.get("length", 14):
                    for _ in range(rng.randint(1, 3)):
                        ops.execute("INSERT INTO tickets VALUES(?,?,?)",
                                    (day.isoformat(), region,
                                     rng.choice(TICKET_SUPPLY).format(
                                         category=p.get("category", "Dairy"), region=region)))

    # routine weekly marketing rows so the source is never empty
    wk = start - dt.timedelta(days=start.weekday())
    while wk <= end:
        for region in REGIONS:
            mkt.execute("INSERT INTO campaigns VALUES(?,?,?,?,?,?)",
                        (wk.isoformat(), region, "AlwaysOn", rng.randint(40000, 70000),
                         wk.isoformat(), (wk + dt.timedelta(days=6)).isoformat()))
        wk += dt.timedelta(days=7)

    for c in (sales, mkt, ops):
        c.commit(); c.close()
    return {"start": start.isoformat(), "end": end.isoformat(), "plants": len(plants)}
