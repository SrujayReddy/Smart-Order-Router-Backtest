#!/usr/bin/env python3
"""
Smart-Order-Router back-test (Cont-Kukanov static allocator).
Produces:
  • JSON summary (stdout)
  • results.png (relative-cost plot)

Only numpy, pandas, matplotlib, and the Python std-lib are used.
"""

import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

TARGET_SHARES = 5_000     # order size (shares)

# ─────────────────────────────  DATA  ──────────────────────────────
df = pd.read_csv("l1_day.csv")
df["ts_event"] = pd.to_datetime(df["ts_event"])
df = df.sort_values(["ts_event", "publisher_id"])
df = df.groupby(["ts_event", "publisher_id"], as_index=False).first()
df = df.sort_values("ts_event").reset_index(drop=True)

# ───────────────────  STATIC ALLOCATOR (exact)  ───────────────────
def allocate(order_size, venues, lam_over, lam_under, theta, step=100):
    """Brute-force static split per allocator_pseudocode.txt (100-share grid)."""
    splits = [[]]                        # incremental cart-product
    for v in venues:
        new = []
        for alloc in splits:
            used = sum(alloc)
            max_v = min(order_size - used, v["ask_size"])
            for q in range(0, max_v + 1, step):
                new.append(alloc + [q])
        splits = new

    best_cost, best_split = float("inf"), [0] * len(venues)
    for split in splits:
        executed = cash = 0.0
        for i, v in enumerate(venues):
            exe = min(split[i], v["ask_size"])
            executed += exe
            cash += exe * (v["ask"] + v["fee"]) - max(split[i] - exe, 0) * v["rebate"]
        under, over = max(order_size - executed, 0), max(executed - order_size, 0)
        cost = cash + theta * (under + over) + lam_under * under + lam_over * over
        if cost < best_cost:
            best_cost, best_split = cost, split
    return best_split


# ────────────────  UTILS (track over every snapshot)  ──────────────
def rec(cash_track, time_track, cash, t0, t_now):
    cash_track.append(cash)
    time_track.append((t_now - t0).total_seconds())


# ───────────────────────  STRATEGY SIMULATORS  ────────────────────
def simulate_static(df, lam_over, lam_under, theta):
    remain, cash = TARGET_SHARES, 0.0
    cash_track, time_track = [], []
    t0 = df.iloc[0]["ts_event"]

    for _, row in df.iterrows():
        venue = {"ask": row["ask_px_00"], "ask_size": row["ask_sz_00"],
                 "fee": 0.0, "rebate": 0.0}
        if remain > 0:
            qty = allocate(remain, [venue], lam_over, lam_under, theta)[0]
            buy = min(qty, venue["ask_size"], remain)
            cash += buy * venue["ask"]
            remain -= buy
        rec(cash_track, time_track, cash, t0, row["ts_event"])

    avg = cash / (TARGET_SHARES - remain) if remain < TARGET_SHARES else 0.0
    return TARGET_SHARES - remain, cash, avg, time_track, cash_track


def simulate_naive(df):
    remain, cash = TARGET_SHARES, 0.0
    ct, tt = [], []
    t0 = df.iloc[0]["ts_event"]

    for _, row in df.iterrows():
        buy = min(row["ask_sz_00"], remain)
        cash += buy * row["ask_px_00"]
        remain -= buy
        rec(ct, tt, cash, t0, row["ts_event"])
    avg = cash / (TARGET_SHARES - remain) if remain < TARGET_SHARES else 0.0
    return TARGET_SHARES - remain, cash, avg, tt, ct


