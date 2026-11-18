"""Generates FICTIONAL sales data for the demo (fixed seed, reproducible)."""
import numpy as np, pandas as pd
rng = np.random.default_rng(7)
n = 1500
segments = ["Retail", "Logistics", "Healthcare", "Services", "Industry"]
channels = ["Phone + WhatsApp", "Phone + Email", "WhatsApp only", "Email only"]
owners = ["Team A", "Team B", "Team C", "Team D"]
reasons = ["Price", "No budget", "Chose competitor", "No response", "Bad timing"]
seg_p = {"Retail": .30, "Logistics": .24, "Healthcare": .26, "Services": .17, "Industry": .13}
ch_m = {"Phone + WhatsApp": 1.35, "Phone + Email": 1.0, "WhatsApp only": .8, "Email only": .5}
dates = pd.to_datetime("2026-01-01") + pd.to_timedelta(rng.integers(0, 181, n), unit="D")
seg = rng.choice(segments, n); ch = rng.choice(channels, n, p=[.3, .3, .25, .15])
p = np.array([seg_p[s] * ch_m[c] * (1 + (d.month - 1) * 0.04) * 0.9 for s, c, d in zip(seg, ch, dates)])
won = rng.random(n) < np.clip(p, 0, .9)
df = pd.DataFrame({"close_date": dates.strftime("%Y-%m-%d"), "segment": seg, "channel": ch,
                   "team": rng.choice(owners, n), "outcome": np.where(won, "won", "lost"),
                   "amount": np.where(won, rng.integers(4, 40, n) * 1000, 0),
                   "cycle_days": rng.integers(3, 60, n),
                   "lost_reason": np.where(won, "", rng.choice(reasons, n, p=[.30, .25, .20, .15, .10]))})
df.sort_values("close_date").to_csv("data/deals_sample.csv", index=False)
print(len(df), "rows | overall win rate", round(won.mean() * 100, 1), "%")
