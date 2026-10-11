"""The entry point (agent.json runs it): the team of agents on the run's clock.

    plan the task from the brief (model)
    investigate every website at once, one agent and one browser each (models navigate and record)
    decide which facts apply (model), then compute the bid (calc.py, exact decimals)
    enter and sign the bid on the submission website (model operates the form, a second agent reads the TAN)

The whole run is bounded by its 20 minutes: investigation stops at INVESTIGATE_UNTIL, the solver has SOLVE_SECONDS,
and the submission starts no later than SUBMIT_RESERVE before the end, whatever is still missing. A partial bid scores; a late one does not.
"""
import asyncio
import json
import sys
import time
from urllib.parse import urlparse

from playwright.async_api import async_playwright

import browsers
import calc
import run as contract
import submit
import team
import web

RUN_SECONDS = 20 * 60
INVESTIGATE_UNTIL = 10 * 60 + 30  # seconds from the start
SOLVE_SECONDS = 150
# entering and signing the bid starts no later than this before the end: a full form (every position through its
# configurator) and the TAN took five minutes in run #8
SUBMIT_RESERVE = 7 * 60 + 30
FOLLOW_UP_SECONDS = 75


def log(text: str):
    print(text, flush=True)


async def open_sites(playwright, task: dict) -> list[web.Site]:
    """One browser per website: the run's browsers (up to 4), or locally a Chromium each."""
    available = len(browsers.cdp_urls()) or len(task["access"])
    sites, browser = [], None
    for number, access in enumerate(task["access"]):
        if number < available:
            browser, page = await browsers.connect(playwright, number)
            context = page.context
        else:  # more websites than browsers: a context of its own in the last one
            context = await browser.new_context()
            page = await context.new_page()
        sites.append(web.Site(access, context, page, log))
    return sites


async def work(task: dict, sites: list[web.Site]) -> dict | None:
    start = time.time()
    end = min(start + RUN_SECONDS, task["expires_at"] / 1000) if task.get("expires_at") else start + RUN_SECONDS
    submit_by = end - SUBMIT_RESERVE
    until = min(start + INVESTIGATE_UNTIL, submit_by - SOLVE_SECONDS)
    schedule = (f"[team] schedule: end +{clock(end - start)}, investigate until +{clock(until - start)}, "
                f"submit by +{clock(submit_by - start)}")
    log(schedule)

    the_plan = await team.plan(task, start + 120)
    log(f"[team] plan: {json.dumps(the_plan, ensure_ascii=False)}")

    ledger = team.Ledger()
    await team.investigate_all(sites, task, the_plan, ledger, until)
    # the platform keeps only the end of the log: the start is repeated here, compactly
    log(schedule)
    log(f"[team] mail topics: {[topic.get('topic') for topic in the_plan.get('mail_topics') or []]}")
    log(f"[team] {len(ledger.entries)} records after investigating:")
    for entry in ledger.entries:
        log(f"  {entry['at']} #{entry['n']} [{entry['agent']}] {entry['topic']}: "
            f"{web.short(json.dumps(entry['facts'], ensure_ascii=False), 140)}")

    by_id = {site.id: site for site in sites}
    target = submission_site(task, the_plan, sites)
    keeper = asyncio.create_task(keep_sessions([site for site in sites if site.context is not target.context]))
    try:
        # from here on nothing may stop the signature: a signed bid with gaps scores, an unsigned one does not
        inputs = await safely("solve", team.solve(task, the_plan, ledger, min(time.time() + SOLVE_SECONDS, submit_by),
                                                  submit_by)) or ledger.latest_inputs
        inputs = await safely("follow-up", follow_up_round(task, the_plan, ledger, inputs, by_id, submit_by),
                              inputs) or inputs
        if inputs:
            for problem in guarded(lambda: team.mismatches(inputs), []):
                log(f"[check] {problem}")
        log(f"[team] calculation inputs: {json.dumps(inputs, ensure_ascii=False)}")

        answer, omitted = None, []
        for candidate in (inputs, ledger.latest_inputs, None):
            try:
                answer, omitted = compute(candidate, the_plan)
                break
            except Exception as error:
                log(f"[team] the calculation failed ({error!r}); trying with less")
        log(f"[team] answer: {json.dumps(answer, ensure_ascii=False)}")
        if task["submission"].get("kind") == "api":
            return answer  # main() sends it

        mail = guarded(lambda: tan_site(the_plan, by_id), None)
        values = guarded(lambda: configurator_values(inputs), {})
        result = await safely("submission", submit.submit(target, mail, task, answer, omitted, end - 20, values))
        log(f"[team] submission: {result}")
        return None  # a "site" submission is entered on the website, not returned
    finally:
        keeper.cancel()


