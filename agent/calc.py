"""The bid calculation: every number in the answer comes from here, in exact decimals.

The model decides which facts apply (which tender, revision, material, mail, condition); this module applies the
brief's arithmetic to them. It knows the rules, never the data: everything arrives in `inputs`, built at run time
from what the investigators read on the websites.

Rounding is always HALF_UP to the cent. Python's round() rounds half to even and would lose cents.
"""
import math
import re
from datetime import datetime, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0")


def dec(value) -> Decimal | None:
    """A Decimal from a number or a string; German "1.234,56" and plain "1234.56" both work. None stays None.

    A locale tag next to the number decides its format: "238,098 (en-US)" is 238098 and "181.429 (de-DE)" is 181429,
    where the bare digits would be read as decimals."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    raw = str(value)
    text = re.sub(r"[^\d,.\-]", "", re.sub(r"\b[a-z]{2}[-_][A-Z]{2}\b", "", raw))
    if not re.search(r"\d", text):
        return None
    if re.search(r"\ben[-_]US\b", raw):  # comma groups thousands, dot marks decimals
        text = text.replace(",", "")
    elif re.search(r"\bde[-_]DE\b", raw):  # dot groups thousands, comma marks decimals
        text = text.replace(".", "").replace(",", ".")
    elif "," in text and "." in text:
        # whichever separator comes last is the decimal one
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(".", "").replace(",", ".") if text.count(",") == 1 else text.replace(",", "")
    elif text.count(".") > 1:  # "1.234.567": dots grouping thousands
        text = text.replace(".", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def whole(value) -> Decimal | None:
    """A count (pieces, a price unit, a minimum quantity, stock): "1.000" or "1,250 ST" group thousands here, where
    dec() would read a lone separator before three digits as decimals."""
    if isinstance(value, str) and not re.search(r"\b[a-z]{2}[-_][A-Z]{2}\b", value) \
            and re.fullmatch(r"\s*\d{1,3}(?:([.,])\d{3})(?:\1\d{3})*\s*[^\d.,]*", value):
        return Decimal(re.sub(r"[^\d]", "", value))
    return dec(value)


def tagged(value, number_format: str | None):
    """A scale value with the condition's number format attached when only that format can tell what it means
    ("181.429" per hundred in de-DE is 181429, not 181.429)."""
    if number_format and isinstance(value, str) and not re.search(r"\b[a-z]{2}[-_][A-Z]{2}\b", value) \
            and re.fullmatch(r"\s*[1-9]\d{0,2}[.,]\d{3}\s*", value):
        return f"{value} ({number_format})"
    return value


def kilograms(value) -> Decimal | None:
    """A mass in kilograms; one written in grams ("1250 g") is converted."""
    amount = dec(value)
    if amount is not None and isinstance(value, str) and re.search(r"\d\s*g\b", value) and "kg" not in value.lower():
        amount /= 1000
    return amount


def money(value: Decimal) -> Decimal:
    """Rounded HALF_UP to the cent."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def position_key(position: str):
    """Natural order of position numbers: "2" before "10", "1.2" before "1.10"."""
    return [(0, int(part), "") if part.isdigit() else (1, 0, part) for part in re.split(r"(\d+)", str(position)) if part]


def day(value) -> str | None:
    """The calendar date (YYYY-MM-DD) of an ISO date or timestamp, or of a German date (25.01.2027)."""
    if not value:
        return None
    text = str(value).strip()
    if match := re.match(r"(\d{4})-(\d{2})-(\d{2})", text):
        return "-".join(match.groups())
    if match := re.match(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", text):
        d, m, y = match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    return None


def stamp(value) -> str:
    """A sortable "YYYY-MM-DD HH:MM" from an ISO or a German date and time ("12.01.2027, 10:30"); an ISO time with
    an offset is taken to UTC first."""
    text = str(value or "")
    if re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})$", text.strip()):
        moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00")).astimezone(timezone.utc)
        return moment.strftime("%Y-%m-%d %H:%M")
    time_of_day = re.search(r"(?:T|\s|,)\s*(\d{1,2}):(\d{2})", text)
    clock = f"{int(time_of_day.group(1)):02d}:{time_of_day.group(2)}" if time_of_day else "00:00"
    return f"{day(text) or ''} {clock}"


