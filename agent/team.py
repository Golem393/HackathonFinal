"""The investigation: one agent per website records facts in a shared ledger, then a solver decides which facts the
rules apply to and hands them to the calculation.

    brief -> plan (model) -> investigators, one per website, in parallel (model-driven browsing) -> ledger
          -> solver (model decides) -> calc.compute (code computes) -> answer
"""
import asyncio
import difflib
import json
import re
import time
import unicodedata

import calc
import prompts
import web
from llm import Agent, tool

STRING, NUMBER = {"type": "string"}, {"type": ["string", "number", "null"]}
NULLABLE_STRING = {"type": ["string", "null"]}
KILOGRAMS = {**NUMBER, "description": "In kilograms: convert grams (1250 g is 1.25)"}


class Ledger:
    """Everything the investigators recorded, with where, when and by which agent; the one place facts come from."""

    def __init__(self):
        self.entries: list[dict] = []
        self.latest_inputs: dict | None = None  # the last calculation inputs a gap check produced
        # per website, the missing facts a gap check handed to an agent of their own: (fact, its task, agent name)
        self.handed: dict[str, list[tuple]] = {}

    def add(self, site: str, url: str, topic: str, facts, source: str = "", agent: str | None = None) -> str:
        self.entries.append({"n": len(self.entries) + 1, "at": time.strftime("%H:%M:%S", time.gmtime()),
                             "site": site, "agent": agent or site, "page": url, "topic": topic,
                             "source": source, "facts": facts})
        return f"Recorded as #{len(self.entries)}."

    def digest(self, exclude_agent: str | None = None, limit: int = 12000) -> str:
        """One line per record of the other agents, oldest first: what the team knows, at a glance. Long enough per
        record to carry its identifiers (a requirement's catalogue group sits after its attributes); when it is too
        long in all, the newest records are kept."""
        lines = [f"#{entry['n']} [{entry['agent']}] {entry['topic']}: "
                 f"{web.short(json.dumps(entry['facts'], ensure_ascii=False), 500)}"
                 for entry in self.entries if entry["agent"] != exclude_agent]
        text = "\n".join(lines)
        return ("[… older records: read_notes()]\n" + text[-limit:]) if len(text) > limit else text

    def for_solver(self) -> str:
        """Every record for the solver, compactly: the order (n) and the source stay, the recording clock does not."""
        def compact(entry):
            entry = {key: value for key, value in entry.items() if key != "at"}
            if entry.get("agent") == entry.get("site"):
                entry.pop("agent")
            return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
        return "\n".join(compact(entry) for entry in self.entries) or "Nothing recorded yet."

    def text(self, topic: str | None = None, exclude_agent: str | None = None, limit: int = 200000) -> str:
        def matches(entry, words) -> bool:
            body = json.dumps(entry, ensure_ascii=False).lower()
            return all(word in body for word in words)
        candidates = [entry for entry in self.entries if entry["agent"] != exclude_agent]
        entries = [entry for entry in candidates if not topic or matches(entry, [topic.lower()])]
        if topic and not entries:  # "price condition HZ" finds the records naming all of its words
            words = [word for word in re.findall(r"[\w-]{3,}", topic.lower())]
            entries = [entry for entry in candidates if words and matches(entry, words)]
        text = "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries)
        return text[-limit:] if text else "Nothing recorded yet."


def record_tools(site: web.Site, ledger: Ledger, agent: str | None = None) -> list:
    agent = agent or site.id
    refused: dict[str, int] = {}

    async def record(topic: str, facts, source: str = "") -> str:
        # values copied from a page were on it: in run #8 an agent pressed to keep working recorded a price it had
        # never opened, and the bid used it
        text = json.dumps(facts, ensure_ascii=False)
        unseen = site.unseen(text) if hasattr(site, "unseen") else []
        checked = len(web.amounts(text))
        # several values no page showed, or the only values a decimal no page showed (run #10: a rate of 0.92 for
        # a message that gives another rate)
        decimals = [token for token in re.findall(r"\d+[.,]\d+", web.NOT_AMOUNTS.sub(" ", text))]
        lone = unseen and len(unseen) == checked and decimals
        if (len(unseen) >= 2 and 2 * len(unseen) >= checked) or lone:
            key = " ".join(sorted(unseen))
            refused[key] = refused.get(key, 0) + 1
            if refused[key] <= 2:
                return ("Nothing was recorded: these values are on no page of this website you have seen: "
                        f"{', '.join(unseen[:8])}. Open the page that shows them (the record's own view) and copy them "
                        "from there; record only what a page or document showed you, and other agents' facts not "
                        "at all.")
            entry = ledger.add(site.id, site.page.url, topic, facts, source, agent)
            ledger.entries[-1]["unverified"] = unseen[:12]
            return entry + " It is marked unverified: its values were not seen on any page."
        return ledger.add(site.id, site.page.url, topic, facts, source, agent)

    async def read_notes(topic: str = "") -> str:
        return ledger.text(topic or None, exclude_agent=agent, limit=30000)

    async def wait_for_notes(topic: str, seconds: float = 45) -> str:
        """Until another agent records something containing `topic` (at most a minute): those records."""
        until = time.time() + max(5.0, min(float(seconds), 60.0))
        alive = time.time()
        while time.time() < until:
            found = ledger.text(topic, exclude_agent=agent, limit=30000)
            if found != "Nothing recorded yet.":
                return found
            if time.time() - alive > 20:  # waiting must not let the website's session expire
                await site.keep_alive()
                alive = time.time()
            await asyncio.sleep(3)
        return (f"Nothing about {topic!r} has been recorded yet. Keep the website's session alive (view the page), "
                "then work on with what you have or wait again.")

    return [
        (tool("record", "Save facts for the team: copied exactly, with units, dates and identifiers.", {
            "topic": {"type": "string", "description": "What the facts are about, e.g. tender, position, "
                                                       "clarification, requirement, specification revision, mail, "
                                                       "material, price condition, stock"},
            "facts": {"anyOf": [{"type": "object"}, {"type": "array", "items": {}}, {"type": "string"}],
                      "description": "The facts, e.g. an object or a list of table rows"},
            "source": {"type": "string", "description": "Where you saw them: page, document, message"}},
              ["topic", "facts"]), record),
        (tool("read_notes", "Read what the agents on the other websites have recorded so far, optionally only "
                            "records containing a word.", {"topic": {"type": "string"}}), read_notes),
        (tool("wait_for_notes", "Wait until the agents on the other websites have recorded something your work "
                                "depends on (records containing `topic`, e.g. \"requirement\"), at most a minute, "
                                "then show those records. Use it instead of finishing while you are waiting for "
                                "their facts.", {"topic": {"type": "string"}, "seconds": {"type": "number"}},
              ["topic"]), wait_for_notes),
    ]


def fold(text: str) -> str:
    """For comparing words: NFC, case-insensitive, as typed."""
    return unicodedata.normalize("NFC", str(text)).casefold()


def transliterated(text: str) -> str:
    """The same word as typed without umlauts and ß (Prüfbericht -> pruefbericht)."""
    folded = fold(text)
    for umlaut, plain in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        folded = folded.replace(umlaut, plain)
    return folded


