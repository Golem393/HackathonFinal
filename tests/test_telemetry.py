"""Telemetry flags and sinks, and the agent loop's events, with a scripted fake model on a local page (no network)."""
import asyncio
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QWEN_BASE_URL", "http://127.0.0.1:9/unused")
os.environ.setdefault("QWEN_API_KEY", "unused")

import telemetry  # noqa: E402
from web_agent import WebAgent  # noqa: E402


class Flags(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(telemetry.parse_flags("steps,usage"), {"steps", "usage"})
        self.assertEqual(telemetry.parse_flags("all,-pages"), set(telemetry.FEATURES) - {"pages"})
        self.assertEqual(telemetry.parse_flags("all,none,errors"), {"errors"})
        self.assertEqual(telemetry.parse_flags("bogus"), set())

    def test_cost(self):
        usage = NS(prompt_tokens=1_000_000, completion_tokens=1_000_000,
                   prompt_tokens_details=NS(cached_tokens=500_000))
        self.assertAlmostEqual(telemetry.cost_of("qwen3.8-flash-next", usage), 0.075 + 0.008 + 0.47)
        self.assertIsNone(telemetry.cost_of("unknown-model", usage))


def call(name, **args):
    return NS(id=f"c-{name}", function=NS(name=name, arguments=json.dumps(args)))


class FakeModel:
    """Plays back tool calls the way the OpenAI client returns them."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.chat = NS(completions=NS(create=self.create))

    async def create(self, **_):
        calls = self.turns.pop(0)
        message = NS(content="thinking aloud", reasoning="why", tool_calls=calls,
                     model_dump=lambda **_: {"role": "assistant", "content": "", "tool_calls": [
                         {"id": c.id, "type": "function",
                          "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in calls]})
        usage = NS(prompt_tokens=1000, completion_tokens=100, prompt_tokens_details=NS(cached_tokens=0))
        return NS(choices=[NS(message=message)], usage=usage)


PAGE = """<form onsubmit="document.body.innerHTML='<h1>Fertig</h1>';return false">
<input name=user aria-label=Benutzer><button>Weiter</button></form>"""


class AgentEvents(unittest.TestCase):
    def run_agent(self, flags):
        from playwright.async_api import async_playwright

        async def go():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page()
                site = {"siteId": "test", "url": "data:text/html," + PAGE,
                        "credentials": {"username": "secret-user", "password": "secret-pass"}}
                agent = WebAgent(page, site, label=f"test-{flags}")
                agent.client = FakeModel([
                    [call("type_credential", id="0.0", field="username")],
                    [call("click", id="0.99")],          # no such control: an error event
                    [call("click", id="0.1")],
                    [call("finish", result={"done": True})],
                ])
                result = await agent.run("Log in.")
                await browser.close()
                return result

        with tempfile.TemporaryDirectory() as folder:
            old = telemetry.FLAGS, telemetry.LOG_DIR
            telemetry.FLAGS, telemetry.LOG_DIR = telemetry.parse_flags(flags), folder
            try:
                out = io.StringIO()
                with redirect_stdout(out):
                    result = asyncio.run(go())
                path = os.path.join(folder, "events.jsonl")
                events = []
                if os.path.exists(path):
                    with open(path) as file:
                        events = [json.loads(line) for line in file]
            finally:
                telemetry.FLAGS, telemetry.LOG_DIR = old
        return result, events, out.getvalue()

    def test_all_features(self):
        result, events, console = self.run_agent("all")
        self.assertTrue(result["done"])
        features = {e["feature"] for e in events}
        self.assertTrue({"steps", "model", "pages", "usage", "timing", "errors", "summary"} <= features, features)
        summary = [e for e in events if e["feature"] == "summary"][0]
        self.assertEqual(summary["model_calls"], 4)
        self.assertEqual(summary["errors"], 1)
        self.assertNotIn("secret-user", json.dumps(events) + console)  # logins never reach a log

    def test_none_is_silent(self):
        result, events, console = self.run_agent("none")
        self.assertTrue(result["done"])
        self.assertEqual(events, [])
        self.assertEqual(console, "")

    def test_only_steps(self):
        _, events, _ = self.run_agent("steps")
        self.assertEqual({e["feature"] for e in events}, {"steps"})


if __name__ == "__main__":
    unittest.main()
