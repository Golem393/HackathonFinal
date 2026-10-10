"""Entry point and orchestrator: agent.json runs `uv run --no-sync python agent.py`, in the sandbox and locally.

Four browsers, one website each, all working at once:

    browser 1  tender portal   research (positions, Q&A)  ->  submission (waits for the bid values when it needs them)
    browser 2  webmail         research (approvals, rule mails); a second tab answers ask_mailbox (address, TAN)
    browser 3  supplier portal specification (current revision, requirements)
    browser 4  ERP             logs in early; then one tab per position (material, prices, stock)

Phase 1 runs the three research agents and the ERP login in parallel. As soon as the tender and specification facts are
in, the ERP positions start. The calculator (calculator.py) turns all facts into the bid. Every model decision is made
by the sub-agents at run time; this file only wires them together, keeps time and hands facts on.
Docs: $API/docs/building-an-agent.md, $API/docs/run-contract.md, and the rules: $API/docs/fair-play.md
"""
import asyncio
import json
import os
import re
import sys
import time

from playwright.async_api import async_playwright

import browsers
import calculator
import erp_agent
import models
import research
import run as contract
import telemetry
from web_agent import WebAgent

PLAYWRIGHT = None  # set by main(): the running Playwright, for browsers 2 to 4

SUBMIT_GOAL = """You submit our company's bid on this tender portal. Our management's task brief is below: follow its
submission instructions exactly (participation, bidder registration, offer type, configurator, number format,
acknowledgements, TAN signing, final confirmation).

- Tender reference and bidder details: as stated in the brief.{contact}
- Offer type: the main offer for a bid, the waiver for a no-bid (the values tell you which).
- When the form asks for positions, prices, discount or totals, call get_bid_values ONCE and enter exactly what it
  returns (it may take a while: our calculation is still running). Omit (e.g. "Position auslassen") every position it
  lists as omitted. Enter numbers in German format as given. Optional breakdown fields: enter them only if given.
- You cannot open the webmail. When the portal sends something by e-mail (signing TAN, confirmation code), trigger the
  sending on the portal first, then call ask_mailbox ONCE and enter the result right away (a TAN is valid five minutes;
  a new request invalidates the old one).
- Never use the browser's back navigation: it clears the later steps.
- On the review/summary page, BEFORE the final binding submission: copy every value it shows (decision, positions with
  material, quantity, prices, lead times, omitted positions, discount, totals) with `note`, verbatim. Then make the
  final binding submission; its browser confirmation dialog is accepted for you.

Finish with {{"submitted": true or false, "summary_as_shown": "<the summary page's values, verbatim>",
"confirmation": "<receipt text or number>", "problems": "..."}}

TASK BRIEF:
{brief}"""

ASK_MAIL_GOAL = """In this webmail (our sales mailbox), a colleague on the tender portal needs this, for tender reference
{reference}: {request}

Get exactly that and finish immediately: if it is already visible (e.g. in the page header), finish right away.
If it is a mail that was just sent, check the inbox newest first; search with the reference plus a topic word if the
list is long. Several similar mails may exist: take the most recent one for exactly this reference.
Finish with {{"answer": "<the code, TAN, link or text asked for, exactly as written>", "received": "...",
"subject": "...", "details": "<anything else the colleague must know, e.g. validity>"}}."""

BRIEF_FACTS_PROMPT = """From this task brief, extract as JSON: {{"reference": "<tender reference>", "buyer": "<contracting
authority>", "scenario_date": "<scenario date, ISO>", "bidder": "<our company name>"}}. Answer with the JSON only.

{brief}"""


# ---- helpers -----------------------------------------------------------------------------------------------------

def site_for(task: dict, *keywords: str) -> dict:
    """A website of the run by siteId, falling back to a keyword in its id or URL (the private dataset renames sites)."""
    for keyword in keywords:
        for site in task["access"]:
            if keyword in (site.get("siteId", "") + " " + site.get("url", "")).lower():
                return site
    raise LookupError(f"No website for {keywords}")


def brief_without_logins(task: dict) -> str:
    """The brief for the model, with login values replaced: the agents type them through type_credential."""
    brief = task["brief"]
    for site in task["access"]:
        for value in (site.get("credentials") or {}).values():
            if value:
                brief = brief.replace(str(value), "(use type_credential)")
    return brief