def final_quantity(position: dict) -> int:
    """Rules 1, "withdrawn answers" and "units": the latest dated quantity change that was not withdrawn, else the
    tender quantity; sets are converted to pieces with the governing specification's pieces per set."""
    withdrawn = {str(number).strip() for number in position.get("withdrawn_qa_numbers") or []}
    changes = [change for change in position.get("quantity_changes") or []
               if str(change.get("qa_number", "")).strip() not in withdrawn and change.get("quantity") is not None]
    quantity = whole(position.get("tender_quantity")) or ZERO
    if changes:
        latest = max(changes, key=lambda change: stamp(change.get("date")))
        quantity = whole(latest["quantity"]) or quantity  # an unreadable change keeps the tender quantity
    pieces_per_set = whole(position.get("pieces_per_set"))
    if pieces_per_set and position.get("unit_is_set"):
        quantity *= pieces_per_set
    return int(quantity)


def scale_price(price: dict, quantity: int) -> Decimal | None:
    """Rule 4 and "currency": the scale with the highest minimum quantity no greater than the quantity, per piece
    (price unit normalised), converted to EUR and rounded HALF_UP to cents."""
    form = price.get("number_format")
    scales = [(whole(tagged(scale.get("min_quantity"), form)) or ZERO, dec(tagged(scale.get("price"), form)))
              for scale in price.get("scales") or []]
    scales = [(minimum, amount) for minimum, amount in scales if amount is not None and minimum <= quantity]
    if not scales:
        return None
    _, amount = max(scales, key=lambda scale: scale[0])
    per_piece = amount / (whole(price.get("price_unit")) or Decimal(1))
    currency = (price.get("currency") or "EUR").strip().upper()
    if currency != "EUR":
        rate = dec(price.get("eur_per_currency_unit"))
        if rate is None:
            return None
        per_piece *= rate
    return money(per_piece)


def metal_rate(index: dict | None, scenario_day: str | None) -> Decimal | None:
    """"Metal indices": the rate whose inclusive validity window contains the scenario date; a rate without a window
    applies when no windowed rate does."""
    if not index:
        return None
    rates = index.get("rates") or []
    for rate in rates:
        start, end = day(rate.get("valid_from")), day(rate.get("valid_to"))
        if (start or end) and scenario_day and (not start or start <= scenario_day) and (not end or scenario_day <= end):
            return dec(rate.get("eur_per_kg"))
    unwindowed = [rate for rate in rates if not rate.get("valid_from") and not rate.get("valid_to")]
    return dec(unwindowed[-1].get("eur_per_kg")) if unwindowed else None


def allocate(total: Decimal, weights: dict[str, Decimal], method: str = "largest_remainder") -> dict[str, Decimal]:
    """Split `total` (in cents) over the keys by weight. Every method floors each share to the cent first; the cents
    left over go by the largest remainders (ties: ascending position), all to the largest share, or all to the first
    or the last position."""
    keys = sorted(weights, key=position_key)
    weight_sum = sum(weights.values())
    if not keys or weight_sum <= 0:
        return {key: ZERO for key in keys}
    exact = {key: total * weights[key] / weight_sum for key in keys}
    shares = {key: exact[key].quantize(CENT, rounding=ROUND_DOWN) for key in keys}
    left = int((total - sum(shares.values())) / CENT)
    if method == "remainder_to_largest_share":
        receivers = [min(keys, key=lambda key: (-exact[key], position_key(key)))] * left
    elif method == "remainder_to_first":
        receivers = [keys[0]] * left
    elif method == "remainder_to_last":
        receivers = [keys[-1]] * left
    else:
        by_remainder = sorted(keys, key=lambda key: (-(exact[key] - shares[key]), position_key(key)))
        receivers = by_remainder[:left]
    for key in receivers:
        shares[key] += CENT
    return shares


