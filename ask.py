"""Ask your sales data in plain language.

Claude never touches the numbers. It only (1) picks one of a few approved analyses and
(2) words the answer from the computed table. The math is done by pandas, the plan is
validated against a whitelist, and the answer is checked so it cannot contain a number
that is not in the table. All data is fictional.
"""
import json, os, re, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent
MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
df = pd.read_csv(ROOT / "data/deals_sample.csv")
df["month"] = df["close_date"].str[:7]
df["won"] = (df["outcome"] == "won").astype(int)

GROUPS = ["segment", "channel", "team", "month", "none"]
TOOLS = {
    "win_rate": "share of deals won (percent)",
    "deal_count": "number of deals",
    "revenue": "total amount of won deals",
    "avg_cycle": "average sales cycle in days",
    "lost_reasons": "count of lost deals by reason",
}
FILTER_KEYS = ["segment", "channel", "team", "month"]


# ---- analyses (the only code that touches the numbers) -------------------------
def run(plan):
    d = df.copy()
    for k, v in plan.get("filters", {}).items():
        d = d[d[k] == v]
    if d.empty:
        return pd.DataFrame()
    g = plan["group_by"]
    key = d[g] if g != "none" else pd.Series("all deals", index=d.index)
    t = plan["tool"]
    by_month = g == "month"
    if t == "win_rate":
        out = d.groupby(key)["won"].agg(deals="count", won="sum")
        out["win_rate_%"] = (out["won"] / out["deals"] * 100).round(1)
        out = out.sort_index() if by_month else out.sort_values("win_rate_%", ascending=False)
        return out.rename_axis(g).reset_index()
    if t == "deal_count":
        return d.groupby(key).size().rename("deals").sort_values(ascending=False).rename_axis(g).reset_index()
    if t == "revenue":
        return d[d.won == 1].groupby(key)["amount"].sum().rename("revenue").sort_values(ascending=False).rename_axis(g).reset_index()
    if t == "avg_cycle":
        return d.groupby(key)["cycle_days"].mean().round(1).rename("avg_cycle_days").sort_values().rename_axis(g).reset_index()
    if t == "lost_reasons":
        lost = d[d.outcome == "lost"]
        return lost.groupby("lost_reason").size().rename("lost_deals").sort_values(ascending=False).reset_index()


def validate(plan):
    """Reject anything outside the approved menu."""
    if not isinstance(plan, dict) or plan.get("unsupported"):
        return False
    if plan.get("tool") not in TOOLS or plan.get("group_by", "none") not in GROUPS:
        return False
    plan.setdefault("group_by", "none")
    f = plan.setdefault("filters", {})
    if not isinstance(f, dict):
        return False
    for k, v in f.items():
        if k not in FILTER_KEYS or v not in set(df[k]):
            return False
    return True


# ---- planning ---------------------------------------------------------------------
PLAN_PROMPT = """You route questions about a sales-deals table to ONE approved analysis.
Analyses: {tools}
group_by options: {groups}
Filters (optional) keys: {fkeys}. Allowed values:
{values}

Question: {q}

Return ONLY JSON: {{"tool": ..., "group_by": ..., "filters": {{}}}}
If the question cannot be answered with these analyses, return {{"unsupported": true}}."""


def llm(prompt, max_tokens=300):
    import anthropic
    msg = anthropic.Anthropic().messages.create(model=MODEL, max_tokens=max_tokens,
                                                messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def plan_with_claude(q):
    values = "\n".join(f"  {k}: {sorted(df[k].unique())}" for k in FILTER_KEYS)
    text = llm(PLAN_PROMPT.format(tools=json.dumps(TOOLS), groups=GROUPS, fkeys=FILTER_KEYS, values=values, q=q))
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))


def plan_with_rules(q):
    """Offline fallback: keyword router with the same output format."""
    s = q.lower()
    if any(w in s for w in ("will", "next year", "predict", "forecast", "future", "should we")):
        return {"unsupported": True}
    tool = ("lost_reasons" if ("lost" in s and "reason" in s) or "why" in s else
            "revenue" if any(w in s for w in ("revenue", "amount", "sales value")) else
            "avg_cycle" if any(w in s for w in ("cycle", "how long", "days")) else
            "deal_count" if any(w in s for w in ("how many", "number of", "count")) else
            "win_rate" if any(w in s for w in ("win", "convert", "conversion")) else None)
    if tool is None:
        return {"unsupported": True}
    group = next((g for g, w in [("channel", "channel"), ("segment", "segment"), ("team", "team"), ("month", "month")] if w in s), "none")
    filters = {}
    for k in ("segment", "channel", "team"):
        for v in df[k].unique():
            if v.lower() in s:
                filters[k] = v
    return {"tool": tool, "group_by": group, "filters": filters}


# ---- explaining ---------------------------------------------------------------------
def numbers(text):
    return set(re.findall(r"\d[\d,.]*\d|\d", text.replace("%", "")))


def grounded(answer, table_text):
    allowed = numbers(table_text)
    return all(n.rstrip(".,") in allowed for n in numbers(answer))


def explain_with_claude(q, table_text):
    return llm(f"Question: {q}\n\nResult table (computed, final):\n{table_text}\n\n"
               "Answer in at most 3 short sentences using ONLY numbers that appear in the table. "
               "Do not speculate about causes.", 200).strip()


def explain_with_rules(table, plan):
    metric = table.columns[-1]
    lowest = plan["tool"] == "avg_cycle"
    row = table.loc[table[metric].idxmin() if lowest else table[metric].idxmax()]
    label = "Lowest" if lowest else "Highest"
    return f"{label} {metric}: {row.iloc[0]} ({', '.join(f'{c}={row[c]}' for c in table.columns[1:])})."


def ask(q, use_claude):
    plan, how = None, "rules"
    if use_claude:
        try:
            plan, how = plan_with_claude(q), "claude"
        except Exception as e:
            print(f"  [claude planning failed: {str(e)[:80]} -> using rules]")
    if plan is None:
        plan = plan_with_rules(q)
    if not validate(plan):
        return "I can't answer that with this data. I can do: " + ", ".join(TOOLS) + ".", None, how
    table = run(plan)
    if table.empty:
        return "No deals match those filters.", plan, how
    ttext = table.to_string(index=False)
    answer = None
    if use_claude:
        try:
            answer = explain_with_claude(q, ttext)
            if not grounded(answer, ttext):
                print("  [answer had a number not in the table -> using safe answer]")
                answer = None
        except Exception as e:
            print(f"  [claude answer failed: {str(e)[:80]}]")
    return answer or explain_with_rules(table, plan), (plan, ttext), how


def main():
    use_claude = bool(os.environ.get("ANTHROPIC_API_KEY"))
    questions = sys.argv[1:] or [
        "Which channel has the best win rate?",
        "How many deals did we close in each segment?",
        "Why do we lose deals?",
        "What is the revenue by team?",
        "Compare win rate by month",
        "What will next year's revenue be?",
    ]
    print(f"mode: {'claude' if use_claude else 'offline rules'} | {len(df)} fictional deals\n")
    for q in questions:
        answer, detail, how = ask(q, use_claude)
        print(f"Q: {q}")
        if isinstance(detail, tuple):
            plan, ttext = detail
            print(f"  analysis: {plan['tool']} by {plan['group_by']} {plan['filters'] or ''} (planned by {how})")
            print("  " + ttext.replace("\n", "\n  "))
        print(f"  A: {answer}\n")


if __name__ == "__main__":
    main()
