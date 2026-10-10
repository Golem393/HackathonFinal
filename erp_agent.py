"""The ERP sub-agents: a scout learns the ERP once, then finders and detail readers do the positions.

1. scout (one, early): learns HOW this ERP works (material search, where status, stock, lead times and price
   conditions are, URL patterns) and writes a site map. Navigation knowledge only, no scenario values; it is learned
   at run time, so it fits whatever ERP the run brings.
2. finder (one per distinct requirement, not per position): lists the catalogue group's candidates, compares the
   attributes, checks status, takes the next candidate when one is blocked.
3. detail reader (one per chosen material): price conditions, stock, lead times, carton, masses, fees.

Results come back per position in RESULT_FORMAT, so the calculator does not care how they were found. Every agent
works in its own tab of one logged-in ERP session.

Local try-out, after `eval "$(atira scout --env)"` and with `atira models proxy` running:

    uv run --no-sync python erp_agent.py --scout
    uv run --no-sync python erp_agent.py dev/out/requirements.json [scenario-date]

requirements.json is a list of positions as read from the tender and specification (see `Requirement`); keep it in
dev/out/, which is never committed or shipped.
"""
import asyncio
import json
import os
import sys
import time
from typing import TypedDict

from web_agent import WebAgent


class Requirement(TypedDict, total=False):
    position: str          # tender position id
    catalogue_group: str   # Kataloggruppe named by the specification
    bore_mm: float
    stroke_mm: float       # stroke to match; see usable_stroke
    usable_stroke: bool    # stroke is usable travel: the nominal stroke adds a reserve per end
    pressure_bar: float
    mounting: str
    certification: str
    quantity_pieces: int   # final quantity in pieces


RESULT_FORMAT = """{
  "position": "<position id>",
  "material_number": "<the matching active material, or null if none matches exactly>",
  "match_evidence": "<which attributes you compared and where>",
  "rejected_candidates": [{"material_number": "...", "reason": "inactive / blocked / which attribute differs"}],
  "price_conditions": [{"valid_from": "...", "valid_to": "...", "currency": "...", "price_unit": "<e.g. per 1 / per 100 pieces>",
                        "fx_key": "<if named>", "scales": [{"from_quantity": 0, "price": 0}], "status": "..."}],
  "stock_available_pieces": null,
  "lead_time_from_stock_weeks": null,
  "lead_time_production_weeks": null,
  "pieces_per_carton": null,
  "surcharge_mass_kg_per_piece": null,
  "allocation_mass": null,
  "setup_fee": null,
  "other_price_facts": "<any other surcharge, index key, fee or remark the ERP shows for this material>",
  "problems": "<anything you could not find or that looked contradictory>"
}"""

SCOUT_GOAL = """You are the first colleague in this company ERP today. Others will look up several materials right after
you, with little time each. Learn HOW this ERP works and write it down for them as a site map. Do NOT collect data for
any particular material: one example material is enough to see where things are.

Find out, using the ERP itself (menus, transaction codes, search helps, tabs, links):
1. How to list materials of a catalogue group (Kataloggruppe) or by description: which transaction/page, which field,
   what the search accepts (exact group code? words? wildcards?), how many results it lists, how results link on.
2. How to open one material and where its attributes (bore, stroke, pressure, mounting, certification), its status
   and the meaning of status codes (active/released vs blocked), its lead times (from stock / production), pieces per
   carton, masses and fees are shown.
3. Where its unrestricted stock is shown.
4. Where its price conditions (validity, currency, price unit, quantity scales) are shown.
For each, note the URL pattern if pages open by URL (e.g. "/page?material=<number>&tab=<tab>"), so colleagues can go
straight there. Note recurring popups or gates and how to pass them.
Finish with exactly this JSON shape (navigation knowledge only, no prices or stock figures):
{"search": "<how to list a catalogue group's materials>", "material_pages": {"<what>": "<URL pattern or path>"},
 "status_codes": {"<code>": "<meaning>"}, "tips": ["<short how-to or trap>"]}"""

