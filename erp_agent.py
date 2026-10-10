"""The ERP sub-agent: for each tender position, a model finds the matching material and its commercial facts in the ERP.

It returns raw facts as the ERP shows them (price conditions with validity and scales, stock, lead times, carton size,
masses, setup fees); the bid arithmetic is done afterwards in code. Each position gets its own browser context, so
positions run in parallel with independent ERP sessions.

Local try-out, after `eval "$(atira scout --env)"` and with `atira models proxy` running:

    uv run --no-sync python erp_agent.py dev/out/requirements.json [scenario-date]
    uv run --no-sync python erp_agent.py --goal "Find out how materials are searched in this ERP and finish."

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
    stroke_mm: float       # nominal stroke to match (after any usable-stroke derivation)
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


def goal_for(requirement: Requirement, scenario_date: str) -> str:
    return f"""You work in your company's ERP to prepare one position of a bid. Scenario date: {scenario_date}.

The position, as required by the buyer's current specification:
{json.dumps(requirement, ensure_ascii=False, indent=2)}

1. Find the material: search the ERP for the catalogue group (Kataloggruppe) named above. Searches that are empty or
   too broad do not list the catalogue: narrow the search until it lists at most 20 results. Compare each candidate's
   bore, stroke, pressure, mounting and certification with the requirement. Only an ACTIVE material (check its status)
   whose attributes all match exactly counts. If none matches, report material_number null.
2. For the matching material, read its price conditions: every condition with its validity period, currency, price
   unit and quantity scales, and say which one is valid on the scenario date.
3. Read its unrestricted stock, the lead time from stock and the production lead time (in weeks), the pieces per
   carton, and any masses (surcharge mass, allocation mass), setup fees or surcharges the ERP records for it.

Copy numbers exactly as the ERP shows them. Use `note` for each confirmed value as you go.
Finish with a result in exactly this JSON shape:
{RESULT_FORMAT}"""


async def find_position(context, site: dict, requirement: Requirement, scenario_date: str,
                        deadline: float | None, learned: list[str] | None = None) -> dict:
    """One position in its own tab of `context`, whose ERP session is already logged in (or logs in itself)."""
    page = await context.new_page()
    try:
        agent = WebAgent(page, site, label=f"erp {requirement.get('position', '?')}", profile="erp_position")
        goal = goal_for(requirement, scenario_date)
        if learned:
            goal += "\n\nWhat colleagues already learned about this ERP:" + "".join(f"\n- {n}" for n in learned[-12:])
        result = await agent.run(goal, deadline=deadline)
        result.setdefault("position", requirement.get("position"))
        return result
    finally:
        await page.close()


async def run_erp(context, site: dict, requirements: list[Requirement], scenario_date: str, *,
                  deadline: float | None = None, parallel: int = 3, learned: list[str] | None = None,
                  results: dict | None = None) -> dict:
    """All positions as tabs of one ERP session, up to `parallel` at once. Results land in `results` (position ->
    result) as each finishes, so a caller can use the finished ones early; a failed position gets {"error"}."""
    gate = asyncio.Semaphore(parallel)
    results = {} if results is None else results

    async def one(requirement: Requirement) -> None:
        async with gate:
            try:
                results[requirement.get("position")] = await find_position(
                    context, site, requirement, scenario_date, deadline, learned)
            except Exception as error:
                results[requirement.get("position")] = {"position": requirement.get("position"), "error": str(error)[:500]}

    await asyncio.gather(*(one(r) for r in requirements))
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
        if sys.argv[1:2] == ["--goal"]:
            result = await WebAgent(page, site, label="erp").run(" ".join(sys.argv[2:]), deadline=deadline)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            telemetry.summary()
            return
        if not sys.argv[1:]:
            raise SystemExit(__doc__)
        requirements = json.loads(open(sys.argv[1]).read())
        scenario_date = sys.argv[2] if len(sys.argv) > 2 else time.strftime("%Y-%m-%d")
        results = await run_erp(page.context, site, requirements, scenario_date, deadline=deadline)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        telemetry.summary()


if __name__ == "__main__":
    asyncio.run(main())
