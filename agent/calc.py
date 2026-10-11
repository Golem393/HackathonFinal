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


DOT_LOCALES = {"en", "ja", "zh", "ko", "he", "th"}
DOT_REGIONS = {"de-ch", "de-li", "it-ch", "es-mx"}
TAG = re.compile(r"\b([a-z]{2})[-_]([a-z]{2})\b", re.I)
IDENTIFIER = re.compile(r"\b[A-Za-z]+[-_]?\d[\w-]*")  # e.g. IDX-7001, QX-11: names, not numbers
NUMBER = re.compile(r"-?\d{1,3}(?:[ \u00a0\u202f']\d{3})+(?:[.,]\d+)?|-?\d[\d.,]*")


def decimal_mark(raw: str) -> str | None:
    """The decimal mark a text states: by a locale tag ("(en-US)", "de-at", any case) or a word ("Dezimalkomma",
    "decimal point"); None when it states none."""
    if re.search(r"dezimalpunkt|decimal point|englisch|english", raw, re.I):
        return "."
    if re.search(r"dezimalkomma|decimal comma|deutsch|german", raw, re.I):
        return ","
    tag = TAG.search(raw)
    if tag:
        language, region = tag.group(1).lower(), f"{tag.group(1)}-{tag.group(2)}".lower()
        return "." if language in DOT_LOCALES or region in DOT_REGIONS else ","
    return None


def dec(value) -> Decimal | None:
    """A Decimal from a number or a string; German "1.234,56" and plain "1234.56" both work. None stays None.

    A locale tag or a word next to the number decides its format: "317,205 (en-US)" is 317205 and "142.736 (de-DE)"
    is 142736, where the bare digits would be read as decimals. Identifiers are not numbers ("IDX-7001: 4,62" is 4.62)
    and of "a = b" the right side counts ("1 Satz = 5 Stück" is 5)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    raw = str(value)
    mark = decimal_mark(raw)
    body = IDENTIFIER.sub(" ", TAG.sub(" ", raw))
    if "=" in body:
        body = body.rsplit("=", 1)[1]
    token = NUMBER.search(body)
    if not token:
        return None
    text = re.sub(r"[ \u00a0\u202f']", "", token.group())
    if mark and re.search(r"\%s(?!\d{3}(?:\D|$))" % ("." if mark == "," else ","), text):
        mark = None  # "1.2345 (from the German format)": a separator the stated format groups by, without 3 digits
    if mark == ".":  # comma groups thousands, dot marks decimals
        text = text.replace(",", "")
    elif mark == ",":  # dot groups thousands, comma marks decimals
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
        return Decimal(text.rstrip(".,") or "x")
    except InvalidOperation:
        return None


def whole(value) -> Decimal | None:
    """A count (pieces, a price unit, a minimum quantity, stock): "1.000" or "1,250 ST" group thousands here, where
    dec() would read a lone separator before three digits as decimals."""
    if isinstance(value, str) and not TAG.search(value) \
            and re.fullmatch(r"\s*\d{1,3}(?:([.,])\d{3})(?:\1\d{3})*\s*[^\d.,]*", value):
        return Decimal(re.sub(r"[^\d]", "", value))
    return dec(value)


def tagged(value, number_format: str | None):
    """A scale value with the condition's number format attached when only that format can tell what it means
    ("142.736" per hundred in de-DE is 142736, not 142.736)."""
    if number_format and isinstance(value, str) and not TAG.search(value) \
            and re.fullmatch(r"\s*[1-9]\d{0,2}[.,]\d{3}\s*", value):
        return f"{value} ({number_format})"
    return value


def kilograms(value) -> Decimal | None:
    """A mass in kilograms, by the unit written after the number: grams ("1.250 g" is 1.25 kg), milligrams, tonnes;
    kilograms or no unit as they are."""
    if not isinstance(value, str):
        return dec(value)
    unit = re.search(r"\d\s*(mg|kg|kilogramm\w*|g|gr|gramm\w*|grams?|t|tonnen?|tons?)\b", value, re.I)
    name = unit.group(1).lower() if unit else ""
    if name in ("g", "gr") or name.startswith("gramm") or name.startswith("gram"):
        amount = whole(value)
        return None if amount is None else amount / 1000
    amount = dec(value)
    if amount is None:
        return None
    if name == "mg":
        return amount / 1000000
    if name in ("t", "tonne", "tonnen", "ton", "tons"):
        return amount * 1000
    return amount


def money(value: Decimal) -> Decimal:
    """Rounded HALF_UP to the cent."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def position_key(position: str):
    """Natural order of position numbers: "2" before "10", "1.2" before "1.10"."""
    return [(0, int(part), "") if part.isdigit() else (1, 0, part) for part in re.split(r"(\d+)", str(position)) if part]


MONTHS = {name: number for number, names in enumerate((
    ("januar", "january", "jan", "jän"), ("februar", "february", "feb"), ("märz", "maerz", "march", "mar", "mär"),
    ("april", "apr"), ("mai", "may"), ("juni", "june", "jun"), ("juli", "july", "jul"), ("august", "aug"),
    ("september", "sept", "sep"), ("oktober", "october", "okt", "oct"), ("november", "nov"),
    ("dezember", "december", "dez", "dec")), 1) for name in names}