async def follow_up_round(task: dict, the_plan: dict, ledger: team.Ledger, inputs: dict | None, by_id: dict,
                          submit_by: float) -> dict | None:
    """One targeted look for the facts the solver found missing, then a second solve. A no_bid stands only when the
    second solve, after a fresh look at the candidate list, agrees, or when the materials were checked and there is
    no time to look again."""
    questions = follow_up_questions(inputs, the_plan, by_id)
    no_bid_first, confirmed = bool(inputs and inputs.get("decision") == "no_bid"), False
    if questions and time.time() + 75 + 30 < submit_by:
        seconds = max(75.0, min(210.0, submit_by - time.time() - 100))
        log(f"[team] following up for {seconds:.0f} s on {questions}")
        until = time.time() + seconds
        mail_topics = [topic for topic, _ in team.gap_topics(inputs, the_plan, task["brief"])]
        try:  # a follow-up stuck on a page must never hold up the submission
            await asyncio.wait_for(asyncio.gather(*(
                team.follow_up(by_id[site_id], task, the_plan, ledger, asked, until,
                               topics=mail_topics if kind_of(the_plan, site_id) == "mail" and mail_topics else None)
                for site_id, asked in questions.items()), return_exceptions=True), seconds + 30)
        except asyncio.TimeoutError:
            log("[team] the follow-up round did not end in time; going on with what is recorded")
        second = await safely("solve", team.solve(task, the_plan, ledger, min(time.time() + SOLVE_SECONDS, submit_by),
                                                  submit_by))
        confirmed = bool(no_bid_first and second and second.get("decision") == "no_bid")
        inputs = second or inputs
    elif no_bid_first:
        confirmed = materials_checked(inputs, ledger, the_plan)
    if inputs and inputs.get("decision") == "no_bid" and not confirmed:
        # a no_bid that a second look at the materials did not confirm is not trusted (a wrong no_bid loses nearly
        # everything): the known positions are bid, a missing material left empty
        log(f"[team] no_bid not confirmed by a second look at the materials: bidding instead "
            f"({inputs.get('decision_reason')})")
        inputs["decision"] = "bid"
    return inputs


def materials_checked(inputs: dict, ledger: team.Ledger, the_plan: dict) -> bool:
    """Every position left without a material has its catalogue group in a record of the materials website."""
    materials = {s["site_id"] for s in the_plan.get("sites", []) if s.get("kind") == "erp"}
    records = " ".join(json.dumps(entry, ensure_ascii=False) for entry in ledger.entries if entry["site"] in materials)
    groups = [(position.get("requirement") or {}).get("catalogue_group") for position in inputs.get("positions") or []
              if not position.get("material_number")]
    return bool(groups) and all(group and group in records for group in groups)


async def safely(what: str, job, fallback=None):
    """The job's result, or the fallback when it fails: one error must not cost the whole bid."""
    try:
        return await job
    except Exception as error:
        log(f"[team] {what} failed: {error!r}")
        return fallback


def guarded(function, fallback):
    try:
        return function()
    except Exception as error:
        log(f"[team] {getattr(function, '__name__', 'a step')} failed: {error!r}")
        return fallback


def clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def kind_of(the_plan: dict, site_id: str) -> str:
    return next((s.get("kind", "") for s in the_plan.get("sites", []) if s.get("site_id") == site_id), "")


def follow_up_questions(inputs: dict | None, the_plan: dict, by_id: dict) -> dict[str, list[str]]:
    """Per website, the facts the solver found missing; for a no_bid also every candidate of the groups without an
    active match, so that a no_bid is decided only on a complete candidate list (run #7 found the active
    alternative to a blocked first hit only minutes before the end)."""
    questions: dict[str, list[str]] = {}
    for gap in (inputs or {}).get("missing") or []:
        if gap.get("site_id") in by_id:
            seen = f" (seen and rejected: {gap['seen']})" if gap.get("seen") else ""
            questions.setdefault(gap["site_id"], []).append(f"{gap.get('fact', '')}{seen}")
    if inputs and inputs.get("decision") == "no_bid":
        materials = next((s["site_id"] for s in the_plan.get("sites", []) if s.get("kind") == "erp"
                          and s.get("site_id") in by_id), None)
        for position in inputs.get("positions") or []:
            group = (position.get("requirement") or {}).get("catalogue_group")
            if materials and group and not position.get("material_number"):
                questions.setdefault(materials, []).append(
                    f"every material of catalogue group {group} (all result pages) with its visible status and all "
                    f"attributes, for position {position.get('position')}; open each one not yet recorded")
    return questions