DATE_KEYS = re.compile(r"date|datum|sent|gesendet|received|empfangen|zeit|time", re.I)
VALIDITY_KEYS = re.compile(r"valid|gültig|gueltig|\bab\b|\bbis\b|\bfrom\b|\bto\b|window|zeitraum", re.I)  # not when sent


def record_days(facts) -> list[str]:
    """The calendar days in a record's date fields (keys named like a date), not dates inside its text."""
    days = []
    if isinstance(facts, dict):
        for key, value in facts.items():
            if isinstance(value, (dict, list)):
                days += record_days(value)
            elif DATE_KEYS.search(str(key)) and not VALIDITY_KEYS.search(str(key)) and calc.day(value):
                days.append(calc.day(value))
    elif isinstance(facts, list):
        for value in facts:
            days += record_days(value)
    return days


class Topics:
    """A mail agent's checklist: each topic is closed only with a recorded message that can apply (the exact
    reference, dated no later than the scenario date) or as absent once its search trail shows the word searched.
    Code checks what it can, because in runs #6 and #7 agents finished with look-alike or future-dated messages,
    transliterated search words and topics never searched. Each check refuses a topic at most twice, so a site
    the checks do not fit cannot trap the agent."""

    def __init__(self, topics: list[dict], reference: str, scenario_date: str, site: web.Site, ledger: Ledger,
                 agent: str | None = None):
        self.topics = {str(t.get("topic", "")).strip(): t for t in topics if str(t.get("topic", "")).strip()}
        self.closed: dict[str, str] = {}
        self.refused: dict[tuple, int] = {}
        self.warned: set[tuple] = set()
        self.reference, self.scenario_day = reference, calc.day(scenario_date)
        self.site, self.ledger, self.agent = site, ledger, agent or site.id
        self.trail_start = len(site.trail) if hasattr(site, "trail") else 0

    def _topic(self, name: str) -> str | None:
        want = fold(name.strip())
        return next((t for t in self.topics if fold(t) == want), None) or \
            next((t for t in self.topics if want and (want in fold(t) or fold(t) in want)), None)

    def status(self) -> str:
        return "; ".join(f"{t}: {self.closed.get(t, 'OPEN')}" for t in self.topics)

    def open(self) -> list[str]:
        return [t for t in self.topics if t not in self.closed]

    def _refuse(self, name: str, kind: str, text: str) -> str | None:
        """The refusal, or None once this check refused this topic twice (it may not fit this website)."""
        self.refused[(name, kind)] = self.refused.get((name, kind), 0) + 1
        return text if self.refused[(name, kind)] <= (3 if kind == "opened" else 2) else None

    def _close(self, name: str, how: str) -> str:
        self.closed[name] = how
        return f"Closed {name}. Open topics: {', '.join(self.open()) or 'none: call finish'}."

    def _searched(self, word: str) -> tuple[int, bool]:
        """How often the trail shows the word searched (distinct addresses, or typed searches), and whether it shows
        only a transliterated spelling."""
        trail = list(getattr(self.site, "trail", []))[self.trail_start:]
        want, plain = fold(word), transliterated(word)
        # one search shown on several pages or opened from its results is one search: page and item parameters
        # are left out when telling searches apart
        addresses = {re.sub(r"[?&](page|seite|p|offset|start|sort|order|id|msg|message|item)=[^&#]*", "", entry)
                     for entry in trail if entry.startswith("http") and want in fold(entry)}
        typed = [entry for entry in trail if not entry.startswith("http") and want in fold(entry)]
        wrong = plain != want and any(plain in fold(entry) for entry in trail)
        return max(len(addresses), len(typed)), wrong

    def _suffixed(self, text: str) -> bool:
        """The tender reference appears in the text, and every time with something added (another tender)."""
        if not self.reference:
            return False
        occurrences = [match.end() for match in re.finditer(re.escape(self.reference), text)]
        return bool(occurrences) and all(re.match(r"[-_/.]?[A-Za-z0-9]", text[end:]) for end in occurrences)

    async def close(self, topic: str, outcome: str, reference_as_written: str = "", date: str = "", sender: str = "",
                    subject: str = "", folders_searched: list | None = None) -> str:
        name = self._topic(topic)
        if name is None:
            return f"{topic!r} is not one of your topics: {', '.join(self.topics)}."
        if outcome == "absent":
            count, wrong = self._searched(name)
            if count < 2:
                problem = self._refuse(name, "absent", (
                    f"The brief spells it {name!r}: your searches used another spelling (the search matches words "
                    f"literally). Search {name!r} exactly, with the exact reference, in every folder." if wrong else
                    f"Your searches do not show {name!r} searched in each folder yet: search the exact reference "
                    f"with {name!r} in every folder of the mailbox (and a shorter form of the word), then close it."))
                if problem:
                    return problem
            folders = ", ".join(str(f) for f in folders_searched or []) or "the folders"
            return self._close(name, f"absent (searched {folders})")
        # the message must have been on a page this agent viewed (its result list or the message itself): run #10
        # closed two topics with records written without opening them, one with a wrong exchange rate
        if hasattr(self.site, "has_seen") and subject and not self.site.has_seen(subject) \
                and not self.site.has_seen(name):
            problem = self._refuse(name, "opened", (
                f"No page you have viewed shows {subject!r}: search the topic, open the message itself and record "
                "what it says, then close the topic. Never record a message you have not opened."))
            if problem:
                return problem
        mine = [e for e in self.ledger.entries if e.get("agent", e["site"]) == self.agent]
        words = [fold(w) for w in (subject, name) if w]
        matching = [e for e in mine if any(w in fold(json.dumps(e, ensure_ascii=False)) for w in words)]
        if not matching:
            return "Record the message (sender, date, subject, reference, its original text) with record() first."
        # the record of this message: the one with the date given, else the latest (a decoy with the same subject
        # can be recorded too)
        day = calc.day(date)
        narrowed = [e for e in matching if day and day in record_days(e["facts"])] or matching[-1:]
        written = str(reference_as_written or subject)
        recorded = json.dumps([e["facts"] for e in narrowed], ensure_ascii=False)
        if self.reference and (self._suffixed(written) or self._suffixed(recorded)
                               or (written and self.reference not in written)):
            problem = self._refuse(name, "reference", (
                f"{written or 'That message'!r} is not exactly the tender reference {self.reference}: a reference "
                "with something added or another number is another tender, and its messages never apply. Open the "
                "message for exactly this reference (other results, other folders), record it, then close the topic."))
            if problem:
                return problem
        # a reference copied with a typo makes the solver reject the message (run #8): have it checked once
        near = sorted({token for token in re.findall(r"[A-Z][A-Z0-9]*-[\dA-Z-]*\d", written + " " + recorded)
                       if self.reference and self.reference not in token  # a longer identifier containing it
                       and difflib.SequenceMatcher(None, token, self.reference).ratio() >= 0.85})
        if near and (name, "near") not in self.warned:
            self.warned.add((name, "near"))
            return (f"Your record writes the reference as {', '.join(near)}, not {self.reference}. Look at the "
                    "message again: if it shows exactly the tender reference, record it again exactly as shown "
                    "(subject included), then close the topic; if it shows another reference, it is another tender.")
        days = [day] if day else record_days([e["facts"] for e in narrowed])
        if self.scenario_day and any(d > self.scenario_day for d in days):
            problem = self._refuse(name, "date", (
                f"That message is dated after the scenario date {self.scenario_day}: it never applies. Open the "
                "latest message on this topic dated no later than the scenario date (other results, other folders), "
                "record it, then close the topic."))
            if problem:
                return problem
        if not days and (name, "date") not in self.warned:
            self.warned.add((name, "date"))
            return ("Give the message's date as its header shows it (e.g. DD.MM.YYYY HH:MM), and record it with the "
                    "message if it is not in your record.")
        expected = str(self.topics[name].get("sender") or "").strip().lower()
        address = re.search(r"([\w.+-]+)@([\w.-]+)", sender or "")
        local, domain = (address.group(1).lower(), address.group(2).lower().rstrip(".")) if address else ("", "")
        if expected and address and local != expected and (name, sender) not in self.warned:
            self.warned.add((name, sender))
            return (f"The brief authorizes {expected}@ for {name}; {sender} is another sender, whose message does not "
                    "apply. Look for the message from the authorized sender; if this one is from it after all, close "
                    "the topic again with the same sender.")
        own = self.mailbox_domain()
        if own and domain and domain != own and (name, "domain") not in self.warned:
            # the same name at another domain, or a quoted or forwarded approval, is another sender
            self.warned.add((name, "domain"))
            return (f"{sender} is not at the bidder's mailbox domain {own}: the same name at another domain, or a "
                    f"message quoted or forwarded by someone else, is another sender. Open the message "
                    f"{expected or local}@{own} sent; if this one is it after all, close the topic again.")
        return self._close(name, f"{subject or 'message'} of {date or days[0] if days else '?'}")

    def mailbox_domain(self) -> str:
        """The bidder's own mail domain: from the mailbox login when it is an address, else the domain most of this
        mailbox's recorded senders share."""
        login = str((getattr(self.site, "credentials", None) or {}).get("username") or "")
        if "@" in login:
            return login.rsplit("@", 1)[1].lower()
        domains: dict[str, int] = {}
        for entry in self.ledger.entries:
            if entry["site"] == self.site.id:
                for found in re.findall(r"[\w.+-]+@([\w.-]+\w)", json.dumps(entry["facts"], ensure_ascii=False)):
                    domains[found.lower()] = domains.get(found.lower(), 0) + 1
        return max(domains, key=domains.get) if len(domains) > 0 and max(domains.values()) >= 2 else ""

    async def check(self, args: dict) -> str | None:
        """finish() is refused while a topic is open."""
        if self.open():
            return (f"Not yet: these topics are still open: {', '.join(self.open())}. For each: search the exact "
                    "reference with the topic word in every folder, open the latest applicable message, record it, "
                    f"then close_topic(). Checklist: {self.status()}")
        return None

    def tools(self) -> list:
        return [(tool("close_topic", "Close one of your mail topics: with the message you recorded for it (outcome "
                                     "\"recorded\"), or as \"absent\" after searching every folder found none.", {
            "topic": {"type": "string"}, "outcome": {"type": "string", "enum": ["recorded", "absent"]},
            "subject": {"type": "string", "description": "The message's subject, exactly"},
            "reference_as_written": {"type": "string", "description": "The tender reference exactly as the message "
                                                                      "writes it"},
            "date": {"type": "string", "description": "The message's date and time as its header shows it"},
            "sender": {"type": "string", "description": "The sender's address"},
            "folders_searched": {"type": "array", "items": {"type": "string"}}},
            ["topic", "outcome"]), self.close)]