def simulate_twap(df):
    start, end = df.iloc[0]["ts_event"], df.iloc[-1]["ts_event"]
    n_int = int((end - start).total_seconds() // 60) + 1
    chunks = np.full(n_int, TARGET_SHARES // n_int)
    chunks[: TARGET_SHARES % n_int] += 1
    triggers = [start + pd.Timedelta(seconds=60 * i) for i in range(n_int)]

    remain, cash, nxt = TARGET_SHARES, 0.0, 0
    ct, tt = [], []
    t0 = start

    for _, row in df.iterrows():
        if nxt < n_int and row["ts_event"] >= triggers[nxt] and remain > 0:
            buy = min(remain, row["ask_sz_00"], chunks[nxt])
            cash += buy * row["ask_px_00"]
            remain -= buy
            nxt += 1
        rec(ct, tt, cash, t0, row["ts_event"])
    avg = cash / (TARGET_SHARES - remain) if remain < TARGET_SHARES else 0.0
    return TARGET_SHARES - remain, cash, avg, tt, ct


def simulate_vwap(df):
    sizes = df["ask_sz_00"].astype(float).values
    tot = sizes.sum()
    if tot == 0:
        return 0, 0.0, 0.0, [], []

    tgt = np.floor(sizes / tot * TARGET_SHARES).astype(int)
    tgt[np.argsort((sizes / tot * TARGET_SHARES) - tgt)[::-1][
        : TARGET_SHARES - tgt.sum()
    ]] += 1

    remain, cash = TARGET_SHARES, 0.0
    ct, tt = [], []
    t0 = df.iloc[0]["ts_event"]

    for i, row in df.iterrows():
        buy = min(remain, row["ask_sz_00"], tgt[i])
        cash += buy * row["ask_px_00"]
        remain -= buy
        rec(ct, tt, cash, t0, row["ts_event"])
    avg = cash / (TARGET_SHARES - remain) if remain < TARGET_SHARES else 0.0
    return TARGET_SHARES - remain, cash, avg, tt, ct


# ───────────────────────────  RUN ALL  ─────────────────────────────
best_params = (0.0, 223.0, 0.0)               # λ_over, λ_under, θ_queue

filled_s, cash_s, avg_s, ts_s, cs_s = simulate_static(df, *best_params)
filled_n, cash_n, avg_n, ts_n, cs_n = simulate_naive(df)
filled_t, cash_t, avg_t, ts_t, cs_t = simulate_twap(df)
filled_v, cash_v, avg_v, ts_v, cs_v = simulate_vwap(df)

# ───────────────────────  JSON OUTPUT  ────────────────────────────
bps = lambda base, new: (base - new) / base * 1e4 if base else 0.0
res = {
    "best_params": {"lambda_over": best_params[0],
                    "lambda_under": best_params[1],
                    "theta_queue": best_params[2]},
    "static": {"total_cash_spent": round(cash_s, 2), "avg_price": round(avg_s, 6)},
    "naive":  {"total_cash_spent": round(cash_n, 2), "avg_price": round(avg_n, 6),
               "savings_bps": round(bps(avg_n, avg_s), 2)},
    "twap":   {"total_cash_spent": round(cash_t, 2), "avg_price": round(avg_t, 6),
               "savings_bps": round(bps(avg_t, avg_s), 2)},
    "vwap":   {"total_cash_spent": round(cash_v, 2), "avg_price": round(avg_v, 6),
               "savings_bps": round(bps(avg_v, avg_s), 2)}
}
print(json.dumps(res, indent=2))

# ───────────────────────  RELATIVE-COST PLOT  ─────────────────────
def trim(a, b):
    n = min(len(a), len(b))
    return np.asarray(a[:n]), np.asarray(b[:n])

base = np.asarray(cs_n)

rel_s, base_s = trim(cs_s, base)
rel_t, base_t = trim(cs_t, base)
rel_v, base_v = trim(cs_v, base)

ts_s = np.asarray(ts_s)[: len(rel_s)]
ts_t = np.asarray(ts_t)[: len(rel_t)]
ts_v = np.asarray(ts_v)[: len(rel_v)]

plt.figure(figsize=(6, 4))
plt.step(ts_s, rel_s - base_s, label="Static – Naïve", ls="--", lw=2)
plt.step(ts_t, rel_t - base_t, label="TWAP – Naïve")
plt.step(ts_v, rel_v - base_v, label="VWAP – Naïve")
plt.axhline(0, color="k", lw=.7)
plt.xlabel("Seconds since start")
plt.ylabel("Cumulative $ savings vs naïve")

# >>> axis formatter for cleaner numbers (-1 300 → -1 K) <<<
ax = plt.gca()
ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x/1e3:.0f}K"))

plt.grid(alpha=.3, ls="--")
plt.legend(bbox_to_anchor=(1.04, 1), loc="upper left")
plt.tight_layout()
plt.savefig("results.png")

