"""The browser side: a compact text view of whatever page is open, and actions on its numbered elements.

Nothing here knows the websites. The view renders any page the same way: text in reading order, tables as rows,
frames after the page, and every element the model can act on as [n kind "label"]. Code helps where the brief allows
it (logging in with the run's credentials, retrying error pages, reading a document the model picked); the model
chooses where to go and what to do.
"""
import asyncio
import base64
import io
import re
import tempfile
import time
import zipfile
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote_plus, urljoin, urlparse

MAX_VIEW = 16000  # characters of the page shown at once; more() pages through the rest
MAX_DOCUMENT = 40000
FRAME_SECONDS = 15.0  # a frame that does not render its view in this time is reported as stuck, not waited for

# Renders the document of one frame and numbers what can be acted on, starting at `start`.
RENDER = r"""
(start) => {
  let n = start, line = '', inCell = 0;
  const lines = [];
  const flush = () => { const t = line.replace(/[​-‍⁠﻿­]/g, '').replace(/[ \t ]+/g, ' ').trim(); if (t && t !== lines[lines.length - 1]) lines.push(t); line = ''; };
  const brk = () => { if (inCell) line += ' '; else flush(); };
  const clip = (s, k) => { s = String(s || '').replace(/[​-‍⁠﻿­]/g, '').replace(/\s+/g, ' ').trim(); return s.length > k ? s.slice(0, k) + '…' : s; };
  const q = (s) => JSON.stringify(s);
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'HEAD', 'META', 'LINK', 'OPTION', 'defs', 'style']);
  const generated = (el, which) => {  // text a style sheet adds before or after an element
    const c = getComputedStyle(el, which).content;
    return c && c !== 'none' && c !== 'normal' && /^["']/.test(c) ? c.slice(1, -1) : '';
  };
  const ROLES = new Set(['button', 'link', 'tab', 'menuitem', 'menuitemcheckbox', 'menuitemradio', 'checkbox', 'radio',
    'option', 'switch', 'treeitem', 'combobox', 'textbox', 'searchbox']);
  const CONTROLS = 'a[href],button,input:not([type=hidden]),select,textarea,[role=button],[role=link],[onclick]';
  document.querySelectorAll('[data-agent-ref]').forEach((e) => e.removeAttribute('data-agent-ref'));
  // collapsed sections (▶ summaries) hide message texts, document contents and form fields: open them, so the view
  // shows what is inside under the summary that names it
  document.querySelectorAll('details:not([open])').forEach((d) => { d.open = true; });

  const labelOf = (el) => {
    let s = el.getAttribute('aria-label') || '';
    if (!s && el.labels && el.labels.length) s = [...el.labels].map((l) => l.innerText).join(' ');
    const by = el.getAttribute('aria-labelledby');
    if (!s && by) s = by.split(/\s+/).map((i) => (document.getElementById(i) || {}).innerText || '').join(' ');
    return clip(s || el.getAttribute('title') || el.getAttribute('placeholder') || el.name || '', 80);
  };
  // a description another element gives (aria-describedby: tooltips, legends hidden until hovered) or a title
  const described = (el) => {
    const by = el.getAttribute('aria-describedby');
    const text = by ? by.split(/\s+/).map((i) => (document.getElementById(i) || {}).textContent || '').join(' ') : '';
    return clip(text, 200);
  };
  const pointer = (el) => {
    const parent = el.parentElement;
    return getComputedStyle(el).cursor === 'pointer' && !(parent && getComputedStyle(parent).cursor === 'pointer')
      && clip(el.innerText, 300).length < 200 && !el.querySelector(CONTROLS) && !(el.tagName === 'LABEL' && el.control);
  };
  const interactive = (el) => {
    const t = el.tagName;
    if (t === 'A') return el.hasAttribute('href') || el.hasAttribute('onclick');
    if (t === 'BUTTON' || t === 'SELECT' || t === 'TEXTAREA' || t === 'SUMMARY') return true;
    if (t === 'INPUT') return el.type !== 'hidden';
    if (el.querySelector(CONTROLS)) return false;  // a container: its controls are listed instead
    const role = el.getAttribute('role');
    if (role && ROLES.has(role)) return true;
    if (el.hasAttribute('onclick') || (el.hasAttribute('tabindex') && el.tabIndex >= 0)) return true;
    if (el.isContentEditable && !(el.parentElement && el.parentElement.isContentEditable)) return true;
    return pointer(el);
  };
  const render = (el) => {
    const t = el.tagName, id = n++;
    el.setAttribute('data-agent-ref', id);
    const off = el.disabled || el.getAttribute('aria-disabled') === 'true' ? ' disabled' : '';
    if (t === 'INPUT' || t === 'TEXTAREA') {
      const type = t === 'TEXTAREA' ? 'textarea' : (el.type || 'text');
      if (type === 'checkbox' || type === 'radio') return `[${id} ${type} ${q(labelOf(el))}${el.checked ? ' checked' : ''}${el.required ? ' required' : ''}${off}]`;
      if (['submit', 'button', 'reset', 'image'].includes(type)) return `[${id} button ${q(clip(el.value || labelOf(el) || el.getAttribute('alt') || type, 80))}${off}]`;
      if (type === 'file') return `[${id} file-input ${q(labelOf(el))}${off}]`;
      const kind = type === 'text' ? 'input' : `${type}-input`;
      const hint = described(el) + (type === 'number' || type === 'range' ? ['min', 'max', 'step'].filter((a) => el.getAttribute(a)).map((a) => ` ${a}=${el.getAttribute(a)}`).join('') : '');
      return `[${id} ${kind} ${q(labelOf(el))} value=${q(clip(el.value, 120))}${el.readOnly ? ' readonly' : ''}${el.required ? ' required' : ''}${hint ? ` about=${q(hint)}` : ''}${off}]`;
    }
    if (t === 'SELECT') {
      const opts = [...el.options];
      const chosen = opts.filter((o) => o.selected).map((o) => clip(o.text, 60)).join(', ');
      const list = opts.slice(0, 40).map((o) => q(clip(o.text, 60))).join(' | ');
      const hint = described(el);
      return `[${id} select ${q(labelOf(el))} selected=${q(chosen)} options: ${list}${opts.length > 40 ? ` | … ${opts.length - 40} more` : ''}${hint ? ` about=${q(hint)}` : ''}${el.required ? ' required' : ''}${off}]`;
    }
    const role = el.getAttribute('role') || (t === 'A' ? 'link' : (t === 'BUTTON' || t === 'SUMMARY') ? 'button' : 'clickable');
    const pictured = el.querySelector('img[alt]:not([alt=""]), [role=img][aria-label]');  // an icon-only control
    const text = clip(el.innerText || el.getAttribute('aria-label') || el.getAttribute('title')
      || (pictured && (pictured.getAttribute('alt') || pictured.getAttribute('aria-label'))) || el.value || '', 100);
    let to = '';
    const href = t === 'A' ? el.getAttribute('href') : '';
    if (href && !href.startsWith('javascript') && href !== '#') {
      try {  // one odd link must not cost the whole page its view
        const u = new URL(el.href, location.href);
        to = ' → ' + (u.origin === location.origin ? u.pathname + u.search + u.hash : u.href);
      } catch (e) { to = ' → ' + href; }
    }
    const state = ['aria-selected', 'aria-checked', 'aria-expanded', 'aria-pressed', 'aria-current']
      .filter((a) => el.getAttribute(a) && el.getAttribute(a) !== 'false').map((a) => ' ' + a.slice(5)).join('');
    const about = described(el), title = clip(el.getAttribute('title'), 200);
    const note = (about && about !== text ? ` about=${q(about)}` : '') + (title && title !== text && title !== about ? ` title=${q(title)}` : '');
    return `[${id} ${role} ${q(text)}${to}${state}${note}${off}]`;
  };
  const walk = (node) => {
    if (node.nodeType === Node.TEXT_NODE) { line += node.textContent; return; }
    if (node.nodeType !== Node.ELEMENT_NODE) return;
    const el = node, t = el.tagName;
    if (SKIP.has(t)) return;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;
    if (t === 'IFRAME' || t === 'FRAME' || t === 'OBJECT' || t === 'EMBED') {
      brk(); line += `[frame ${q(el.title || el.name || '')} src=${q(clip(el.getAttribute('src') || el.getAttribute('data') || '', 160))}]`; brk();
      return;
    }
    if (t === 'BR' || t === 'HR') { brk(); return; }
    // an image's text alternative can carry what the page says (a code, a status icon): shown, unless decorative
    if ((t === 'IMG' || (el.getAttribute('role') === 'img' && !clip(el.innerText, 10))) && !interactive(el)) {
      const alt = clip(el.getAttribute('alt') || el.getAttribute('aria-label') || el.getAttribute('title') || '', 160);
      if (alt) line += ` [image ${q(alt)}] `;
      return;
    }
    if (interactive(el)) {
      const control = ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'SUMMARY', 'LABEL'].includes(t);
      if (control || clip(el.innerText, 200).length <= 100) { line += ' ' + render(el) + ' '; return; }
      // a focusable or clickable box with long content (a scrollable message, a table area): number it, then
      // show all of its text, which a short label would cut off
      const id = n++;
      el.setAttribute('data-agent-ref', id);
      brk(); line += `[${id} ${el.getAttribute('role') || 'box'}] `;
    }
    if (t === 'TR') {
      flush(); inCell++;
      for (const cell of el.children) { walk(cell); line += ' |'; }
      inCell--; line = '| ' + line; flush();
      return;
    }
    const role = el.getAttribute('role');
    const block = !style.display.startsWith('inline') || /^H[1-6]$/.test(t) || t === 'LI';
    if (block) brk();
    if (/^H[1-6]$/.test(t) && !inCell) line += '#'.repeat(+t[1]) + ' ';
    if (t === 'LI' && !inCell) line += '- ';
    if (t === 'DIALOG' || role === 'dialog' || role === 'alertdialog' || el.getAttribute('aria-modal') === 'true') { line += '[dialog] '; }
    if (role === 'alert' || role === 'status') line += '[notice] ';
    line += generated(el, '::before');
    for (const child of el.childNodes) walk(child);
    line += generated(el, '::after');
    const about = described(el), title = clip(el.getAttribute('title'), 200);
    if (about) line += ` (${about})`;
    if (title && title !== about && title !== clip(el.innerText, 200)) line += ` (${title})`;
    if (el.shadowRoot) for (const child of el.shadowRoot.childNodes) walk(child);
    if (block) brk();
  };
  if (document.body) walk(document.body);
  flush();
  return { text: lines.join('\n'), next: n };
}
"""