# the calculation inputs a mail topic can give (the brief's shared rules), to route a missing input to its topic
FEEDS = ["discount", "condition_rules", "metal_index", "technical_release", "packaging", "delivery", "fx",
         "setup_pool", "project_bonus", "other"]
# the shared rules list authorized subjects as "Subject/sender"
SUBJECT_SENDER = re.compile(r"(?<![\w/])([A-ZÄÖÜ][\wäöüß]{3,})/([a-z][a-z0-9._-]*)\b")
MAX_TOPICS = 12


# the rules also name messages by their subject: "the latest Zinsblatt message ... from x@"
SUBJECT_MESSAGE = re.compile(r"(?<![\w-])([A-ZÄÖÜ][\wäöüß]{4,})\s+(?:message|messages|Nachricht|Nachrichten|mail)\b"
                             r"(?:[^.@]{0,80}?\b([a-z][a-z0-9._-]*)@)?")


def plan_topics(topics: list[dict], brief: str, reference: str = "") -> list[dict]:
    """The plan's mail topics in the brief's own spelling (a transliterated word finds nothing in a literal search),
    plus each "Subject/sender" pair and each "<Subject> message" the brief names that the plan left out; never the
    tender reference itself (every search has it already); at most MAX_TOPICS. In run #9 the plan listed the
    reference as a topic and left out two subjects the rules name."""
    tokens = re.findall(r"[^\W\d_][\w-]*", brief)
    by_plain = {}
    for token in tokens:
        by_plain.setdefault(transliterated(token), token)
    result, seen = [], set()
    for topic in topics or []:
        word = str(topic.get("topic", "")).strip()
        if not word:
            continue
        if fold(word) not in fold(brief) and transliterated(word) in by_plain:
            print(f"[team] mail topic {word!r} is spelled {by_plain[transliterated(word)]!r} in the brief", flush=True)
            word = by_plain[transliterated(word)]
        if fold(word) in seen or (reference and fold(reference) in fold(word) and topic.get("feeds") != "discount"):
            continue  # the reference alone is a topic only for the approval, whose subject the brief does not name
        seen.add(fold(word))
        result.append({**topic, "topic": word})
    for match in list(SUBJECT_SENDER.finditer(brief)) + list(SUBJECT_MESSAGE.finditer(brief)):
        word, sender = match.group(1), match.group(2) or ""
        if fold(word) not in seen:
            seen.add(fold(word))
            print(f"[team] mail topic {word!r} (from {sender or '?'}@) added from the brief", flush=True)
            result.append({"topic": word, "sender": sender, "gives": "", "feeds": "other"})
    return result[:MAX_TOPICS]


PLAN_SCHEMA = {
    "tender_reference": {"type": "string", "description": "The tender reference, exactly as in the brief"},
    "bidder_company": STRING, "bidder_vat_id": STRING,
    "scenario_date": {"type": "string", "description": "ISO 8601"},
    "sites": {"type": "array", "items": {"type": "object", "properties": {
        "site_id": STRING, "kind": {"type": "string", "enum": ["tender", "specification", "erp", "mail", "other"]},
        "also": {"type": "array", "items": {"type": "string", "enum": ["tender", "specification", "erp", "mail"]},
                 "description": "Other kinds of facts the brief says this website holds as well (e.g. a "
                                "specification inside the materials system, approval messages in a portal), else empty"},
        "holds": {"type": "string", "description": "What the brief says this website holds"}},
        "required": ["site_id", "kind", "also", "holds"]}},
    "tan_site_id": {"type": "string", "description": "The website where the brief says the signing TAN arrives"},
    "mail_topics": {"type": "array", "description": "Every kind of mailbox message the brief's rules use, one entry "
                                                    "each: the discount approval, condition rules, price indices and "
                                                    "every authorized subject the brief lists",
                    "items": {"type": "object", "properties": {
                        "topic": {"type": "string", "description": "The subject or topic word to search for, exactly "
                                                                   "as the brief spells it (umlauts included)"},
                        "sender": {"type": "string", "description": "The authorized sender's local part (before @) "
                                                                    "if the brief names one, else empty"},
                        "gives": {"type": "string", "description": "What the rules take from it, in a few words"},
                        "feeds": {"type": "string", "enum": FEEDS, "description": "Which calculation input it gives"}},
                        "required": ["topic", "sender", "gives", "feeds"]}},
}