def submission_site(task: dict, the_plan: dict, sites: list[web.Site]) -> web.Site:
    """Where the bid is entered: the site the submission names, else the one whose address it uses, else the
    tender website."""
    by_id = {site.id: site for site in sites}
    submission = task["submission"]
    if submission.get("siteId") in by_id:
        return by_id[submission["siteId"]]
    host = urlparse(submission.get("url") or "").hostname
    return next((site for site in sites if host and urlparse(site.url).hostname == host), None) or next(
        (by_id[s["site_id"]] for s in the_plan.get("sites", []) if s.get("kind") == "tender" and s["site_id"] in by_id),
        sites[0])


def tan_site(the_plan: dict, by_id: dict) -> web.Site | None:
    """Where the signing TAN arrives: the website the brief names for it, else the mailbox."""
    named = the_plan.get("tan_site_id")
    if named in by_id:
        return by_id[named]
    return next((by_id[s["site_id"]] for s in the_plan.get("sites", []) if s.get("kind") == "mail"
                 and s["site_id"] in by_id), None)


async def keep_sessions(sites: list[web.Site], every: float = 20.0):
    """Between investigating and signing nothing touches the websites, and short sessions expire: a request now and
    then keeps each logged in (one per browser, the cookies are shared)."""
    contexts = {}
    for site in sites:
        contexts.setdefault(id(site.context), site)
    while True:
        await asyncio.sleep(every)
        await asyncio.gather(*(site.keep_alive() for site in contexts.values()), return_exceptions=True)


def compute(inputs: dict | None, the_plan: dict) -> tuple[dict, list[str]]:
    """The answer from the solver's inputs, and the positions left out for lack of facts. Without inputs, an empty
    bid on the planned tender: signed, it still scores its reference and decision."""
    if not inputs:
        return {"tender_reference": the_plan.get("tender_reference", ""), "decision": "bid", "currency": "EUR",
                "discount_percent": 0.0, "positions": [], "total_net": 0.0}, []
    answer, steps = calc.compute(inputs)
    for step in steps:
        log(f"[calc] {step}")
    entered = {p["position"] for p in answer["positions"]}
    omitted = [str(p["position"]) for p in inputs.get("positions") or [] if str(p["position"]) not in entered]
    return answer, omitted if answer["decision"] == "bid" else []


def configurator_values(inputs: dict | None) -> dict[str, dict]:
    """Per position, the attribute values a bid form's material configurator asks for before it offers materials:
    the chosen material's own values where known, else the requirement's (after amendments and stroke derivation)."""
    values = {}
    for position in (inputs or {}).get("positions") or []:
        material, requirement = position.get("material_attributes") or {}, position.get("requirement") or {}
        values[str(position.get("position"))] = {
            key: material.get(key) or requirement.get(key)
            for key in ("bore", "stroke", "pressure", "mounting", "certification")
            if material.get(key) or requirement.get(key)}
    return values


async def main() -> int:
    task, token = contract.load_run()
    sites = ", ".join(f"{site.get('siteId')} {site.get('url')}" for site in task["access"])
    log(f"Run {task.get('run_id') or '(local: the scouting logins, nothing counts)'}; websites: {sites}; "
        f"answer via {task['submission']['kind']}")
    async with async_playwright() as playwright:
        answer = await work(task, await open_sites(playwright, task))
    if answer is None:
        log("No answer to submit through the API")
        return 0
    if not token:
        log(f"Your answer (locally nothing is submitted): {json.dumps(answer, ensure_ascii=False)}")
        return 0
    status, body = contract.submit_answer(task, token, answer)
    log(f"Answer: HTTP {status} {body[:2000]}")
    return 0 if status == 202 else 1


class Clock:
    """Every line of the run's log starts with the minutes and seconds since the agent started: where the time goes."""

    def __init__(self, stream, start: float):
        self.stream, self.start, self.fresh = stream, start, True

    def write(self, text: str) -> int:
        for part in text.splitlines(keepends=True):
            if self.fresh and part.strip():
                elapsed = int(time.time() - self.start)
                self.stream.write(f"{elapsed // 60:02d}:{elapsed % 60:02d} ")
            self.stream.write(part)
            self.fresh = part.endswith("\n")
        return len(text)

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


if __name__ == "__main__":
    sys.stdout = Clock(sys.stdout, time.time())
    sys.exit(asyncio.run(main()))
