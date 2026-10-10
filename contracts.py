"""Data contracts between the sub-agents, the calculator and the submission agent.

Every research agent returns facts in one of the shapes below, copied as the websites show them (no arithmetic, no
interpretation beyond what the field asks for). The calculator (calculator.py) turns them into bid values. Keeping
these shapes stable lets each part be built and tested on its own.

The *_FORMAT strings are what the agents are shown; the TypedDicts are the same shapes for the code.
"""
from typing import TypedDict


# ---- Tender portal (tender_research) ---------------------------------------------------------------------------

class TenderPosition(TypedDict, total=False):
    position: str              # position number as the portal shows it, e.g. "01.03"
    description: str
    quantity: float            # original tender quantity, in `unit`
    unit: str                  # e.g. "Stück", "Satz"
    requirement: str           # specification requirement it references, e.g. "A-2"


class Clarification(TypedDict, total=False):
    number: str                # Q&A answer number
    date: str                  # as shown, with time and timezone if given
    text: str                  # the answer, verbatim
    position: str | None       # position it concerns, if any
    new_quantity: float | None # quantity change for that position, in the position's unit
    withdraws: str | None      # number of an earlier answer this one withdraws (zurückziehen)
    amendment: dict | None     # {"revision": "...", "requirement": "...", "attributes": {"stroke_mm": 410, ...}}
    keys: dict | None          # assignments it makes, e.g. {"konditionsgruppe": "K2", "verpackung": "V1",
                               #  "termin": "T3", "ruestpool": ["01.01", "01.04"]}


class TenderFacts(TypedDict, total=False):
    reference: str
    title: str
    deadline: str
    positions: list[TenderPosition]
    clarifications: list[Clarification]
    problems: str


TENDER_FORMAT = """{
  "reference": "<tender reference>", "title": "...", "deadline": "<as shown, with timezone>",
  "positions": [{"position": "<number as shown>", "description": "...", "quantity": <number>, "unit": "<Stück/Satz/...>",
                 "requirement": "<specification requirement it references, e.g. A-1>"}],
  "clarifications": [{"number": "<Q&A number>", "date": "<as shown>", "text": "<answer verbatim>",
                      "position": "<position or null>", "new_quantity": <number or null>,
                      "withdraws": "<number of the answer it withdraws, or null>",
                      "amendment": {"revision": "...", "requirement": "...", "attributes": {"<attribute>": <value>}} or null,
                      "keys": {"<key type, e.g. konditionsgruppe / verpackung / termin / ruestpool>": "<value>"} or null}],
  "problems": "<anything unclear or not found>"
}"""


# ---- Supplier portal (spec) ------------------------------------------------------------------------------------

class Requirement(TypedDict, total=False):
    id: str                    # e.g. "A-1"
    catalogue_group: str       # Kataloggruppe
    bore_mm: float
    stroke_mm: float
    usable_stroke: bool        # marked "nutzbarer Weg": stroke is usable travel, reserve is added later
    pressure_bar: float
    mounting: str
    certification: str
    pieces_per_set: float | None


class SpecFacts(TypedDict, total=False):
    current_revision: str
    revisions_seen: list[str]
    requirements: list[Requirement]
    problems: str


SPEC_FORMAT = """{
  "current_revision": "<the revision marked current>", "revisions_seen": ["<all revisions listed, with status>"],
  "requirements": [{"id": "<e.g. A-1>", "catalogue_group": "<Kataloggruppe>", "bore_mm": <n>, "stroke_mm": <n>,
                    "usable_stroke": <true if the stroke is marked nutzbarer Weg>, "pressure_bar": <n>,
                    "mounting": "...", "certification": "...", "pieces_per_set": <n or null>}],
  "problems": "..."
}"""


# ---- Webmail (mail_research) -----------------------------------------------------------------------------------

class Approval(TypedDict, total=False):
    sender: str
    date: str
    reference: str             # the exact reference the mail names
    percent: float
    min_order_value: float | None   # minimum undiscounted net order value, if the approval is conditional
    text: str


class RuleMail(TypedDict, total=False):
    kind: str                  # Konditionsregeln, Technikfreigabe, Verpackungstarife, Terminfreigabe, Devisenfixing,
                               # Rüstpools, Projektbonus, Preisindizes
    sender: str
    date: str
    reference: str
    text: str                  # body verbatim (tables as text)


class MailFacts(TypedDict, total=False):
    mailbox_address: str       # this mailbox's own address
    bidder_domain: str         # the part after @
    approvals: list[Approval]
    rule_mails: list[RuleMail]
    problems: str


MAIL_FORMAT = """{
  "mailbox_address": "<this mailbox's own address>", "bidder_domain": "<domain after @>",
  "approvals": [{"sender": "...", "date": "<as shown>", "reference": "<exact reference in the mail>", "percent": <n>,
                 "min_order_value": <n or null>, "text": "<body verbatim>"}],
  "rule_mails": [{"kind": "<Konditionsregeln/Technikfreigabe/Verpackungstarife/Terminfreigabe/Devisenfixing/Rüstpools/Projektbonus/Preisindizes>",
                  "sender": "...", "date": "<as shown>", "reference": "<exact reference>", "text": "<body verbatim>"}],
  "problems": "..."
}"""


# ---- ERP (erp_position) ----------------------------------------------------------------------------------------
# The ERP agent's format lives in erp_agent.RESULT_FORMAT (one result per position).


# ---- Calculator output, input of the submission agent ----------------------------------------------------------

class BidPosition(TypedDict, total=False):
    position: str
    material_number: str
    quantity: int              # final pieces
    unit_price: float          # final net EUR per piece, rounded half up to cents
    lead_time_weeks: int
    base_unit_price: float | None
    surcharge_per_unit: float | None
    packaging_per_unit: float | None
    rebate_total: float | None


class Bid(TypedDict, total=False):
    tender_reference: str
    decision: str              # "bid" | "no_bid"
    currency: str              # "EUR"
    discount_percent: float
    positions: list[BidPosition]     # only finished positions; the others are omitted on the form
    omitted: list[str]               # positions to omit explicitly (Position auslassen)
    total_net: float
    notes: str