async def plan(task: dict, deadline: float) -> dict:
    """The model reads the brief: the identifiers, and which website is which. Code checks the reference."""
    sites = [{"site_id": access.get("siteId"), "url": access["url"]} for access in task["access"]]
    message = f"# The brief\n{task['brief']}\n\n# The websites\n{json.dumps(sites)}\n\nCall finish with the plan."
    for _ in range(2):
        result = await Agent("plan", prompts.PLAN, [], deadline, finish=PLAN_SCHEMA, effort="low").run(
            message, max_steps=3) or {}
        result["mail_topics"] = plan_topics(result.get("mail_topics") or [], task["brief"],
                                            result.get("tender_reference", ""))
        mail = any(site.get("kind") == "mail" for site in result.get("sites") or [])
        if result.get("tender_reference") and result["tender_reference"] in task["brief"] \
                and (result["mail_topics"] or not mail):
            return result
        message += ("\n\nThe tender reference must appear in the brief exactly as you write it, and every kind of "
                    "mailbox message the rules use must be listed in mail_topics.")
    return result


ENTER_SECONDS = 60.0  # opening a website (its first page and the login) may not hold an agent up longer


async def enter(site: web.Site) -> str:
    """The website's start page, logged in with the run's credentials if it shows a login form. A start that hangs
    (run #15: one agent never got past it, silently) is given up for a fresh tab, and the model takes over."""
    try:
        return await asyncio.wait_for(_enter(site), ENTER_SECONDS)
    except Exception as error:
        print(f"[{site.id}] opening the website hung or failed ({error!r}): a fresh tab", flush=True)
        try:
            return await asyncio.wait_for(_fresh(site), ENTER_SECONDS)
        except Exception as again:
            print(f"[{site.id}] the fresh tab failed too ({again!r})", flush=True)
            return "The website did not load. Try goto() with its address, or fresh_tab()."


async def _fresh(site: web.Site) -> str:
    """A fresh tab on the start page, logged in when it shows a login form (run #16 review)."""
    view = await site.fresh_tab()
    if "password-input" in view:
        try:
            return await site.login()
        except Exception as error:  # the model sees the login form and can try itself
            print(f"[{site.id}] logging in on the fresh tab failed ({type(error).__name__})", flush=True)
    return view


async def _enter(site: web.Site) -> str:
    first_view = await site.goto(site.url)
    if "password-input" in first_view:  # a login form: the run's credentials go in before the model looks
        try:
            first_view = await site.login()
        except Exception as error:  # an odd login form: the model takes over from the page as it is
            print(f"[{site.id}] the login did not go through by itself: {error!r}", flush=True)
            first_view = await site.view()
    return first_view


HELPERS = 3  # parallel helpers an ERP agent may run at once, each in its own tab


def kind_of(the_plan: dict, site_id: str) -> str:
    return next((s.get("kind", "") for s in the_plan.get("sites", []) if s.get("site_id") == site_id), "")


def mail_site_id(the_plan: dict) -> str | None:
    """The website holding the messages: the mailbox, else the one website that holds messages as well."""
    sites = the_plan.get("sites", [])
    main = next((s.get("site_id") for s in sites if s.get("kind") == "mail"), None)
    if main:
        return main
    also = [s.get("site_id") for s in sites if "mail" in (s.get("also") or [])]
    return also[0] if len(also) == 1 else None


def kinds_of(the_plan: dict, site_id: str) -> list[str]:
    """Every kind of facts a website holds: its main kind first, then what the brief says it holds as well."""
    entry = next((s for s in the_plan.get("sites", []) if s.get("site_id") == site_id), {})
    kinds = [entry.get("kind", "")] + [kind for kind in entry.get("also") or [] if kind != entry.get("kind")]
    return [kind for kind in kinds if kind]
HELPER_TASKS: list[asyncio.Task] = []  # every helper agent, stopped at the investigation's hard stop
KEY = re.compile(r"\b[A-Z][A-Z0-9]*-\d+[A-Z0-9-]*\b")  # identifiers such as group keys and requirement ids


def helper_tools(site: web.Site, task: dict, the_plan: dict, ledger: Ledger, deadline: float,
                 helpers: list) -> list:
    """delegate(): the agent hands an independent part of its website's work (one requirement's materials) to a
    helper agent in a new tab of the same browser; the model decides what to split, the code runs it in parallel."""
    jobs: list[set[str]] = []
    refused = [0]  # jobs refused for want of recorded identifiers

    async def delegate(job: str) -> str:
        if sum(not helper.done() for helper in helpers) >= HELPERS:
            return f"All {HELPERS} helpers are busy; do this part yourself."
        others = ledger.text(exclude_agent=site.id)
        # the tender reference is in every record and every job: it says nothing about the part (run #13)
        reference = the_plan.get("tender_reference", "")
        named = [key for key in KEY.findall(job) if key in others and key != reference]
        if len(set(named)) < 2:
            # identifiers of another shape ("WG 4711", "Klasse B12") count when the specification side recorded them
            spec = " ".join(json.dumps(entry, ensure_ascii=False) for entry in ledger.entries
                            if kind_of(the_plan, entry["site"]) not in ("tender", "erp") and entry["agent"] != site.id)
            tokens = {token.strip(".,;:()") for token in re.findall(r"\b[\w./-]*\d[\w./-]*\b|\b[A-ZÄÖÜ]{2,}[\w/-]{2,}\b", job)}
            shaped = [token for token in tokens if re.search(r"[^\d.,/-]", token) and len(token) >= 3
                      and token in spec and token != reference]
            if shaped:
                named = shaped + named
        refused[0] += 1 if len(set(named)) < 2 else 0
        if len(set(named)) < 2 and refused[0] > 2 and any(
                kind_of(the_plan, entry["site"]) not in ("tender", "erp") for entry in ledger.entries):
            named = ["(as written)"]  # refused twice already and the specification is recorded: let it go
        if len(set(named)) < 2 and named != ["(as written)"]:
            # run #10 started helpers before any requirement was recorded: they found nothing to do and stopped
            return ("Name the requirement and its catalogue group (and its attributes) exactly as the other agents "
                    "recorded them (read_notes). If they are not recorded yet, call wait_for_notes() first; a "
                    "helper without them has nothing to look up.")
        tender = " ".join(json.dumps(entry, ensure_ascii=False) for entry in ledger.entries
                          if kind_of(the_plan, entry["site"]) == "tender")
        if tender and named != ["(as written)"] and not any(key in tender for key in named):
            return ("No position of the tender refers to that requirement (the tender's records do not name it): "
                    "its materials are never needed. Delegate the requirements the positions use.")
        if time.time() > deadline - 60:
            return "Too little time is left for a helper; do this part yourself."
        known = ledger.text()
        invented = [key for key in KEY.findall(job) if key not in known]
        if invented:  # run #8 delegated a requirement with a group key and attributes that no record held
            return (f"{', '.join(invented)} is in no record of the team: take the requirement's identifiers and "
                    "attributes exactly from the records (read_notes), then delegate again.")
        keys = {key for key in KEY.findall(job) if key in known}
        if keys and any(keys <= earlier for earlier in jobs):
            return "A helper already works on that part; go on with another one."
        name = f"{site.id}-{len(helpers) + 2}"
        tab = await site.spawn()  # a helper that ends early frees its place for the next part
        first_view = await tab.goto(site.page.url)  # where the lead is: past the login and any entry notice
        jobs.append(keys)  # taken only once its helper has a tab
        helpers.append(asyncio.create_task(investigate(
            tab, task, the_plan, ledger, deadline, name=name, first_view=first_view,
            extra=f"\nYour part of this website (the rest of the team's agents do the others): {job}\nDo only this "
                  "part, record as you go, and call finish when it is done.")))
        HELPER_TASKS.append(helpers[-1])
        print(f"[{name}] started on: {job[:200]}", flush=True)
        return f"Helper {name} works on this in another tab now: do not do it yourself; go on with the rest."

    return [(tool("delegate", "Start a helper on one independent part of this website's work, in another tab.",
                  {"job": {"type": "string", "description": "The part, with every identifier and attribute the "
                                                            "helper needs"}}, ["job"]), delegate)]


