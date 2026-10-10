"""The orchestrator's wiring with fake sub-agents (made-up facts, local headless browsers, no network, no model)."""
import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QWEN_BASE_URL", "http://127.0.0.1:9/unused")
os.environ.setdefault("QWEN_API_KEY", "unused")
os.environ["HEADLESS"] = "1"

import agent  # noqa: E402
import erp_agent  # noqa: E402
import mail  # noqa: E402
import telemetry  # noqa: E402

FACTS = {
    "tender-research": {"reference": "T-9", "positions": [
        {"position": "1", "quantity": 3, "unit": "Stück", "requirement": "R1"},
        {"position": "2", "quantity": 2, "unit": "Stück", "requirement": "R2"}], "clarifications": []},
    "spec": {"current_revision": "B", "requirements": [{"id": "R1", "catalogue_group": "G1", "bore_mm": 40}]},
    "spec-followup": {"requirements": [{"id": "R2", "catalogue_group": "G2", "bore_mm": 50}]},
    "mail-approvals": {"mailbox_address": "verkauf@firma.example", "bidder_domain": "firma.example", "approvals": [
        {"sender": "leitung@firma.example", "date": "01.01.2030", "reference": "T-9", "percent": 10}]},
    "erp-login": {"ready": True, "notes": ["menu has a search"]},
    "tender-qa": {"clarifications": [{"number": "7", "date": "01.01.2030", "position": "1", "new_quantity": 5}]},
}
CONDITION = [{"valid_from": "01.01.2030", "valid_to": "31.12.2030", "currency": "EUR",
              "scales": [{"from_quantity": 1, "price": "100,00"}]}]


class FakeAgent:
    seen: list = []

    def __init__(self, page, site, *, label="", profile="", extra_tools=None, **_):
        self.label, self.tools, self.notes = label, extra_tools or {}, []

    values = ""

    async def run(self, goal, *, deadline=None):
        FakeAgent.seen.append((self.label, goal))
        await asyncio.sleep(0.05)
        if self.label == "erp-scout":
            return {"search": "search by description", "tips": ["status 03 = blocked"]}
        if self.label.startswith("erp-find "):
            return {"material_number": "M-" + self.label.split()[1], "match_evidence": "all equal"}
        if self.label.startswith("erp-detail "):
            return {"price_conditions": CONDITION, "stock_available_pieces": 100, "lead_time_from_stock_weeks": 2,
                    "lead_time_production_weeks": 9}
        if self.label == "tender-submit":
            FakeAgent.values = await self.tools["get_bid_values"][2]({})
            return {"submitted": True}
        return FACTS.get(self.label, {})


class Orchestrator(unittest.TestCase):
    def test_phases_and_values(self):
        from playwright.async_api import async_playwright

        async def go():
            async with async_playwright() as playwright:
                agent.PLAYWRIGHT = playwright
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page()
                task = {"brief": "Scenario 2030-06-01T09:00:00Z", "access": [
                    {"siteId": s, "url": f"https://{s}.example", "credentials": {}}
                    for s in ("tender-portal", "customer-portal", "erp", "mail")]}
                facts = {"reference": "T-9", "scenario_date": "2030-06-01", "buyer": "Stadt"}
                with mock.patch.object(agent, "WebAgent", FakeAgent), mock.patch.object(erp_agent, "WebAgent", FakeAgent), \
                        mock.patch.object(mail, "WebAgent", FakeAgent), \
                        mock.patch.object(agent, "brief_facts", mock.AsyncMock(return_value=facts)), \
                        mock.patch.dict(os.environ, {"RUN_SECONDS": "400"}):
                    await agent.solve(task, page)
                await browser.close()

        old = telemetry.FLAGS
        telemetry.FLAGS = set()
        FakeAgent.seen = []
        try:
            asyncio.run(go())
        finally:
            telemetry.FLAGS = old
        labels = [label for label, _ in FakeAgent.seen]
        self.assertTrue({"tender-research", "tender-qa", "spec", "mail-login", "erp-login"} <= set(labels[:8]))
        self.assertTrue({"mail-fx", "mail-tech", "mail-approvals", "mail-rules"} <= set(labels))   # mail topics
        self.assertIn("erp-scout", labels)
        self.assertIn("R2", dict(FakeAgent.seen)["spec-followup"])      # missing requirement searched again
        self.assertEqual({l for l in labels if l.startswith("erp-find")}, {"erp-find G1", "erp-find G2"})
        self.assertEqual({l for l in labels if l.startswith("erp-detail")}, {"erp-detail M-G1", "erp-detail M-G2"})
        erp_goal = dict(FakeAgent.seen)["erp-find G1"]
        self.assertIn('"catalogue_group": "G1"', erp_goal)       # requirement handed to the finder
        self.assertIn("status 03 = blocked", erp_goal)          # the scout's site map
        self.assertIn("menu has a search", erp_goal)            # what the ERP login learned
        submit_goal = dict(FakeAgent.seen)["tender-submit"]
        self.assertIn("verkauf@firma.example", submit_goal)     # contact e-mail from the mail research
        self.assertIn("Position 1: material M-G1, quantity 5 pieces", FakeAgent.values)   # Q&A change -> bid
        self.assertIn("Position 2: material M-G2, quantity 2 pieces", FakeAgent.values)


    def test_values_text(self):
        bid = {"decision": "bid", "discount_percent": 10.0, "total_net": 1234.5, "omitted": ["3"],
               "positions": [{"position": "1", "material_number": "M1", "quantity": 3, "unit_price": 90.0,
                              "lead_time_weeks": 2, "base_unit_price": 100.0}]}
        text = agent.bid_for_form(bid)
        self.assertIn("Discount: 10,00 %", text)
        self.assertIn("Net total: 1.234,50 EUR", text)
        self.assertIn("unit price 90,00 EUR", text)
        self.assertIn("Omit these positions: 3", text)


if __name__ == "__main__":
    unittest.main()


class ErpSharing(unittest.TestCase):
    def test_positions_with_one_requirement_share_finder_and_details(self):
        from playwright.async_api import async_playwright

        async def go():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                context = await browser.new_context()
                jobs = [{"position": p, "catalogue_group": "G9", "bore_mm": 63} for p in ("01.02", "01.03")]
                with mock.patch.object(erp_agent, "WebAgent", FakeAgent):
                    results = await erp_agent.run_erp(context, {"url": "https://erp.example"}, jobs, "2030-06-01",
                                                      site_map={"search": "x"})
                await browser.close()
                return results

        old = telemetry.FLAGS
        telemetry.FLAGS = set()
        FakeAgent.seen = []
        try:
            results = asyncio.run(go())
        finally:
            telemetry.FLAGS = old
        labels = [label for label, _ in FakeAgent.seen]
        self.assertEqual(labels, ["erp-find G9", "erp-detail M-G9"])
        self.assertEqual({p: r["material_number"] for p, r in results.items()}, {"01.02": "M-G9", "01.03": "M-G9"})
        self.assertEqual(results["01.03"]["stock_available_pieces"], 100)
