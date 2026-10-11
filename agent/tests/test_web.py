"""The page view against a made-up page that copies the kinds of traps the websites set: collapsed sections, a hidden
decoy value next to the visible one, invisible characters inside identifiers, a frame inside a frame, and a form field
inside a collapsed section. Offline: the page is inline HTML in a headless Chromium."""
import asyncio
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import web  # noqa: E402

PAGE = """<!doctype html><html><body><main>
<h1>Record</h1>
<p>Code: AB&#8203;C-1&#8203;23</p>
<dl><dt>Status</dt><dd><output>01</output><span aria-hidden="true" hidden style="display:none!important">77</span>
<button type="button" aria-describedby="legend">?</button><span id="legend" role="tooltip" hidden>01 active, 02 paused</span>
<abbr title="Price unit: per hundred pieces">PU</abbr></dd></dl>
<details><summary>Original text</summary><p>The real content 4711</p></details>
<details><summary>Breakdown</summary><label>Base <input name="base"></label></details>
<iframe srcdoc="<p>outer frame</p><iframe srcdoc='<p>inner content 815</p>'></iframe>"></iframe>
</main></body></html>"""


class View(unittest.TestCase):
    def test_the_view_shows_what_a_person_sees_after_opening_every_section(self):
        asyncio.run(self.check())

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content(PAGE)
                await page.wait_for_timeout(300)
                site = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                view = await site.view()
                self.assertIn("ABC-123", view)  # invisible characters removed
                self.assertIn("The real content 4711", view)  # the collapsed section was opened
                self.assertIn("01", view)
                self.assertNotIn("77", view)  # the hidden decoy is not shown
                self.assertIn("inner content 815", view)  # a frame inside a frame
                self.assertIn('about="01 active, 02 paused"', view)  # a tooltip's text, hidden until hovered
                self.assertIn("PU (Price unit: per hundred pieces)", view)  # a title

                # a field inside a section that is collapsed again can still be filled
                await page.evaluate("document.querySelectorAll('details').forEach((d) => { d.open = false; })")
                ref = int(re.search(r'\[(\d+) input "Base', view).group(1))
                report = await site.fill([{"ref": ref, "value": "12,34"}])
                self.assertTrue(report.startswith("Filled."), report[:200])
                self.assertEqual(await page.locator("input[name=base]").input_value(), "12,34")
            finally:
                await browser.close()


CONFIGURATOR = """<!doctype html><html><body><main><form onsubmit="return false">
<label>Size (mm) <select name="size"><option value="">Choose</option><option>8</option><option>20</option>
  <option>200</option></select></label>
<label>Length (mm) <select name="length" disabled><option value="">Choose</option></select></label>
<label>Article <select name="article" disabled><option value="">Choose</option></select></label>
<button type="button" id="apply">Apply choice</button>
</form>
<script>
  document.getElementById('apply').addEventListener('click', () => {
    const size = document.querySelector('[name=size]'), length = document.querySelector('[name=length]');
    const article = document.querySelector('[name=article]');
    setTimeout(() => {  // the next field opens a moment later, as after a reload
      if (size.value && length.disabled) {
        length.innerHTML = '<option value="">Choose</option><option>300</option><option>500</option>';
        length.disabled = false;
      } else if (length.value && article.disabled) {
        article.innerHTML = '<option value="">Choose</option><option value="X-1">X-1 · blocked</option>' +
          '<option value="X-2">X-2 · heavy</option>';
        article.disabled = false;
      }
    }, 300);
  });
</script></main></body></html>"""


