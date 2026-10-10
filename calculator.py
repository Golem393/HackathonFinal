"""The bid calculator: research facts in (contracts.py), bid values out. Pure Python, no model, no browser.

Implemented (rules of the brief): final quantities with withdrawn answers and Satz conversion, scoped amendments of
requirements, valid price condition and quantity scale, director discount with its minimum-order threshold, shared
stock lead times, half-up rounding, total, no_bid when a position has no matching material.

Not implemented yet (TODO, see `advanced_components`): commercial clauses (Konditionsgruppe), mass surcharge with metal
indices, packaging cartons, shared setup pools, project bonus, currency conversion, usable-stroke reserve. Positions
that need one of them get `missing` entries instead of a guessed value; their unit price then uses only what is known.

Money is Decimal throughout and rounded HALF_UP to cents only where the rules say so.
"""
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from contracts import Bid, BidPosition, MailFacts, Requirement, SpecFacts, TenderFacts

CENT = Decimal("0.01")
REQUIREMENT_KEYS = ("bore_mm", "stroke_mm", "pressure_bar", "mounting", "certification")


# ---- parsing helpers ---------------------------------------------------------------------------------------------

def num(value) -> Decimal | None:
    """A number as the websites write it: 1.234,56 / 1234.56 / '12,5 %' / 'EUR 3.400,00' -> Decimal."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = re.sub(r"[^\d,.\-]", "", str(value))
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    elif text.count(".") > 1 or re.fullmatch(r"-?\d{1,3}\.\d{3}", text):
        text = text.replace(".", "")   # German thousands separator (the sites write decimals with a comma)
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def day(value) -> date | None:
    """A date as shown: 2027-01-24, 24.01.2027, 24.01.27, 01/24/2027 (US order when written with a slash)."""
    if not value:
        return None
    text = str(value)
    for pattern, order in ((r"(\d{4})-(\d{2})-(\d{2})", "ymd"), (r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})", "dmy"),
                           (r"(\d{1,2})/(\d{1,2})/(\d{2,4})", "mdy")):
        m = re.search(pattern, text)
        if m:
            parts = dict(zip(order, (int(g) for g in m.groups())))
            year = parts["y"] + 2000 if parts["y"] < 100 else parts["y"]
            try:
                return date(year, parts["m"], parts["d"])
            except ValueError:
                return None
    return None


def stamp(value) -> datetime:
    """Sortable timestamp of a dated record (date plus time when given); unknown dates sort first."""
    d = day(value) or date.min
    m = re.search(r"(\d{1,2}):(\d{2})", str(value or ""))
    return datetime(d.year, d.month, d.day, int(m.group(1)) if m else 0, int(m.group(2)) if m else 0)


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


# ---- rules -------------------------------------------------------------------------------------------------------

def final_quantities(tender: TenderFacts, spec: SpecFacts) -> dict[str, Decimal]:
    """Rule 1 + withdrawn answers + units: latest remaining quantity change per position, in pieces."""
    clarifications = sorted(tender.get("clarifications") or [], key=lambda c: stamp(c.get("date")))
    withdrawn = {str(c["withdraws"]) for c in clarifications if c.get("withdraws")}
    requirements = {r.get("id"): r for r in spec.get("requirements") or []}
    result = {}
    for position in tender.get("positions") or []:
        pid = position.get("position")
        quantity = num(position.get("quantity"))
        for c in clarifications:
            if c.get("position") == pid and c.get("new_quantity") is not None and str(c.get("number")) not in withdrawn:
                quantity = num(c["new_quantity"])
        if quantity is not None and "satz" in str(position.get("unit", "")).lower():
            per_set = num((requirements.get(position.get("requirement")) or {}).get("pieces_per_set"))
            quantity = quantity * per_set if per_set else None   # unknown set size: leave the quantity open
        result[pid] = quantity
    return result


def final_requirements(tender: TenderFacts, spec: SpecFacts) -> dict[str, Requirement]:
    """Rule 2 + scoped amendments: the current revision's requirements with the latest amendment per attribute that
    names that revision and requirement. (The usable-stroke reserve is added later: see advanced_components.)"""
    current = str(spec.get("current_revision") or "").strip().lower()
    result = {r["id"]: dict(r) for r in spec.get("requirements") or [] if r.get("id")}
    amendments = sorted((c for c in tender.get("clarifications") or [] if c.get("amendment")),
                        key=lambda c: stamp(c.get("date")))
    withdrawn = {str(c["withdraws"]) for c in tender.get("clarifications") or [] if c.get("withdraws")}
    for c in amendments:
        a = c["amendment"]
        if str(c.get("number")) in withdrawn or str(a.get("revision", "")).strip().lower() != current:
            continue
        if a.get("requirement") in result:
            result[a["requirement"]].update(a.get("attributes") or {})
    return result


def valid_condition(conditions: list[dict], on: date) -> dict | None:
    """Rule 4: the price condition valid on the scenario date, both endpoints inclusive."""
    valid = [c for c in conditions or []
             if (day(c.get("valid_from")) or date.min) <= on <= (day(c.get("valid_to")) or date.max)
             and "inaktiv" not in str(c.get("status", "")).lower()]
    return valid[-1] if valid else None


def scale_price(condition: dict, quantity: Decimal) -> Decimal | None:
    """Rule 4: the scale with the highest minimum quantity not above the final quantity, per piece."""
    scales = sorted(((num(s.get("from_quantity")) or Decimal(0), num(s.get("price"))) for s in condition.get("scales") or []
                     if num(s.get("price")) is not None), key=lambda s: s[0])
    price = None
    for minimum, value in scales:
        if minimum <= quantity:
            price = value
    if price is None:
        return None
    per = re.search(r"(\d[\d.]*)", str(condition.get("price_unit") or ""))   # "per 100 Stück" -> 100
    divisor = num(per.group(1)) if per else Decimal(1)
    return price / (divisor or Decimal(1))


def approved_discount(mail: MailFacts, reference: str, on: date, undiscounted_net: Decimal | None) -> Decimal:
    """Rules 5 + conditional discount: latest exact-reference approval from leitung@<our domain> up to the scenario
    date; a failed minimum order value means 0 % (no fallback to older approvals)."""
    domain = (mail.get("bidder_domain") or str(mail.get("mailbox_address", "")).split("@")[-1]).lower()
    approvals = [a for a in mail.get("approvals") or []
                 if str(a.get("reference", "")).strip() == reference
                 and str(a.get("sender", "")).lower().startswith("leitung@")
                 and (not domain or str(a.get("sender", "")).lower().endswith("@" + domain))
                 and (day(a.get("date")) or date.min) <= on]
    if not approvals:
        return Decimal(0)
    latest = max(approvals, key=lambda a: stamp(a.get("date")))
    minimum = num(latest.get("min_order_value"))
    if minimum is not None and (undiscounted_net is None or undiscounted_net < minimum):
        return Decimal(0)
    return num(latest.get("percent")) or Decimal(0)


def lead_times(chosen: dict[str, str], quantities: dict[str, Decimal], erp: dict[str, dict]) -> dict[str, int | None]:
    """Rule 6 + shared stock: stock must cover the summed quantity of all positions with the same material."""
    demand: dict[str, Decimal] = {}
    for pid, material in chosen.items():
        demand[material] = demand.get(material, Decimal(0)) + (quantities.get(pid) or Decimal(0))
    result = {}
    for pid, material in chosen.items():
        facts = erp.get(pid) or {}
        stock = num(facts.get("stock_available_pieces"))
        weeks = facts.get("lead_time_from_stock_weeks") if stock is not None and stock >= demand[material] \
            else facts.get("lead_time_production_weeks")
        result[pid] = int(num(weeks)) if num(weeks) is not None else None
    return result


def advanced_components(pid: str, facts: dict, tender: TenderFacts, mail: MailFacts) -> dict:
    """TODO (teammate): per-piece components beyond the scale price, each BEFORE discount unless stated:
    surcharge (mass x metal index from Preisindizes), packaging (ceil(pieces / carton) x tariff from Verpackungstarife),
    ordinary + allocated shared setup fee (Rüstpools), project bonus credit (Projektbonus bands), discount scope per
    Konditionsgruppe (Konditionsregeln), currency conversion (Devisenfixing). Return what is known, e.g.
    {"surcharge": Decimal, "packaging_total": Decimal, "setup_total": Decimal, "rebate_total": Decimal,
     "discount_on_surcharge": bool, "missing": [...]}."""
    return {"missing": ["surcharge", "packaging", "setup", "project_bonus", "discount_clause", "currency"]}


# ---- the bid -----------------------------------------------------------------------------------------------------

def compute_bid(reference: str, scenario_date: str, tender: TenderFacts, spec: SpecFacts, mail: MailFacts,
                erp: dict[str, dict]) -> Bid:
    """All rules together. `erp` maps position -> the ERP agent's result for it."""
    on = day(scenario_date) or date.today()
    quantities = final_quantities(tender, spec)
    positions = [p.get("position") for p in tender.get("positions") or []]
    notes = []

    # Decision: a position whose ERP search completed without an exact active match means no_bid.
    for pid in positions:
        facts = erp.get(pid) or {}
        if facts and not facts.get("incomplete") and not facts.get("error") and facts.get("material_number") is None:
            return Bid(tender_reference=reference, decision="no_bid", currency="EUR", discount_percent=0.0,
                       positions=[], omitted=[], total_net=0.0, notes=f"no matching active material for {pid}")

    chosen = {pid: (erp.get(pid) or {}).get("material_number") for pid in positions}
    chosen = {pid: m for pid, m in chosen.items() if m}
    base = {}
    for pid in chosen:
        condition = valid_condition((erp.get(pid) or {}).get("price_conditions") or [], on)
        if condition and quantities.get(pid) is not None and str(condition.get("currency") or "EUR").upper() in ("EUR", "€", ""):
            base[pid] = scale_price(condition, quantities[pid])
        else:
            notes.append(f"{pid}: no valid EUR price condition (currency conversion not implemented)")
    undiscounted = cents(sum((quantities[p] * cents(b) for p, b in base.items() if b is not None), Decimal(0))) \
        if base and len(base) == len(chosen) else None
    discount = approved_discount(mail, reference, on, undiscounted)
    weeks = lead_times(chosen, quantities, erp)

    bid_positions: list[BidPosition] = []
    for pid in positions:
        price = base.get(pid)
        if pid not in chosen or price is None or quantities.get(pid) is None or weeks.get(pid) is None:
            continue
        extra = advanced_components(pid, erp.get(pid) or {}, tender, mail)
        unit = cents(price * (1 - discount / 100))
        bid_positions.append(BidPosition(
            position=pid, material_number=chosen[pid], quantity=int(quantities[pid]), unit_price=float(unit),
            lead_time_weeks=weeks[pid], base_unit_price=float(cents(price)),
            surcharge_per_unit=None, packaging_per_unit=None, rebate_total=None))
        if extra.get("missing"):
            notes.append(f"{pid}: not yet computed: {', '.join(extra['missing'])}")
    done = {p["position"] for p in bid_positions}
    total = cents(sum((Decimal(p["quantity"]) * Decimal(str(p["unit_price"])) for p in bid_positions), Decimal(0)))
    return Bid(tender_reference=reference, decision="bid", currency="EUR", discount_percent=float(discount),
               positions=bid_positions, omitted=[p for p in positions if p not in done], total_net=float(total),
               notes="; ".join(notes))
