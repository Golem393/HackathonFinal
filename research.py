"""Phase-1 research sub-agents: each reads one website and returns facts in its contract shape (contracts.py).

The goals describe WHAT to find in terms of the bid rules every scenario shares (they come from the task brief), never
WHERE it is on a particular website: the final run uses other websites with other layouts.
"""
from contracts import MAIL_FORMAT, SPEC_FORMAT, TENDER_FORMAT

TENDER_RESEARCH_GOAL = """You research one public tender on this tender portal for our bid. Do NOT start or fill the bid
submission: another colleague does that later with your facts.

Tender reference: {reference}. Scenario date: {scenario_date}.

Find and copy exactly as shown:
1. The tender's positions (bill of quantities / Leistungsverzeichnis): number, description, quantity, unit (Stück,
   Satz, ...) and the specification requirement each position references. Documents may be files (CSV, TXT, ZIP),
   embedded frames or behind an expression of interest: use open_document for files, and express interest
   (Teilnahme bekunden) if the documents require it.
2. Do NOT read the bidder Q&A: a colleague reads it in parallel. Leave "clarifications" empty.
Note each finding with `note` as you go, and finish as soon as you have the positions. Finish with exactly this JSON
shape:
{format}"""

QA_GOAL = """You read ALL bidder questions and answers (Q&A, Bieterfragen, Rückfragen, Klarstellungen) of one public
tender on this tender portal, for our bid. Do NOT start or fill the bid submission, do not read other documents.

Tender reference: {reference}. Scenario date: {scenario_date}.

Open the tender's Q&A and read EVERY answer on EVERY page (use read_all_pages on the list's next-page control). Some
details (dates, full text) may only show after expanding a row or pressing a button: open them. For each answer copy:
number, date (as shown, with time and timezone), the answer verbatim, and what it does:
- a quantity change for a position (new total quantity, in the position's unit),
- a withdrawal (zurückziehen) of an earlier answer, by its number,
- a technical amendment: which specification revision and requirement, which attributes and values,
- assignments of keys for a position: Konditionsgruppe, packaging tariff (Verpackung), delivery commitment (Termin),
  shared setup pool (Rüstpool), project bonus plan, or similar,
- fees or other commercial statements (e.g. one-off setup costs for a position).
Finish only after the last page. Finish with exactly this JSON shape (positions empty, clarifications filled):
{format}"""

SPEC_GOAL = """You read the buyer's technical specification for our bid on this supplier portal.

Tender reference: {reference} (buyer: {buyer}). Scenario date: {scenario_date}.

1. Find the specification / data sheet for this tender. It may have several revisions and the portal may open an old
   one first: list the revisions you see and use only the revision marked current (gültig / aktuell / current).
   Superseded revisions do not apply.
2. From the current revision, copy every requirement (all pages of the requirement table): its id, catalogue group
   (Kataloggruppe), bore, stroke, operating pressure, mounting, certification, pieces per set if given, and whether
   the stroke is marked as usable travel (nutzbarer Weg). Copy values exactly; give numbers without units.
Note each finding with `note`. Finish with exactly this JSON shape:
{format}"""

MAIL_RESEARCH_GOAL = """You research our sales mailbox (webmail) for the bid on tender reference {reference}.
Scenario date: {scenario_date}. Only records for EXACTLY this reference count (look-alikes such as "{reference}-A" do
not); records dated after the scenario date never apply.

Find and copy verbatim (subject, sender, date, body), checking the inbox AND the archive, every result page:
1. This mailbox's own address (often shown as "logged in as" or as recipient).
2. Every discount approval (Rabattfreigabe) for this reference from the sales director (leitung@ + our mailbox
   domain), including any minimum order value it requires.
3. Every rule mail for this reference from these senders (local part @ our mailbox domain): Konditionsregeln from
   kalkulation@, Technikfreigabe from technik@, Verpackungstarife from logistik@, Terminfreigabe from logistik@,
   Devisenfixing from finanzen@, Rüstpools from kalkulation@, Projektbonus from finanzen@, Preisindizes from
   kalkulation@. Tables in the body: copy them as text.
Search works best with the reference plus one topic word (the search combines words with AND). Do not request a TAN.
Note each mail with `note`. Finish with exactly this JSON shape:
{format}"""

ERP_WARMUP_GOAL = """Log in to this ERP and get past any login, consent, notice or blocking check until its start or
menu page (transactions, search) is shown. Then call finish right away; do not search anything yet.
Finish with {"ready": true} or {"ready": false, "problem": "..."}."""


def tender_goal(reference: str, scenario_date: str) -> str:
    return TENDER_RESEARCH_GOAL.format(reference=reference, scenario_date=scenario_date, format=TENDER_FORMAT)


def qa_goal(reference: str, scenario_date: str) -> str:
    return QA_GOAL.format(reference=reference, scenario_date=scenario_date, format=TENDER_FORMAT)


def spec_goal(reference: str, buyer: str, scenario_date: str) -> str:
    return SPEC_GOAL.format(reference=reference, buyer=buyer, scenario_date=scenario_date, format=SPEC_FORMAT)


def mail_goal(reference: str, scenario_date: str) -> str:
    return MAIL_RESEARCH_GOAL.format(reference=reference, scenario_date=scenario_date, format=MAIL_FORMAT)