class Configurator(unittest.TestCase):
    def test_choose_option(self):
        options = [{"text": "Choose", "value": ""}, {"text": "300", "value": "300"}, {"text": "500", "value": "500"},
                   {"text": "X-2 · heavy", "value": "X-2"}, {"text": "None at all", "value": "none"}]
        self.assertEqual(web.choose_option(options, "500")["value"], "500")
        self.assertEqual(web.choose_option(options, "482")["value"], "500")  # the next larger size
        self.assertEqual(web.choose_option(options, "X-2")["value"], "X-2")  # the start of the text
        self.assertEqual(web.choose_option(options, "none")["value"], "none")  # the option's value
        self.assertIsNone(web.choose_option(options, "999"))
        self.assertIsNone(web.choose_option(options, "Y-7"))
        # "none" in the table's words picks the one option that says none in the form's words
        sizes = [{"text": "Choose", "value": ""}, {"text": "1.200 mm", "value": "a"}, {"text": "1.250 mm", "value": "b"}]
        self.assertEqual(web.choose_option(sizes, "1250")["value"], "b")  # thousands groups read as such
        self.assertEqual(web.choose_option(sizes, "1250 mm")["value"], "b")
        self.assertEqual(web.choose_option([{"text": "200 mm", "value": "x"}, {"text": "1250 mm", "value": "y"}],
                                           "1.250 mm")["value"], "y")
        self.assertIsNone(web.choose_option([{"text": "5000 mm", "value": "x"}], "40"))  # not a next size
        coats = [{"text": "Choose", "value": ""}, {"text": "Zinc", "value": "z"},
                 {"text": "Ohne Beschichtung", "value": "o"}]
        self.assertEqual(web.choose_option(coats, "Keine")["value"], "o")
        self.assertEqual(web.choose_option(coats, "none")["value"], "o")
        coats.append({"text": "No primer, no paint", "value": "n"})
        self.assertIsNone(web.choose_option(coats, "Keine"))  # two options say none: no guess

    def test_a_chain_of_choices_each_applied_before_the_next(self):
        asyncio.run(self.check())

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content(CONFIGURATOR)
                site = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                await site.view()
                report = await site.configure([{"field": "Size (mm)", "value": "200"},
                                               {"field": "Length (mm)", "value": "482"},
                                               {"field": "Article", "value": "X-2"}], apply="Apply choice")
                self.assertTrue(report.startswith("Chosen:"), report[:300])
                values = [await page.locator(f"[name={name}]").input_value() for name in ("size", "length", "article")]
                self.assertEqual(values, ["200", "500", "X-2"])
                # a field the form does not have is skipped and the chain goes on
                await page.set_content(CONFIGURATOR)
                report = await site.configure([{"field": "Size (mm)", "value": "200"},
                                               {"field": "Pressure", "value": "250"},
                                               {"field": "Length (mm)", "value": "300"}], apply="Apply choice")
                self.assertIn("no field 'Pressure': skipped", report)
                report = await site.configure([{"field": "Colour", "value": "red"}], apply="Apply choice")
                self.assertTrue(report.startswith("Nothing was chosen"), report[:200])
                self.assertEqual(await page.locator("[name=length]").input_value(), "300")
                # a value that is not offered stops the chain and says what is offered
                await page.set_content(CONFIGURATOR)
                report = await site.configure([{"field": "Size (mm)", "value": "7000"}], apply="Apply choice")
                self.assertIn("offers no '7000'", report)
            finally:
                await browser.close()


class Typing(unittest.TestCase):
    def test_typing_into_a_button_presses_nothing(self):
        asyncio.run(self.check())

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content('<main><label>Name <input name="name"></label>'
                                       '<button type="button" onclick="window.pressed = true">Leave this out</button>'
                                       '</main>')
                site = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                view = await site.view()
                button = int(re.search(r'\[(\d+) button "Leave this out"', view).group(1))
                answer = await site.type(button, "")
                self.assertIn("is not a text field", answer)
                self.assertIsNone(await page.evaluate("window.pressed"))  # the button was not pressed
                field = int(re.search(r'\[(\d+) input "Name', view).group(1))
                await site.type(field, "typed")
                self.assertEqual(await page.locator("input[name=name]").input_value(), "typed")
                # a password field means a login form: the agent is told its session expired, nothing is typed
                await page.set_content('<main><label>Secret <input type="password" name="secret"></label></main>')
                view = await site.view()
                secret = int(re.search(r'\[(\d+) password-input', view).group(1))
                answer = await site.type(secret, "a search term")
                self.assertIn("session has probably expired", answer)
                self.assertEqual(await page.locator("input[name=secret]").input_value(), "")
                answer = await site.fill([{"ref": secret, "value": "a search term"}])  # fill() refuses it too
                self.assertIn("session has probably expired", answer)
                self.assertEqual(await page.locator("input[name=secret]").input_value(), "")
                site.secrets.add("7F3A")  # a TAN the team just read may go in
                await site.fill([{"ref": secret, "value": "7F3A"}])
                self.assertEqual(await page.locator("input[name=secret]").input_value(), "7F3A")
                # a select whose options carry descriptions and opaque values
                await page.set_content('<main><label>Article <select name="a"><option value="">Choose</option>'
                                       '<option value="17">QX-11 – round, 40 mm</option>'
                                       '<option value="18">QX-12 – flat</option></select></label></main>')
                view = await site.view()
                article = int(re.search(r'\[(\d+) select "Article', view).group(1))
                report = await site.fill([{"ref": article, "value": "QX-11"}])
                self.assertTrue(report.startswith("Filled."), report[:200])
                self.assertEqual(await page.locator("select[name=a]").input_value(), "17")
                # an address on a host the page does not link to is not opened
                answer = await site.goto("https://made-up-host.invalid/start")
                self.assertIn("is not this website", answer)
            finally:
                await browser.close()


