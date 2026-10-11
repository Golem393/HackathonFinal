"""The submission: an agent enters the computed bid on the submission website and signs it with a TAN that a second
agent reads from the mailbox. The values come from calc; the model only operates the form."""
import asyncio
import re
import time
from decimal import Decimal

import prompts
import web
import calc
from calc import german
from llm import Agent, tool


def _german(value) -> str:
    """A value in the form's number format; an unknown one is left empty."""
    return "(leave empty)" if value is None else german(value)


def table(answer: dict, omitted: list[str], configurator: dict[str, dict] | None = None) -> str:
    """The bid as the submitter sees it: every value already in the form's German number format, and per position
    the attribute values a material configurator asks for before it offers the materials."""
    configurator = configurator or {}
    lines = [f"Tender reference: {answer['tender_reference']}",
             f"Decision: {answer['decision']} ({'main bid' if answer['decision'] == 'bid' else 'declaration of no bid'})",
             f"Currency: EUR", f"Discount percent: {german(answer['discount_percent'])}",
             f"Total net (EUR): {german(answer['total_net'])}", ""]
    if answer["decision"] == "bid":
        lines.append("| Position | Configurator values | Material | Quantity (pieces) | Unit price net | Lead time (weeks) "
                     "| Base price/piece | Surcharge/piece | Packaging/piece | Project bonus (whole position) "
                     "| Line total (quantity × unit price) |")
        for p in answer["positions"]:
            values = configurator.get(str(p["position"])) or {}
            shown = " / ".join(f"{key} {value}" for key, value in values.items()) or "(see the requirement)"
            material = p["material_number"] or "(choose: the material the configurator offers for these values)"
            weeks = p["lead_time_weeks"] if p["lead_time_weeks"] is not None else "(unknown: choose any)"
            line_total = Decimal(str(p["quantity"])) * Decimal(str(p["unit_price"] or 0))
            lines.append(f"| {p['position']} | {shown} | {material} | {p['quantity']} | {_german(p['unit_price'])} | "
                         f"{weeks} | {_german(p['base_unit_price'])} | {_german(p['surcharge_per_unit'])} | "
                         f"{_german(p['packaging_per_unit'])} | {_german(p['rebate_total'])} | "
                         f"{german(line_total)} |")
        for position in omitted:
            lines.append(f"| {position} | | OMIT | | | | | | | | |")
    return "\n".join(lines)


CONTINUE = re.compile(r"weiter|next|continue|fortfahren|speichern|save|übernehmen und|nächste", re.I)
TOTAL = re.compile(r"gesamt|total|summe|netto|\bnet\b", re.I)
NOT_TOTAL = re.compile(r"brutto|gross|mwst|ust|vat|steuer|tax|rabatt|discount|nachlass|%|position|pos\.|menge|"
                       r"quantity|stück|einzel|unit|zeile|line|preis je|per piece", re.I)


def _id_pattern(position: str) -> re.Pattern:
    """A position id by its digit groups, standing alone: 1.3 matches 01.03; the date 01.03.2027, a price and the
    digits of an article number do not."""
    groups = re.findall(r"\d+", str(position))
    if not groups:
        return re.compile(re.escape(str(position)))
    body = r"[.\s/-]".join(rf"0*{int(group)}" for group in groups)
    return re.compile(rf"(?<![\w.,-]){body}(?![\d]|[.,]\d)")