def project_bonus(bands: list[dict], goods_total: Decimal) -> Decimal:
    """"Project bonus": marginal bands, each percentage applied only to its portion of the goods total, rounded
    HALF_UP once."""
    credit = ZERO
    for band in bands:
        start = dec(band.get("from_eur")) or ZERO
        end = dec(band.get("to_eur"))
        top = goods_total if end is None else min(goods_total, end)
        if top > start:
            credit += (top - start) * (dec(band.get("percent")) or ZERO) / 100
    return money(credit)


def compute(inputs: dict) -> tuple[dict, list[str]]:
    """The answer and a log of how each number came about."""
    log: list[str] = []
    reference = inputs["tender_reference"]
    scenario_day = day(inputs.get("scenario_date"))
    approval = inputs.get("discount_approval") or {}
    percent = dec(approval.get("percent")) or ZERO

    if inputs.get("decision") == "no_bid":
        conditional = dec(approval.get("min_order_value_eur")) is not None
        discount = ZERO if conditional else percent
        log.append(f"no_bid: {inputs.get('decision_reason', '')}")
        return {"tender_reference": reference, "decision": "no_bid", "currency": "EUR",
                "discount_percent": float(discount), "positions": [], "total_net": 0.0}, log

    lines = []
    for position in sorted(inputs.get("positions") or [], key=lambda p: position_key(p["position"])):
        quantity = final_quantity(position)
        material = position.get("material_number")
        base = scale_price(position.get("price") or {}, quantity) if quantity and material else None
        if not quantity:
            log.append(f"position {position['position']}: omitted (no quantity)")
            continue
        # entered even without a material or a valid price (unit price zero): every field scores on its own, so
        # the known quantity (and material, lead time) still count, while an omitted position scores nothing
        lines.append({**position, "quantity": quantity, "base": base})
        log.append(f"position {position['position']}: {quantity} pieces of {material}, base {base} EUR"
                   + ("" if base is not None else " (no valid price found: unit price 0)"))
    priced = [line for line in lines if line["base"] is not None]

    # "Conditional discount": the undiscounted net order value against the approval's inclusive threshold. With
    # prices missing the value is unknown, and the approved percentage is the best estimate.
    order_value = money(sum((line["base"] * line["quantity"] for line in priced), ZERO))
    threshold = dec(approval.get("min_order_value_eur"))
    if threshold is None or order_value >= threshold or not priced or len(priced) < len(lines):
        discount = percent
    else:
        discount = ZERO
    log.append(f"discount {discount} % (approved {percent} %, threshold {threshold}, order value {order_value}"
               f"{'' if len(priced) == len(lines) else ', some prices missing'})")
    rate = 1 - discount / 100

    metal = metal_rate(inputs.get("metal_index"), scenario_day)
    log.append(f"metal rate {metal} EUR/kg on {scenario_day}")

    # "Shared setup": one fee per pool, split by quantity x allocation mass
    pool_share: dict[str, Decimal] = {}
    for pool in inputs.get("setup_pools") or []:
        members = {line["position"]: line["quantity"] * (kilograms(line.get("allocation_mass_kg")) or ZERO)
                   for line in lines if line.get("setup_pool_key") == pool.get("key")}
        shares = allocate(dec(pool.get("fee_eur")) or ZERO, members, pool.get("allocation") or "largest_remainder")
        pool_share.update(shares)
        log.append(f"setup pool {pool.get('key')}: {dict((k, str(v)) for k, v in shares.items())}")

    # "Project bonus": on the eligible undiscounted goods total, split by largest remainder
    bonus_share: dict[str, Decimal] = {}
    bonus = inputs.get("project_bonus") or {}
    eligible = {line["position"]: line["base"] * line["quantity"] for line in priced if line.get("project_bonus_member")}
    if bonus.get("bands") and eligible:
        credit = project_bonus(bonus["bands"], sum(eligible.values(), ZERO))
        bonus_share = allocate(credit, eligible)
        log.append(f"project bonus {credit} EUR: {dict((k, str(v)) for k, v in bonus_share.items())}")

    # "Shared stock" and "delivery": demand pooled per material
    demand: dict[str, int] = {}
    for line in lines:
        if line.get("material_number"):
            demand[line["material_number"]] = demand.get(line["material_number"], 0) + line["quantity"]

    positions, total = [], ZERO
    for line in lines:
        key, quantity = line["position"], line["quantity"]
        # "Commercial clauses": only a condition group changes the default base-only discount
        scope = (line.get("discount_scope") or "base_only") if line.get("condition_group") else "base_only"
        base = line["base"]
        mass = (kilograms(line.get("surcharge_mass_kg")) or ZERO) * (metal or ZERO)
        setup = (dec(line.get("setup_fee")) or ZERO) + pool_share.get(key, ZERO)
        per_carton = dec(line.get("carton_tariff_eur"))
        carton_size = whole(line.get("pieces_per_carton"))
        packaging = (Decimal(math.ceil(quantity / carton_size)) * per_carton
                     if per_carton is not None and carton_size else ZERO)
        credit = bonus_share.get(key, ZERO)

        # "Final price": from unrounded parts, rounded once
        if base is None:
            discounted_base = discounted_mass = unit_price = ZERO
        else:
            discounted_base = base * rate if scope in ("base_only", "base_and_surcharge") else base
            discounted_mass = mass * rate if scope == "base_and_surcharge" else mass
            unit_price = money(discounted_base + discounted_mass + (setup + packaging - credit) / quantity)
        total += quantity * unit_price

        answer = {"position": str(key), "material_number": line["material_number"], "quantity": quantity,
                  "unit_price": float(unit_price), "lead_time_weeks": lead_time(line, demand)}
        # the breakdown fields score on their own and a wrong value costs nothing, so they are always filled
        answer.update(base_unit_price=None if base is None else float(base),
                      surcharge_per_unit=float(money(mass + setup / quantity)),
                      packaging_per_unit=float(money(packaging / quantity)), rebate_total=float(credit))
        positions.append(answer)
        log.append(f"position {key}: unit {unit_price} = base {discounted_base} ({base}, {scope}) + mass "
                   f"{discounted_mass} + (setup {setup} + packaging {packaging} - bonus {credit}) / {quantity}; "
                   f"lead {answer['lead_time_weeks']} weeks")

    return {"tender_reference": reference, "decision": "bid", "currency": "EUR",
            "discount_percent": float(discount), "positions": positions,
            "total_net": float(money(total))}, log