class Failures(unittest.TestCase):
    def test_a_browser_error_keeps_its_reason(self):
        error = ('Locator.fill: Timeout 4000ms exceeded.\nCall log:\n  - waiting for locator("[data-agent-ref=\\"3\\"]")'
                 '.first\n  -   locator resolved to <input name="code" data-agent-ref="3"/>\n  - attempting fill action\n'
                 '  -   2 × waiting for element to be visible, enabled and editable\n  -     - element is not editable\n'
                 '  -   - retrying fill action')
        self.assertEqual(web.failure(error), "Locator.fill: Timeout 4000ms exceeded. (element is not editable)")
        self.assertEqual(web.failure("plain"), "plain")


class NumberFields(unittest.TestCase):
    def test_german_amounts_go_into_number_fields_as_plain_numbers(self):
        self.assertEqual(web.plain_number("512,46"), "512.46")
        self.assertEqual(web.plain_number("4.321,09"), "4321.09")
        self.assertEqual(web.plain_number("25"), "25")
        asyncio.run(self.check())

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content('<main><label>Preis <input type="number" name="p" step="0.01"></label>'
                                       '<label>Text <input name="t"></label></main>')
                site = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                view = await site.view()
                price = int(re.search(r'\[(\d+) number-input "Preis', view).group(1))
                text = int(re.search(r'\[(\d+) input "Text', view).group(1))
                report = await site.fill([{"ref": price, "value": "4.321,09"}, {"ref": text, "value": "4.321,09"}])
                self.assertTrue(report.startswith("Filled."), report[:200])
                self.assertEqual(await page.locator("[name=p]").input_value(), "4321.09")
                self.assertEqual(await page.locator("[name=t]").input_value(), "4.321,09")  # text stays as given
            finally:
                await browser.close()


class RequiredFields(unittest.TestCase):
    def test_a_blocked_send_names_the_required_fields(self):
        asyncio.run(self.check())

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content('<main><form onsubmit="document.body.dataset.sent = 1; return false">'
                                       '<label><input type="checkbox" name="d" required> Eigenerklärung</label>'
                                       '<button>Weiter</button><button formnovalidate name="skip">Auslassen</button>'
                                       '</form></main>')
                site = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                view = await site.view()
                self.assertRegex(view, r'checkbox "Eigenerklärung" required')
                go = int(re.search(r'\[(\d+) button "Weiter"', view).group(1))
                answer = await site.click(go)
                self.assertIn("The form was not sent", answer)
                self.assertIn("Eigenerklärung", answer)
                skip = int(re.search(r'\[(\d+) button "Auslassen"', await site.view()).group(1))
                self.assertNotIn("The form was not sent", await site.click(skip))  # no check for this button
                # a page script handles this button itself, so the empty required field blocks nothing
                await page.set_content('<main><form><label>Code <input name="c" required></label>'
                                       '<button onclick="event.preventDefault(); document.body.dataset.asked = 1">'
                                       'Code anfordern</button></form></main>')
                ask = int(re.search(r'\[(\d+) button "Code anfordern"', await site.view()).group(1))
                self.assertNotIn("The form was not sent", await site.click(ask))
                self.assertEqual(await page.evaluate("document.body.dataset.asked"), "1")
                gone = int(re.search(r'\[(\d+) button "Code anfordern"', await site.view()).group(1))
                await page.set_content("<main><p>Neu geladen</p></main>")
                self.assertIn("no longer on the page", await site.click(gone))
            finally:
                await browser.close()