FINDER_GOAL = """You find the material for one requirement of a bid in this company ERP. Scenario date: {scenario_date}.

The requirement, from the buyer's current specification:
{requirement}
{stroke_note}
Site map from a colleague who explored this ERP today (use it, do not explore again):
{site_map}

1. List the materials of the catalogue group (narrow the search until it lists at most 20 results).
2. For each candidate, compare bore, stroke, pressure, mounting and certification with the requirement, and check its
   status: only an ACTIVE (released) material counts; blocked or inactive ones never do.
3. If the best candidate is blocked or differs, go on with the next candidate. Stop as soon as you have ONE active
   material whose attributes all match, or when every candidate is checked.
Do not read prices, stock or lead times (another colleague does). Note each checked candidate with `note`.
Finish with exactly this JSON shape:
{{"material_number": "<the active exact match, or null>", "match_evidence": "<attributes compared, and where>",
  "rejected_candidates": [{{"material_number": "...", "reason": "blocked / inactive / which attribute differs"}}],
  "candidates_checked": <n>, "problems": "..."}}"""

DETAILS_GOAL = """You read the commercial facts of ONE material in this company ERP: {material}. Scenario date:
{scenario_date}. Do not search for other materials.

Site map from a colleague who explored this ERP today (go straight to the pages it names):
{site_map}

Read, copying numbers exactly as shown:
1. Every price condition: validity period, currency, price unit, FX key if named, all quantity scales, status.
2. Unrestricted (freely usable) stock in pieces; blocked or quality-inspection stock does not count.
3. Lead time from stock and production lead time, in weeks.
4. Pieces per carton, masses (surcharge mass per piece, allocation mass), setup fees, any surcharge or index key.
Finish as soon as you have these (null for what the ERP does not show). Finish with exactly this JSON shape:
{{"price_conditions": [{{"valid_from": "...", "valid_to": "...", "currency": "...", "price_unit": "...", "fx_key": null,
   "scales": [{{"from_quantity": 0, "price": 0}}], "status": "..."}}],
  "stock_available_pieces": null, "lead_time_from_stock_weeks": null, "lead_time_production_weeks": null,
  "pieces_per_carton": null, "surcharge_mass_kg_per_piece": null, "allocation_mass": null, "setup_fee": null,
  "other_price_facts": "...", "problems": "..."}}"""

USABLE_STROKE_NOTE = """The stroke above is USABLE travel (nutzbarer Weg): the nominal stroke in the ERP is larger by a reserve
at each end, given in the Technikfreigabe ({reserve}). Match the nominal stroke = usable travel + 2 x reserve; if the
reserve is unknown, take the candidate whose stroke is the smallest one above the usable travel and that matches
everything else, and say so in problems."""

REQUIREMENT_KEYS = ("catalogue_group", "bore_mm", "stroke_mm", "usable_stroke", "pressure_bar", "mounting",
                    "certification", "reserve_mm")


def site_map_text(site_map: dict | None) -> str:
    if not site_map:
        return "(none: find your way yourself)"
    shown = {k: v for k, v in site_map.items() if k in ("search", "material_pages", "status_codes", "tips")}
    return json.dumps(shown, ensure_ascii=False, indent=1)[:3000]


def finder_goal(requirement: dict, scenario_date: str, site_map: dict | None) -> str:
    req = {k: v for k, v in requirement.items() if k in REQUIREMENT_KEYS and v is not None}
    note = ""
    if req.get("usable_stroke"):
        reserve = f"{req['reserve_mm']} mm per end" if req.get("reserve_mm") is not None else "not known yet"
        note = "\n" + USABLE_STROKE_NOTE.format(reserve=reserve) + "\n"
    return FINDER_GOAL.format(scenario_date=scenario_date, requirement=json.dumps(req, ensure_ascii=False, indent=1),
                              stroke_note=note, site_map=site_map_text(site_map))


def details_goal(material: str, scenario_date: str, site_map: dict | None) -> str:
    return DETAILS_GOAL.format(material=material, scenario_date=scenario_date, site_map=site_map_text(site_map))


def requirement_key(job: dict) -> str:
    """Positions with the same requirement share one finder."""
    return json.dumps({k: job.get(k) for k in REQUIREMENT_KEYS}, sort_keys=True, ensure_ascii=False)