# Marks the visible login form's user and password fields, for login().
MARK_LOGIN = r"""
() => {
  const visible = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  document.querySelectorAll('[data-agent-login]').forEach((e) => e.removeAttribute('data-agent-login'));
  const password = [...document.querySelectorAll('input[type=password]')].find(visible);
  if (!password) return false;
  const fields = [...(password.form || document).querySelectorAll('input')].filter((e) => visible(e)
    && !['password', 'hidden', 'checkbox', 'radio', 'submit', 'button', 'image', 'reset'].includes(e.type));
  const before = fields.filter((e) => e.compareDocumentPosition(password) & Node.DOCUMENT_POSITION_FOLLOWING);
  const user = before.length ? before[before.length - 1] : fields[0];
  password.setAttribute('data-agent-login', 'password');
  if (user) user.setAttribute('data-agent-login', 'user');
  return true;
}
"""

# Finds the visible selection field whose own label (without its options) matches, marks it, and lists its options.
FIND_SELECT = r"""
(label) => {
  const norm = (s) => String(s || '').replace(/[​-‍⁠﻿­]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
  const own = (el) => {
    if (el.labels && el.labels.length) {
      const copy = el.labels[0].cloneNode(true);
      copy.querySelectorAll('select,option,input,textarea,button').forEach((x) => x.remove());
      if (norm(copy.textContent)) return norm(copy.textContent);
    }
    return norm(el.getAttribute('aria-label') || el.getAttribute('title') || el.name || '');
  };
  document.querySelectorAll('[data-agent-pick]').forEach((e) => e.removeAttribute('data-agent-pick'));
  const want = norm(label);
  const shown = [...document.querySelectorAll('select')].filter((s) => { const r = s.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
  const hit = shown.find((s) => own(s) === want) || shown.find((s) => own(s).startsWith(want))
    || shown.find((s) => own(s).includes(want)) || shown.find((s) => own(s) && want.includes(own(s)));
  if (!hit) return null;
  hit.setAttribute('data-agent-pick', 'select');
  return { label: own(hit), disabled: hit.disabled, options: [...hit.options].map((o) => ({ text: o.text.replace(/\s+/g, ' ').trim(), value: o.value })) };
}
"""

# Marks the visible button or submit input whose text contains `text`.
FIND_BUTTON = r"""
(text) => {
  const norm = (s) => String(s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  document.querySelectorAll('[data-agent-pick=button]').forEach((e) => e.removeAttribute('data-agent-pick'));
  const want = norm(text);
  const hit = [...document.querySelectorAll('button,input[type=submit],input[type=button],[role=button]')].find((b) => {
    const r = b.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && !b.disabled && norm(b.innerText || b.value || b.getAttribute('aria-label')).includes(want);
  });
  if (!hit) return false;
  hit.setAttribute('data-agent-pick', 'button');
  return true;
}
"""

# Fetches a URL inside the page, with its cookies and through the browser's own network path.
FETCH = r"""
async (url) => {
  const r = await fetch(url, { credentials: 'include' });
  const bytes = new Uint8Array(await r.arrayBuffer());
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return { status: r.status, type: r.headers.get('content-type') || '', name: r.headers.get('content-disposition') || '',
           url: r.url, data: btoa(bin) };
}
"""


def plain_number(value) -> str:
    """A number as an HTML number field takes it: "4.321,09" becomes "4321.09"; a plain number stays as it is."""
    text = str(value).strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return text
    import calc  # the one place that reads German, English and tagged numbers
    amount = calc.dec(text)
    return format(amount, "f") if amount is not None else text


def short(text, limit=300) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text if len(text) <= limit else text[:limit] + "…"


WHY = re.compile(r"intercepts pointer events|element is not|is not visible|not enabled|not editable|not stable|"
                 r"outside of the viewport|detached", re.I)


def failure(error, limit=200) -> str:
    """A browser error with its reason kept: the call log ends in why the browser waited ("element is not editable",
    "<div class="overlay"> intercepts pointer events"), past where a plain cut would end (run #17's ERP gate)."""
    lines = str(error).splitlines()
    reasons = []
    for line in lines[1:]:
        line = line.strip(" -\t")
        if WHY.search(line) and line not in reasons:
            reasons.append(line)
    if not reasons:
        return short(error, limit)
    return short(f"{lines[0]} ({'; '.join(reasons[-2:])})", limit)


# per browser context (held, so its key is never reused): the Sites driving tabs in it, and how many tabs the code
# is opening itself right now (not popups of a page)
_SITES: dict[object, list["Site"]] = {}
_OPENING: dict[object, int] = {}
_LOGINS: dict[object, list] = {}  # per context: one login at a time, and when the last one was sent
_SEEN: dict[object, set[str]] = {}  # per context: the digits of every number its pages and documents showed

NOT_AMOUNTS = re.compile(r"\d{1,2}\.\d{1,2}\.\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}(?::\d{2})?")
AMOUNT = re.compile(r"(?<![A-Za-z\d_-])\d(?:[\d']|[.,\u00a0\u202f](?=\d))*(?![A-Za-z\d_])")