class FormGuard:
    """Code checks on what the submitter enters, from the computed bid: a position step's values before it is left,
    and the summary before the TAN. In run #7 a step got another position's row and fields were skipped; in run #5
    the total still counted an omitted position. The checks only advise: each refuses once per problem, then lets
    the agent go on, so a layout they do not fit can never block the signature."""

    def __init__(self, answer: dict, omitted: list[str]):
        self.rows = {str(p["position"]): p for p in answer.get("positions") or []}
        self.omitted = {str(position) for position in omitted}
        self.patterns = {position: _id_pattern(position) for position in list(self.rows) + list(self.omitted)}
        self.refused: set[tuple] = set()
        # a plain number as position id ("3") cannot be told apart from quantities on a page: no checks then
        self.usable = bool(self.rows) and all(len(re.findall(r"\d+", p)) >= 2 for p in self.patterns)

    def _values(self, row: dict) -> dict[str, str]:
        values = {"quantity": str(row["quantity"]), "unit price": german(row["unit_price"] or 0),
                  "surcharge": german(row["surcharge_per_unit"]), "packaging": german(row["packaging_per_unit"]),
                  "project bonus": german(row["rebate_total"])}
        if row.get("base_unit_price") is not None:
            values["base price"] = german(row["base_unit_price"])
        if row.get("lead_time_weeks") is not None:
            values["lead time"] = str(row["lead_time_weeks"])
        return values

    def step_position(self, view: str) -> str | None:
        """The one position a page is about: named in a heading, else the only one named at all."""
        headings = "\n".join(line for line in view.splitlines() if line.startswith("#"))
        for text in (headings, view):
            named = [position for position, pattern in self.patterns.items() if pattern.search(text)]
            if len(named) == 1:
                return named[0]
        return None

    @staticmethod
    def _entered(view: str) -> tuple[list, list[str]]:
        """What the page's fields hold: as numbers, and as texts (with the selected options)."""
        texts = re.findall(r'\[\d+ [\w-]*input "[^"]*" value="([^"]*)"', view) + re.findall(r'selected="([^"]*)"', view)
        # a number with its unit ("3 Wochen" in a dropdown, "2.614,68 EUR") counts as that number
        leading = [re.match(r"\s*(-?\d[\d.,]*)(?:\s|$)", text) for text in texts]
        numbers = [calc.dec(match.group(1)) for match in leading if match]
        return [number for number in numbers if number is not None], texts

    @staticmethod
    def _holds(entered: tuple[list, list[str]], value: str) -> bool:
        numbers, texts = entered
        if re.fullmatch(r"-?[\d.,]+", value.strip()):
            return calc.dec(value) in numbers
        return any(value.lower() in text.lower() for text in texts)

    def entered_total(self) -> Decimal:
        return sum((Decimal(str(row["quantity"])) * Decimal(str(row["unit_price"] or 0))
                    for position, row in self.rows.items() if position not in self.omitted), Decimal(0))

    def total_problem(self, view: str) -> str | None:
        """A field for the order's net total must hold the total of the positions entered (run #8 typed one
        position's line total there)."""
        if self.step_position(view) is not None:
            return None  # a position's own step: its totals are the position's, not the order's
        total = self.entered_total()
        for label, value in re.findall(r'\[\d+ [\w-]*input "([^"]*)" value="([^"]*)"', view):
            if TOTAL.search(label) and not NOT_TOTAL.search(label) and re.fullmatch(r"\s*[\d.,]+\s*", value):
                if calc.dec(value) is not None and abs(calc.dec(value) - total) > Decimal("0.005"):
                    return (f"The field {label!r} holds {value}, but the net total of the positions entered is "
                            f"{german(total)} (the bid table's total; if you omitted a position yourself, subtract "
                            "its line total). Enter that before you continue.")
        return None

    def step_problem(self, view: str, label: str) -> str | None:
        """Before a step's continue button: a net total field must hold the total; a position's step must hold its
        own row, completely."""
        if not self.usable or not CONTINUE.search(label):
            return None
        problem = self.total_problem(view)
        if problem:
            if ("total", problem) in self.refused:
                return None
            self.refused.add(("total", problem))
            return "Not clicked. " + problem
        position = self.step_position(view)
        if position is None or position in self.omitted or position not in self.rows:
            return None
        entered = self._entered(view)
        scores = {other: sum(self._holds(entered, value) for key, value in self._values(row).items()
                             if key not in ("project bonus",) and calc.dec(value) not in (None, 0))
                  for other, row in self.rows.items()}
        best = max(scores, key=scores.get)
        row = self.rows[position]
        if best != position and scores[best] >= 2 and scores[best] > scores[position]:
            problem = (f"This step is for position {position}, but its fields hold the values of position {best}. "
                       f"Enter {position}'s row: {self._row_text(position)}.")
        else:
            missing = [f"{key} {value}" for key, value in self._values(row).items()
                       if not self._holds(entered, value)]
            if row.get("material_number") and not self._holds(entered, row["material_number"]):
                missing.insert(0, f"material {row['material_number']}")
            if not missing:
                return None
            problem = (f"Still missing on the step for position {position}: {'; '.join(missing)}. Fill them (0,00 "
                       "included) before you continue, or click again to continue anyway.")
        if (position, problem) in self.refused:
            return None
        self.refused.add((position, problem))
        return "Not clicked. " + problem

    def _row_text(self, position: str) -> str:
        row = self.rows[position]
        return ", ".join([f"material {row.get('material_number') or '(the configurator offers it)'}"]
                         + [f"{key} {value}" for key, value in self._values(row).items()])

    def summary_problems(self, view: str) -> list[str]:
        """The summary against the bid: each entered position with its material and unit price, and the total of
        the positions entered."""
        if not self.usable:
            return []
        shown = [position for position, pattern in self.patterns.items() if pattern.search(view)]
        if len(self.rows) >= 2 and len(shown) < 2:
            return []  # a single position's step, not the summary
        problems = []
        starts = sorted((match.start(), position) for position, pattern in self.patterns.items()
                        for match in pattern.finditer(view))
        if not starts:
            return []
        segments: dict[str, list[str]] = {}
        for number, (at, position) in enumerate(starts):
            end = starts[number + 1][0] if number + 1 < len(starts) else len(view)
            segments.setdefault(position, []).append(view[at:min(end, at + 600)])
        entered = [position for position in self.rows if position not in self.omitted]
        for position in entered:
            row = self.rows[position]
            if position not in segments:
                problems.append(f"position {position} is not in the summary (omitted?)")
                continue
            text = " ".join(segments[position])
            if row.get("material_number") and row["material_number"] not in text:
                problems.append(f"{position}: material {row['material_number']} not shown")
            if not _shown(german(row["unit_price"] or 0), text):
                problems.append(f"{position}: unit price {german(row['unit_price'] or 0)} not shown")
        shown = [position for position in entered if position in segments]
        total = sum((Decimal(str(self.rows[p]["quantity"])) * Decimal(str(self.rows[p]["unit_price"] or 0))
                     for p in shown), Decimal(0))
        if not _shown(german(total), view):
            problems.append(f"the net total of the positions in the summary should be {german(total)}")
        return problems


