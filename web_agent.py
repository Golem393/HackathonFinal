"""A generic browser sub-agent: a model drives one Playwright page through tools until it calls `finish`.

The model decides where to go, what to type and search for, and which pages matter. The code here only carries out
its actions and describes the page back to it (text plus a numbered list of the controls it can use). Site-specific
knowledge lives in each sub-agent's goal prompt, never in this loop, so the same agent works on websites it has not
seen before.
"""
import asyncio
import json
import re
import time
from collections import Counter
from urllib.parse import urljoin, urlparse

import documents
import models
import telemetry
from profiles import Profile, profile as get_profile

# Numbers every visible control in every frame (data-agent-id="frame.index") and describes it for the model.
OBSERVE_JS = """(frameNo) => {
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const name = el => ((el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute('aria-label')
    || el.getAttribute('title') || el.placeholder || el.innerText || el.value || el.name || '').trim().replace(/\\s+/g, ' ').slice(0, 80);
  const sel = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[role=link],[role=tab],[role=menuitem],[onclick]';
  const controls = [];
  document.querySelectorAll('[data-agent-id]').forEach(el => el.removeAttribute('data-agent-id'));
  document.querySelectorAll(sel).forEach((el, i) => {
    const toggle = el.type === 'checkbox' || el.type === 'radio';
    // Styled checkboxes hide the real input; then its visible label is what gets clicked.
    const target = visible(el) ? el : (toggle && el.labels && [...el.labels].find(visible));
    if (!target) return;
    const id = `${frameNo}.${i}`;
    target.setAttribute('data-agent-id', id);
    const c = {id, tag: el.tagName.toLowerCase(), name: name(el)};
    if (el.type && el.tagName !== 'BUTTON') c.type = el.type;
    if (el.name) c.field = el.name;
    if (el.type === 'range') Object.assign(c, {min: el.min || '0', max: el.max || '100'});
    if (toggle) c.checked = el.checked;
    else if (['INPUT', 'TEXTAREA'].includes(el.tagName) && el.type !== 'password' && el.value) c.value = el.value.slice(0, 80);
    if (el.tagName === 'SELECT') c.options = [...el.options].map(o => o.text.trim()).slice(0, 40);
    if (el.tagName === 'A') c.href = el.getAttribute('href');
    if (el.required) c.required = true;
    if (el.willValidate && !el.checkValidity()) c.invalid = el.validationMessage || true;
    if (el.disabled) c.disabled = true;
    controls.push(c);
  });
  // Scroll areas: elements holding more than they show (lists that may load more when scrolled).
  let n = 0;
  document.querySelectorAll('div,section,ul,ol,table,tbody,main,aside,[role=region],[role=list],[role=grid],[role=log]')
    .forEach(el => {
      const st = getComputedStyle(el);
      if (!visible(el) || !/(auto|scroll)/.test(st.overflowY) || el.scrollHeight <= el.clientHeight + 20) return;
      const id = `${frameNo}.s${n++}`;
      el.setAttribute('data-agent-id', id);
      controls.push({id, tag: 'scroll area', name: (el.getAttribute('aria-label') || el.id || '').slice(0, 60),
                     scrolled: `${Math.round(100 * (el.scrollTop + el.clientHeight) / el.scrollHeight)} %`});
    });
  // Text a screen reader would hear but innerText misses: images, canvases and icons with an accessible name.
  const graphics = [...document.querySelectorAll('img,canvas,svg,[role=img]')].filter(visible)
    .map(el => (el.getAttribute('aria-label') || el.getAttribute('alt') || el.getAttribute('title') || '').trim())
    .filter(Boolean).map(t => `[image: ${t}]`);
  const text = (document.body ? document.body.innerText : '').replace(/\\n{3,}/g, '\\n\\n');
  return {title: document.title, text: graphics.length ? text + '\\n' + [...new Set(graphics)].join('\\n') : text, controls};
}"""