async def in_tab(context, site: dict, label: str, profile: str, goal: str, deadline: float | None,
                 gate: asyncio.Semaphore) -> dict:
    """One sub-agent in its own tab of the shared ERP session."""
    async with gate:
        page = await context.new_page()
        try:
            return await WebAgent(page, site, label=label, profile=profile).run(goal, deadline=deadline)
        except Exception as error:
            return {"error": str(error)[:500]}
        finally:
            await page.close()


async def scout(page, site: dict, deadline: float | None) -> dict:
    """Learn the ERP once (on an already logged-in page); returns the site map (may be partial)."""
    return await WebAgent(page, site, label="erp-scout", profile="erp_scout").run(SCOUT_GOAL, deadline=deadline)


async def run_erp(context, site: dict, requirements: list[Requirement], scenario_date: str, *,
                  deadline: float | None = None, parallel: int = 3, learned: list[str] | None = None,
                  results: dict | None = None, site_map: dict | None = None) -> dict:
    """All positions: one finder per distinct requirement, then one detail reader per chosen material, up to
    `parallel` tabs at once. Each position's result (RESULT_FORMAT) lands in `results` as soon as it is complete."""
    results = {} if results is None else results
    gate = asyncio.Semaphore(parallel)
    if learned:
        site_map = dict(site_map or {})
        site_map["tips"] = list(site_map.get("tips") or []) + [str(n) for n in learned[-6:]]
    groups: dict[str, list[Requirement]] = {}
    for job in requirements:
        groups.setdefault(requirement_key(job), []).append(job)
    details_by_material: dict[str, asyncio.Task] = {}

    async def details(material: str) -> dict:
        if material not in details_by_material:   # positions sharing a material share one detail reader
            details_by_material[material] = asyncio.create_task(in_tab(
                context, site, f"erp-detail {material}", "erp_details", details_goal(material, scenario_date, site_map),
                deadline, gate))
        return await details_by_material[material]

    async def one_group(jobs: list[Requirement]) -> None:
        first = jobs[0]
        label = f"erp-find {first.get('catalogue_group') or first.get('position')}"
        found = await in_tab(context, site, label, "erp_finder", finder_goal(first, scenario_date, site_map),
                             deadline, gate)
        material = found.get("material_number")
        facts = await details(material) if material else {}
        for job in jobs:
            merged = {"position": job.get("position"), **{k: v for k, v in facts.items() if k != "notes"},
                      "material_number": material, "match_evidence": found.get("match_evidence"),
                      "rejected_candidates": found.get("rejected_candidates") or [],
                      "problems": "; ".join(str(p) for p in (found.get("problems"), facts.get("problems")) if p)}
            if found.get("incomplete") or found.get("error"):
                merged["incomplete"] = True   # an unfinished search proves nothing (never a no_bid)
            results[job.get("position")] = merged

    await asyncio.gather(*(one_group(jobs) for jobs in groups.values()))
    return results


def erp_site(task: dict) -> dict:
    """The ERP among the run's websites. The private dataset renames sites, so fall back to asking by keyword."""
    sites = task["access"]
    return next((s for s in sites if s.get("siteId") == "erp"), None) \
        or next(s for s in sites if "erp" in (s.get("siteId", "") + s.get("url", "")).lower())


async def main() -> None:
    from playwright.async_api import async_playwright

    import browsers
    import run as contract
    import telemetry

    task, _ = contract.load_run()
    site = erp_site(task)
    deadline = time.time() + float(os.environ.get("ERP_SECONDS", "600"))
    async with async_playwright() as playwright:
        browser, page = await browsers.connect(playwright)
        site_map = await scout(page, site, deadline)
        print("SITE MAP:", json.dumps(site_map, ensure_ascii=False, indent=2), flush=True)
        if sys.argv[1:2] not in (["--scout"], []):
            requirements = json.loads(open(sys.argv[1]).read())
            scenario_date = sys.argv[2] if len(sys.argv) > 2 else time.strftime("%Y-%m-%d")
            results = await run_erp(page.context, site, requirements, scenario_date, deadline=deadline,
                                    site_map=site_map)
            print(json.dumps(results, ensure_ascii=False, indent=2))
        telemetry.summary()


if __name__ == "__main__":
    asyncio.run(main())
