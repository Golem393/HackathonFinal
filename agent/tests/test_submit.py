"""The submission's code checks against made-up form pages written in the page view's format: a step holding
another position's row, a step with a field left empty, and summaries that do or do not match the bid."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import submit  # noqa: E402

ANSWER = {"tender_reference": "AB-1", "decision": "bid", "discount_percent": 0.0, "total_net": 1630.0, "positions": [
    {"position": "02.01", "material_number": "QX-11", "quantity": 10, "unit_price": 100.0, "lead_time_weeks": 4,
     "base_unit_price": 95.5, "surcharge_per_unit": 3.25, "packaging_per_unit": 1.25, "rebate_total": 0.0},
    {"position": "02.02", "material_number": "QX-22", "quantity": 7, "unit_price": 90.0, "lead_time_weeks": 6,
     "base_unit_price": 88.0, "surcharge_per_unit": 1.75, "packaging_per_unit": 0.25, "rebate_total": 12.5}]}


def step(position: str, values: dict, material: str) -> str:
    fields = " ".join(f'[{n} input "{label}" value="{value}"]' for n, (label, value) in enumerate(values.items(), 10))
    return (f"URL: https://form.example/bid\n\n## Position {position}\n[3 select \"Artikel\" selected=\"{material}\" "
            f"options: \"{material}\"]\n{fields}\n[30 button \"Weiter\"] [31 button \"Wahl anwenden\"]")


class Steps(unittest.TestCase):
    def setUp(self):
        self.guard = submit.FormGuard(ANSWER, [])

    def test_a_step_holding_another_positions_row_is_not_left(self):
        view = step("02.01", {"Menge": "7", "Preis": "90,00", "Zuschlag": "1,75", "Verpackung": "0,25"}, "QX-22")
        problem = self.guard.step_problem(view, "Weiter")
        self.assertIn("values of position 02.02", problem)
        self.assertIsNone(self.guard.step_problem(view, "Weiter"))  # once: a second click goes through
        self.assertIsNone(submit.FormGuard(ANSWER, []).step_problem(view, "Wahl anwenden"))  # not a continue

    def test_a_missing_field_is_named_and_a_complete_step_passes(self):
        values = {"Menge": "10", "Preis": "100,00", "Basis": "95,50", "Zuschlag": "3,25", "Verpackung": "1,25",
                  "Bonus": "", "Wochen": "4"}
        problem = self.guard.step_problem(step("2.1", values, "QX-11"), "Weiter")
        self.assertIn("project bonus 0,00", problem)
        values["Bonus"] = "0,00"
        self.assertIsNone(submit.FormGuard(ANSWER, []).step_problem(step("02.01", values, "QX-11"), "Weiter"))

    def test_a_date_is_not_taken_for_a_position(self):
        view = "## Angebot vom 02.01.2030\n[4 input \"Menge\" value=\"\"]"
        self.assertIsNone(self.guard.step_position(view))


class OtherIds(unittest.TestCase):
    def test_bare_and_prefixed_position_ids(self):
        answer = {**ANSWER, "positions": [dict(ANSWER["positions"][0], position="10"),
                                          dict(ANSWER["positions"][1], position="20")]}
        guard = submit.FormGuard(answer, [])
        self.assertTrue(guard.usable)
        view = ('## Position 20\nSchritt 4 von 9\n[3 select "Artikel" selected="QX-11" options: "QX-11"]\n'
                '[10 input "Menge" value="10"] [11 input "Preis" value="100,00"] [12 input "Zuschlag" value="3,25"]')
        self.assertEqual(guard.step_position(view), "20")
        self.assertIn("values of position 10", guard.step_problem(view, "Weiter"))
        prefixed = submit.FormGuard({**ANSWER, "positions": [dict(ANSWER["positions"][0], position="A-2")]}, [])
        self.assertEqual(prefixed.step_position("## Los A-2\nSchritt 4 von 9"), "A-2")
        self.assertIsNone(prefixed.step_position("Schritt 2 von 9"))


class Summary(unittest.TestCase):
    def test_the_summary_is_checked_against_the_bid(self):
        guard = submit.FormGuard(ANSWER, [])
        right = ("| 02.01 | QX-11 | 10 | 100,00 |\n| 02.02 | QX-22 | 7 | 90,00 |\nNetto gesamt: 1.630,00 EUR\n"
                 "Brutto: 1.939,70 EUR")
        self.assertEqual(guard.summary_problems(right), [])
        wrong = "| 02.01 | QX-22 | 10 | 100,00 |\n| 02.02 | QX-22 | 7 | 90,00 |\nNetto gesamt: 1.630,00 EUR"
        self.assertEqual(guard.summary_problems(wrong), ["02.01: material QX-11 not shown"])

    def test_an_omitted_position_is_left_out_of_the_total(self):
        guard = submit.FormGuard(ANSWER, ["02.02"])
        view = "Kontrolle 2\n| 02.01 | QX-11 | 10 | 100,00 |\nAusgelassen: 02.02\nNetto: 1.000,00"
        self.assertEqual(guard.summary_problems(view), [])
        problems = guard.summary_problems(view.replace("1.000,00", "1.630,00"))
        self.assertEqual(problems, ["the net total of the positions in the summary should be 1.000,00"])
        # a page naming one position is that position's step, not the summary: nothing to compare yet
        self.assertEqual(guard.summary_problems("## Position 02.02\n| 02.02 | QX-22 |"), [])
        three = {**ANSWER, "positions": ANSWER["positions"] + [
            {"position": "02.03", "material_number": "QX-33", "quantity": 1, "unit_price": 5.0, "lead_time_weeks": 1,
             "base_unit_price": 5.0, "surcharge_per_unit": 0.0, "packaging_per_unit": 0.0, "rebate_total": 0.0}]}
        problems = submit.FormGuard(three, []).summary_problems("| 02.02 | QX-22 | 7 | 90,00 |\n| 02.03 | QX-33 | 1 | "
                                                                "5,00 |\nNetto: 635,00")
        self.assertIn("position 02.01 is not in the summary (omitted?)", problems)

    def test_a_total_field_must_hold_the_total_of_the_positions_entered(self):
        guard = submit.FormGuard(ANSWER, [])
        view = '## Abschluss\n[7 input "Nachlass (%)" value="0,00"] [8 input "Summe netto" value="1.000,00"]'
        self.assertIn("1.630,00", guard.step_problem(view, "Weiter"))
        self.assertIsNone(guard.step_problem(view, "Weiter"))  # once
        right = view.replace("1.000,00", "1.630,00")
        self.assertIsNone(submit.FormGuard(ANSWER, []).step_problem(right, "Weiter"))

    def test_a_positions_own_total_is_not_taken_for_the_order_total(self):
        values = {"Menge": "10", "Preis": "100,00", "Basis": "95,50", "Zuschlag": "3,25", "Verpackung": "1,25",
                  "Bonus": "0,00", "Wochen": "4", "Gesamtpreis netto": "1.000,00"}
        self.assertIsNone(submit.FormGuard(ANSWER, []).step_problem(step("02.01", values, "QX-11"), "Weiter"))

    def test_a_dropdown_value_with_its_unit_counts(self):
        values = {"Menge": "10", "Preis": "100,00", "Basis": "95,50", "Zuschlag": "3,25", "Verpackung": "1,25",
                  "Bonus": "0,00"}
        view = step("02.01", values, "QX-11") + '\n[21 select "Lieferzeit" selected="4 Wochen" options: "4 Wochen"]'
        self.assertIsNone(submit.FormGuard(ANSWER, []).step_problem(view, "Weiter"))


if __name__ == "__main__":
    unittest.main()