TOOLS = [
    {"name": "click", "description": "Click a control by its id.",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "type", "description": "Replace the text of an input by its id; submit=true presses Enter afterwards. "
                                    "For a slider (type range), text is the target value: it is dragged there.",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"},
                                                     "submit": {"type": "boolean"}}, "required": ["id", "text"]}},
    {"name": "type_credential", "description": "Type this website's login username or password into an input.",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"},
                                                     "field": {"type": "string", "enum": ["username", "password"]}},
                    "required": ["id", "field"]}},
    {"name": "select", "description": "Choose an option (by its visible text) in a select control.",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"}, "option": {"type": "string"}},
                    "required": ["id", "option"]}},
    {"name": "press", "description": "Press a key on the focused element, e.g. Enter, Escape, F4, Tab.",
     "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}},
    {"name": "goto", "description": "Open a URL or a path on this website.",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "back", "description": "Go back one page.", "parameters": {"type": "object", "properties": {}}},
    {"name": "read_page", "description": "Read the current page again, with more of its text (offset in characters).",
     "parameters": {"type": "object", "properties": {"offset": {"type": "integer"}}}},
    {"name": "scroll", "description": "Scroll a scroll area (or the page, without id) with the mouse wheel, as a person "
                                      "does; lists that load more when scrolled show their new rows. to_end=true keeps "
                                      "scrolling until nothing new loads.",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"}, "to_end": {"type": "boolean"}}}},
    {"name": "read_all_pages", "description": "Read a paged list or table to its end in one go: give the id of its "
                                              "next-page control (button or link); every page's text comes back "
                                              "together. Use it for result lists, Q&A pages, tables with pages.",
     "parameters": {"type": "object", "properties": {"next_id": {"type": "string"},
                                                     "max_pages": {"type": "integer"}}, "required": ["next_id"]}},
    {"name": "open_document", "description": "Read a document (CSV, TXT, ZIP, JSON, XML, PDF...) behind a link or "
                                             "download button you chose; returns its text. Use it for files the page "
                                             "itself does not show.",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "note", "description": "Record a fact you confirmed on the page, so it survives when old pages are "
                                    "dropped from your context. Quote values exactly as shown.",
     "parameters": {"type": "object", "properties": {"fact": {"type": "string"}}, "required": ["fact"]}},
    {"name": "finish", "description": "Stop and return your result, matching the requested format.",
     "parameters": {"type": "object", "properties": {"result": {"type": "object"}}, "required": ["result"]}},
]

# Zero-width and other invisible characters that some pages put inside words ("T\u200be\u200br...") so that a model
# no longer recognizes them; the reader sees the same text without them.
INVISIBLE = re.compile("[\u00ad\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]")
# Closes the topmost open popup if it only informs (survey, maintenance notice, banner): returns what it closed.
DISMISS_JS = """() => {
  const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const popups = [...document.querySelectorAll('dialog[open], [role=dialog], [role=alertdialog], [aria-modal=true]')]
    .filter(visible);
  const popup = popups[popups.length - 1];
  if (!popup) return '';
  const name = (popup.getAttribute('aria-label') || popup.querySelector('h1,h2,h3')?.innerText || 'popup').trim();
  if (popup.querySelector('input[type=range], input[type=checkbox]:not(:checked), input[type=text], input:not([type])'))
    return '';  // a gate that needs input: the model solves it
  const words = /^(×|✕|x|schließen|schliessen|close|später|spaeter|nicht jetzt|abbrechen|ablehnen|verstanden|ok|okay|ausblenden|überspringen|skip|dismiss|zur kenntnis genommen|weiter ohne)$/i;
  const buttons = [...popup.querySelectorAll('button, [role=button], a')].filter(visible);
  const close = buttons.find(b => words.test((b.innerText || b.getAttribute('aria-label') || '').trim()))
    || buttons.find(b => /close|schlie/i.test(b.getAttribute('aria-label') || b.className || ''));
  if (close) { close.click(); return name; }
  if (popup.tagName === 'DIALOG' && popup.close) { popup.close(); return name + ' (closed)'; }
  return '';
}"""

# Finds the enabled next-page control with the given label on the current page (after OBSERVE_JS numbered it).
NEXT_JS = """(label) => {
  const els = [...document.querySelectorAll('[data-agent-id]')];
  const norm = s => (s || '').trim().replace(/\\s+/g, ' ');
  const hit = els.find(e => norm(e.getAttribute('aria-label') || e.innerText || e.value).slice(0, 60) === label
    && !e.disabled && e.getAttribute('aria-disabled') !== 'true');
  return hit ? hit.getAttribute('data-agent-id') : null;
}"""

LOGIN_GOAL = """Log in to this website with your login (type_credential) and accept what stands right after it
(cookie consent, notices). A colleague handles access checks (sliders, "not a robot", codes): if one shows, just
continue once it is gone. The moment the site's normal content or menu is shown, call finish; do nothing else there.
Finish with {"logged_in": true} or {"logged_in": false, "problem": "..."}."""

GATE_GOAL = """This page shows an access check before its content (unlock slider, "not a robot" box, a receipt or
code shown on the page, a terms confirmation, a continue button). Pass it: drag every slider to its maximum (type the
max value into it), tick every box the check asks for, type any code or receipt number exactly as the page shows it
(it may be in an image's text), then press its continue/unlock button. If it fails, read the message and redo it once.
Do all of it in ONE turn when the controls are visible: several tool calls at once (every slider, every box, the code,
then the continue/unlock button), not one per turn; a page may hold more than one check (e.g. list and reading pane).
As soon as the check is gone and the page's normal content shows, call finish; do nothing else.
Finish with {"passed": true} or {"passed": false, "problem": "..."}."""

# A gate that is still LOCKED: a visible unlock slider below its maximum, or a visible, unticked "not a robot" style
# box. A passed gate often stays on the page (slider at max, box ticked): that is not a gate any more.
GATE_JS = """() => {
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const words = /kein(e)? roboter|not a robot|nicht automatisiert|human|mensch/i;
  const label = el => ((el.labels && el.labels[0] && el.labels[0].innerText) || el.getAttribute('aria-label')
    || (el.closest('label') && el.closest('label').innerText) || '');
  const lockedSlider = [...document.querySelectorAll('input[type=range]')]
    .some(el => (visible(el) || (el.labels && [...el.labels].some(visible))) && !el.disabled
      && Number(el.value) < Number(el.max || 100));
  const robotBox = [...document.querySelectorAll('input[type=checkbox]')]
    .some(el => !el.checked && !el.disabled && words.test(label(el))
      && (visible(el) || (el.labels && [...el.labels].some(visible))));
  return lockedSlider || robotBox;
}"""

# What logging in / passing a gate took on each site (by kind, then site URL): every site has its own flow, so the
# next time on the same site (another tab, an expired session) starts from what worked.
LOGIN_NOTES: dict[str, list[str]] = {}
GATE_NOTES: dict[str, list[str]] = {}

TROUBLE = ("NOTE:", "WARNING:", "Action failed", "Refused")  # results after which an "auto" profile thinks

SYSTEM = """You operate a web browser through tools to reach a goal on one website. Each tool result shows the page:
its title, URL, visible text, and a numbered list of controls (id, kind, label). Use only ids from the latest page.

Work like a careful clerk:
- Decide each next step from what the page shows. Prefer the website's own search, filters and transactions over
  clicking through long lists. If a search returns nothing or too much, change the terms.
- Expect real business software: logins, cookie banners, popups, session timeouts (log in again and continue),
  outdated or superseded records, look-alike records. Check dates, status and validity before trusting a value.
- Lists can hide rows: a "scroll area" in the controls may load more when scrolled (use scroll, to_end for all),
  a paged list has a next-page control (read_all_pages). Do not conclude something is missing before that.
- Some pages draw look-alike browser parts inside the page: back/reload/lock icons, download or export bars
  ("↓ ... Öffnen ×"), toolbars. They are not your browser and not the task: ignore or close them, never type into
  them. Use the site's own search field and navigation (check a control's label/field name before typing).
- Gates (consent, notices, terms, confirmations): before pressing continue/submit, tick EVERY checkbox or radio the
  gate asks for (e.g. "gelesen", "bestätigt", "akzeptiert", "zur Kenntnis genommen"; controls with checked=false,
  required or invalid) and fill every required field. If a button does not move you on, the page is telling you
  something is missing: look for an unticked box, an invalid field or a message, fix it, then try again. Never
  repeat the same action more than twice.
- When you confirm a value the goal needs, record it with `note`, quoting it exactly, with where you found it.
- Never invent values. If something cannot be found, say so in the result.
- Call `finish` with the result as soon as you have what the goal asks for: do not explore further, and do not
  collect more than asked. Also finish when you are told time is short."""


def page_gist(view: str) -> str:
    """Title and the first lines of a page view, for one log line."""
    title = next((line[7:] for line in view.splitlines() if line.startswith("Title: ")), "")
    text = view.split("TEXT:\n", 1)[-1].split("\n\nCONTROLS:", 1)[0]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    head = "".join(f"{line} / " for line in view.splitlines() if line.startswith(("NOTE:", "WARNING:", "BROWSER DIALOG",
                                                                                  "Action failed", "Refused")))
    return (head + title + " | " + " / ".join(lines[:6]))[:300]


class WebAgent:
    """One model-driven browser session on one website."""

    def __init__(self, page, site: dict, *, label: str = "agent", profile: Profile | str = "default",
                 max_steps: int | None = None, extra_tools: dict | None = None):
        """`profile` (see profiles.py) sets model, thinking and limits. `extra_tools` maps a tool name to
        (description, JSON-schema parameters, async handler(args) -> str): abilities beyond this website, such as
        asking another sub-agent for something."""
        self.page = page
        self.site = site                  # {"siteId", "url", "credentials": {"username", "password"}}
        self.label = label
        self.profile = profile if isinstance(profile, Profile) else get_profile(profile)
        self.max_steps = max_steps or self.profile.max_steps
        self.in_trouble = False           # the last result went wrong: an "auto" profile thinks on the next step
        self.extra_tools = extra_tools or {}
        self.notes: list[str] = []
        self.last_view = ""
        self.repeats: Counter = Counter()
        self.dialogs: list[str] = []
        self.popups_closed: list[str] = []
        self.client = models.qwen()
        self.tel = telemetry.tracker(label)
        telemetry.redact(*(site.get("credentials") or {}).values())
        page.on("dialog", self.on_dialog)

    async def on_dialog(self, dialog) -> None:
        """Browser dialogs (alert/confirm/prompt) block the page; Playwright would dismiss them. The model clicked
        the button that opened it, so accept it and tell the model what it said."""
        self.dialogs.append(f"{dialog.type}: {dialog.message}")
        self.tel.event("steps", f"browser dialog ({dialog.type}) accepted: {dialog.message[:160]}")
        await dialog.accept()

    async def observe(self, offset: int = 0) -> str:
        parts, controls = [], []
        for number, frame in enumerate(self.page.frames):
            try:  # evaluate has no timeout of its own: a frame that is navigating could hang it forever
                info = await asyncio.wait_for(frame.evaluate(OBSERVE_JS, number), timeout=10)
            except Exception:
                continue  # detached, cross-origin, still loading, or hanging frame
            if number and not (info["text"].strip() or info["controls"]):
                continue
            header = "" if number == 0 else f"\n--- frame {number} ({frame.url}) ---\n"
            parts.append(header + info["text"])
            controls += info["controls"]
        text = INVISIBLE.sub("", "".join(parts))
        controls = json.loads(INVISIBLE.sub("", json.dumps(controls, ensure_ascii=False)))
        limit = self.profile.text_limit
        shown = text[offset:offset + limit]
        more = f"\n[... {len(text) - offset - limit} more characters: read_page offset={offset + limit}]" \
            if len(text) > offset + limit else ""
        return (f"URL: {self.page.url}\nTitle: {await self.safe_title()}\n\nTEXT:\n{shown}{more}\n\nCONTROLS:\n"
                + "\n".join(json.dumps(c, ensure_ascii=False) for c in controls))

    async def safe_title(self) -> str:
        try:
            return await asyncio.wait_for(self.page.title(), timeout=5)
        except Exception:
            return ""

    def locate(self, control_id: str):
        frame_no = int(control_id.split(".")[0])
        frame = self.page.frames[frame_no] if frame_no < len(self.page.frames) else self.page.main_frame
        return frame.locator(f'[data-agent-id="{control_id}"]').first

    async def settle(self) -> None:
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            await self.page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass  # pages that keep polling never go idle; what has loaded is enough

    async def drag_slider(self, slider, value: str) -> None:
        """Move a range input the way a person does: press on its handle, drag to the target, release. Pages that
        check for a real drag (unlock sliders) ignore a value set directly."""
        low, high, now = await slider.evaluate("e => [+e.min || 0, +e.max || 100, +e.value || 0]")
        target = min(max(float(value), low), high)
        box = await slider.bounding_box()
        if not box:
            raise LookupError("The slider is not on screen.")
        x_at = lambda v: box["x"] + 6 + (box["width"] - 12) * (v - low) / ((high - low) or 1)
        y = box["y"] + box["height"] / 2
        await slider.scroll_into_view_if_needed()
        await self.page.mouse.move(x_at(now), y)
        await self.page.mouse.down()
        await self.page.mouse.move(x_at(target) + (2 if target >= high else 0), y, steps=15)
        await self.page.mouse.up()

    async def open_document(self, control_id: str) -> str:
        """The text of the document behind a control: a link is fetched with this session's cookies; a button that
        starts a download is clicked and the download read. ZIP files list and read their members."""
        control = self.locate(control_id)
        href = await control.get_attribute("href")
        name, data = "", b""
        if href and not href.startswith(("javascript:", "#")):
            response = await self.page.context.request.get(urljoin(self.page.url, href), timeout=30000)
            name, data = href.rsplit("/", 1)[-1], await response.body()
            if "text/html" in (response.headers.get("content-type") or "") and not name.lower().endswith((".csv", ".txt")):
                await control.click(timeout=10000)   # an HTML page, not a file: just open it
                await self.settle()
                return await self.observe()
        else:
            try:
                async with self.page.expect_download(timeout=6000) as info:
                    await control.click(timeout=10000)
            except Exception:  # no file came: the control opened a page, a frame or a viewer instead
                await self.settle()
                return "No download started; the control opened this instead:\n\n" + await self.observe()
            download = await info.value
            name, data = download.suggested_filename, open(await download.path(), "rb").read()
        return f"DOCUMENT {name} ({len(data)} bytes):\n" + documents.to_text(name, data)[:self.profile.text_limit * 2]

    async def needs_login(self) -> bool:
        """A visible password field on this site means: not logged in (start, or a session that expired)."""
        try:
            return await asyncio.wait_for(self.page.locator("input[type=password]:visible").count(), timeout=10) > 0
        except Exception:
            return False

    async def needs_gate(self) -> bool:
        try:
            return bool(await asyncio.wait_for(self.page.evaluate(GATE_JS), timeout=10))
        except Exception:
            return False

    async def delegate(self, kind: str, deadline: float | None) -> bool:
        """Hand the tab to a helper agent for this site: "login" (credentials) or "gate" (access check). It works on
        this same tab, learns from earlier times on this site, and gives the tab back; True when it ran."""
        goal_text, profile, memory = {"login": (LOGIN_GOAL, "site_login", LOGIN_NOTES),
                                      "gate": (GATE_GOAL, "site_gate", GATE_NOTES)}[kind]
        self.tel.event("steps", f"{kind}: handing over to the {kind} agent")
        known = memory.get(self.site["url"], [])
        goal = goal_text + (f"\n\nHow this went on this site before (same flow, values may differ):"
                            + "".join(f"\n- {n}" for n in known[-8:]) if known else "")
        result = await WebAgent(self.page, self.site, label=f"{self.label}-{kind}", profile=profile) \
            .run(goal, deadline=deadline)
        learned = [str(n) for n in result.get("notes") or []]
        memory.setdefault(self.site["url"], []).extend(n for n in learned if n not in known)
        self.notes.extend(f"({kind}) {n}" for n in learned[-3:])
        self.last_view = ""
        return True

    async def ensure_logged_in(self, deadline: float | None) -> bool:
        """Login form -> login agent; access check -> gate agent (also for the login agent). True when one ran.
        The gate agent never delegates; the login agent only hands over gates."""
        ran = False
        if self.profile.name not in ("site_login", "site_gate") and self.site.get("credentials") \
                and await self.needs_login():
            ran = await self.delegate("login", deadline)
        if self.profile.name != "site_gate" and await self.needs_gate():
            ran = await self.delegate("gate", deadline) or ran
        return ran

    async def snapshot(self, step: int, action: str, view: str) -> None:
        """With the `html` log feature: keep the page's HTML (frames inlined after it) for offline study."""
        if not telemetry.enabled("html") or action in ("note", "finish"):
            return
        try:
            parts = []
            for number, frame in enumerate(self.page.frames):
                html = await asyncio.wait_for(frame.content(), timeout=10)
                parts.append(html if number == 0 else f"\n<!-- ===== frame {number}: {frame.url} ===== -->\n{html}")
            telemetry.save_snapshot(self.label, step, action, self.page.url, await self.page.title(), "".join(parts), view)
        except Exception as error:  # a page that navigates away mid-read: skip this snapshot
            self.tel.event("errors", f"snapshot failed: {str(error)[:120]}")

    async def click(self, control) -> None:
        """Click; if a popup covers the control, close the popup (Escape, then its close button) and click again.
        Saves the model the failed click, the closing step and the retry."""
        try:
            await control.click(timeout=4000)
            return
        except Exception as error:
            if "intercepts pointer events" not in str(error):
                raise
        closed = await self.dismiss_popup()
        try:
            await control.click(timeout=6000)
        except Exception as error:
            raise RuntimeError(f"{str(error).splitlines()[0]} (popup handling: {closed or 'nothing could be closed'})")
        if closed:
            self.popups_closed.append(closed)

    async def dismiss_popup(self) -> str:
        """Close the topmost dismissable popup: Escape first, then a close-like button inside it. Gates that ask for
        input (checkboxes, sliders, codes) are left for the model."""
        await self.page.keyboard.press("Escape")
        await self.page.wait_for_timeout(300)
        try:
            return await asyncio.wait_for(self.page.evaluate(DISMISS_JS), timeout=10)
        except Exception:
            return ""

    async def scroll(self, control_id: str | None, to_end: bool = False) -> str:
        """Mouse-wheel scrolling over an area (lazy lists load on wheel/scroll events), until nothing new appears."""
        target = self.locate(control_id) if control_id else None
        box = await target.bounding_box() if target is not None else None
        x, y = (box["x"] + box["width"] / 2, box["y"] + min(box["height"] / 2, 200)) if box else (640, 400)
        measure = (lambda: target.evaluate("e => [e.scrollHeight, e.scrollTop, e.childElementCount]")) if target is not None \
            else (lambda: self.page.evaluate("() => [document.body.scrollHeight, scrollY, 0]"))
        await self.page.mouse.move(x, y)
        rounds, before = 0, None
        for rounds in range(1, (25 if to_end else 1) + 1):
            await self.page.mouse.wheel(0, 900)
            await self.page.wait_for_timeout(500)          # time for a lazy list to fetch its next rows
            now = await asyncio.wait_for(measure(), timeout=5)
            if now == before:
                break
            before = now
        await self.settle()
        return f"Scrolled ({rounds} wheel turns).\n\n" + await self.observe()

    async def read_all_pages(self, next_id: str, max_pages: int = 12) -> str:
        """Collect the text of every page of a model-chosen paged list, following its next-page control."""
        control = self.locate(next_id)
        label = (await control.evaluate("e => (e.getAttribute('aria-label') || e.innerText || e.value || '').trim()"))[:60]
        pages, seen = [], set()
        for number in range(1, max(1, min(max_pages, 30)) + 1):
            view = await self.observe()
            text = view.split("TEXT:\n", 1)[-1].split("\n\nCONTROLS:", 1)[0]
            if text in seen:
                break
            seen.add(text)
            pages.append(f"=== page {number} ({self.page.url}) ===\n{text}")
            # the same next-page control on the new page: same label, enabled
            nxt = await self.page.evaluate(NEXT_JS, label)
            if not nxt:
                break
            try:
                await self.click(self.page.locator(f'[data-agent-id="{nxt}"]').first)
            except Exception:
                break
            await self.settle()
        joined = "\n\n".join(pages)
        return (f"READ {len(pages)} PAGES (next control: {label!r})\n\n" + joined[:self.profile.text_limit * 3]
                + "\n\nCurrent page now:\n" + await self.observe())

    async def act(self, name: str, args: dict) -> str:
        """Carry out one tool call; the result is the page afterwards (or the reason it failed)."""
        if "id" in args and not await self.locate(args["id"]).count():
            raise LookupError(f"No control {args['id']} on the current page; use an id from the latest page view.")
        if name == "click":
            await self.click(self.locate(args["id"]))
        elif name == "type":
            field = self.locate(args["id"])
            if await field.get_attribute("type") == "range":
                await self.drag_slider(field, args["text"])
            else:
                await field.fill(args["text"], timeout=10000)
                if args.get("submit"):
                    await field.press("Enter")
        elif name == "type_credential":
            await self.locate(args["id"]).fill(self.site["credentials"][args["field"]], timeout=10000)
        elif name == "select":
            await self.locate(args["id"]).select_option(label=args["option"], timeout=10000)
        elif name == "press":
            await self.page.keyboard.press(args["key"])
        elif name == "goto":
            url = urljoin(self.site["url"].rstrip("/") + "/", args["url"])
            if urlparse(url).netloc != urlparse(self.site["url"]).netloc:
                others = ", ".join(self.extra_tools) or "finish and report what you need"
                return (f"Refused: you work only on {self.site['url']}; your login is valid only there. For anything "
                        f"from another system use your tools ({others}).\n\n" + await self.observe())
            await self.page.goto(url, timeout=30000)
        elif name == "back":
            await self.page.go_back(timeout=15000)
        elif name == "read_page":
            return await self.observe(int(args.get("offset") or 0))
        elif name == "scroll":
            return await self.scroll(args.get("id"), bool(args.get("to_end")))
        elif name == "read_all_pages":
            return await self.read_all_pages(args["next_id"], int(args.get("max_pages") or 12))
        elif name == "open_document":
            return await self.open_document(args["id"])
        elif name in self.extra_tools:
            return await self.extra_tools[name][2](args)
        elif name == "note":
            self.notes.append(args["fact"])
            self.tel.event("notes", f"note: {args['fact']}", fact=args["fact"])
            return f"Noted ({len(self.notes)} notes)."
        else:
            return f"Unknown tool {name}."
        await self.settle()
        view = await self.observe()
        if self.popups_closed:
            view = "".join(f"POPUP CLOSED for you: {p}\n" for p in self.popups_closed) + "\n" + view
            self.popups_closed.clear()
        if self.dialogs:
            view = "".join(f"BROWSER DIALOG (accepted) {d}\n" for d in self.dialogs) + "\n" + view
            self.dialogs.clear()
        elif name in ("click", "press") and view == self.last_view:
            view = ("NOTE: the page did not change. Something is probably missing: an unticked checkbox, a required "
                    "or invalid field, or a message on the page.\n\n" + view)
        self.last_view = view
        return view

    def thinks(self) -> bool:
        mode = self.profile.thinking
        return mode == "on" or (mode == "auto" and self.in_trouble)

    async def call_model(self, messages: list, tools: list, step: int, attempts: int = 3):
        """One model call, retried with a pause like any provider call; None when it keeps failing."""
        think = self.thinks()
        options = self.profile.request_options(think)
        # A lost request must not stall the agent for the client's full timeout: short first, longer on retries
        # (a model waking up from idle can take minutes).
        timeouts = (45, 90, 180) if think else (30, 60, 120)
        for attempt in range(1, attempts + 1):
            try:
                client = self.client.with_options(timeout=timeouts[min(attempt, len(timeouts)) - 1]) \
                    if hasattr(self.client, "with_options") else self.client
                return await client.chat.completions.create(model=self.profile.model, messages=messages,
                                                            tools=tools, tool_choice="auto", **options)
            except Exception as error:
                self.tel.event("errors", f"step {step}: model call failed ({attempt}/{attempts}): "
                                         f"{str(error).splitlines()[0][:200]}", step=step)
                if attempt < attempts:
                    await asyncio.sleep(3 * attempt)
        return None

    async def finalize(self, goal: str, reason: str) -> dict:
        """The agent stopped without calling finish: turn its notes into the result the goal asks for with one
        short model call, so nothing it found is lost. Marked incomplete either way."""
        result: dict = {}
        if self.notes:
            prompt = (f"You worked on this goal but had to stop ({reason}):\n\n{goal}\n\nThese are the facts you "
                      "confirmed, verbatim:\n" + "\n".join(f"- {n}" for n in self.notes) +
                      "\n\nWrite the final result now, in exactly the JSON shape the goal asks for, using ONLY these "
                      "facts (null or empty for anything not found). Answer with the JSON only.")
            try:
                client = self.client.with_options(timeout=60) if hasattr(self.client, "with_options") else self.client
                reply = await client.chat.completions.create(
                    model=self.profile.model, messages=[{"role": "user", "content": prompt}],
                    **self.profile.request_options(False))
                text = reply.choices[0].message.content or ""
                result = json.loads(text[text.index("{"):text.rindex("}") + 1])
            except Exception as error:
                self.tel.event("errors", f"finalize failed: {str(error)[:200]}")
        if not isinstance(result, dict):
            result = {"raw": result}
        result.update(incomplete=True, stopped=reason)
        result.setdefault("notes", self.notes)
        self.tel.finish(f"{reason} (finalized from {len(self.notes)} notes)")
        return result

    def shrink_old_pages(self, messages: list) -> None:
        """Keep the newest page views (profile.keep_pages) in full; notes keep the facts from older ones."""
        bulky = ("URL: ", "READ ", "DOCUMENT ", "No download", "POPUP CLOSED", "BROWSER DIALOG", *TROUBLE)
        pages = [m for m in messages if m["role"] == "tool" and m["content"].startswith(bulky)]
        for message in pages[:-self.profile.keep_pages]:
            message["content"] = message["content"].split("\n", 1)[0] + "\n[older page view dropped; see your notes]"

    async def run(self, goal: str, *, deadline: float | None = None) -> dict:
        """Work towards `goal` until the model finishes, steps run out or `deadline` (epoch seconds) is near."""
        if not self.page.url.startswith(self.site["url"]):
            await self.page.goto(self.site["url"], timeout=30000)
            await self.settle()
        await self.ensure_logged_in(deadline)
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Website: {self.site['url']} ({self.site.get('siteId')}). "
                                        f"You are logged in. Colleagues handle logins and access checks (sliders, "
                                        f"'not a robot'): if one appears, it is handled for you.\n\nGOAL:\n{goal}\n\n"
                                        f"Current page:\n{await self.observe()}"},
        ]
        self.tel.event("pages", f"profile {self.profile.name}: thinking {self.profile.thinking}, "
                                f"{self.max_steps} steps; goal and first page", content=messages[1]["content"])
        tools = [{"type": "function", "function": tool} for tool in TOOLS] + [
            {"type": "function", "function": {"name": name, "description": spec[0], "parameters": spec[1]}}
            for name, spec in self.extra_tools.items()]

        for step in range(1, self.max_steps + 1):
            remaining = None if deadline is None else deadline - time.time()
            if remaining is not None and remaining < 5:
                return await self.finalize(goal, "deadline reached")
            if remaining is not None and remaining < 45:
                messages.append({"role": "user", "content": "Time is almost up: call finish now with what you have."})
            self.shrink_old_pages(messages)
            started = time.time()
            reply = await self.call_model(messages, tools, step)
            if reply is None:  # the model stayed unreachable (or the run already ended): keep what we have
                return await self.finalize(goal, "model unreachable")
            self.tel.model_call(step, self.profile.model, reply, time.time() - started, thinking=self.thinks())
            message = reply.choices[0].message
            self.tel.event("model", f"step {step}: model says: {(message.content or '').strip()[:200]}", step=step,
                           reasoning=getattr(message, "reasoning", None), content=message.content)
            messages.append(message.model_dump(exclude_none=True, include={"role", "content", "tool_calls"}))
            if not message.tool_calls:
                messages.append({"role": "user", "content": "Use a tool: continue towards the goal, or finish."})
                continue
            for call in message.tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except ValueError:
                    args = {}
                shown = {k: v for k, v in args.items() if k != "result"}
                self.tel.event("steps", f"step {step}: {name} {json.dumps(shown, ensure_ascii=False)[:160]}",
                               step=step, tool=name, args=shown)
                if name == "finish":
                    result = args.get("result") if isinstance(args.get("result"), dict) else {"raw": args}
                    result.setdefault("notes", self.notes)
                    self.tel.finish("finished")
                    return result
                try:
                    with self.tel.action(step, name):   # hard ceiling: no single action may hang the agent
                        limit = 600 if name in self.extra_tools else 90
                        content = await asyncio.wait_for(self.act(name, args), timeout=limit)
                    if name != "type_credential" and await self.ensure_logged_in(deadline):
                        content = ("NOTE: a colleague just handled a login or access check on this tab. Continue "
                                   "with your goal from here.\n\n" + await self.observe())
                except Exception as error:
                    lines = str(error).splitlines()
                    blocker = next((l.strip() for l in lines if "intercepts pointer events" in l), "")
                    reason = lines[0][:300] + (f" ({blocker[:200]}: a popup or overlay covers it; close or "
                                               "dismiss it first)" if blocker else "")
                    self.tel.event("errors", f"step {step}: {name} failed: {reason}", step=step, tool=name,
                                   error=reason)
                    content = f"Action failed: {reason}\n\n" + await self.observe()
                await self.snapshot(step, name, content)
                self.tel.event("pages", f"step {step}: now {self.page.url} | {page_gist(content)}", step=step,
                               content=content)
                key = (self.page.url, name, json.dumps(args, sort_keys=True))
                self.repeats[key] += 1
                if self.repeats[key] >= 3:
                    content = (f"WARNING: this is the {self.repeats[key]}th time you did exactly this here and it did "
                               "not get you further. Do something different: read the page for messages, look for "
                               "missing inputs, or use another tool.\n\n" + content)
                if name not in ("note", "read_page"):
                    self.in_trouble = content.startswith(TROUBLE)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
        return await self.finalize(goal, "out of steps")