async def investigate(site: web.Site, task: dict, the_plan: dict, ledger: Ledger, deadline: float,
                      extra: str = "", first_view: str | None = None, topics: list[dict] | None = None,
                      name: str | None = None, refusals: int | None = None) -> dict | None:
    kind = next((entry for entry in the_plan.get("sites", []) if entry.get("site_id") == site.id), {})
    reference = the_plan.get("tender_reference", "")
    checklist, helpers, lead, name = None, [], name is None, name or site.id
    kinds = kinds_of(the_plan, site.id)
    if kinds and kinds[0] == "erp":
        helper = not lead and "Your part of this website" in extra
        extra = prompts.ERP_EXTRA + ("" if helper else prompts.ERP_ROUTING) + (prompts.ERP_LEAD if lead else "") \
            + extra
    elif topics and "mail" in kinds:
        checklist = Topics(topics, reference, the_plan.get("scenario_date", ""), site, ledger, name)
        extra = prompts.MAIL_EXTRA + prompts.mail_topics(topics, reference, the_plan.get("scenario_date", "")) + extra
    elif kinds and kinds[0] == "mail":
        extra = prompts.MAIL_EXTRA + (prompts.MAIL_ALL_TOPICS if lead else "") + extra
    # a website that holds other kinds of facts as well gets their instructions too (the private websites may split
    # the facts differently: a specification inside the materials system, approval messages in a portal)
    if lead:
        extra += "".join(prompts.ALSO.get(other, "") for other in kinds[1:])
    if first_view is None:
        first_view = await enter(site)
    minutes = max(1, int((deadline - time.time()) / 60))
    # the ERP's lookups depend on the specification's catalogue groups: it must not give up before they arrive
    shown = {"size": -1, "at": 0.0}

    def news() -> str:
        asyncio.get_running_loop().create_task(site.keep_alive())  # a refused agent sends no requests either
        # refused again right away with nothing new: the digest it just read is not sent a second time
        if len(ledger.entries) == shown["size"] and time.time() - shown["at"] < 20:
            return "\n\nNothing new from the other websites since your last check (read_notes() shows all)."
        shown.update(size=len(ledger.entries), at=time.time())
        known = ledger.digest(exclude_agent=name)
        # only the lead: helpers and follow-ups have their own questions, and the gap list may be old by then
        missing = [gap.get("fact", "") for gap in (ledger.latest_inputs or {}).get("missing") or []
                   if gap.get("site_id") == site.id and gap.get("fact")] if lead else []
        wanted = ("\n\nThe team's last check still misses from your website: " + "; ".join(missing)
                  + ". Look these up first.") if missing else ""
        return wanted + ("\n\nWhat the agents on the other websites have recorded so far (one line each; look for "
                         f"facts that your website's records depend on and that you have not looked up yet):\n{known}"
                         if known else "")

    # an agent that waits for the other websites' facts (the ERP) is refused for as long as the team investigates,
    # not a fixed number of times: in run #4 it used up six refusals while waiting and stopped with nothing. A mail
    # agent with a topic checklist may stop once every topic is closed (the code refuses it until then), a helper once
    # its part is done.
    if refusals is None:
        # a helper is refused twice (one failed search must not end it, run #10); a checklist agent never
        refusals = 0 if checklist else 2 if not lead else 1000 if "erp" in kinds else 4
    elif checklist:
        refusals = 0
    tools = web.toolbox(site) + record_tools(site, ledger, name) + (checklist.tools() if checklist else [])
    if "erp" in kinds and lead:
        tools += helper_tools(site, task, the_plan, ledger, deadline, helpers)
    agent = Agent(name, prompts.BROWSER, tools, deadline, effort="low", stay_until=deadline - (90 if lead else 20),
                  refusals=refusals, news=news, check=checklist.check if checklist else None,
                  enough=enough_refusing(ledger, name, site))
    # time is the limit, not a step count: refused finishes count as steps too
    result = await agent.run(prompts.investigate(task["brief"], site, kind.get("holds", ""), reference, minutes,
                                                 first_view, extra), max_steps=400)
    if checklist:
        print(f"[{name}] topics: {checklist.status()}", flush=True)
    if helpers:  # the website's work is done when its helpers are
        await asyncio.wait(helpers, timeout=max(1.0, deadline - time.time() + 20))
    return result


def enough_refusing(ledger: Ledger, name: str, site: web.Site | None = None, idle: int = 2):
    """When to stop refusing an agent's early finish: never while it has recorded nothing (it waits for other
    websites' facts), else once `idle` refusals in a row brought no new value into the team's records (the same facts
    recorded again count for nothing). In run #8 the ERP agent was refused 28 times after its work was done, recorded
    the same facts again and again, and finally an invented price."""
    state = {"known": -1, "idle": 0}

    def own_work(entry) -> bool:
        """A record of this agent with values its own website showed (not facts copied from the others)."""
        text = json.dumps(entry["facts"], ensure_ascii=False)
        return entry["agent"] == name and bool(web.amounts(text)) and not (site and site.unseen(text))

    site_id = site.id if site else name

    def handed(fact: str) -> bool:
        """A missing fact another agent of this website was started on, and is still working on or recorded."""
        for given, job, agent in ledger.handed.get(site_id, []):
            if given == fact:
                return not job.done() or any(entry["agent"] == agent for entry in ledger.entries)
        return False

    def news(entry) -> set:
        """What a record adds to the team's knowledge: its values and identifiers."""
        text = json.dumps(entry["facts"], ensure_ascii=False)
        return set(web.amounts(text)) | set(KEY.findall(text))

    def enough() -> bool:
        if not any(own_work(entry) for entry in ledger.entries):
            return False
        # only a gap check can tell that this website's part is complete: without one, or while it lists a fact
        # this website should give that no other agent has taken over, the agent keeps working (run #9 let the ERP
        # agent go before two of its lookups; run #11 kept it 45 calls longer although a follow-up had the gap)
        latest = ledger.latest_inputs
        if latest is None or any(gap.get("site_id") == site_id and not handed(gap.get("fact", ""))
                                 for gap in latest.get("missing") or []):
            return False
        # the same website's helpers and follow-ups bring nothing this agent could add: only other websites' records
        # and its own count as new
        known = len(set().union(*(news(entry) for entry in ledger.entries
                                  if entry["agent"] == name or entry["site"] != site_id)))
        state["idle"] = state["idle"] + 1 if known == state["known"] else 0
        state["known"] = known
        if state["idle"] >= idle:
            print(f"[{name}] finish accepted: refusing brought nothing new", flush=True)
            return True
        return False
    return enough


