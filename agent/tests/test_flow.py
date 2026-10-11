"""The run's flow after the investigation with stubs for the websites and models: whatever fails between the
investigation and the signature, the bid still goes to the submitter."""
import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent  # noqa: E402

PLAN = {"tender_reference": "AB-1", "scenario_date": "2030-03-10", "sites": [
    {"site_id": "portal", "kind": "tender", "holds": "the tender"}, {"site_id": "post", "kind": "mail", "holds": ""}],
    "mail_topics": []}


class Flow(unittest.TestCase):
    def run_work(self, solve):
        submitted = []

        async def plan(task, deadline):
            return PLAN

        async def investigate_all(*args):
            return None

        async def submit(target, mail, task, answer, omitted, deadline, values):
            submitted.append(answer)
            return {"status": "submitted"}

        sites = [SimpleNamespace(id="portal", context=object(), url="https://portal.example/"),
                 SimpleNamespace(id="post", context=object(), url="https://post.example/")]
        task = {"brief": "", "access": [], "submission": {"kind": "site", "siteId": "portal"}}
        with patch.object(agent.team, "plan", plan), patch.object(agent.team, "investigate_all", investigate_all), \
                patch.object(agent.team, "solve", solve), patch.object(agent.submit, "submit", submit), \
                patch.object(agent, "keep_sessions", lambda sites: asyncio.sleep(0)):
            asyncio.run(agent.work(task, sites))
        return submitted

    def test_a_failing_solver_still_leads_to_a_signed_bid(self):
        async def solve(*args, **kwargs):
            raise RuntimeError("the model proxy refused")

        submitted = self.run_work(solve)
        self.assertEqual(len(submitted), 1)
        self.assertEqual(submitted[0]["tender_reference"], "AB-1")

    def test_inputs_the_calculation_cannot_use_still_lead_to_a_signed_bid(self):
        async def solve(*args, **kwargs):
            return {"tender_reference": "AB-1", "decision": "bid", "positions": [{"position": "1.1"}]}  # broken

        submitted = self.run_work(solve)
        self.assertEqual(len(submitted), 1)


class Prefill(unittest.TestCase):
    def test_prefill_runs_an_agent_on_a_new_tab(self):
        """The prefill's own code path (a new tab, the entry, an agent with the prefill prompt), with stubs."""
        seen = {}

        class Tab:
            id, url = "portal", "https://portal.example/"

        class Site(Tab):
            async def spawn(self):
                return Tab()

        async def enter(tab):
            return "the tender portal"

        class StubAgent:
            def __init__(self, name, system, tools, deadline, **kwargs):
                seen["name"], seen["tools"] = name, [schema["function"]["name"] for schema, _ in tools]

            async def run(self, task, max_steps=0):
                seen["task"] = task
                return {"summary": "bidder data done"}

        with patch.object(agent.team, "enter", enter), patch.object(agent, "Agent", StubAgent), \
                patch.object(agent.web, "toolbox", lambda tab: []):
            result = asyncio.run(agent.prefill(Site(), {"brief": "Brief"}, agent.team.Ledger(), 0))
        self.assertEqual(result, {"summary": "bidder data done"})
        self.assertEqual(seen["name"], "prefill")
        self.assertIn("read_notes", seen["tools"])
        self.assertNotIn("record", seen["tools"])
        self.assertIn("STOP", seen["task"])


if __name__ == "__main__":
    unittest.main()