class ScrollTerms(unittest.TestCase):
    def test_scrolling_the_terms_unlocks_their_checkbox(self):
        asyncio.run(self.check())

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content('<main><div id="t" style="height:60px;overflow:auto">' + "Bedingung. " * 300 +
                                       '</div><label><input type="checkbox" id="c" disabled> gelesen</label><script>'
                                       'const t = document.getElementById("t"); t.addEventListener("scroll", () => {'
                                       ' if (t.scrollTop + t.clientHeight >= t.scrollHeight - 2)'
                                       ' document.getElementById("c").disabled = false; });</script></main>')
                site = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                self.assertRegex(await site.view(), r'checkbox "gelesen" disabled')
                self.assertNotRegex(await site.scroll(), r'checkbox "gelesen" disabled')
            finally:
                await browser.close()


class KeystrokesOnly(unittest.TestCase):
    def test_a_field_that_drops_script_values_gets_real_keystrokes(self):
        asyncio.run(self.check())

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content('<main><label>Menge <input name="q"></label>'
                                       '<label>TAN <input name="t" maxlength="4"></label><script>'
                                       'let keys = false; const q = document.querySelector("[name=q]");'
                                       'q.addEventListener("keydown", () => { keys = true; });'
                                       'q.addEventListener("input", () => { if (!keys) setTimeout(() => { q.value = ""; }, 30); });'
                                       '</script></main>')
                site = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                view = await site.view()
                ref = int(re.search(r'\[(\d+) input "Menge', view).group(1))
                report = await site.fill([{"ref": ref, "value": "130"}])
                self.assertTrue(report.startswith("Filled."), report[:200])
                self.assertEqual(await page.locator("[name=q]").input_value(), "130")
                report = await site.fill([{"ref": ref, "value": "130"}])  # the same value again: still kept
                self.assertTrue(report.startswith("Filled."), report[:200])
                tan = int(re.search(r'\[(\d+) input "TAN', view).group(1))
                report = await site.fill([{"ref": tan, "value": "7F3A99"}])  # longer than the field: reported
                self.assertIn("several fields", report)
            finally:
                await browser.close()


class TwoStepLogin(unittest.TestCase):
    def test_user_name_first_then_the_password(self):
        asyncio.run(self.check())

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content('<main><form id="f" onsubmit="return false"><label>Benutzer <input '
                                       'name="username" autocomplete="username"></label></form><script>'
                                       'document.getElementById("f").addEventListener("submit", () => {'
                                       ' document.querySelector("main").innerHTML = \'<label>Kennwort <input '
                                       'type="password" id="p" onkeydown="if (event.key === \\\'Enter\\\') '
                                       'document.body.dataset.done = this.value"></label>\'; });</script></main>')
                access = {"siteId": "test", "url": "about:blank", "credentials": {"username": "u1", "password": "pw-123456"}}
                site = web.Site(access, context, page, log=lambda *_: None)
                answer = await site.login()
                self.assertIn("two steps", answer)
                self.assertEqual(await page.evaluate("document.body.dataset.done"), "pw-123456")
            finally:
                await browser.close()


class Prompts(unittest.TestCase):
    def test_a_prompt_gets_the_tan_or_the_quoted_word(self):
        asyncio.run(self.check())

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content('<main><button onclick="document.body.dataset.a = prompt(\'Bitte TAN eingeben\')">'
                                       'TAN</button><button onclick="document.body.dataset.b = prompt(\'Zur Bestätigung '
                                       '„VERBINDLICH“ eingeben\')">Senden</button></main>')
                site = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                self.assertIsNone(site._prompt_answer("TAN für „Anforderung 3“ eingeben", ""))  # no TAN read yet
                self.assertEqual(site._prompt_answer("Code „JA“ eingeben", ""), "JA")
                site.secrets.update({"OLD4TAN9", "7F3A99"})  # as get_tan keeps them: an older one has expired
                site.last_secret = "7F3A99"
                view = await site.view()
                await site.click(int(re.search(r'\[(\d+) button "TAN"', view).group(1)))
                self.assertEqual(await page.evaluate("document.body.dataset.a"), "7F3A99")
                view = await site.view()
                await site.click(int(re.search(r'\[(\d+) button "Senden"', view).group(1)))
                self.assertEqual(await page.evaluate("document.body.dataset.b"), "VERBINDLICH")
            finally:
                await browser.close()


