# Agent instructions

## Project

Atira EHL Challenge, "From RFQ to bid" (challenge id `rfq`). We build an agent system that, with no human in the
loop, turns a public tender into one priced, signed bid:

1. **Tender portal** (`tender-portal`): read the tender, bill of quantities and bidder Q&A (quantity changes,
   withdrawals, amendments, commercial/packaging/delivery/setup keys). The bid is entered in its configurator.
2. **Supplier portal** (`customer-portal`): buyer's technical specification; use the revision marked *current*
   (it opens the oldest first).
3. **ERP** (`erp`): materials, stock, lead times, price conditions (validity dates, quantity scales, currency/FX).
   SAP-style transaction codes, F4 search popup, short session timeout.
4. **Webmail** (`mail`): sales director's discount approval, signing TAN, and keyed mails (Konditionsregeln,
   Technikfreigabe, Verpackungstarife, Terminfreigabe, Devisenfixing, Rüstpools, Projektbonus, Preisindizes).

The run's `brief` holds the full bid rules and is the source of truth. Challenge page with all 29 rules:
https://ehl-challenge.atira.ai/challenges/rfq.md

## Findings log

`FINDINGS.md` records why agents failed and the general fix for each. Add to it whenever a run shows a new failure.
No website values in it (the reviewer rejects them in notes too); `tests/test_no_scenario_values.py` checks every
tracked file against the facts of the last local run.

## Hard rules (package is reviewed by an AI before every scored run)

- **No hardcoded scenario values** anywhere in the package (code, prompts, config, notes, defaults, fallbacks):
  tender references, material numbers, prices, totals, discounts, logins, TANs. Facts the brief states for every
  scenario are fine.
- **Agentic, not scripted:** a model must choose where to navigate, what to search and which documents matter, at
  run time. Helpers may extract a page the model picked, parse documents, paginate a model-selected result set,
  calculate, validate, retry and fill forms. No fixed click paths, no crawler that collects everything for one
  model call.
- **Generalize:** the final (decisive) run uses a private dataset with different website software, layout,
  navigation, site names and data split. Never tune to public-1 page structure.
- In the sandbox: only the platform, the 4 websites and the model proxy are reachable. Use only the browsers from
  `CDP_URLS` (max 4, set `"browsers"` in `agent.json`); never launch browsers there. No local models.

## Scoring

Eligible (correct tender reference) first → quality 0–100 ↓ → cost × time ↑. Every field scores independently, so
a partial answer submitted in time beats a perfect one that is late (late = 0). Scored run: 20 min; submit ~1 min
before `run.seconds_left(task)` hits 0. Bid case weights: decision 5, reference 5, discount 5, positions ~75,
total 5, arithmetic consistency 5. Per position: material 20%, quantity 15%, base price 15%, surcharge 10%,
packaging 10%, project bonus 10%, final unit price 10%, delivery 10%.

## Code layout (from the Atira starter kit)

| File | Role |
| --- | --- |
| `agent.py` | Entry point. `solve(task, page)` is where the agent goes. Answer is entered on the tender portal (`submission.kind == "site"`), so `solve` returns `None` after signing. |
| `run.py` | Run contract: `load_run()`, `seconds_left()`, `submit_answer()` (API submissions only). |
| `browsers.py` | `connect(playwright, n)` attaches to sandbox browser n over CDP; locally launches Chromium. |
| `models.py` | Hosted models: `qwen()` (OpenAI client), `ask_qwen`, `ask_clef`. |
| `agent.json` | Sandbox `setup`/`run` commands, `models`, optional `browsers`. |
| `tests/` | Plumbing tests: `uv run python -m unittest discover -s tests`. |

Python 3.12 with uv. Money math: use `Decimal` with `ROUND_HALF_UP`, round once at the end as the rules say.

## Workflow

```sh
atira models proxy                         # terminal 1, keep open (free Qwen + Clef locally)
eval "$(atira scout --env)"                # terminal 2: scouting logins + model env vars
uv run --no-sync python agent.py           # local run; nothing counts, answer is only printed
atira test-run .                           # sandbox run on public data, up to 2 h, full score breakdown
atira submit .                             # reviewed, then one scored run (ask the team first)
```

## Architecture (agent.py)

| Browser | Site | Phase 1 (parallel) | Later |
| --- | --- | --- | --- |
| 1 | tender portal | `tender-research`: positions, Q&A | `tender-submit`: form; calls `get_bid_values` (waits for the calculator) and `ask_mailbox` |
| 2 | webmail | `mail-research`: approvals, rule mails, own address | second tab answers `ask_mailbox` (TAN) |
| 3 | supplier portal | `spec`: current revision, requirements | |
| 4 | ERP | `erp-login` | one tab per position (`erp_agent.run_erp`) once tender + spec are in |

Shapes between parts: `contracts.py`. Goals: `research.py`, `erp_agent.py`. Time: phase 1 until 45 % of the clock,
bid values at end − 5 min, submission done by end − 1 min. A failing sub-agent yields `{}` and the bid goes out with
what is known (missing positions omitted).

## Calculator (calculator.py): open work

Implemented and tested (`tests/test_calculator.py`): quantities (withdrawals, Satz), scoped amendments, valid condition
and scale, conditional director discount, shared stock lead time, rounding, total, no_bid. **TODO**:
`advanced_components()`: Konditionsgruppe clauses, mass surcharge with metal index, packaging cartons, shared setup pool,
project bonus, currency conversion, usable-stroke reserve (rules 12–28 of the brief). Rule mails arrive verbatim in
`MailFacts.rule_mails`; turning their prose/tables into numbers may need one model call per mail. Test with made-up
numbers only.

## Agent profiles

Every sub-agent runs with a profile from `profiles.py`: model, thinking mode and limits. Thinking costs ~2.5× time and
~25× output tokens per step, so: `off` (logins, gates, fetching a TAN), `auto` (fast, thinks only on the step after
something went wrong), `on` (reading rules, matching attributes). Profiles: `mail_login`, `mail`, `mail_research`,
`tender_submit`, `tender_research`, `erp_position`, `spec`, `default`. Override without code changes:
`AGENT_PROFILES='{"mail": {"thinking": "on", "max_steps": 40}}'`.

Local runs get a 20-minute clock like a scored run (`RUN_SECONDS` to change it).

## Observability

All sub-agents log through `telemetry.py`. Features are switched with flags, without code changes:

| Variable | Effect |
| --- | --- |
| `AGENT_LOG` | Comma-separated features: `steps`, `model`, `pages`, `usage`, `timing`, `notes`, `errors`, `summary`. Also `all`, `none`, `-feature`. Default `steps,usage,errors,summary`. |
| `AGENT_LOG_DIR` | Also write every event as JSON lines to `<dir>/events.jsonl`. Locally use `dev/out/log` (gitignored: it holds scenario data). |
| `AGENT_LOG_CONSOLE=0` | Silence the console; the file still gets events. |

Logins are masked in every sink. Debugging locally: `AGENT_LOG=all AGENT_LOG_DIR=dev/out/log`. In scored runs keep the
default: run logs are visible to the team through `atira` and cost nothing.

The `atira` MCP server (`atira mcp`) exposes `test_run`, `wait_for_run`, `diagnose_run`, `run_logs`,
`run_screenshot`, `run_inputs` and `submit`. Never submit without a teammate's go-ahead.

Docs: https://ehl-challenge.atira.ai/llms.txt (index), `/docs/run-contract.md`, `/docs/building-an-agent.md`,
`/docs/fair-play.md`, `/docs/scoring.md`, `/docs/submitting.md`.