MAIL_AGENTS = 3  # parallel mail agents at most, each in its own tab with a share of the topics


def topic_groups(topics: list[dict], most: int = MAIL_AGENTS) -> list[list[dict]]:
    """The mail topics dealt out to up to `most` agents, about three each, in the brief's order."""
    topics = [t for t in topics or [] if str(t.get("topic", "")).strip()]
    count = max(1, min(most, len(topics) // 3 + (1 if len(topics) % 3 else 0)))
    return [group for group in (topics[i::count] for i in range(count)) if group]


async def investigate_mail(site: web.Site, task: dict, the_plan: dict, ledger: Ledger, deadline: float):
    """The mailbox, its topics shared among parallel agents in tabs of the same browser: one agent alone ran out of
    time before reaching every topic (runs #6, #7). The first tab logs in before the others open."""
    groups = topic_groups(the_plan.get("mail_topics") or [])
    first_view = await enter(site)
    if len(groups) <= 1:
        return await investigate(site, task, the_plan, ledger, deadline, first_view=first_view,
                                 topics=groups[0] if groups else None)
    tabs = [site]
    for _ in groups[1:]:
        try:
            tabs.append(await site.spawn())
        except Exception as error:
            print(f"[team] another mail tab failed: {error!r}", flush=True)
    if len(tabs) < len(groups):  # fewer tabs than planned: deal the topics out again
        groups = topic_groups(the_plan.get("mail_topics") or [], len(tabs))

    async def one(number: int, tab: web.Site, group: list[dict]):
        name = site.id if number == 0 else f"{site.id}-{number + 1}"
        for attempt in range(2):  # a tab that fails is replaced once: its topics must not be lost unnoticed
            try:
                view = first_view if tab is site and attempt == 0 else await enter(tab)
                return await investigate(tab, task, the_plan, ledger, deadline, first_view=view, topics=group,
                                         name=name)
            except Exception as error:
                print(f"[{name}] failed: {error!r}", flush=True)
                if deadline - time.time() < 90:
                    return None
                tab = await site.spawn()

    print(f"[team] mail topics: {[[t.get('topic') for t in group] for group in groups]}", flush=True)
    return await asyncio.gather(*(one(number, tab, group) for number, (tab, group) in enumerate(zip(tabs, groups))),
                                return_exceptions=True)


async def follow_up(site: web.Site, task: dict, the_plan: dict, ledger: Ledger, questions: list[str],
                    deadline: float, topics: list[dict] | None = None, name: str | None = None) -> dict | None:
    """A targeted second look at one website for facts the solver found missing: in a new tab of its browser (the
    investigator's page can be stuck or on a dead end), logged in, with the website's own instructions and, for the
    mailbox, a checklist of the missing topics. In runs #5 to #7 a bare follow-up on the old page found nothing."""
    tab = await site.spawn()
    view = await enter(tab)
    extra = ("\nThe team already has most facts. Find specifically these missing ones:\n"
             + "\n".join(f"- {question}" for question in questions)) if questions else ""
    return await investigate(tab, task, the_plan, ledger, deadline, extra=extra, first_view=view, topics=topics,
                             name=name or f"{site.id}+", refusals=2)


def code_gaps(inputs: dict | None) -> list[dict]:
    """Calculation inputs the shared rules need but the solver had to leave empty, found in code from the inputs
    alone: each with the kind of mail topic that gives it (FEEDS)."""
    if not inputs or inputs.get("decision") == "no_bid":
        return []
    positions = inputs.get("positions") or []
    gaps = []
    foreign = [p for p in positions if (p.get("price") or {}).get("currency")
               and str(p["price"]["currency"]).strip().upper() != "EUR"
               and calc.eur_per_unit(p["price"], str(p["price"]["currency"]).strip().upper()) is None]
    if foreign:
        gaps.append({"feeds": "fx", "fact": "the exchange rate (currency fixing) for "
                     + ", ".join(sorted({str(p["price"]["currency"]) for p in foreign}))})
    index = inputs.get("metal_index") or {}
    if any(calc.kilograms(p.get("surcharge_mass_kg")) for p in positions) and not index.get("rates"):
        gaps.append({"feeds": "metal_index", "fact": "the metal price index rates with their validity windows"})
    pools = {str(pool.get("key")) for pool in inputs.get("setup_pools") or [] if calc.dec(pool.get("fee_eur"))}
    missing_pools = {str(p["setup_pool_key"]) for p in positions if p.get("setup_pool_key")} - pools
    if missing_pools:
        gaps.append({"feeds": "setup_pool", "fact": f"the fee and cent rule of setup pool {', '.join(missing_pools)}"})
    if any(p.get("project_bonus_member") for p in positions) and not (inputs.get("project_bonus") or {}).get("bands"):
        gaps.append({"feeds": "project_bonus", "fact": "the project bonus bands"})
    if any(p.get("condition_group") and not p.get("discount_scope") for p in positions):
        gaps.append({"feeds": "condition_rules", "fact": "the condition rules for the condition groups"})
    return gaps


def gap_topics(inputs: dict | None, the_plan: dict, brief: str = "") -> list[tuple[dict, str]]:
    """The plan's mail topics that would fill the gaps: by the kind of input they give, or by the topic word the
    solver named for a missing mailbox fact. Each with what to tell the agent."""
    topics = the_plan.get("mail_topics") or []
    found: dict[str, tuple[dict, str]] = {}
    for gap in code_gaps(inputs):
        for topic in topics:
            if topic.get("feeds") == gap["feeds"]:
                found.setdefault(fold(topic["topic"]), (topic, gap["fact"]))
    for gap in (inputs or {}).get("missing") or []:
        word = fold(gap.get("topic") or "")
        topic = next((t for t in topics if word and (fold(t["topic"]) == word or fold(t["topic"]) in word)), None)
        if topic is None and word and len(word) > 4 and word in fold(brief):  # a subject the plan left out
            topic = {"topic": gap["topic"].strip(), "sender": "", "gives": gap.get("fact", ""), "feeds": "other"}
        if topic:
            seen = f" (seen and rejected: {gap['seen']})" if gap.get("seen") else ""
            found.setdefault(fold(topic["topic"]), (topic, f"{gap.get('fact', '')}{seen}"))
    return list(found.values())


FIRST_GAP_CHECK = 240  # seconds into the investigation at the latest


async def gap_rounds(sites: list[web.Site], task: dict, the_plan: dict, ledger: Ledger, until: float, mail_job,
                     others: list | None = None):
    """While the team still investigates: once the mailbox agents are done (or a few minutes before the end), a
    quick solve finds the inputs still empty, and a fresh mail agent goes after each topic that gives one. Twice at
    most. The last inputs are kept for the case that the final solve fails."""
    kinds = {entry.get("site_id"): entry.get("kind") for entry in the_plan.get("sites", [])}
    mail = next((site for site in sites if site.id == mail_site_id(the_plan)), None)
    # the first check comes when the mailbox is done or FIRST_GAP_CHECK seconds into the investigation, whichever is
    # first: the ERP lead may only stop after a gap check, and waiting for a slow mailbox held the whole team (the
    # scored run of 11 Oct: the check came at +7:03 although every other website was done by +4)
    first_check = min(until - 210, time.time() + FIRST_GAP_CHECK)
    try:
        if mail_job is not None:
            await asyncio.wait_for(asyncio.shield(mail_job), timeout=max(0.0, first_check - time.time()))
        else:
            # the ERP lead waits for the gap check itself: waiting for it would hold the first round to the end
            jobs = list(others or [])
            waiting = [job for job, site in zip(jobs, sites) if "erp" not in kinds_of(the_plan, site.id)] or jobs
            await asyncio.wait(waiting or [asyncio.sleep(0)], timeout=max(0.0, first_check - time.time()))
    except (asyncio.TimeoutError, Exception):
        pass
    dispatched, agents, busy = set(), [], {}
    for round_number in (1, 2):
        if until - time.time() < 120:
            break
        inputs = await solve(task, the_plan, ledger, min(time.time() + 100, until - 90), until - 60, effort="low",
                             name=f"gaps{round_number}")
        if inputs:
            ledger.latest_inputs = inputs
            fresh = [(topic, why) for topic, why in gap_topics(inputs, the_plan, task["brief"])
                     if fold(topic["topic"]) not in dispatched] if mail is not None else []
            print(f"[team] gap check {round_number}: {[gap['feeds'] for gap in code_gaps(inputs)]}; mail topics "
                  f"to search again: {[topic['topic'] for topic, _ in fresh]}", flush=True)
            for number, (topic, why) in enumerate(fresh, len(dispatched) + 1):
                dispatched.add(fold(topic["topic"]))
                agents.append(asyncio.create_task(follow_up(
                    mail, task, the_plan, ledger, [f"{topic['topic']}: {why}"], until, topics=[topic],
                    name=f"{mail.id}+{number}")))
                HELPER_TASKS.append(agents[-1])  # stopped at the investigation's hard stop like the helpers
            # the other websites' missing facts get an agent of their own too, while there is time (run #10 left
            # three materials to a 75-second follow-up after the investigation)
            by_id = {site.id: site for site in sites}
            asked: dict[str, list[str]] = {}
            for gap in inputs.get("missing") or []:
                site_id = gap.get("site_id")
                if site_id in by_id and (mail is None or site_id != mail.id) and kinds.get(site_id) != "mail" \
                        and gap.get("fact"):
                    asked.setdefault(site_id, []).append(gap["fact"])
            for site_id, facts in asked.items():
                if busy.get(site_id) and not busy[site_id].done():
                    continue
                print(f"[team] gap check {round_number}: {site_id} is asked for {facts}", flush=True)
                busy[site_id] = asyncio.create_task(follow_up(by_id[site_id], task, the_plan, ledger, facts, until,
                                                              name=f"{site_id}+g{round_number}"))
                agents.append(busy[site_id])
                HELPER_TASKS.append(busy[site_id])
                ledger.handed.setdefault(site_id, []).extend(
                    (fact, busy[site_id], f"{site_id}+g{round_number}") for fact in facts)
        if round_number == 1:  # a second look a few minutes before the end, when more has been recorded
            wait = until - 210 - time.time()
            if wait < 60:
                break
            running = [job for job in others or [] if not job.done() and job is not asyncio.current_task()]
            if not running:
                break  # everyone has finished: the solve after the investigation looks at the gaps
            await asyncio.wait(running, timeout=wait)
            if all(job.done() for job in running):
                break
    if agents:
        await asyncio.wait(agents, timeout=max(1.0, until - time.time() + 20))


EVIDENCE = {"type": "string", "description": "In a few words: which record this is and why it applies"}
# attributes the brief's matching rule names besides the five above (another product has other attributes)
OTHER = {"type": "object", "description": "Every further attribute the brief's matching rule names, name: value",
         "additionalProperties": {"type": "string"}}
ATTRIBUTES = ("bore", "stroke", "pressure", "mounting", "certification")
POSITION = {"type": "object", "properties": {
    "position": STRING,
    "tender_quantity": NUMBER, "unit": STRING,
    "unit_is_set": {"type": "boolean", "description": "The quantity is in sets and must be converted to pieces"},
    "pieces_per_set": NUMBER,
    "quantity_changes": {"type": "array", "items": {"type": "object", "properties": {
        "qa_number": STRING, "date": STRING, "quantity": NUMBER}}},
    "withdrawn_qa_numbers": {"type": "array", "items": STRING},
    "requirement": {"type": "object", "description": "After amendments and stroke derivation", "properties": {
        "id": STRING, "catalogue_group": {"type": "string", "description": "The key the specification gives for "
                                                                    "finding the material in the ERP, whatever its "
                                                                    "label (catalogue group, material class, ...)"},
        "bore": STRING, "stroke": STRING, "pressure": STRING,
        "mounting": STRING, "certification": STRING, "other": OTHER}},
    "material_number": NULLABLE_STRING,
    "material_attributes": {"type": "object", "properties": {
        "status": {"type": "string", "description": "The visible status value and its meaning, e.g. active or "
                                                    "blocked"},
        "bore": STRING, "stroke": STRING, "pressure": STRING, "mounting": STRING,
        "certification": STRING, "other": OTHER}},
    "price": {"type": "object", "properties": {
        "valid_from": STRING, "valid_to": STRING, "currency": STRING, "price_unit": NUMBER,
        "number_format": {"type": ["string", "null"], "description": "The condition's number format or locale as "
                                                                    "the website states it (e.g. de-DE, en-US)"},
        "scales": {"type": "array", "items": {"type": "object", "properties": {"min_quantity": NUMBER,
                                                                             "price": NUMBER}}},
        "eur_per_currency_unit": NUMBER,
        "currency_per_eur": {**NUMBER, "description": "Only if the fixing is quoted the other way round (units of "
                                                      "the currency per EUR); never invert it yourself"}}},
    "condition_group": {"type": ["string", "null"], "description": "The condition group a clarification assigned "
                                                                   "to this position, or null"},
    "discount_scope": {"type": "string", "enum": ["base_only", "base_and_surcharge", "none"],
                       "description": "What the condition rules say for the position's group"},
    "surcharge_mass_kg": KILOGRAMS, "setup_fee": NUMBER, "setup_pool_key": NULLABLE_STRING,
    "allocation_mass_kg": KILOGRAMS, "pieces_per_carton": NUMBER, "carton_tariff_eur": NUMBER,
    "stock": {**NUMBER, "description": "Freely usable stock only: blocked or inspection stock does not count"},
    "stock_lead_time_weeks": NUMBER, "production_lead_time_weeks": NUMBER,
    "delivery_commitment": {"type": ["object", "null"], "properties": {
        "material_number": STRING, "ceiling_pieces": NUMBER, "lead_time_weeks": NUMBER}},
    "project_bonus_member": {"type": "boolean"}},
    "required": ["position", "tender_quantity", "unit", "material_number"]}

INPUTS_SCHEMA = {
    "tender_reference": STRING,
    "decision": {"type": "string", "enum": ["bid", "no_bid"]},
    "decision_reason": STRING,
    "scenario_date": STRING,
    "discount_approval": {"type": ["object", "null"], "properties": {
        "percent": NUMBER, "min_order_value_eur": NUMBER, "evidence": EVIDENCE}},
    "metal_index": {"type": ["object", "null"], "properties": {
        "rates": {"type": "array", "items": {"type": "object", "properties": {
            "valid_from": NULLABLE_STRING, "valid_to": NULLABLE_STRING, "eur_per_kg": NUMBER}}},
        "evidence": EVIDENCE}},
    "setup_pools": {"type": "array", "items": {"type": "object", "properties": {
        "key": STRING, "fee_eur": NUMBER, "evidence": EVIDENCE,
        "allocation": {"type": "string", "enum": ["largest_remainder", "remainder_to_largest_share",
                                                  "remainder_to_first", "remainder_to_last"]}}}},
    "project_bonus": {"type": ["object", "null"], "properties": {
        "bands": {"type": "array", "items": {"type": "object", "properties": {
            "from_eur": NUMBER, "to_eur": NUMBER, "percent": NUMBER}}},
        "evidence": EVIDENCE}},
    "positions": {"type": "array", "items": POSITION},
    "missing": {"type": "array", "items": {"type": "object", "properties": {
        "fact": STRING, "site_id": STRING,
        "topic": {"type": "string", "description": "For a mailbox fact: the topic word as the brief spells it, "
                                                   "else empty"},
        "seen": {"type": "string", "description": "What was found instead and rejected (another reference, a later "
                                                  "date, another sender), else empty"}}}},
    "notes": {"type": "string", "description": "At most a few sentences"},
}


async def solve(task: dict, the_plan: dict, ledger: Ledger, deadline: float,
                hard_deadline: float = float("inf"), effort: str = "medium", name: str = "solver") -> dict | None:
    agent = Agent(name, prompts.SOLVER, [], deadline, finish=INPUTS_SCHEMA, effort=effort,
                  hard_deadline=hard_deadline)
    inputs = await agent.run(prompts.solve(prompts.brief_for(task["brief"], prompts.FOR_ALL, task),
                                           {k: v for k, v in the_plan.items() if k not in ("tan_site_id",)},
                                           ledger.for_solver()), max_steps=4)
    if inputs is not None:
        inputs["tender_reference"] = the_plan.get("tender_reference") or inputs.get("tender_reference")
        inputs.setdefault("scenario_date", the_plan.get("scenario_date"))
        if inputs.get("decision") == "no_bid":
            normalize_no_bid(inputs, ledger)
        if inputs.get("decision") == "no_bid" and not no_bid_shown(inputs):
            print(f"[team] no_bid without a requirement that has no matching material: bidding instead "
                  f"({inputs.get('decision_reason')})", flush=True)
            inputs["decision"] = "bid"
    return inputs


BLOCKED = re.compile(r"gesperrt|blocked|\binaktiv|\binactive|nicht\s+freigegeben|gelöscht|deleted", re.I)
ACTIVE = re.compile(r"(?<!nicht )freigegeben|\bactive\b|\baktiv\b", re.I)


def blocked(status: str) -> bool:
    """Whether a material's own status is blocked: only the status itself counts, not a legend or a note about another
    candidate after it ("01 freigegeben (status key: 01 freigegeben · 03 gesperrt)" is active, run #16 review)."""
    head = re.split(r"[;(·]", str(status or ""), maxsplit=1)[0]
    head = re.sub(r"nicht\s+gesperrt|not\s+blocked", "", head, flags=re.I)
    return bool(BLOCKED.search(head)) and not ACTIVE.search(head)


def normalize_no_bid(inputs: dict, ledger: Ledger):
    """A no_bid written in another shape than "a position without a material": a blocked candidate named as the
    material is no material; no positions at all take the last gap check's positions without their materials. The
    follow-up round then checks the candidate list before the no_bid may stand."""
    positions = inputs.get("positions") or []
    if not positions and ledger.latest_inputs:
        positions = [{**position, "material_number": None} for position in ledger.latest_inputs.get("positions") or []]
        inputs["positions"] = positions
    for position in positions:
        status = str((position.get("material_attributes") or {}).get("status") or "")
        if position.get("material_number") and blocked(status):
            position["material_number"] = None


def no_bid_shown(inputs: dict) -> bool:
    """Rule 3 calls for no_bid only when a position's requirement has no active matching material: that needs a
    position whose requirement is known (by its search key or its id) and which has no material."""
    return any(((position.get("requirement") or {}).get("catalogue_group")
                or (position.get("requirement") or {}).get("id")) and not position.get("material_number")
               for position in inputs.get("positions") or [])


def mismatches(inputs: dict) -> list[str]:
    """Positions whose chosen material does not equal the requirement on every attribute the rules name."""
    problems = []
    for position in inputs.get("positions") or []:
        requirement, material = position.get("requirement") or {}, position.get("material_attributes") or {}
        if not position.get("material_number"):
            continue
        wanted = {**{a: requirement.get(a) for a in ATTRIBUTES}, **(requirement.get("other") or {})}
        held = {**{a: material.get(a) for a in ATTRIBUTES}, **(material.get("other") or {})}
        for attribute, value in wanted.items():
            want, have = _norm(value), _norm(held.get(attribute))
            if want and have and want != have:
                problems.append(f"position {position.get('position')}: {attribute} {have!r} != required {want!r}")
    return problems


def _norm(value) -> str:
    return "".join(str(value or "").lower().replace(",", ".").split()).removesuffix(".0")


async def investigate_all(sites: list[web.Site], task: dict, the_plan: dict, ledger: Ledger, until: float):
    """Every website at once, each agent stopping by `until`, and the gap rounds; a hard stop shortly after."""
    # the parallel topic agents take a whole website: only the mailbox itself; a website that holds messages as well
    # keeps its own investigator (with the message instructions), and the gap rounds send topic agents there
    mail_id = next((s.get("site_id") for s in the_plan.get("sites", []) if s.get("kind") == "mail"), None)
    jobs = [asyncio.create_task((investigate_mail if site.id == mail_id else investigate)(
        site, task, the_plan, ledger, until)) for site in sites]
    for job, site in zip(jobs, sites):  # a crash shows in the log when it happens, not at the end (run #15)
        job.add_done_callback(lambda done, name=site.id: done.cancelled() or not done.exception() or print(
            f"[team] the {name} investigator failed: {done.exception()!r}", flush=True))
    # the gap rounds run in any case: without a mailbox they still chase the other websites' missing facts
    mail_job = next((job for job, site in zip(jobs, sites) if site.id == mail_id), None)
    jobs.append(asyncio.create_task(gap_rounds(sites, task, the_plan, ledger, until, mail_job, list(jobs))))
    done, pending = await asyncio.wait(jobs, timeout=max(1.0, until - time.time() + 45))
    for job in list(pending) + [helper for helper in HELPER_TASKS if not helper.done()]:
        job.cancel()
    for job in done:
        if job.exception():
            print(f"[team] an investigator failed: {job.exception()!r}", flush=True)
