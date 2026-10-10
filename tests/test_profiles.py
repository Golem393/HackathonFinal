"""Agent profiles: overrides, request options, and "auto" thinking only after a step went wrong."""
import asyncio
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QWEN_BASE_URL", "http://127.0.0.1:9/unused")
os.environ.setdefault("QWEN_API_KEY", "unused")

import profiles  # noqa: E402
import telemetry  # noqa: E402
from test_telemetry import FakeModel, call  # noqa: E402
from web_agent import WebAgent  # noqa: E402


class Profiles(unittest.TestCase):
    def test_override_from_environment(self):
        with mock.patch.dict(os.environ, {"AGENT_PROFILES": '{"mail": {"thinking": "on", "max_steps": 7, "bogus": 1}}'}):
            p = profiles.profile("mail")
        self.assertEqual((p.thinking, p.max_steps), ("on", 7))

    def test_unknown_name_gets_default_settings(self):
        p = profiles.profile("something-new")
        self.assertEqual((p.name, p.thinking), ("something-new", profiles.PROFILES["default"].thinking))

    def test_qwen_thinking_switch(self):
        options = profiles.profile("mail").request_options(False)
        self.assertEqual(options["extra_body"]["chat_template_kwargs"], {"enable_thinking": False})


class RecordingModel(FakeModel):
    def __init__(self, turns):
        super().__init__(turns)
        self.thinking = []

    async def create(self, **kwargs):
        self.thinking.append(kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"])
        return await super().create(**kwargs)


class AutoThinking(unittest.TestCase):
    def test_thinks_only_after_trouble(self):
        from playwright.async_api import async_playwright

        async def go():
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                page = await browser.new_page()
                site = {"siteId": "t", "url": "data:text/html,<input aria-label=A><button>B</button>", "credentials": {}}
                agent = WebAgent(page, site, label="auto-test", profile="tender_submit")
                agent.client = RecordingModel([
                    [call("type", id="0.0", text="x")],   # fine
                    [call("click", id="0.99")],           # fails: next step thinks
                    [call("type", id="0.0", text="y")],   # fine again: next step fast
                    [call("finish", result={})],
                ])
                await agent.run("test")
                await browser.close()
                return agent.client.thinking

        old = telemetry.FLAGS
        telemetry.FLAGS = set()
        try:
            self.assertEqual(asyncio.run(go()), [False, False, True, False])
        finally:
            telemetry.FLAGS = old


if __name__ == "__main__":
    unittest.main()