async def brief_facts(task: dict) -> dict:
    """Reference, buyer, scenario date and bidder, read from the brief by the model (no thinking needed)."""
    brief = brief_without_logins(task)
    try:
        reply = await models.qwen().with_options(timeout=90).chat.completions.create(
            model=models.QWEN_MODEL, messages=[{"role": "user", "content": BRIEF_FACTS_PROMPT.format(brief=brief[:6000])}],
            extra_body={"chat_template_kwargs": {"enable_thinking": False}})
        text = reply.choices[0].message.content or ""
        facts = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except Exception as error:
        telemetry.tracker("orchestrator").event("errors", f"brief facts: {error}")
        facts = {}
    if not facts.get("scenario_date"):  # the date is also plainly in the brief's text
        m = re.search(r"\d{4}-\d{2}-\d{2}T[\d:]+Z?", brief)
        facts["scenario_date"] = m.group(0) if m else time.strftime("%Y-%m-%d")
    return facts


def german(value) -> str:
    """1234.5 -> '1.234,50' (the portal wants German number format)."""
    return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def bid_for_form(bid: dict) -> str:
    """The calculator's bid as instructions for the submission agent."""
    lines = [f"Decision: {'bid (main offer)' if bid['decision'] == 'bid' else 'no bid (waiver)'}",
             f"Discount: {german(bid['discount_percent'])} %", f"Net total: {german(bid['total_net'])} EUR"]
    for p in bid.get("positions") or []:
        extra = "".join(f", {label} {german(p[key])}" for key, label in
                        (("base_unit_price", "base price/piece"), ("surcharge_per_unit", "surcharge/piece"),
                         ("packaging_per_unit", "packaging/piece"), ("rebate_total", "project bonus (whole position)"))
                        if p.get(key) is not None)
        lines.append(f"Position {p['position']}: material {p['material_number']}, quantity {p['quantity']} pieces, "
                     f"unit price {german(p['unit_price'])} EUR, lead time {p['lead_time_weeks']} weeks{extra}")
    if bid.get("omitted"):
        lines.append("Omit these positions: " + ", ".join(bid["omitted"]))
    return "\n".join(lines)


def bid_table(bid: dict) -> str:
    """The bid as a readable block for the log."""
    rows = [f"  {bid.get('tender_reference')} | {bid.get('decision')} | discount {bid.get('discount_percent')} % | "
            f"total {bid.get('total_net')} EUR"]
    for p in bid.get("positions") or []:
        rows.append(f"  {p['position']:>6}  {p['material_number']:<14} qty {p['quantity']:>5}  unit {p['unit_price']:>10}"
                    f"  base {p.get('base_unit_price')}  lead {p['lead_time_weeks']} w")
    if bid.get("omitted"):
        rows.append(f"  omitted: {', '.join(bid['omitted'])}")
    if bid.get("notes"):
        rows.append(f"  notes: {bid['notes'][:600]}")
    return "\n".join(rows)


def record(label: str, facts: dict) -> dict:
    """Log a research result in full (feature `facts`) and keep it in AGENT_LOG_DIR/facts/<label>.json."""
    telemetry.tracker(label).event("facts", f"{label} facts: {len(json.dumps(facts, ensure_ascii=False))} chars",
                                   facts=facts)
    folder = os.environ.get("AGENT_LOG_DIR")
    if folder:
        os.makedirs(os.path.join(folder, "facts"), exist_ok=True)
        with open(os.path.join(folder, "facts", re.sub(r"\W+", "_", label) + ".json"), "w") as file:
            json.dump(facts, file, ensure_ascii=False, indent=2)
    return facts


async def browser_page(number: int, fallback):
    """A fresh context page in browser `number` (0 is browser 1); a new tab in `fallback`'s browser when the run has
    fewer browsers. Locally, browsers.connect starts a Chromium of its own."""
    urls = browsers.cdp_urls()
    if PLAYWRIGHT is None or (urls and number >= len(urls)):
        return await fallback.context.new_page()
    return (await browsers.connect(PLAYWRIGHT, number))[1]


async def safely(coroutine, label: str, fallback: dict | None = None) -> dict:
    """A sub-agent's result (logged as facts), or `fallback` when it fails: one broken site must not stop the bid."""
    try:
        result = await coroutine
    except Exception as error:
        telemetry.tracker(label).event("errors", f"{label} failed: {str(error)[:300]}")
        result = dict(fallback or {}, error=str(error)[:300])
    return record(label, result) if isinstance(result, dict) else result