class Hold(unittest.TestCase):
    def test_a_hold_to_confirm_control_unlocks(self):
        asyncio.run(self.check())

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content('<main><button id="h" type="button">Gedrückt halten</button><p id="s">gesperrt</p>'
                                       '<script>let t; const b = document.getElementById("h");'
                                       'b.addEventListener("mousedown", () => { t = Date.now(); });'
                                       'b.addEventListener("mouseup", () => { if (Date.now() - t > 1500) '
                                       'document.getElementById("s").textContent = "entsperrt"; });</script></main>')
                site = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                view = await site.view()
                ref = int(re.search(r'\[(\d+) button "Gedrückt halten"', view).group(1))
                self.assertIn("entsperrt", await site.hold(ref, 2))
                # a control that relabels itself when pressed shrinks away from the pointer and ends the hold
                await page.set_content('<main><button id="h" type="button">Bitte lange festhalten zum Bestätigen</button>'
                                       '<script>(() => { let t; const b = document.getElementById("h");'
                                       'b.addEventListener("pointerdown", () => { b.textContent = "Halten"; t = setTimeout('
                                       '() => { b.textContent = "Bestätigt"; b.disabled = true; }, 1500); });'
                                       'const stop = () => { if (!b.disabled) { clearTimeout(t); b.textContent = '
                                       '"Bitte lange festhalten zum Bestätigen"; } };'
                                       'b.addEventListener("pointerup", stop); b.addEventListener("pointerleave", stop);'
                                       '})();</script></main>')  # its own scope: the page ran a script before
                view = await site.view()
                ref = int(re.search(r'\[(\d+) button "Bitte lange', view).group(1))
                self.assertIn("Bestätigt", await site.hold(ref, 2))
                await page.set_content('<main><input id="i"><p id="k">-</p><script>document.getElementById("i")'
                                       '.addEventListener("keydown", (e) => { document.getElementById("k").textContent'
                                       ' = e.key; });</script></main>')
                view = await site.view()
                field = int(re.search(r'\[(\d+) input', view).group(1))
                self.assertIn("Tab", await site.press("TAB", field))  # a key name in another case still works
            finally:
                await browser.close()


class DragOnto(unittest.TestCase):
    def test_a_piece_is_dragged_onto_its_slot(self):
        asyncio.run(self.check())

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content(
                    '<main><div id="piece" style="position:absolute;left:20px;top:80px;width:40px;height:40px;'
                    'background:#c33;cursor:pointer" tabindex="0">Teil</div>'
                    '<div id="slot" style="position:absolute;left:300px;top:80px;width:60px;height:60px;'
                    'border:1px solid #333" tabindex="0">Ziel</div><p id="s" style="margin-top:160px">offen</p>'
                    '<script>const p = document.getElementById("piece"); let down = false;'
                    'p.addEventListener("mousedown", () => { down = true; });'
                    'document.addEventListener("mouseup", (e) => { if (!down) return; down = false;'
                    'const r = document.getElementById("slot").getBoundingClientRect();'
                    'if (e.clientX > r.left && e.clientX < r.right && e.clientY > r.top && e.clientY < r.bottom)'
                    ' document.getElementById("s").textContent = "gelöst"; });</script></main>')
                site = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                view = await site.view()
                piece = int(re.search(r'\[(\d+) \w+ "Teil"', view).group(1))
                slot = int(re.search(r'\[(\d+) \w+ "Ziel"', view).group(1))
                self.assertIn("gelöst", await site.drag(piece, to=slot))
                # a slider dragged with to= itself (run #13) still moves all the way
                await page.set_content('<main><label>Freigabe <input type="range" name="r" min="0" max="100" '
                                       'value="0"></label></main>')
                view = await site.view()
                slider = int(re.search(r'\[(\d+) range-input', view).group(1))
                # the slider path ran (it reports the slider's value), not a drop onto itself
                self.assertIn("The slider is now at", await site.drag(slider, to=slider))
            finally:
                await browser.close()


class KeepAlive(unittest.TestCase):
    def test_keep_alive_requests_the_current_page_with_the_cookies(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        seen: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append(self.headers.get("Cookie") or "")
                body = b"<main><p>Start page</p></main>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Set-Cookie", "session=abc; Path=/")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        try:
            asyncio.run(self.check(url, seen))
        finally:
            server.shutdown()

    async def check(self, url: str, seen: list[str]):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                site = web.Site({"siteId": "test", "url": url}, context, page, log=lambda *_: None)
                await site.goto(url)
                before = len(seen)
                await site.keep_alive()
                self.assertEqual(len(seen), before + 1)
                self.assertIn("session=abc", seen[-1])  # the browser's session cookie went along
                self.assertIn("Start page", await site.view())  # the page itself was not touched
            finally:
                await browser.close()


