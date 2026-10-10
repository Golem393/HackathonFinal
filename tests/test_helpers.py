"""Popup auto-dismiss and the paging tool on local pages (no network, no model)."""
import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QWEN_BASE_URL", "http://127.0.0.1:9/unused")
os.environ.setdefault("QWEN_API_KEY", "unused")

import telemetry  # noqa: E402
import documents  # noqa: E402
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


def run(html, action, flags=frozenset()):
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
    telemetry.FLAGS = set(flags)
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

    def test_html_document_is_extracted_as_text_with_tables(self):
        source = b"""<!doctype html><html><head><style>.x{display:none}</style></head><body>
        <h1>Rate notice</h1><table><tr><th>FX key</th><th>Currency</th><th>EUR per unit</th></tr>
        <tr><td>KEY-X</td><td>XYZ</td><td>1.2345</td></tr></table>
        <script>do_not_include()</script></body></html>"""
        text = documents.to_text("message.html", source, content_type="text/html")
        self.assertIn("Rate notice", text)
        self.assertIn("FX key\tCurrency\tEUR per unit", text)
        self.assertIn("KEY-X\tXYZ\t1.2345", text)
        self.assertNotIn("do_not_include", text)

    def test_read_html_reads_past_a_clipped_mail_pane_without_scrolling(self):
        html = """<h1>Message</h1><div style='height:12px;overflow:auto'>
        <p>Beginning of mail</p><p>Middle of mail</p><table><tr><td>Final field</td><td>42</td></tr></table>
        </div><script>not_mail_content()</script>"""
        text = run(html, lambda a: a.act("read_html", {}))
        self.assertIn("HTML CONTENT (complete DOM available by frame; no scrolling needed)", text)
        self.assertIn("Beginning of mail", text)
        self.assertIn("Final field\t42", text)
        self.assertNotIn("not_mail_content", text)

    def test_read_html_supports_frame_offsets_for_long_mail(self):
        html = "<iframe srcdoc=\"<p>" + ("x" * 22000) + "</p><p>End marker</p>\"></iframe>"

        async def read(agent):
            first = await agent.act("read_html", {})
            frame = 0
            for number, item in enumerate(agent.page.frames):
                if item.url == "about:srcdoc":
                    frame = number
                    break
            rest = await agent.act("read_html", {"frame": frame, "offset": 21000})
            return first, rest

        first, rest = run(html, read)
        self.assertIn("read_html frame=", first)
        self.assertIn("End marker", rest)
        self.assertIn("[complete frame]", rest)

    def test_mail_goals_require_full_html_extraction(self):
        import agent as orchestrator
        import mail as mail_module

        self.assertIn("`read_html`", mail_module.COMMON)
        self.assertIn("`read_html`", orchestrator.ASK_MAIL_GOAL)


if __name__ == "__main__":
    unittest.main()


class Snapshots(unittest.TestCase):
    def test_html_snapshots_are_written_once_and_masked(self):
        import json as _json
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            old = telemetry.FLAGS, telemetry.LOG_DIR
            telemetry.FLAGS, telemetry.LOG_DIR = {"html"}, folder
            telemetry.redact("geheim-123")
            try:
                async def act(agent):
                    await agent.snapshot(1, "click", "view one")
                    await agent.snapshot(2, "click", "view again")   # same HTML: kept once
                run('<p>Hallo geheim-123</p><iframe srcdoc="<b>innen</b>"></iframe>', act, flags={"html"})
            finally:
                telemetry.FLAGS, telemetry.LOG_DIR = old
            files = sorted(os.listdir(os.path.join(folder, "html", "helper_test")))
            self.assertEqual(files, ["001_click_about_blank.html", "001_click_about_blank.txt"])
            html = open(os.path.join(folder, "html", "helper_test", files[0])).read()
            self.assertNotIn("geheim-123", html)
            self.assertIn("innen", html)                                  # frame content kept
            index = [_json.loads(l) for l in open(os.path.join(folder, "html", "index.jsonl"))]
            self.assertEqual([e["duplicate"] for e in index], [False, True])