# ---- the run -----------------------------------------------------------------------------------------------------

async def solve(task: dict, page) -> dict | None:
    log = telemetry.tracker("orchestrator")
    seconds = contract.seconds_left(task)
    if seconds == float("inf"):  # locally there is no clock: act like a scored run (RUN_SECONDS, default 20 min)
        seconds = float(os.environ.get("RUN_SECONDS", "1200"))
    start = time.time()
    end = start + seconds - 60                      # submitted before this, whatever happens
    research_until = start + seconds * 0.45         # phase 1
    values_by = end - 300                           # the bid values must be ready: the submission needs ~5 min after

    tender_site, mail_site = site_for(task, "tender", "vergabe"), site_for(task, "mail", "post")
    spec_site, erp_site = site_for(task, "customer", "liefer", "supplier"), site_for(task, "erp")
    brief = brief_without_logins(task)
    facts = await brief_facts(task)
    reference, scenario_date = facts.get("reference") or "", facts.get("scenario_date")
    log.event("steps", f"brief: {json.dumps(facts, ensure_ascii=False)}")

    mail_page, spec_page, erp_page = (await browser_page(1, page), await browser_page(2, page),
                                      await browser_page(3, page))

    # Phase 1: everything that does not depend on anything else, at once.
    tender_task = asyncio.create_task(safely(
        WebAgent(page, tender_site, label="tender-research", profile="tender_research")
        .run(research.tender_goal(reference, scenario_date), deadline=research_until), "tender-research"))
    spec_task = asyncio.create_task(safely(
        WebAgent(spec_page, spec_site, label="spec", profile="spec")
        .run(research.spec_goal(reference, facts.get("buyer") or "", scenario_date), deadline=research_until), "spec"))
    mail_task = asyncio.create_task(safely(
        WebAgent(mail_page, mail_site, label="mail-research", profile="mail_research")
        .run(research.mail_goal(reference, scenario_date), deadline=research_until), "mail-research"))
    erp_login = asyncio.create_task(safely(
        WebAgent(erp_page, erp_site, label="erp-login", profile="site_login")
        .run(research.ERP_WARMUP_GOAL, deadline=research_until), "erp-login"))

    # Phase 2: ERP positions once tender and specification are known; results arrive one by one.
    erp_results: dict = {}

    async def erp_phase() -> None:
        tender, spec = await tender_task, await spec_task
        requirements = calculator.final_requirements(tender, spec)
        quantities = calculator.final_quantities(tender, spec)
        login = await erp_login
        jobs = []
        for position in tender.get("positions") or []:
            req = dict(requirements.get(position.get("requirement")) or {})
            if not req:
                log.event("errors", f"no requirement {position.get('requirement')} for position {position.get('position')}")
                continue
            req.pop("id", None)
            req.update(position=position.get("position"),
                       quantity_pieces=int(quantities[position["position"]]) if quantities.get(position.get("position")) else None)
            jobs.append(req)
        log.event("steps", f"ERP: {len(jobs)} positions in parallel tabs")
        await erp_agent.run_erp(erp_page.context, erp_site, jobs, scenario_date, deadline=values_by - 20,
                                learned=[str(n) for n in login.get("notes") or []], results=erp_results)
        record("erp-positions", erp_results)

    erp_task = asyncio.create_task(safely(erp_phase(), "erp"))

    async def bid_values() -> dict:
        """Wait for the ERP until the values deadline, then compute with whatever is finished."""
        try:
            await asyncio.wait_for(asyncio.shield(erp_task), timeout=max(5, values_by - time.time()))
        except asyncio.TimeoutError:
            log.event("errors", f"values deadline: ERP finished {len(erp_results)} positions")
        tender = tender_task.result() if tender_task.done() else {}
        spec = spec_task.result() if spec_task.done() else {}
        if not mail_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(mail_task), timeout=30)
            except asyncio.TimeoutError:
                log.event("errors", "values deadline: mail research not finished, discount 0 %")
        mail = mail_task.result() if mail_task.done() else {}
        bid = calculator.compute_bid(reference, scenario_date, tender, spec, mail, dict(erp_results))
        log.event("bid", "BID\n" + bid_table(bid), bid=bid)
        return bid

    # Asking the mailbox (address, TAN) uses its own tab in the mail session, next to the research agent.
    ask_page = None

    async def ask_mailbox(args: dict) -> str:
        nonlocal ask_page
        if ask_page is None:
            ask_page = await mail_page.context.new_page()
        else:
            try:
                await ask_page.reload(timeout=20000)   # newly arrived mail (a TAN) shows after a refresh
            except Exception:
                pass
        known = mail_task.result().get("notes") if mail_task.done() else []
        goal = ASK_MAIL_GOAL.format(reference=args.get("reference") or reference, request=args.get("request")) + \
            ("\n\nWhat a colleague learned in this mailbox:" + "".join(f"\n- {n}" for n in (known or [])[-10:])
             if known else "")
        found = await WebAgent(ask_page, mail_site, label="mail", profile="mail").run(goal, deadline=end)
        await page.bring_to_front()
        answer = str(found.get("answer") or "").strip()
        if answer:
            return (f"From the mailbox: {answer} (received {found.get('received')}, subject {found.get('subject')!r}; "
                    f"{found.get('details') or ''}). Enter it now.")
        return f"The mailbox agent found nothing: {json.dumps(found, ensure_ascii=False)[:500]}"

    async def get_bid_values(args: dict) -> str:
        return "Enter exactly these values:\n" + bid_for_form(await bid_values())

    tools = {
        "ask_mailbox": ("Ask the mail sub-agent for something the portal sent to our webmail (signing TAN, confirmation "
                        "code) or for our mailbox address. Trigger any sending on the portal first.",
                        {"type": "object", "properties": {"reference": {"type": "string"},
                                                          "request": {"type": "string"}}, "required": ["request"]},
                        ask_mailbox),
        "get_bid_values": ("Get the bid values to enter (decision, positions, prices, discount, total, positions to "
                           "omit). Call it once, when the form asks for them; it waits for our calculation.",
                           {"type": "object", "properties": {}}, get_bid_values)}

    # Browser 1 moves on to the submission right after its research, while the ERP still works.
    tender_facts = await tender_task
    log.event("steps", f"tender facts: {len(tender_facts.get('positions') or [])} positions, "
                       f"{len(tender_facts.get('clarifications') or [])} clarifications")
    mail_facts = mail_task.result() if mail_task.done() else {}
    address = mail_facts.get("mailbox_address")
    contact = f"\n- Contact e-mail for the bidder registration: {address}." if address else \
        "\n- Contact e-mail for the bidder registration: our mailbox's own address; get it with ask_mailbox."
    submit = WebAgent(page, tender_site, label="tender-submit", profile="tender_submit", extra_tools=tools)
    result = await submit.run(SUBMIT_GOAL.format(contact=contact, brief=brief), deadline=end)
    try:  # the page after the binding submission: the portal's receipt
        result["final_page"] = (await page.inner_text("body", timeout=5000))[:3000]
    except Exception:
        pass
    log.event("bid", f"SUBMISSION: {json.dumps(result, ensure_ascii=False)[:1000]}", submission=result)
    for running in (spec_task, mail_task, erp_login, erp_task):
        if not running.done():
            running.cancel()
    return None  # a "site" submission: the agent entered and confirmed the bid itself


async def main() -> int:
    task, token = contract.load_run()
    sites = ", ".join(f"{site.get('siteId')} {site.get('url')}" for site in task["access"])
    print(f"Run {task.get('run_id') or '(local: the scouting logins, nothing counts)'}; websites: {sites}; "
          f"answer via {task['submission']['kind']}", flush=True)
    async with async_playwright() as playwright:
        browser, page = await browsers.connect(playwright)
        global PLAYWRIGHT
        PLAYWRIGHT = playwright  # lets solve() attach to the run's other browsers
        answer = await solve(task, page)
    telemetry.summary()
    if answer is None:
        print("No answer to submit here: the bid was entered on the tender portal.", flush=True)
        return 0
    if not token:
        print("Your answer (locally nothing is submitted):", json.dumps(answer, ensure_ascii=False), flush=True)
        return 0
    status, body = contract.submit_answer(task, token, answer)
    print(f"Answer: HTTP {status} {body[:2000]}", flush=True)
    return 0 if status == 202 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
