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