def _shown(amount: str, text: str) -> bool:
    """An amount (given in German format) on the page: German with or without thousands points, plain, or en-US."""
    whole, _, cents = amount.partition(",")
    digits = whole.replace(".", "")
    forms = {amount, f"{digits},{cents}", f"{digits}.{cents}", f"{whole.replace('.', ',')}.{cents}"}
    return any(form in text for form in forms)


def _code(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", str(text).lower())


async def fetch_tan(mail: web.Site, requested_at: float, deadline: float, reference: str = "",
                    request: str = "") -> str:
    """The TAN from the mailbox: the message for `request` (the number the submission website gave the request),
    else the newest TAN message. It starts in a fresh tab: the page the mail investigator left can be stuck."""
    reader = mail
    try:  # a tab of its own: the TAN website can be the one the submitter is working in
        reader = await asyncio.wait_for(mail.spawn(), 30)
        first_view = await asyncio.wait_for(reader.goto(reader.url), 45)
        if "password-input" in first_view:
            first_view = await reader.login()
    except Exception as error:
        print(f"[tan] a new mailbox tab failed ({type(error).__name__}); using the open one", flush=True)
        reader = mail
        first_view = await asyncio.wait_for(mail.view(), 30)

    async def real_tan(args: dict) -> str | None:
        """A TAN is a code of its own: not empty, not a word like "unknown", not the tender reference or the request
        number (it need not have digits: some are letters only)."""
        tan = _code(args.get("tan", ""))
        if len(tan) < 4 or tan in ("unknown", "none", "notfound", "unbekannt", "keine") \
                or (reference and tan in _code(reference)) or (request and tan == _code(request)):
            return ("That is not a TAN: copy the code itself from the message text (it is neither the tender "
                    "reference nor the request number in the subject). Open the message, unlock it, open its "
                    "original text, or call screenshot() to see it.")
        return None

    agent = Agent("tan", prompts.BROWSER, web.toolbox(reader), deadline, check=real_tan,
                  finish={"tan": {"type": "string", "description": "The TAN exactly as written in the message"}})
    result = await agent.run(prompts.tan(time.strftime("%H:%M:%S", time.gmtime(requested_at)), request, first_view),
                             max_steps=25)
    tan = (result or {}).get("tan", "")
    if await real_tan({"tan": tan}):  # for the run's log: what the mailbox showed instead
        print(f"[tan] no TAN found; the mailbox page was:\n{reader.full_view[:4000]}", flush=True)
        return ""
    return tan


async def submit(site: web.Site, mail: web.Site | None, task: dict, answer: dict, omitted: list[str],
                 deadline: float, configurator: dict[str, dict] | None = None) -> dict | None:
    guard = FormGuard(answer, omitted)
    told: set[tuple] = set()

    async def get_tan(request: str = "") -> str:
        if mail is None:
            return "No mailbox website is known; look for the TAN where the brief says it arrives."
        problems = tuple(guard.summary_problems(site.full_view))
        if problems and not told and deadline - time.time() > 150:  # once: it may never keep the bid unsigned
            told.add(problems)
            print(f"[submit] summary check: {'; '.join(problems)}", flush=True)
            return ("Do not use a TAN yet: the summary differs from the bid: " + "; ".join(problems) + ". Correct "
                    "these first (then request a new TAN). If the summary is right after all, call get_tan again.")
        tan = await fetch_tan(mail, time.time(), time.time() + 120, answer.get("tender_reference", ""), request)
        if tan:
            site.secrets.add(tan)  # a TAN field may be a password field
        return f"The TAN is {tan}" if tan else "No TAN message was found yet; call get_tan() again in a moment."

    async def check_summary() -> str:
        view = await site.view()
        problems = guard.summary_problems(site.full_view)
        verdict = ("The summary differs from the bid: " + "; ".join(problems)) if problems else \
            "The summary matches the bid (materials, unit prices, total)."
        return verdict + "\n\n" + view

    async def click(ref) -> str:
        line = re.search(rf"\[{int(ref)} [\w-]+ \"([^\"]*)\"", site.full_view)
        problem = guard.step_problem(site.full_view, line.group(1) if line else "")
        if problem:
            print(f"[submit] step check: {problem[:300]}", flush=True)
            return problem  # the page is unchanged: the agent's last view still shows it
        return await site.click(ref)

    browsing = [(schema, click if schema["function"]["name"] == "click" else function)
                for schema, function in web.toolbox(site)]
    tools = browsing + web.configure_tool(site) + [(tool(
        "check_summary", "Compare the summary page with the bid (materials, unit prices, total) before you request "
                         "the TAN.", {}), check_summary), (tool(
        "get_tan", "Read the signing TAN from the mailbox. Call it right after you requested the TAN on this website, "
                   "with the request number or identifier the website showed for your request, so that the TAN of "
                   "exactly this request is used.",
        {"request": {"type": "string", "description": "The number the website gave your TAN request, copied from "
                                                      "the page (empty if it showed none)"}}), get_tan)]
    # no way to give up: in runs #8 and #9 the model reached for "failed" whenever a step looked hard, and the
    # advice it got then (omit what is open) cost run #9 a whole position and four checks
    finish = {"receipt": {"type": "string", "description": "The website's confirmation that the bid was submitted, "
                                                          "copied exactly from the page (e.g. its receipt number "
                                                          "line)"}}

    async def confirmed(args: dict) -> str | None:
        """finish() counts only when the confirmation the agent quotes is on the page; until then it is told what
        the page in front of it needs (on a position's step: that position's row)."""
        position = guard.step_position(site.full_view)
        if position in guard.rows and position not in guard.omitted:
            values = configurator.get(position) or {} if configurator else {}
            chain = " / ".join(f"{key} {value}" for key, value in values.items())
            return (f"The bid is not submitted yet, and this is a normal step: the form asks for position {position} "
                    f"now (the form's order differs from the table's). Enter its row: configurator values {chain or '(see the requirement)'}"
                    f", then {guard._row_text(position)}; then continue to the next step. Keep going until the website "
                    "confirms the submission, then call finish with that confirmation.")
        await site.view()
        quoted = re.sub(r"\s+", " ", args.get("receipt", "")).strip().lower()
        page_text = re.sub(r"\[\d+ [^\]]*\]", " ", site.full_view)  # without buttons, links and fields
        if len(quoted) < 6 or quoted not in re.sub(r"\s+", " ", page_text).lower():
            problems = guard.summary_problems(site.full_view)
            return ("The bid is not submitted yet: the page does not show that as the website's confirmation (a "
                    "button or link label does not count). Complete the remaining steps: every position the form "
                    "asks for, the conditions and declarations, then at the signing step request the TAN, call "
                    "get_tan(request=...), enter the TAN and confirm; then quote the confirmation exactly."
                    + (" The summary differs from the bid: " + "; ".join(problems) + "." if problems else ""))
        return None

    first_view = await site.view()
    # a signed partial bid scores, an unsigned one does not: well before the end, the rest is omitted and signed
    wrap_up = ("Less than three minutes are left. Stop entering positions now: omit every position you have not "
               "entered yet (with the form's option to omit a position), then go straight on: declarations, "
               "request the TAN, get_tan(request=...), enter it and confirm the bid. A signed partial bid scores; "
               "an unsigned one scores nothing.")
    agent = Agent("submit", prompts.BROWSER, tools, deadline, finish=finish, check=confirmed, effort="low",
                  warn_at=deadline - 180, warning=wrap_up)
    return await agent.run(prompts.submit(task["brief"], table(answer, omitted, configurator), first_view), max_steps=400)
