"""Popup auto-dismiss and the paging tool on local pages (no network, no model)."""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QWEN_BASE_URL", "http://127.0.0.1:9/unused")
os.environ.setdefault("QWEN_API_KEY", "unused")

import telemetry  # noqa: E402
from web_agent import WebAgent  # noqa: E402

SURVEY = """<button onclick="document.body.insertAdjacentHTML('beforeend','<p>angemeldet</p>')">Teilnahme</button>
<dialog open aria-label="Kurze Umfrage" style="position:fixed;inset:0;margin:0;width:100%;height:100%">
  <h2>Kurze Umfrage</h2><button onclick="this.closest('dialog').close()">Später</button></dialog>"""
GATE = """<button>Weiter</button>
<dialog open aria-label="Zugangsprüfung" style="position:fixed;inset:0;margin:0;width:100%;height:100%">
  <input type=range aria-label="Ziehen"><button>Schließen</button></dialog>"""
PAGED = """<div id=list></div><button id=next onclick="go()">Nächste Seite</button><script>
let n = 1; const show = () => document.getElementById('list').innerText = 'Antwort ' + (3*n-2) + ', ' + (3*n-1) + ', ' + 3*n;
function go() { if (n < 3) { n++; show(); } if (n === 3) document.getElementById('next').disabled = true; } show();
</script>"""


def run(html, action):
    from playwright.async_api import async_playwright

    async def go():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_content(html)
            agent = WebAgent(page, {"url": "about:blank", "credentials": {}}, label="helper-test")
            await agent.observe()
            try:
                return await action(agent)
            finally:
                await browser.close()

    old = telemetry.FLAGS
    telemetry.FLAGS = set()
    try:
        return asyncio.run(go())
    finally:
        telemetry.FLAGS = old


class Helpers(unittest.TestCase):
    def test_survey_popup_is_closed_and_the_click_goes_through(self):
        view = run(SURVEY, lambda a: a.act("click", {"id": "0.0"}))
        self.assertIn("POPUP CLOSED for you: Kurze Umfrage", view)
        self.assertIn("angemeldet", view)

    def test_a_gate_that_needs_input_is_left_to_the_model(self):
        async def click(agent):
            try:
                await agent.act("click", {"id": "0.0"})
                return "clicked"
            except Exception as error:
                return str(error)
        self.assertIn("nothing could be closed", run(GATE, click))

    def test_read_all_pages(self):
        text = run(PAGED, lambda a: a.act("read_all_pages", {"next_id": "0.0"}))
        self.assertIn("READ 3 PAGES", text)
        for n in (1, 5, 9):
            self.assertIn(f"{n}", text)
        self.assertIn("Antwort 7, 8, 9", text)


if __name__ == "__main__":
    unittest.main()