class LoginHandOver(unittest.TestCase):
    def test_a_login_form_goes_to_the_login_agent_and_work_continues(self):
        from unittest import mock

        import web_agent

        calls = []

        class LoginStub(web_agent.WebAgent):
            async def run(self, goal, *, deadline=None):
                calls.append((self.label, self.profile.name, "Log in" in goal))
                await self.page.set_content("<h1>Startseite</h1><a href='#'>Materialsuche</a>")
                return {"logged_in": True, "notes": ["passed the gate"]}

        async def act(agent):
            agent.site = {"url": "about:blank", "credentials": {"username": "u", "password": "p"}}
            with mock.patch.object(web_agent, "WebAgent", LoginStub):
                first = await agent.ensure_logged_in(None)
                second = await agent.ensure_logged_in(None)   # logged in now: nothing to do
            return first, second, await agent.observe()

        first, second, view = run("<form><input name=u><input type=password name=p><button>Anmelden</button></form>", act)
        self.assertEqual((first, second), (True, False))
        self.assertEqual(calls, [("helper-test-login", "site_login", True)])
        self.assertIn("Materialsuche", view)
        self.assertEqual(web_agent.LOGIN_NOTES["about:blank"], ["passed the gate"])   # remembered per site


class GateHandOver(unittest.TestCase):
    def test_an_access_check_goes_to_the_gate_agent(self):
        from unittest import mock

        import web_agent

        calls = []

        class GateStub(web_agent.WebAgent):
            async def run(self, goal, *, deadline=None):
                calls.append((self.label, self.profile.name))
                await self.page.set_content("<h1>Posteingang</h1><p>31 Nachrichten</p>")
                return {"passed": True, "notes": ["slider to 100, then Weiter"]}

        async def act(agent):
            agent.site = {"url": "https://mail.example", "credentials": {"username": "u", "password": "p"}}
            with mock.patch.object(web_agent, "WebAgent", GateStub):
                ran = await agent.ensure_logged_in(None)
                again = await agent.ensure_logged_in(None)
            return ran, again, await agent.observe()

        gate = """<section aria-label="Zugangsprüfung"><p>Zum Entsperren ganz nach rechts ziehen</p>
        <input type=range min=0 max=100 value=0><label><input type=checkbox> Ich bin kein Roboter</label>
        <button>Weiter</button></section>"""
        ran, again, view = run(gate, act)
        self.assertEqual((ran, again), (True, False))
        self.assertEqual(calls, [("helper-test-gate", "site_gate")])
        self.assertIn("31 Nachrichten", view)
        self.assertEqual(web_agent.GATE_NOTES["https://mail.example"], ["slider to 100, then Weiter"])

    def test_normal_pages_are_not_gates(self):
        async def act(agent):
            return await agent.needs_gate()
        self.assertFalse(run("<h1>Posteingang</h1><input type=checkbox> Alle auswählen <button>Suchen</button>", act))


class GateDetection(unittest.TestCase):
    def test_locked_vs_passed(self):
        async def act(agent):
            return await agent.needs_gate()
        locked = "<input type=range min=0 max=100 value=0><label><input type=checkbox> Ich bin kein Roboter</label>"
        passed = "<input type=range min=0 max=100 value=100><label><input type=checkbox checked> Ich bin kein Roboter</label><p>Entsperrt</p>"
        box_only = "<label><input type=checkbox> I am not a robot</label><button>Continue</button>"
        self.assertTrue(run(locked, act))
        self.assertFalse(run(passed, act))      # a passed gate that stays on the page is not a gate
        self.assertTrue(run(box_only, act))


class Scrolling(unittest.TestCase):
    def test_lazy_list_loads_when_scrolled(self):
        lazy = """<div id=box aria-label="Nachrichtenliste" style="height:120px;overflow-y:auto">
        <div id=rows></div></div><script>
        let n = 0; const add = k => { for (let i = 0; i < k; i++) { n++; const d = document.createElement('div');
          d.style.height = '30px'; d.textContent = 'Mail ' + n; rows.appendChild(d); } };
        add(8); box.addEventListener('scroll', () => { if (n < 30 && box.scrollTop + box.clientHeight >= box.scrollHeight - 5) add(8); });
        </script>"""

        async def act(agent):
            view = await agent.observe()
            area = next(line for line in view.splitlines() if '"scroll area"' in line)
            area_id = area.split('"id": "')[1].split('"')[0]
            return view, await agent.act("scroll", {"id": area_id, "to_end": True})

        before, after = run(lazy, act)
        self.assertNotIn("Mail 30", before)
        self.assertIn("Mail 30", after)   # every lazily loaded row is now in the page text
