# Ask Your Sales Data: natural-language questions with verifiable answers (demo)

Ask a question in plain English ("Which channel has the best win rate?") and get a table plus a short answer.
**All data is fictional** (1,500 generated deals, `make_data.py`). The pattern is what matters.

## The design choice: the model never does the math
1. **Plan:** Claude picks ONE analysis from an approved menu (win rate, deal count, revenue, average cycle, lost reasons), a grouping, and optional filters.
2. **Validate:** the plan is checked against a whitelist. Unknown tools, groupings or filter values are rejected. Questions the data can't answer (forecasts, off-topic) get an honest "I can't answer that".
3. **Compute:** pandas calculates the table. This is the only code that touches the numbers.
4. **Explain:** Claude words a short answer from the computed table only.
5. **Check:** every number in the answer must appear in the table; otherwise a safe templated answer is used instead.

The output always shows the analysis that ran and its table, so a person can verify any answer.

## Run
    pip install -r requirements.txt
    python make_data.py                          # regenerates the fictional data
    python ask.py                                # offline: keyword router + templated answers
    ANTHROPIC_API_KEY=... python ask.py          # Claude plans and explains
    python ask.py "Win rate for Retail by channel"   # your own question

## Why this pattern
Large language models are good at understanding a question and bad at arithmetic over many rows.
Splitting "understand" from "compute" and checking the output is what makes this safe for a team to rely on.
It extends naturally to real sources (SQL, GA4, a CRM): replace `run()` with approved queries.

## Honest limits
Fixed menu of five analyses; no multi-step reasoning or custom date ranges; the offline router is a simple keyword matcher.
The Claude path should be run with your own key and tested on your questions before relying on it.