def amounts(text: str) -> list[str]:
    """The numbers in a text as bare digits ("1.234,56" and "1234.56" are both "123456"), without dates, times and
    the digits of identifiers (a material number): whole numbers of three digits or more, and numbers with a
    decimal separator of two digits or more ("0,92" is "092")."""
    text = NOT_AMOUNTS.sub(" ", str(text))
    found = []
    for token in AMOUNT.findall(text):
        digits = re.sub(r"\D", "", token)
        if re.search(r"[.,]", token) and len(digits) >= 2:
            found.append(digits)
        elif len(digits) >= 3:
            found.append(digits.lstrip("0") or "0")
    return found


# counts the browser's "invalid" events from now on: only those mean it kept a form back (run #16 review: a
# script-handled submit button in a form with an empty required field was reported as not sent)
INVALID_COUNTER = ("(b) => { const d = b.ownerDocument, w = d.defaultView; w.__agentInvalid = 0; if (!w.__agentListens) {"
                   " w.__agentListens = true; d.addEventListener('invalid', () => { w.__agentInvalid += 1; }, true); } }")


# counts the pointer leaving a held control from now on, and notes where the control was at that moment (it shrank
# or moved under the pointer): read in the capture phase, before the page's own handler can change it back
HOLD_WATCH = ("(e) => { const d = e.ownerDocument; e.__agentLeft = 0; e.__agentRect = null; if (!e.__agentWatch) {"
              " e.__agentWatch = true; for (const t of ['pointerleave', 'pointercancel']) d.addEventListener(t, (ev) => {"
              " if (ev.target !== e) return; e.__agentLeft += 1; const r = e.getBoundingClientRect();"
              " e.__agentRect = {x: r.x, y: r.y, w: r.width, h: r.height}; }, true); }"
              " const r = e.getBoundingClientRect(); return {x: r.x, y: r.y}; }")