def lead_time(line: dict, demand: dict[str, int]) -> int | None:
    """Rule 6, "shared stock" and "delivery": a matching commitment within its ceiling, else stock delivery when stock
    covers the whole pooled demand for the material, else production. None when nothing is known."""
    pooled = demand.get(line.get("material_number"), line["quantity"])
    commitment = line.get("delivery_commitment") or {}
    ceiling = whole(commitment.get("ceiling_pieces"))
    if (weeks_of(commitment.get("lead_time_weeks")) is not None
            and commitment.get("material_number") == line["material_number"]
            and (ceiling is None or pooled <= ceiling)):
        return weeks_of(commitment["lead_time_weeks"])
    stock = whole(line.get("stock"))
    if stock is not None and stock >= pooled and weeks_of(line.get("stock_lead_time_weeks")) is not None:
        return weeks_of(line["stock_lead_time_weeks"])
    weeks = weeks_of(line.get("production_lead_time_weeks"))
    return weeks if weeks is not None else weeks_of(line.get("stock_lead_time_weeks"))


def weeks_of(value) -> int | None:
    """Whole weeks from 3, "3", "3.0" or "3 Wochen"; a fraction rounds up (a promise cannot be early)."""
    amount = dec(value)
    return None if amount is None else int(math.ceil(amount))


def german(value, decimals: int = 2) -> str:
    """A number as the German forms want it: 1234.5 -> "1.234,50"."""
    amount = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    whole, _, fraction = f"{amount:,.{decimals}f}".partition(".")
    whole = whole.replace(",", ".")
    return f"{whole},{fraction}" if decimals else whole
