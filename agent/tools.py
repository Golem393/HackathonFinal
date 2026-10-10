"""The browser tools the model drives: each one acts on the page the model chose and returns what is there now.

Nothing here knows the websites. `observe` lists a page's text and its interactive elements with a number each;
the model picks the numbers, URLs and texts.
"""
TEXT_LIMIT = 6000  # characters of page text per observation; `read` pages through the rest

# Numbers the visible interactive elements of one frame (data-ref) and returns them with the frame's text.
SNAPSHOT = """(start) => {
  let n = start
  const lines = []
  const short = (s) => (s || '').trim().replace(/\\s+/g, ' ').slice(0, 80)
  const shown = (e) => {
    const box = e.getBoundingClientRect(), style = getComputedStyle(e)
    return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none'
  }
  document.querySelectorAll('[data-ref]').forEach((e) => e.removeAttribute('data-ref'))
  const selector = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=tab],' +
    '[role=menuitem],[role=option],[role=checkbox],[onclick],[contenteditable=true]'
  for (const e of document.querySelectorAll(selector)) {
    if (e.type === 'hidden' || !shown(e)) continue
    e.setAttribute('data-ref', ++n)
    const tag = e.tagName.toLowerCase()
    let line = `[${n}] ${tag}`
    if (tag === 'input') line += ` ${e.type}`
    const label = short([...(e.labels || [])].map((l) => l.innerText).join(' ')) || short(e.getAttribute('aria-label'))
      || short(e.placeholder) || short(e.name) || short(e.title)
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      if (label) line += ` "${label}"`
      if (tag === 'select') line += ` options: ${[...e.options].map((o) => short(o.text)).join(' | ')}`
      if (e.type === 'checkbox' || e.type === 'radio') line += e.checked ? ' (checked)' : ' (unchecked)'
      else if (e.type !== 'password' && e.value) line += ` = "${short(e.value)}"`
    } else {
      line += ` "${short(e.innerText) || label}"`
      if (tag === 'a') line += ` -> ${e.getAttribute('href').slice(0, 120)}`
    }
    if (e.disabled) line += ' (disabled)'
    lines.push(line)
  }
  return { text: document.body ? document.body.innerText : '', lines, next: n }
}"""

TOOLS = [
    {"name": "open", "description": "Go to a URL in the current tab.",
     "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "click", "description": "Click the element with this number.",
     "parameters": {"type": "object", "properties": {"ref": {"type": "integer"}}, "required": ["ref"]}},
    {"name": "fill", "description": "Replace the value of the input or textarea with this number; `enter` presses "
                                    "Enter afterwards.",
     "parameters": {"type": "object", "properties": {"ref": {"type": "integer"}, "text": {"type": "string"},
                                                     "enter": {"type": "boolean"}}, "required": ["ref", "text"]}},
    {"name": "select", "description": "Choose the option with this visible text in the select with this number.",
     "parameters": {"type": "object", "properties": {"ref": {"type": "integer"}, "option": {"type": "string"}},
                    "required": ["ref", "option"]}},
    {"name": "press", "description": "Press a key on the page, e.g. Enter, Escape, F4.",
     "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}},
    {"name": "read", "description": "Read the current page again, with its text from character `offset` on.",
     "parameters": {"type": "object", "properties": {"offset": {"type": "integer"}}}},
    {"name": "finish", "description": "End the run. Call it only once the job is done or cannot go on. `answer` is "
                                      "the answer object, only when the answer is handed in through the API.",
     "parameters": {"type": "object", "properties": {"summary": {"type": "string"}, "answer": {"type": "object"}},
                    "required": ["summary"]}},
]
SCHEMAS = [{"type": "function", "function": tool} for tool in TOOLS]


class Browser:
    """One browser context as the model sees it: the newest open tab, its frames, and the numbered elements."""

    def __init__(self, page):
        self.context, self.refs = page.context, {}

    @property
    def page(self):
        return [page for page in self.context.pages if not page.is_closed()][-1]  # a popup becomes the current tab

    async def observe(self, offset: int = 0) -> str:
        page = self.page
        try:
            await page.wait_for_load_state("networkidle", timeout=3000)
        except Exception:
            pass  # a page that keeps polling is read as it is
        self.refs, texts, lines, count = {}, [], [], 0
        for frame in page.frames:
            try:
                shot = await frame.evaluate(SNAPSHOT, count)
            except Exception:
                continue  # a frame that went away or holds no document
            for ref in range(count + 1, shot["next"] + 1):
                self.refs[ref] = frame
            count = shot["next"]
            if shot["text"].strip():
                texts.append(shot["text"] if frame is page.main_frame else f"--- frame {frame.url}\n{shot['text']}")
            lines += shot["lines"]
        text = "\n".join(texts)
        more = f"\n... {len(text) - offset - TEXT_LIMIT} more characters: read(offset={offset + TEXT_LIMIT})" \
            if len(text) > offset + TEXT_LIMIT else ""
        return (f"URL: {page.url}\nTitle: {await page.title()}\n\n{text[offset:offset + TEXT_LIMIT]}{more}\n\n"
                "Elements:\n" + "\n".join(lines))

    def element(self, ref: int):
        if ref not in self.refs:
            raise ValueError(f"No element {ref} on the page as last read")
        return self.refs[ref].locator(f'[data-ref="{ref}"]')

    async def call(self, name: str, args: dict) -> str:
        """Run one tool call of the model and return the page as it is afterwards, or the error."""
        try:
            if name == "open":
                await self.page.goto(args["url"], wait_until="domcontentloaded")
            elif name == "click":
                await self.element(args["ref"]).click(timeout=5000)
            elif name == "fill":
                await self.element(args["ref"]).fill(args["text"], timeout=5000)
                if args.get("enter"):
                    await self.element(args["ref"]).press("Enter")
            elif name == "select":
                await self.element(args["ref"]).select_option(label=args["option"], timeout=5000)
            elif name == "press":
                await self.page.keyboard.press(args["key"])
            elif name != "read":
                return f"Unknown tool {name}"
            return await self.observe(args.get("offset") or 0)
        except Exception as error:
            return f"Error: {str(error)[:500]}"