class Site:
    """One website, driven in its own browser: the active tab, its numbered elements, dialogs, new tabs, downloads.

    Several Sites can share one browser (spawn()): each drives its own tabs, with the same login."""

    def __init__(self, access: dict, context, page, log=print):
        self.access = access
        self.id = access.get("siteId") or urlparse(access["url"]).hostname
        self.url = access["url"]
        self.credentials = access.get("credentials") or {}
        self.context, self.page, self.log = context, page, log
        self.tabs = [page]  # this Site's own tabs, oldest first
        self.acted_at = 0.0  # when this Site last acted on a page: a popup without an opener goes to the last one
        self.refs: dict[int, object] = {}  # element number -> the frame it is in
        self.events: list[str] = []  # dialogs, tabs and downloads since the last view
        self.downloads: list[Path] = []
        self.full_view, self.shown = "", 0
        self.trail: deque[str] = deque(maxlen=200)  # addresses viewed and text typed: what the agent searched for
        self.seen_pages: deque[str] = deque(maxlen=60)  # the text of the pages this Site's agent viewed, newest last
        self.secrets: set[str] = set()  # values that may go into a password field (a TAN the team just read)
        self.last_secret = ""  # the newest TAN: an earlier one may have expired
        self.warned: set[tuple] = set()  # warnings given once (a password field that may not be a login)
        sites = _SITES.setdefault(context, [])
        if not sites:  # one handler per browser hands each new tab to the Site that opened it
            # whether the code is opening a tab is read when the event arrives, before the opening call returns
            context.on("page", lambda tab, key=context: _hand_over(key, tab, _OPENING.get(key, 0) > 0))
        sites.append(self)
        self._watch(page)

    async def spawn(self) -> "Site":
        """Another Site on this website in a new tab of the same browser (same login), for an agent working in
        parallel: it starts at the website's start address."""
        page = await self._open_page()
        return Site(self.access, self.context, page, self.log)

    async def _open_page(self):
        key = self.context
        _OPENING[key] = _OPENING.get(key, 0) + 1
        try:
            return await self.context.new_page()
        finally:
            _OPENING[key] -= 1

    # --- events -------------------------------------------------------------------------------------------------

    def _watch(self, page):
        page.on("dialog", self._dialog)
        page.on("download", self._download)

    def _adopt(self, page):
        self._watch(page)
        self.tabs.append(page)
        self.page = page
        self.events.append("A new tab opened and is now the active tab.")

    async def _dialog(self, dialog):
        # Browser dialogs block the page until answered. The agents only trigger them on purpose (the final
        # confirmation of a bid is one), so they are accepted and reported in the next view. A prompt that asks for a
        # value (a TAN, a confirmation word) gets it: an empty answer would let the step pass without it.
        try:
            if dialog.type == "prompt":
                answer = self._prompt_answer(dialog.message, dialog.default_value)
                if answer is None:
                    self.events.append(f"A browser prompt asked {short(dialog.message)!r}; nothing fitting was known, "
                                       "so it was dismissed: do the step again once you know the answer.")
                    await dialog.dismiss()
                    return
                shown = "the TAN" if answer in self.secrets else repr(answer)
                self.events.append(f"A browser prompt asked {short(dialog.message)!r}; it was answered with {shown}.")
                await dialog.accept(answer)
                return
            self.events.append(f"A browser {dialog.type} dialog said {short(dialog.message)!r}; it was accepted.")
            await dialog.accept()
        except Exception:
            pass

    def _prompt_answer(self, message: str, default: str) -> str | None:
        """What a prompt asks for: the TAN just read (it asks for a TAN, PIN or code), the word it quotes to type
        ("type „VERBINDLICH“ to confirm"), or its own preset value."""
        quoted = re.findall(r"[„\"»“‚']([^\"“”«»‘’']{2,40})[\"“”«»‘’']", message)
        if re.search(r"\bTAN\b|\bPIN\b|code", message, re.I):
            if self.last_secret:
                return self.last_secret
            # no TAN read yet: a confirmation word may still be asked for, but never a quoted reference or number
            return quoted[0].strip() if len(quoted) == 1 and not re.search(r"\d", quoted[0]) else None
        if len(quoted) == 1:
            return quoted[0].strip()
        return default or None

    async def _download(self, download):
        target = Path(tempfile.mkdtemp()) / (download.suggested_filename or "download")
        try:
            await download.save_as(target)
        except Exception as error:
            self.events.append(f"A download failed: {short(error)}")
            return
        self.downloads.append(target)
        self.events.append(f"Downloaded {target.name!r}: read it with read_document(download={len(self.downloads)}).")

    async def nudge(self):
        """A sign of life for a page that logs out when idle, without any request (a reload of a signing step could
        reissue a TAN or reset the form): a mouse move inside the page."""
        try:
            page = await self._active()
            await page.evaluate("() => { for (const t of [document, window]) t.dispatchEvent(new MouseEvent("
                                "'mousemove', {clientX: 1, clientY: 1, bubbles: true})); }")
        except Exception:
            pass

    def remember(self, text: str):
        """Notes the numbers a page or document showed (a recorded value must have been on one of them) and the
        page's text for this agent."""
        _SEEN.setdefault(self.context, set()).update(amounts(text))
        self.seen_pages.append(text)

    def has_seen(self, text: str) -> bool:
        """Whether a page or document this agent viewed showed `text` (case and spacing aside)."""
        want = re.sub(r"\s+", " ", str(text)).strip().casefold()
        return bool(want) and any(want in re.sub(r"\s+", " ", page).casefold() for page in self.seen_pages)

    def unseen(self, text: str) -> list[str]:
        """The numbers in `text` that no page or document of this website has shown."""
        seen = _SEEN.get(self.context, set())
        return [digits for digits in amounts(text) if digits not in seen]

    async def keep_alive(self):
        """Loads the current address in the background with this browser's cookies, leaving the page untouched: a
        website that logs out after a short idle time keeps the session while its agent waits."""
        try:
            await self.context.request.get(self.page.url, timeout=8000)
        except Exception:
            pass

    async def fresh_tab(self, url: str | None = None) -> str:
        """A new tab in this website's browser (same login), made the active one: away from a page that is stuck."""
        page = await self._open_page()
        self._watch(page)
        self.tabs.append(page)
        self.page = page
        return await self.goto(url or self.url)

    def _open_tabs(self) -> list:
        self.tabs = [page for page in self.tabs if not page.is_closed()]
        return self.tabs

    async def _active(self):
        if self.page.is_closed():
            open_pages = self._open_tabs()
            if open_pages:
                self.page = open_pages[-1]
            else:
                self.page = await self._open_page()
                self._watch(self.page)
                self.tabs.append(self.page)
            self.events.append("The tab closed; switched to the previous tab.")
        return self.page

    async def _settle(self):
        page = await self._active()
        for state, timeout in (("domcontentloaded", 10000), ("networkidle", 1500)):
            try:
                await page.wait_for_load_state(state, timeout=timeout)
            except Exception:
                pass
        await asyncio.sleep(0.2)

    # --- the view -----------------------------------------------------------------------------------------------

    async def view(self) -> str:
        """The page as text, from the top; long pages are cut, more() shows the rest."""
        page = await self._active()
        self.refs, number, parts = {}, 1, []
        for frame in page.frames:
            try:
                rendered = await asyncio.wait_for(frame.evaluate(RENDER, number), FRAME_SECONDS)
            except asyncio.TimeoutError:
                # a page that stops answering scripts must not stop the agent: say so, it can reload or go elsewhere
                parts.append(f"--- {'the page' if frame is page.main_frame else 'frame ' + short(frame.url, 120)} "
                             "does not respond: reload() it, or goto() its address again ---")
                continue
            except Exception:
                continue
            for ref in range(number, rendered["next"]):
                self.refs[ref] = frame
            number = rendered["next"]
            if frame is page.main_frame:
                parts.insert(0, rendered["text"])
            elif rendered["text"].strip():
                parts.append(f"--- inside frame {frame.name or ''} {short(frame.url, 120)} ---\n{rendered['text']}")
            else:
                parts.append(f"--- frame {short(frame.url, 120)} shows nothing here: open it with goto() to read it ---")
        try:
            title = await asyncio.wait_for(page.title(), 5)
        except Exception:
            title = ""
        tabs = self._open_tabs()
        header = f"URL: {page.url}\nTitle: {title}\n"
        if len(tabs) > 1:
            header += "Tabs: " + " | ".join(f"{i}{' (active)' if p is page else ''}: {short(p.url, 80)}"
                                            for i, p in enumerate(tabs)) + "\n"
        if self.events:
            header += "".join(f"Event: {event}\n" for event in self.events)
            self.events = []
        self.full_view = header + "\n" + "\n\n".join(parts)
        self.trail.append(unquote_plus(page.url))
        self.remember(self.full_view)
        return self._part(0)

    def _part(self, start: int) -> str:
        end = start + MAX_VIEW
        self.shown = end
        text = self.full_view[start:end]
        if start:
            text = f"[page text from character {start}]\n" + text
        if end < len(self.full_view):
            text += f"\n[… {len(self.full_view) - end} more characters: more() shows them, find(text) searches them]"
        return text

    async def more(self) -> str:
        if self.shown >= len(self.full_view):
            return "That was the end of the page."
        return self._part(self.shown)

    async def find(self, text: str) -> str:
        """Lines of the current page containing `text` (case-insensitive), with the line after each."""
        lines = self.full_view.splitlines()
        hits = [i for i, line in enumerate(lines) if text.lower() in line.lower()]
        if not hits:
            return f"{text!r} is not on the current page (as of the last view)."
        return "\n".join("\n".join(lines[i:i + 2]) for i in hits[:40])

    # --- actions ------------------------------------------------------------------------------------------------

    def _element(self, ref):
        frame = self.refs.get(int(ref))
        if frame is None:
            raise LookupError(f"There is no element [{ref}] on the page as last viewed; look at the current view.")
        return frame.locator(f'[data-agent-ref="{int(ref)}"]').first

    @staticmethod
    async def _read(element) -> str:
        try:
            return await element.input_value(timeout=2000)
        except Exception:
            return ""

    async def _make_it_stick(self, element, value: str, before: str) -> str:
        """Some forms take only real keystrokes and drop a value set by script (run #11's form fields read empty
        after a fill). A dropped value (the field empty, or as before) is typed key by key; a split field (a TAN in
        several boxes, a length limit) is reported, not forced. Returns a problem, or ""."""
        await asyncio.sleep(0.15)
        held = await self._read(element)
        if held == value:
            return ""  # kept as given, also when the field held it already (run #16 reported that as split)
        if held.strip() and len(held) < len(value) and value.startswith(held):
            return f"holds {held!r}: the value may span several fields; fill each part"
        if held.strip() and held != before:
            return ""  # kept, possibly reformatted by the form
        limit = await element.evaluate("(e) => e.maxLength", timeout=2000)
        if isinstance(limit, int) and 0 < limit < len(value):
            return f"holds {held!r}: the value may span several fields; fill each part"
        try:
            await element.click(timeout=3000)
            page = await self._active()
            await page.keyboard.press("ControlOrMeta+a")
            await page.keyboard.type(value, delay=20)
            await element.evaluate("(e) => { e.dispatchEvent(new Event('change', {bubbles: true})); e.blur(); }",
                                   timeout=2000)
        except Exception:
            # in run #16 a popup in a fresh tab covered the field: the value never landed and the click was blocked
            return (f"reads {held!r}, not {value!r}: something covers the field or the page changed (a popup or "
                    "dialog to close first?); look at the page")
        await asyncio.sleep(0.15)
        held = await self._read(element)
        return "" if held.strip() and held != before else f"does not keep {value!r} (it reads {held!r}): look at the page"

    async def _select(self, element, value):
        """Chooses an option by its label or value, else the option choose_option() finds (a material number
        followed by a description, the next larger size, a 'none' option)."""
        for how in ("label", "value"):
            try:
                await element.select_option(**{how: str(value)}, timeout=3000)
                return
            except Exception:
                pass
        options = await element.evaluate("(e) => [...e.options].map((o) => ({text: o.text.replace(/\\s+/g, ' ').trim(), "
                                         "value: o.value}))", timeout=3000)
        option = choose_option(options, value)
        if option is None:
            offered = ", ".join(o["text"] for o in options if o["value"])
            raise LookupError(f"no option {value!r}; the field offers: {short(offered, 300)}")
        await element.select_option(value=option["value"], timeout=3000)

    async def click(self, ref) -> str:
        element = self._element(ref)
        self.acted_at = time.time()
        try:
            present = await element.count()
        except Exception:
            present = 1
        if not present:  # only view() hands out refs: an element that left the page never gets this one back
            return f"[{ref}] is no longer on the page (it changed since the last view):\n\n" + await self.view()
        blocked = await self._unsendable(element)
        if blocked:  # count the browser's own validation: a page script may handle the click and move on instead
            try:
                await element.evaluate(INVALID_COUNTER, timeout=2000)
            except Exception:
                blocked = ""
        try:
            # short: a popup that covers the page (they reappear on many pages) should cost seconds, not a minute
            await element.click(timeout=2500)
        except Exception as error:
            try:  # covered by an overlay or off screen: a DOM click still reaches the element's handler
                await element.evaluate("(e) => e.click()", timeout=3000)
            except Exception:
                return f"Could not click [{ref}]: {failure(error, 300)}\n\n" + await self.view()
        await self._settle()
        if blocked:
            try:
                blocked = blocked if await element.evaluate(
                    "(b) => b.ownerDocument.defaultView.__agentInvalid || 0", timeout=1500) else ""
            except Exception:
                blocked = ""  # the button is gone or the page moved on: the form was sent
        if blocked:  # the browser kept the form back: say which fields it wants
            self.log(f"[{self.id}] the form was not sent: {blocked}")
            return f"The form was not sent: the browser requires these fields first: {blocked}\n\n" + await self.view()
        return await self.view()

    async def _unsendable(self, element) -> str:
        """For a button that sends a form the browser checks: the fields that keep it from being sent (without
        firing the page's own invalid handlers), else ""."""
        try:
            return await element.evaluate(
                "(b) => { const t = (b.type || '').toLowerCase(); const f = b.form;"
                " if (!f || !(b.tagName === 'BUTTON' ? t !== 'button' && t !== 'reset' : t === 'submit' || t === 'image')"
                " || f.noValidate || b.formNoValidate) return '';"
                " return [...f.elements].filter((e) => e.willValidate && !e.validity.valid).map((e) =>"
                " `[${e.getAttribute('data-agent-ref') || '?'}] ${((e.labels && e.labels[0] && e.labels[0].innerText) ||"
                " e.name || '').trim().slice(0, 60)} (${e.validationMessage})`).join('; '); }", timeout=3000)
        except Exception:
            return ""

    async def fill(self, fields: list[dict]) -> str:
        """Several inputs at once: text is typed, selects choose the option by label or value, checkboxes take
        true/false."""
        self.acted_at = time.time()
        problems = []
        for field in fields:
            ref, value = field.get("ref"), field.get("value")
            try:
                element = self._element(ref)
                # a field inside a collapsed section is not editable until the section is open
                kind = await element.evaluate("(e) => { for (let d = e.closest('details'); d; d = d.parentElement && "
                                              "d.parentElement.closest('details')) d.open = true; "
                                              "return e.tagName === 'SELECT' ? 'select' : (e.type || '').toLowerCase(); }",
                                              timeout=4000)
                if kind == "password" and str(value) not in self.secrets and ("fill", ref, self.page.url) not in self.warned:
                    # in runs #5 and #7 search words went into an expired session's login form unnoticed
                    self.warned.add(("fill", ref, self.page.url))
                    problems.append(f"[{ref}] is a password field: if this is a login form, your session has "
                                    "probably expired: call login() to log in again. Nothing was filled there; if it "
                                    "is not a login form, fill it again")
                    continue
                if kind == "select":
                    await self._select(element, value)
                elif kind in ("checkbox", "radio"):
                    want = value if isinstance(value, bool) else str(value).lower() in ("true", "1", "yes", "ja", "on")
                    try:
                        await element.set_checked(want, timeout=3000)
                    except Exception:
                        await element.set_checked(want, force=True, timeout=3000)
                else:
                    before = await self._read(element)
                    # a number field takes "4321.09", never the German "4.321,09" (another form may use one)
                    await element.fill(plain_number(value) if kind == "number" else str(value), timeout=4000)
                    self.trail.append(str(value))
                    if kind in ("", "text", "search", "email", "tel", "url", "textarea") and str(value):
                        problem = await self._make_it_stick(element, str(value), before)
                        if problem:
                            problems.append(f"[{ref}] {problem}")
            except Exception as error:
                problems.append(f"[{ref}]: {failure(error)}")
        await self._settle()
        report = "Filled." if not problems else "Problems: " + "; ".join(problems)
        return report + "\n\n" + await self.view()

    async def type(self, ref, text: str, enter: bool = False) -> str:
        element = self._element(ref)
        self.acted_at = time.time()
        # only text fields take typing: on a button the fallback click below would press it (in run #5 that
        # silently omitted bid positions)
        kind = await element.evaluate("(e) => ({tag: e.tagName, type: (e.type || '').toLowerCase(), "
                                      "editable: e.isContentEditable})", timeout=4000)
        if kind["tag"] == "INPUT" and kind["type"] == "password" and text not in self.secrets \
                and ("type", ref, self.page.url) not in self.warned:
            self.warned.add(("type", ref, self.page.url))
            # an agent typing a search into a password field had been logged out without noticing (run #6)
            return ("[" + str(ref) + "] is a password field: this is a login form, so your session has probably "
                    "expired. Call login() to log in again, then go back to where you were. Nothing was typed.\n\n"
                    + await self.view())
        typable = kind["editable"] or kind["tag"] == "TEXTAREA" or (kind["tag"] == "INPUT" and kind["type"] in (
            "", "text", "search", "email", "number", "tel", "url", "date", "datetime-local", "time"))
        if not typable:
            return (f"[{ref}] is not a text field ({kind['tag'].lower()} {kind['type']}): nothing was typed or "
                    "clicked. Use click() for buttons and links, fill() for selects and checkboxes.\n\n"
                    + await self.view())
        self.trail.append(text)
        if kind["tag"] == "INPUT" and kind["type"] == "number":
            text = plain_number(text)
        try:
            await element.fill(text, timeout=4000)
        except Exception:
            await element.click(timeout=3000)
            page = await self._active()
            await page.keyboard.press("ControlOrMeta+a")  # replace what the field held, do not append to it
            await page.keyboard.type(text)
        if enter:
            await element.press("Enter")
        await self._settle()
        return await self.view()

    async def drag(self, ref, dx: float | None = None, dy: float = 0, to=None) -> str:
        """Drags an element with the mouse, such as a slider's handle or a range input; without dx, all the way to
        the right end of its track; with `to`, onto the centre of another element (a piece into its slot)."""
        self.acted_at = time.time()
        element = self._element(ref)
        page = await self._active()
        # onto another element only: a "to" naming the element itself, or given with a distance, is a slider drag
        # (run #13: the model passed to=<the slider> with dx, and the slider never moved)
        if to is not None and int(to) != int(ref) and dx is None:
            await element.scroll_into_view_if_needed(timeout=3000)
            start, target = await element.bounding_box(), await self._element(to).bounding_box()
            if not start or not target:
                return "An element is not on screen.\n\n" + await self.view()
            x, y = start["x"] + start["width"] / 2, start["y"] + start["height"] / 2
            end_x, end_y = target["x"] + target["width"] / 2, target["y"] + target["height"] / 2
            await page.mouse.move(x, y)
            await page.mouse.down()
            for step in range(1, 21):
                await page.mouse.move(x + (end_x - x) * step / 20, y + (end_y - y) * step / 20)
                await asyncio.sleep(0.02)
            await page.mouse.up()
            await self._settle()
            return await self.view()
        await element.scroll_into_view_if_needed(timeout=3000)
        box = await element.bounding_box()
        if not box:
            return "The element is not on screen.\n\n" + await self.view()
        track = box
        if box["width"] < 60:  # a small handle: its track is the parent
            track = await element.evaluate("(e) => { const r = e.parentElement.getBoundingClientRect(); "
                                           "return {x: r.x, y: r.y, width: r.width, height: r.height}; }",
                                           timeout=4000)
        slider = await element.evaluate("(e) => e.type === 'range' ? {min: +e.min || 0, max: +(e.max || 100), "
                                        "value: +e.value} : null", timeout=4000)
        if slider:
            share = (slider["value"] - slider["min"]) / max(1e-9, slider["max"] - slider["min"])
            x = box["x"] + 8 + (box["width"] - 16) * share
        else:
            x = box["x"] + min(10, box["width"] / 2)
        y = box["y"] + box["height"] / 2
        end_x = x + dx if dx is not None else track["x"] + track["width"] + 30
        await page.mouse.move(x, y)
        await page.mouse.down()
        for step in range(1, 21):
            await page.mouse.move(x + (end_x - x) * step / 20, y + dy * step / 20)
            await asyncio.sleep(0.02)
        await page.mouse.up()
        await self._settle()
        report = ""
        if slider:  # say where the slider ended up, so the model knows whether the drag worked
            try:
                state = await element.evaluate("(e) => ({value: e.value, max: e.max || '100'})", timeout=2000)
                report = f"The slider is now at {state['value']} of {state['max']}.\n\n"
            except Exception:
                report = "The slider was replaced by the page (it may have unlocked).\n\n"
        return report + await self.view()

    async def hold(self, ref, seconds: float = 3.0) -> str:
        """Presses the mouse on an element and keeps it down (a "press and hold" confirmation), then releases."""
        self.acted_at = time.time()
        element = self._element(ref)
        page = await self._active()
        await element.scroll_into_view_if_needed(timeout=3000)
        box = await element.bounding_box()
        if not box:
            return "The element is not on screen.\n\n" + await self.view()
        seconds = max(0.5, min(float(seconds), 15.0))
        point = (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        for attempt in range(3):
            origin = await element.evaluate(HOLD_WATCH, timeout=2000)
            offset = (box["x"] - origin["x"], box["y"] - origin["y"])  # a frame's place in the page
            await page.mouse.move(*point)
            await page.mouse.down()
            await asyncio.sleep(0.4)
            # a control that relabels itself when pressed can shrink away from the pointer, and the page then ends
            # the hold (the run #16 code failed every hold of a teammate's eval this way): let go and press again in
            # the middle of where the control was while pressed, which lies inside it in both shapes
            state = await element.evaluate("(e) => ({left: e.__agentLeft || 0, rect: e.__agentRect})", timeout=2000)
            if state["left"] and state["rect"] and attempt < 2:
                await page.mouse.up()
                rect = state["rect"]
                point = (rect["x"] + rect["w"] / 2 + offset[0], rect["y"] + rect["h"] / 2 + offset[1])
                box = await element.bounding_box() or box
                await asyncio.sleep(0.2)
                continue
            await asyncio.sleep(seconds - 0.4)
            await page.mouse.up()
            break
        await self._settle()
        return await self.view()

    KEYS = {name.lower(): name for name in ("Enter", "Escape", "Tab", "Backspace", "Delete", "Space", "Home", "End",
                                              "PageUp", "PageDown", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
                                              "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12")}

    async def scroll(self, ref=None) -> str:
        """Scrolls a box to its end (terms that must be read before a checkbox unlocks): the given element or the
        boxes around it, or else every scrollable box of the page and the page itself. The view already shows all
        text, so this is for unlocking, not reading."""
        self.acted_at = time.time()
        page = await self._active()
        script = ("(start) => { const boxes = []; let e = start;"
                  " while (e) { if (e.scrollHeight > e.clientHeight + 1) boxes.push(e); e = e.parentElement; }"
                  " if (!start) document.querySelectorAll('*').forEach((x) => { const o = getComputedStyle(x).overflowY;"
                  " if ((o === 'auto' || o === 'scroll') && x.scrollHeight > x.clientHeight + 1) boxes.push(x); });"
                  " for (const b of boxes) { b.scrollTop = b.scrollHeight; b.dispatchEvent(new Event('scroll')); }"
                  " window.scrollTo(0, document.body.scrollHeight); return boxes.length; }")
        if ref is not None:
            element = self._element(ref)
            try:  # real wheel events first: some pages only count those
                box = await element.bounding_box()
                if box:
                    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    for _ in range(10):
                        await page.mouse.wheel(0, 2000)
            except Exception:
                pass
            await element.evaluate(script, timeout=4000)
        else:
            for frame in page.frames:
                try:
                    await frame.evaluate(script, None)
                except Exception:
                    continue
        await self._settle()
        return await self.view()

    async def press(self, key: str, ref=None) -> str:
        self.acted_at = time.time()
        # key names are case-sensitive for the browser: "TAB" or "enter" would press nothing
        key = "+".join(self.KEYS.get(part.lower(), {"esc": "Escape", "return": "Enter", "down": "ArrowDown",
                                                     "up": "ArrowUp"}.get(part.lower(), part))
                       for part in str(key).split("+"))
        if ref is not None:
            await self._element(ref).press(key, timeout=4000)
        else:
            await (await self._active()).keyboard.press(key)
        await self._settle()
        return await self.view()

    async def goto(self, url: str) -> str:
        page = await self._active()
        target = urljoin(page.url if page.url.startswith("http") else self.url, url)
        host = urlparse(target).hostname
        # a made-up address on another host costs a minute of retries (run #5): only this website's hosts, and hosts
        # the page links to, are opened
        if host and host not in (urlparse(self.url).hostname, urlparse(page.url).hostname) \
                and host not in self.full_view:
            return (f"{host} is not this website ({urlparse(self.url).hostname}) and the page does not link to it: "
                    "use a path on this website such as /…, or a link from the page.\n\n" + await self.view())
        for attempt in range(3):  # flaky error pages: retry a server error a few times
            try:
                response = await page.goto(target, wait_until="domcontentloaded", timeout=20000)
                if response is None or response.status < 500:
                    break
                self.log(f"[{self.id}] HTTP {response.status} on {target}, retrying")
            except Exception as error:
                self.log(f"[{self.id}] {short(error, 120)}, retrying")
                if "ERR_NAME_NOT_RESOLVED" in str(error) or "ERR_TUNNEL_CONNECTION_FAILED" in str(error):
                    break  # an address that does not exist does not come back
            await asyncio.sleep(1.5 * (attempt + 1))
        await self._settle()
        return await self.view()

    async def reload(self) -> str:
        page = await self._active()
        try:
            await page.reload(wait_until="domcontentloaded", timeout=20000)
        except Exception:
            pass
        await self._settle()
        return await self.view()

    async def back(self) -> str:
        page = await self._active()
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
        await self._settle()
        return await self.view()

    async def switch_tab(self, index: int) -> str:
        tabs = self._open_tabs()
        if not 0 <= int(index) < len(tabs):
            return f"There is no tab {index}; there are {len(tabs)}."
        self.page = tabs[int(index)]
        await self.page.bring_to_front()
        return await self.view()

    async def login(self) -> str:
        """Fills this website's username and password into the visible login form and submits it. Agents in tabs of
        one browser share its login: one logs in at a time, and a tab that meets the login form just after another
        tab logged in only reloads."""
        lock = _LOGINS.setdefault(self.context, [asyncio.Lock(), 0.0])
        async with lock[0]:
            if time.time() - lock[1] < 20:
                view = await self.reload()
                if "password-input" not in view:
                    return "Logged in already (another tab of this website just did).\n\n" + view
            report = await self._login()
            if report.startswith("Submitted"):
                lock[1] = time.time()
            return report

    async def _login(self) -> str:
        page = await self._active()
        for frame in page.frames:
            try:
                found = await frame.evaluate(MARK_LOGIN)
            except Exception:
                continue
            if not found:
                continue
            problems = []
            user = frame.locator('[data-agent-login="user"]')
            password = frame.locator('[data-agent-login="password"]')
            for field, value, what in ((user, self.credentials.get("username", ""), "user name"),
                                       (password, self.credentials.get("password", ""), "password")):
                try:
                    if not await field.count():
                        continue
                    # a preset or locked field (a fixed client or user name) is left as it is
                    if not await field.is_enabled(timeout=2000) or not await field.is_editable(timeout=2000):
                        problems.append(f"the {what} field is locked and was left as it is")
                        continue
                    await field.fill(str(value), timeout=5000)
                except Exception as error:
                    problems.append(f"the {what} field could not be filled ({short(error, 80)})")
            try:
                await password.press("Enter", timeout=5000)
            except Exception as error:
                problems.append(f"Enter could not be pressed ({short(error, 80)})")
            await self._settle()
            note = ("; ".join(problems) + ": finish the login yourself.\n\n") if problems else ""
            return "Submitted the login form. " + note + "\n\n" + await self.view()
        # a login in two steps: the user name first, the password on the next page
        for frame in page.frames:
            try:
                user = frame.locator("input[autocomplete=username], input[type=email], input[name*=user i], "
                                     "input[name*=login i], input[id*=user i], input[name*=benutz i]").first
                if not await user.count() or not await user.is_visible(timeout=1000) \
                        or not await user.is_editable(timeout=1000):
                    continue
                await user.fill(str(self.credentials.get("username", "")), timeout=5000)
                await user.press("Enter", timeout=5000)
                for _ in range(20):  # the password field appears on the next page or in place
                    await asyncio.sleep(0.5)
                    password = (await self._active()).locator("input[type=password]").first
                    if await password.count() and await password.is_visible(timeout=500):
                        await password.fill(str(self.credentials.get("password", "")), timeout=5000)
                        await password.press("Enter", timeout=5000)
                        await self._settle()
                        return "Submitted the login in two steps.\n\n" + await self.view()
                return "Entered the user name; no password field followed.\n\n" + await self.view()
            except Exception:
                continue
        return "There is no login form (password field) on this page.\n\n" + await self.view()

    async def _pick(self, script: str, argument: str):
        """The first frame where `script` finds and marks an element: (frame, what it reported)."""
        page = await self._active()
        for frame in page.frames:
            try:
                found = await frame.evaluate(script, argument)
            except Exception:
                continue
            if found:
                return frame, found
        return None, None

    async def configure(self, steps: list[dict], apply: str = "") -> str:
        """Choices that unlock one another (a configurator): each step selects a value in the field with that label,
        then clicks the `apply` button (except after the last step, or where a step says "apply": false) and waits
        for the next field to open. Stops at the first step that cannot be done and says why."""
        done: list[str] = []
        skipped: list[str] = []
        applied = False
        for number, step in enumerate(steps):
            field, value = str(step.get("field", "")), str(step.get("value", ""))
            frame, found = None, None
            # after an apply the next field can take a moment to unlock; before any apply a missing field is missing
            for _ in range(12 if applied else 3):
                frame, found = await self._pick(FIND_SELECT, field)
                if found and not found["disabled"]:
                    break
                await asyncio.sleep(0.5)
            so_far = "; ".join(done) or "nothing yet"
            if not found:  # a field this form does not have: skipped, the chain goes on
                done.append(f"(no field {field!r}: skipped)")
                skipped.append(field)
                continue
            if found["disabled"]:
                return (f"The field {found['label']!r} is still locked (chosen so far: {so_far}); the choice before "
                        "it may need applying.\n\n" + await self.view())
            option = choose_option(found["options"], value)
            if option is None:
                offered = ", ".join(o["text"] for o in found["options"] if o["value"])
                return (f"{found['label']!r} offers no {value!r}; it offers: {offered} (chosen so far: {so_far})."
                        "\n\n" + await self.view())
            await frame.locator('[data-agent-pick="select"]').first.select_option(value=option["value"], timeout=4000)
            done.append(f"{found['label']} = {option['text']}")
            last = number == len(steps) - 1
            if apply and step.get("apply", not last):
                button_frame, ok = await self._pick(FIND_BUTTON, apply)
                if not ok:
                    return f"No button {apply!r} to apply {done[-1]} (chosen so far: {'; '.join(done)}).\n\n" + \
                        await self.view()
                button = button_frame.locator('[data-agent-pick="button"]').first
                try:
                    await button.click(timeout=2500)
                except Exception:
                    try:
                        await button.evaluate("(e) => e.click()", timeout=3000)
                    except Exception:
                        pass  # the click started a reload that took the button away: the wait below covers it
                applied = True
                await self._settle()
        if skipped and len(skipped) == len(steps):
            return ("Nothing was chosen: this page has no selection list (<select>) labelled "
                    + ", ".join(repr(f) for f in skipped) + ". If the form uses other controls (a list that opens on "
                    "click, option tiles, a search field), set each value with click() or fill().\n\n"
                    + await self.view())
        return "Chosen: " + "; ".join(done) + "\n\n" + await self.view()

    async def screenshot(self) -> dict:
        """What the screen shows, as an image for the model, with the text view."""
        page = await self._active()
        image = await page.screenshot(type="jpeg", quality=70)
        return {"text": "The screenshot follows as an image.", "image": base64.b64encode(image).decode()}

    async def wait(self, seconds: float) -> str:
        await asyncio.sleep(max(0.0, min(float(seconds), 30.0)))
        return await self.view()

    # --- documents ----------------------------------------------------------------------------------------------

    async def read_document(self, ref=None, url: str | None = None, download: int | None = None) -> str:
        """The text of a document the model picked: a linked file, a frame's source, or a download."""
        if download:
            path = self.downloads[int(download) - 1]
            text = extract(path.read_bytes(), path.name)
            self.remember(text)
            return f"Document {path.name}:\n" + text
        page = await self._active()
        frame = page.main_frame
        if ref is not None:
            element = self._element(ref)
            frame = self.refs[int(ref)]
            url = await element.evaluate("(e) => e.href || e.src || e.data || e.getAttribute('href') || ''",
                                         timeout=5000)
            if not url or url.startswith("javascript"):
                # a button that starts a download: click it and read what arrives
                before = len(self.downloads)
                await self.click(ref)
                for _ in range(20):
                    if len(self.downloads) > before:
                        return await self.read_document(download=len(self.downloads))
                    await asyncio.sleep(0.5)
                return "The element has no link and clicking it downloaded nothing.\n\n" + await self.view()
        if not url:
            return "Give the element number, a url, or a download number."
        url = urljoin(frame.url, url)
        try:
            fetched = await frame.evaluate(FETCH, url)
        except Exception:
            fetched = await page.main_frame.evaluate(FETCH, url)
        data = base64.b64decode(fetched["data"])
        if "html" in fetched["type"] and "attachment" not in fetched["name"].lower():
            # a page's server HTML is not what the browser shows (scripts fill in and change it): open it instead
            return f"{url} is a web page, so it was opened in the browser:\n\n" + await self.goto(url)
        name = re.sub(r'.*filename\*?=(?:UTF-8\'\')?"?([^";]+)"?.*', r"\1", fetched["name"]) or url
        text = extract(data, name, fetched["type"])
        self.remember(text)
        return f"Document {short(name, 120)} (HTTP {fetched['status']}, {fetched['type']}):\n" + text


async def _hand_over(key, page, code_opened: bool):
    """A new tab in a browser that Sites share goes to the Site whose tab opened it, or (a link without an opener)
    to the Site that acted last. Tabs the code opens itself (fresh_tab, spawn) are taken by the Site that asked."""
    sites = _SITES.get(key) or []
    try:
        opener = await page.opener()
    except Exception:
        opener = None
    if opener is None and code_opened:
        return
    owner = next((site for site in sites if opener is not None and opener in site.tabs), None)
    if owner is None and sites:
        owner = max(sites, key=lambda site: site.acted_at)
    if owner is not None:
        owner._adopt(page)


INVISIBLE = re.compile("[\u200b-\u200d\u2060\ufeff\u00ad]")


def _number(text) -> float | None:
    """The first number of a text; "1.250" and "1,250" with thousands groups are 1250 (sizes are whole numbers)."""
    text = str(text)
    grouped = re.search(r"(?<![\d.,])-?[1-9]\d{0,2}([.,])\d{3}(?:\1\d{3})*(?![\d.,])", text)
    if grouped:
        return float(re.sub(r"[.,]", "", grouped.group()))
    match = re.search(r"-?\d+(?:[.,]\d+)?", text)
    return float(match.group().replace(",", ".")) if match else None


NONE_WORD = re.compile(r"(kein\w*|ohne|none|no|n/?a|nicht\s+\w+|[-–—]|keine?\s+\w+)", re.I)
NEGATION = re.compile(r"\b(ohne|kein\w*|none|without|nicht|no)\b", re.I)


def choose_option(options: list[dict], value) -> dict | None:
    """The option meant by `value`: the same text or value; else the only option whose text starts with it or
    contains it (e.g. a material number followed by a description); for a "none" word, the one option that says
    none; else, for a number, the smallest offered number not below it (the next nominal size). None when nothing
    fits."""
    def norm(text) -> str:
        return re.sub(r"\s+", " ", INVISIBLE.sub("", str(text))).strip().lower()

    want = norm(value)
    real = [option for option in options if option.get("value") not in ("", None)]
    exact = [o for o in real if want in (norm(o["text"]), norm(o["value"]))]
    if exact:
        return exact[0]
    # the same text with its thousands groups written another way ("1.250 mm" and "1250 mm")
    def ungrouped(text):
        return re.sub(r"(?<=\d)[.,](?=\d{3}(?!\d))", "", norm(text))
    same = [o for o in real if ungrouped(o["text"]) == ungrouped(value)]
    if len(same) == 1:
        return same[0]
    # "none" is worded differently by each source ("keine", "ohne …", "none", "-"): the one option saying so
    if NONE_WORD.fullmatch(want):
        negative = [o for o in real if NEGATION.search(norm(o["text"]))]
        if len(negative) == 1:
            return negative[0]
    for test in (lambda o: norm(o["text"]).startswith(want), lambda o: want in norm(o["text"])):
        hits = [o for o in real if want and test(o)]
        if len(hits) == 1:
            return hits[0]
    wanted = _number(value)
    if wanted is not None and re.fullmatch(r"-?[\d.,]+\s*\w{0,3}", want):
        above = [(n, o) for o in real if (n := _number(o["text"])) is not None and n >= wanted]
        if above:
            number, option = min(above, key=lambda pair: pair[0])
            # far above what was asked is not "the next size": a unit or a misread number, not a match
            return option if wanted <= 0 or number <= wanted * 10 else None
    return None


def configure_tool(site: "Site") -> list[tuple[dict, object]]:
    """The tool for configurators, where each choice opens the next field only once it is applied."""
    return [(_tool(
        "configure", "Make a chain of choices in a configurator in one go: for each step, the field's label as shown "
                     "in the view and the value to choose; the code selects it, clicks the apply button (its label "
                     "in `apply`) and waits for the next field to open, then the next step. The last step (usually "
                     "the material) is not applied unless it says \"apply\": true. A number that is not offered "
                     "exactly picks the next larger offered size. Returns what was chosen and the page.",
        {"steps": {"type": "array", "items": {"type": "object", "properties": {
            "field": {"type": "string", "description": "The field's label, e.g. as in [12 select \"Label\" ...]"},
            "value": {"type": "string", "description": "The option to choose (its text or the start of it)"},
            "apply": {"type": "boolean"}}, "required": ["field", "value"]}},
         "apply": {"type": "string", "description": "The label of the button that applies a choice, if the form "
                                                    "has one"}}, ["steps"]), site.configure)]


def extract(data: bytes, name: str = "", content_type: str = "") -> str:
    """Readable text from a PDF, a ZIP (each file inside), a Word file, HTML or plain text."""
    text = INVISIBLE.sub("", _extract(data, name.lower(), content_type.lower(), depth=0))
    return text if len(text) <= MAX_DOCUMENT else text[:MAX_DOCUMENT] + f"\n[… {len(text) - MAX_DOCUMENT} more characters]"


def _extract(data: bytes, name: str, content_type: str, depth: int) -> str:
    if data[:4] == b"%PDF":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(f"--- page {i} ---\n{page.extract_text() or ''}" for i, page in enumerate(reader.pages, 1))
    if data[:2] == b"PK":
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = archive.namelist()
        if "word/document.xml" in names:
            xml = archive.read("word/document.xml").decode("utf-8", "replace")
            return _strip_xml(xml.replace("</w:p>", "\n").replace("</w:tc>", " | "))
        if depth > 1:
            return f"(archive with {len(names)} files)"
        parts = [f"Archive with {len(names)} files: {', '.join(names)}"]
        for member in names:
            if not member.endswith("/"):
                parts.append(f"=== {member} ===\n" + _extract(archive.read(member), member.lower(), "", depth + 1))
        return "\n".join(parts)
    for encoding in ("utf-8", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", "replace")
    if "html" in content_type or name.endswith((".html", ".htm")) or re.search(r"<(html|body|table|div)\b", text[:2000], re.I):
        return html_text(text)
    if name.endswith(".xml") or text.lstrip().startswith("<?xml"):
        return _strip_xml(text)
    return text


def _strip_xml(xml: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table", "ul", "ol"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "tr":
            self.parts.append("\n| ")
        elif tag in ("td", "th"):
            pass
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    text = "".join(parser.parts)
    return "\n".join(re.sub(r"[ \t ]+", " ", line).strip() for line in text.splitlines() if line.strip())


def toolbox(site: Site) -> list[tuple[dict, object]]:
    """The browser tools every agent gets, as (OpenAI tool schema, coroutine) pairs."""
    ref = {"type": "integer", "description": "The element's number in the page view, e.g. 12 for [12 button ...]"}
    number = {"type": "integer"}  # the same element number: described once, at click and fill
    return [
        (_tool("view", "Show the current page again (it may have changed by itself).", {}), site.view),
        (_tool("more", "Show the next part of a long page.", {}), site.more),
        (_tool("find", "Search the current page's full text for a word or number; returns the matching lines.",
               {"text": {"type": "string"}}, ["text"]), site.find),
        (_tool("click", "Click an element: a link, button, tab, row, checkbox, ...", {"ref": ref}, ["ref"]), site.click),
        (_tool("fill", "Enter values into several form fields at once. Text inputs get the text, selects the option "
                       "label, checkboxes and radios true or false. Does not submit.",
               {"fields": {"type": "array", "items": {"type": "object", "properties": {
                   "ref": ref, "value": {"type": ["string", "number", "boolean"]}}, "required": ["ref", "value"]}}},
               ["fields"]), site.fill),
        (_tool("type", "Type text into one input, optionally pressing Enter afterwards (to search, for example).",
               {"ref": number, "text": {"type": "string"}, "enter": {"type": "boolean"}}, ["ref", "text"]), site.type),
        (_tool("drag", "Drag an element with the mouse: a slider handle or range input (without dx: all the way to "
                       "the right end), any draggable item by dx/dy pixels, or onto another element (to).",
               {"ref": number, "dx": {"type": "number"}, "dy": {"type": "number"},
                "to": {"type": "integer", "description": "Only to drop it on ANOTHER element; leave out for sliders"}},
               ["ref"]), site.drag),
        (_tool("scroll", "Scroll a box (or every box) to its end: terms you must scroll through before a checkbox "
                         "unlocks. Not needed for reading.", {"ref": number}), site.scroll),
        (_tool("hold", "Press and hold the mouse on an element for some seconds (a hold-to-confirm control).",
               {"ref": number, "seconds": {"type": "number"}}, ["ref"]), site.hold),
        (_tool("press", "Press a key (Enter, Escape, Tab, F4, ArrowDown, ...), on an element or the page.",
               {"key": {"type": "string"}, "ref": number}, ["key"]), site.press),
        (_tool("goto", "Open a URL or a path on this website.", {"url": {"type": "string"}}, ["url"]), site.goto),
        (_tool("reload", "Reload the page, e.g. after an error page.", {}), site.reload),
        (_tool("back", "Browser back. Never use it inside a multi-step form: it clears the later steps.", {}), site.back),
        (_tool("switch_tab", "Make another open tab the active one (numbers as in the Tabs line).",
               {"index": {"type": "integer"}}, ["index"]), site.switch_tab),
        (_tool("fresh_tab", "Continue in a new tab on this website (the login carries over), at its start page or a "
                            "given address: when a page is stuck, does not respond or keeps timing out.",
               {"url": {"type": "string"}}), site.fresh_tab),
        (_tool("login", "Log in with this website's credentials (a login page, an expired session).", {}), site.login),
        (_tool("read_document", "Read a file as text: a link to a PDF, ZIP, Word, CSV or text file, a frame whose "
                                "content is not shown, or a downloaded file. Not for web pages: open those with "
                                "goto or click. Give the element number, a url, or the download number.",
               {"ref": number, "url": {"type": "string"}, "download": {"type": "integer"}}), site.read_document),
        (_tool("screenshot", "Look at the screen as an image, when the text view leaves something unclear (a value "
                             "that seems hidden, a layout, a code shown as a picture).", {}), site.screenshot),
        (_tool("wait", "Wait some seconds (at most 30), then show the page.", {"seconds": {"type": "number"}},
               ["seconds"]), site.wait),
    ]


def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, **({"required": required} if required else {})}}}