def day(value) -> str | None:
    """The calendar date (YYYY-MM-DD) of an ISO date or timestamp, a German date (25.01.2027, 25.01.27), a date
    with a weekday in front ("Mo, 25.01.2027"), with a month name ("25. Januar 2027", "Jan 25, 2027") or with
    slashes in year-first order (2027/01/25). Day-month order of other slashed dates is left to the model."""
    if not value:
        return None
    text = str(value).strip()
    if match := re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text):
        y, m, d = match.groups()
        return f"{y}-{int(m):02d}-{int(d):02d}"
    if match := re.search(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})(?![\d])", text):
        d, m, y = match.groups()
        return f"{'20' + y if len(y) == 2 else y}-{int(m):02d}-{int(d):02d}"
    if match := re.search(r"(?<!\d)(\d{1,2})\.?\s+([A-Za-zÄÖÜäöü]{3,9})\.?\s+(\d{4})", text):
        d, name, y = match.groups()
        if name.lower() in MONTHS:
            return f"{y}-{MONTHS[name.lower()]:02d}-{int(d):02d}"
    if match := re.search(r"([A-Za-zÄÖÜäöü]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", text):
        name, d, y = match.groups()
        if name.lower() in MONTHS:
            return f"{y}-{MONTHS[name.lower()]:02d}-{int(d):02d}"
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


ISO_ZONED = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})$")


def _after(date, scenario_day: str | None, scenario_date=None) -> bool:
    """Whether a record is dated after the scenario: to the minute when both carry a time zone, else by day (a local
    time without a zone must not be filtered out on the scenario day itself)."""
    if scenario_date and ISO_ZONED.match(str(date or "").strip()) and ISO_ZONED.match(str(scenario_date).strip()):
        return stamp(date) > stamp(scenario_date)
    when = day(date)
    return bool(scenario_day and when and when > scenario_day)


def final_quantity(position: dict, scenario_day: str | None = None, scenario_date=None) -> int:
    """Rules 1, "withdrawn answers" and "units": the latest dated quantity change that was not withdrawn, else the
    tender quantity; sets are converted to pieces with the governing specification's pieces per set. A change dated
    after the scenario date has not happened yet ("authority and time")."""
    withdrawn = {str(number).strip() for number in position.get("withdrawn_qa_numbers") or []}
    changes = [change for change in position.get("quantity_changes") or []
               if str(change.get("qa_number", "")).strip() not in withdrawn and change.get("quantity") is not None
               and not _after(change.get("date"), scenario_day, scenario_date)]
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
        rate = eur_per_unit(price, currency)
        if rate is None:
            return None
        per_piece *= rate
    return money(per_piece)


def eur_per_unit(price: dict, currency: str) -> Decimal | None:
    """EUR per unit of the condition's currency: as given, or from a quote the other way round (units per EUR), or
    from a written fixing "1 XYZ = 1,2345 EUR" / "1 EUR = 0,8100 XYZ"."""
    given = price.get("eur_per_currency_unit")
    fixing = re.search(r"(\d[\d.,]*)\s*([A-Z]{3})\s*=\s*(\d[\d.,]*)\s*([A-Z]{3})",
                       IDENTIFIER.sub(" ", str(given or "")).upper())  # the first written equation counts
    if fixing:
        a, b = dec(fixing[1]), dec(fixing[3])
        if a and b:
            if fixing[4] == "EUR" and fixing[2] != "EUR":
                return b / a
            if fixing[2] == "EUR":
                return a / b
    rate = dec(given)
    if rate:
        return rate
    inverse = dec(price.get("currency_per_eur"))
    return Decimal(1) / inverse if inverse else None


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
        quantity = final_quantity(position, scenario_day, inputs.get("scenario_date"))
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
    """Whole weeks from 3, "3", "3.0" or "3 Wochen"; days become weeks ("14 Tage" is 2, "10 Arbeitstage" is 2); a
    fraction rounds up (a promise cannot be early)."""
    amount = dec(value)
    if amount is None:
        return None
    body = IDENTIFIER.sub(" ", TAG.sub(" ", str(value))).rsplit("=", 1)[-1]  # the number dec() read
    unit = re.match(r"\D*?\d[\d.,]*\s*(arbeitstage|werktage|working days|business days|at\b|tage|days?\b|kalendertage)",
                    body, re.I)
    if unit:
        per = 5 if re.match(r"arbeits|werk|working|business|at", unit.group(1), re.I) else 7
        amount = amount / per
    return int(math.ceil(amount))


def german(value, decimals: int = 2) -> str:
    """A number as the German forms want it: 1234.5 -> "1.234,50"."""
    amount = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    whole, _, fraction = f"{amount:,.{decimals}f}".partition(".")
    whole = whole.replace(",", ".")
    return f"{whole},{fraction}" if decimals else whole
