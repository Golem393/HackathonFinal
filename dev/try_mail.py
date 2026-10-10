"""Dev-only: run just the mail research against the scouting websites, in a few minutes instead of a full run.

    cd <repo> && eval "$(atira scout --env)" && AGENT_LOG=all,-pages AGENT_LOG_DIR=dev/out/log \
        uv run --no-sync python dev/try_mail.py [topics...] [--seconds 300]

topics: fx tech approvals rules (default: all). Prints the merged mail facts; logs and HTML snapshots go to
AGENT_LOG_DIR as in a full run.
"""
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from playwright.async_api import async_playwright  # noqa: E402

import agent  # noqa: E402
import browsers  # noqa: E402
import mail  # noqa: E402
import run as contract  # noqa: E402
import telemetry  # noqa: E402


async def main() -> None:
    args = sys.argv[1:]
    seconds = 300.0
    if "--seconds" in args:
        i = args.index("--seconds")
        seconds = float(args[i + 1])
        args = args[:i] + args[i + 2:]
    topics = tuple(args) or ("fx", "tech", "approvals", "rules")
    task, _ = contract.load_run()
    facts = await agent.brief_facts(task)
    site = agent.site_for(task, "mail", "post")
    async with async_playwright() as playwright:
        _, page = await browsers.connect(playwright)
        research = mail.MailResearch(page, site, facts.get("reference") or "", facts.get("scenario_date") or "")
        started = time.time()
        result = await research.run(deadline=time.time() + seconds, topics=topics)
        agent.record("mail-research", result)
    shown = {k: v for k, v in result.items() if k != "notes"}
    print(json.dumps(shown, ensure_ascii=False, indent=2))
    print(f"\n{time.time() - started:.0f} s for topics {topics}", flush=True)
    telemetry.summary()


if __name__ == "__main__":
    asyncio.run(main())
