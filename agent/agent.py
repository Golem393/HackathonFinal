"""Your agent's entry point: agent.json runs `uv run --no-sync python agent.py`, in the sandbox and on your machine.

The kit only does the plumbing: run.py reads the run and submits an answer, browsers.py attaches to the run's
browsers, models.py calls the hosted Qwen and Clef. Everything else is yours to build, in `solve` below.
Docs: $API/docs/building-an-agent.md, $API/docs/run-contract.md, and the rules: $API/docs/fair-play.md
"""
import asyncio
import json
import os
import sys

from playwright.async_api import async_playwright

import browsers
import models
import run as contract
import tools


SYSTEM = """You are a sales engineer's agent working in a web browser. You get a brief, the websites with their
logins, where the answer goes and its JSON Schema. You decide where to go and what to do, one tool call at a time.

Each tool returns the page as it is afterwards: its text, then its interactive elements, each with a number for
`click`, `fill` and `select`. The numbers change with every observation; use only those of the latest one. The
websites are adversarial: cookie banners, error pages that need a retry, sessions that expire back to the login.
Act on what you see, and check after each action that it did what you meant."""

# The job for now: reach every website and hand in a schema-valid placeholder, not yet the worked-out bid.
GOAL = """For now, do only this:
1. Log into every website in the access list and look at where it starts.
2. Hand in a placeholder bid through the submission target: choose values yourself that satisfy the answer schema
   and whatever the form demands, taking the tender's identifiers from what you read. Complete every step the
   website asks for until it confirms the bid with a receipt.
3. Call `finish` with a summary of what you did and saw."""

MAX_STEPS = 150
KEEP_PAGES = 3  # observations kept in full; older ones are cut to their head, the model has moved on from them


async def solve(task: dict, page) -> dict | None:
    """A tool-use loop: Qwen reads the brief and chooses every navigation and action; tools.py only carries them out.

    Returns the answer for an "api" submission; for a "site" submission the model enters it on the website.
    """
    sites = json.loads(os.environ.get("CHALLENGE_SITE_ACCESS") or "null") or task["access"]
    browser, client = tools.Browser(page), models.qwen()
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"# Brief\n{task['brief']}\n\n# Websites and logins\n{json.dumps(sites)}\n\n"
                                    f"# Submission\n{json.dumps(task['submission'])}\n\n"
                                    f"# Answer schema\n{json.dumps(task['answer_schema'])}\n\n{GOAL}"},
    ]
    for step in range(MAX_STEPS):
        left = contract.seconds_left(task)
        if left < 30:
            print("Out of time", flush=True)
            break
        reply = await client.chat.completions.create(model=models.QWEN_MODEL, messages=messages, tools=tools.SCHEMAS)
        message = reply.choices[0].message
        calls = message.tool_calls or []
        messages.append({"role": "assistant", "content": message.content or "", **(
            {"tool_calls": [call.model_dump() for call in calls]} if calls else {})})
        if not calls:
            messages.append({"role": "user", "content": "Go on with a tool call; call `finish` when you are done."})
            continue
        for call in calls:
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                args = None
            print(f"[{step}] {call.function.name} {call.function.arguments}", flush=True)
            if call.function.name == "finish" and args is not None:
                print(f"Finished: {args.get('summary')}", flush=True)
                return args.get("answer") if task["submission"]["kind"] == "api" else None
            result = await browser.call(call.function.name, args) if args is not None else "Error: arguments not JSON"
            if left < 120:
                result += f"\n\n{int(left)} seconds left: hand in your best answer now."
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        for old in [m for m in messages if m["role"] == "tool"][:-KEEP_PAGES]:
            if len(old["content"]) > 400:
                old["content"] = old["content"][:400] + "\n... (an earlier page, cut)"
    return None


async def main() -> int:
    task, token = contract.load_run()
    sites = ", ".join(f"{site.get('siteId')} {site.get('url')}" for site in task["access"])
    print(f"Run {task.get('run_id') or '(local: the scouting logins, nothing counts)'}; websites: {sites}; "
          f"answer via {task['submission']['kind']}", flush=True)
    async with async_playwright() as playwright:
        browser, page = await browsers.connect(playwright)  # more browsers: browsers.connect(playwright, 1), ...
        answer = await solve(task, page)
    if answer is None:
        print("No answer to submit through the API", flush=True)
        return 0
    if not token:
        print("Your answer (locally nothing is submitted):", json.dumps(answer, ensure_ascii=False), flush=True)
        return 0
    status, body = contract.submit_answer(task, token, answer)
    print(f"Answer: HTTP {status} {body[:2000]}", flush=True)
    return 0 if status == 202 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