class StuckPages(unittest.TestCase):
    def test_a_page_that_stops_answering_is_reported_and_left_for_a_fresh_tab(self):
        asyncio.run(asyncio.wait_for(self.check(), 90))

    async def check(self):
        from playwright.async_api import async_playwright
        web.FRAME_SECONDS, saved = 1.0, web.FRAME_SECONDS
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.set_content("<main><p>Before</p></main>"
                                       "<script>setTimeout(() => { for (;;) {} }, 200)</script>")
                await asyncio.sleep(0.5)  # the page's script now blocks it for good
                site = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                view = await site.view()
                self.assertIn("does not respond", view)
                view = await site.fresh_tab("data:text/html,<main><p>Fresh page</p></main>")
                self.assertIn("Fresh page", view)
                self.assertIsNot(site.page, page)
            finally:
                web.FRAME_SECONDS = saved
                await browser.close()


class SharedBrowser(unittest.TestCase):
    def test_agents_in_parallel_tabs_of_one_browser_keep_their_own_tabs(self):
        asyncio.run(asyncio.wait_for(self.check(), 60))

    async def check(self):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                first = web.Site({"siteId": "test", "url": "about:blank"}, context, page, log=lambda *_: None)
                await page.set_content("<main><p>First agent</p></main>")
                second = await first.spawn()
                self.assertIsNot(second.page, first.page)
                self.assertIs(first.page, page)  # opening the second agent's tab did not move the first agent
                await second.page.set_content('<main><button onclick="window.open(\'about:blank#popup\')">Open'
                                              '</button></main>')
                view = await second.view()
                await second.click(int(re.search(r'\[(\d+) button "Open"', view).group(1)))
                for _ in range(20):
                    if len(second.tabs) == 2:
                        break
                    await asyncio.sleep(0.1)
                self.assertEqual(len(second.tabs), 2)  # the popup is the second agent's
                self.assertTrue(second.page.url.endswith("#popup"))
                self.assertIs(first.page, page)
                self.assertEqual(first.tabs, [page])
                await first.fresh_tab("data:text/html,<main><p>Fresh</p></main>")
                await asyncio.sleep(0.3)
                self.assertEqual(len(first.tabs), 2)
                self.assertEqual(len(second.tabs), 2)  # the first agent's new tab stayed out of the second's
                self.assertIn("First agent", await first.switch_tab(0))
            finally:
                await browser.close()


class SharedLogin(unittest.TestCase):
    def test_tabs_of_one_browser_log_in_once(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        posts: list[str] = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                logged_in = "session=ok" in (self.headers.get("Cookie") or "")
                body = (b"<main><p>Inbox</p></main>" if logged_in else
                        b'<main><form method="post" action="/login"><input name="user">'
                        b'<input type="password" name="secret"><button>Go</button></form></main>')
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                posts.append(self.path)
                self.send_response(303)
                self.send_header("Set-Cookie", "session=ok; Path=/")
                self.send_header("Location", "/")
                self.end_headers()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        try:
            asyncio.run(asyncio.wait_for(self.check(url), 60))
        finally:
            server.shutdown()
        self.assertEqual(posts, ["/login"])

    async def check(self, url: str):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context()
                access = {"siteId": "post", "url": url, "credentials": {"username": "u", "password": "p"}}
                first = web.Site(access, context, await context.new_page(), log=lambda *_: None)
                second = await first.spawn()
                await asyncio.gather(first.goto(url), second.goto(url))
                views = await asyncio.gather(first.login(), second.login())
                self.assertTrue(all("Inbox" in view for view in views), views)
            finally:
                await browser.close()


class StuckTools(unittest.TestCase):
    def test_a_tool_that_never_returns_is_abandoned_with_advice(self):
        import llm
        llm.TOOL_SECONDS, saved = 0.5, llm.TOOL_SECONDS

        async def hangs() -> str:
            await asyncio.sleep(60)
            return "never"

        try:
            agent = llm.Agent("test", "system", [(llm.tool("hangs", "Hangs.", {}), hangs)], deadline=0)
            answer = asyncio.run(agent._call("hangs", "{}"))
            self.assertIn("did not finish within", answer)
            self.assertIn("fresh_tab()", answer)
        finally:
            llm.TOOL_SECONDS = saved


if __name__ == "__main__":
    unittest.main()
