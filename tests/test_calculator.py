"""Calculator rules on made-up facts (never values from the challenge websites)."""
import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import calculator as calc  # noqa: E402


class Parsing(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(calc.num("1.234,56"), Decimal("1234.56"))
        self.assertEqual(calc.num("1,234.56"), Decimal("1234.56"))
        self.assertEqual(calc.num("12,5 %"), Decimal("12.5"))
        self.assertEqual(calc.num("EUR 3.400"), Decimal("3400"))
        self.assertIsNone(calc.num("n/a"))

    def test_dates(self):
        self.assertEqual(str(calc.day("2027-03-04T10:00Z")), "2027-03-04")
        self.assertEqual(str(calc.day("04.03.2027, 10:00")), "2027-03-04")
        self.assertEqual(str(calc.day("03/04/2027")), "2027-03-04")
        self.assertEqual(str(calc.day("05/01 (TT/MM) 2027")), "2027-01-05")
        self.assertEqual(str(calc.day("01/17 (MM/TT) · 2027")), "2027-01-17")

    def test_half_up(self):
        self.assertEqual(calc.cents(Decimal("2.345")), Decimal("2.35"))


TENDER = {
    "positions": [{"position": "1", "quantity": 10, "unit": "Stück", "requirement": "R1"},
                  {"position": "2", "quantity": 4, "unit": "Satz", "requirement": "R2"}],
    "clarifications": [
        {"number": "1", "date": "01.01.2030", "position": "1", "new_quantity": 12},
        {"number": "2", "date": "02.01.2030", "position": "1", "new_quantity": 15},
        {"number": "3", "date": "03.01.2030", "withdraws": "2", "text": "Antwort 2 wird zurückgezogen"},
        {"number": "4", "date": "04.01.2030", "amendment": {"revision": "C", "requirement": "R1",
                                                           "attributes": {"stroke_mm": 250}}},
        {"number": "5", "date": "05.01.2030", "amendment": {"revision": "B", "requirement": "R1",
                                                           "attributes": {"bore_mm": 99}}},
    ],
}
SPEC = {"current_revision": "C", "requirements": [
    {"id": "R1", "bore_mm": 50, "stroke_mm": 200}, {"id": "R2", "bore_mm": 40, "pieces_per_set": 2}]}


class Rules(unittest.TestCase):
    def test_quantities_withdrawal_and_sets(self):
        q = calc.final_quantities(TENDER, SPEC)
        self.assertEqual(q["1"], Decimal(12))       # answer 2 withdrawn: answer 1 applies
        self.assertEqual(q["2"], Decimal(8))        # 4 Satz x 2 pieces

    def test_scoped_amendments(self):
        r = calc.final_requirements(TENDER, SPEC)
        self.assertEqual(r["R1"]["stroke_mm"], 250)  # amendment to the current revision
        self.assertEqual(r["R1"]["bore_mm"], 50)     # amendment to another revision ignored

    def test_amendment_attribute_names_are_normalized(self):
        tender = {"positions": [], "clarifications": [
            {"number": "1", "date": "22.01.2030, 10:00", "amendment": {"revision": "C", "requirement": "R1", "attributes": {"Hub/Stellweg": "310 mm"}}},
            {"number": "2", "date": "23.01.2030, 10:00", "amendment": {"revision": "C", "requirement": "R1", "attributes": {"Hub/Stellweg": "305 mm"}}},
            {"number": "3", "date": "24.01.2030, 10:00", "amendment": {"revision": "C", "requirement": "R1", "attributes": {"Befestigung": "Flansch"}}}]}
        r = calc.final_requirements(tender, SPEC)["R1"]
        self.assertEqual((r["stroke_mm"], r["mounting"], r["bore_mm"]), (305, "Flansch", 50))   # latest per attribute

    def test_condition_and_scale(self):
        conditions = [{"valid_from": "01.01.2029", "valid_to": "31.12.2029", "scales": [{"from_quantity": 1, "price": 9}]},
                      {"valid_from": "01.01.2030", "valid_to": "31.12.2030", "price_unit": "per 100 Stück",
                       "scales": [{"from_quantity": 1, "price": "1.000,00"}, {"from_quantity": 10, "price": "900,00"},
                                  {"from_quantity": 20, "price": "800,00"}]}]
        c = calc.valid_condition(conditions, calc.day("31.12.2030"))      # end date inclusive
        self.assertEqual(calc.scale_price(c, Decimal(12)), Decimal(9))    # 900 per 100 pieces

    def test_conditional_discount(self):
        mail = {"bidder_domain": "firma.example", "approvals": [
            {"sender": "leitung@firma.example", "date": "01.01.2030", "reference": "T-1", "percent": 5},
            {"sender": "leitung@firma.example", "date": "02.01.2030", "reference": "T-1", "percent": 8,
             "min_order_value": "1.000,00"},
            {"sender": "leitung@firma.example", "date": "03.01.2030", "reference": "T-1-A", "percent": 20},
            {"sender": "einkauf@firma.example", "date": "04.01.2030", "reference": "T-1", "percent": 30}]}
        on = calc.day("10.01.2030")
        self.assertEqual(calc.approved_discount(mail, "T-1", on, Decimal(1000)), Decimal(8))   # threshold inclusive
        self.assertEqual(calc.approved_discount(mail, "T-1", on, Decimal(999)), Decimal(0))    # no fallback to 5 %

    def test_shared_stock(self):
        erp = {"1": {"stock_available_pieces": 20, "lead_time_from_stock_weeks": 2, "lead_time_production_weeks": 8},
               "2": {"stock_available_pieces": 20, "lead_time_from_stock_weeks": 2, "lead_time_production_weeks": 8}}
        weeks = calc.lead_times({"1": "M", "2": "M"}, {"1": Decimal(12), "2": Decimal(9)}, erp)
        self.assertEqual(weeks, {"1": 8, "2": 8})   # 21 > 20: both from production

    def test_compute_bid_and_no_bid(self):
        erp = {p: {"material_number": "M" + p, "stock_available_pieces": 100, "lead_time_from_stock_weeks": 1,
                   "lead_time_production_weeks": 6,
                   "price_conditions": [{"valid_from": "01.01.2030", "valid_to": "31.12.2030", "currency": "EUR",
                                         "scales": [{"from_quantity": 1, "price": "10,005"}]}]} for p in ("1", "2")}
        bid = calc.compute_bid("T-1", "2030-06-01", TENDER, SPEC, {}, erp)
        self.assertEqual(bid["decision"], "bid")
        self.assertEqual([p["quantity"] for p in bid["positions"]], [12, 8])
        self.assertEqual(bid["total_net"], 200.2)   # 20 pieces x 10.01
        erp["2"] = {"material_number": None}
        self.assertEqual(calc.compute_bid("T-1", "2030-06-01", TENDER, SPEC, {}, erp)["decision"], "no_bid")

    def test_no_bid_never_from_a_usable_stroke_without_reserve(self):
        spec = {"current_revision": "C", "requirements": [{"id": "R1", "bore_mm": 50, "stroke_mm": 200, "usable_stroke": True},
                                                          {"id": "R2", "bore_mm": 40, "pieces_per_set": 2}]}
        bid = calc.compute_bid("T-1", "2030-06-01", TENDER, spec, {}, {"1": {"material_number": None}})
        self.assertEqual((bid["decision"], bid["omitted"]), ("bid", ["1", "2"]))

    def test_partial_sum_proves_a_reached_minimum(self):
        mail = {"bidder_domain": "firma.example", "approvals": [
            {"sender": "leitung@firma.example", "date": "01.01.2030", "reference": "T-1", "percent": 5, "min_order_value": 1}]}
        on = calc.day("10.01.2030")
        self.assertEqual(calc.approved_discount(mail, "T-1", on, Decimal(50), complete=False), Decimal(5))
        self.assertEqual(calc.approved_discount(mail, "T-1", on, Decimal(0), complete=False), Decimal(0))


if __name__ == "__main__":
    unittest.main()


class NeverOmit(unittest.TestCase):
    def test_positions_with_material_stay_in_even_without_price(self):
        erp = {"1": {"material_number": "M1", "lead_time_production_weeks": 6, "price_conditions": [
                   {"valid_from": "01.01.2030", "valid_to": "31.12.2030", "currency": "USD", "fx_key": "FX-1",
                    "scales": [{"from_quantity": 1, "price": 100}]}]},
               "2": {"material_number": "M2", "lead_time_production_weeks": 4}}
        bid = calc.compute_bid("T-1", "2030-06-01", TENDER, SPEC, {}, erp)
        self.assertEqual([p["position"] for p in bid["positions"]], ["1", "2"])
        self.assertEqual([p["unit_price"] for p in bid["positions"]], [0.0, 0.0])
        self.assertEqual(bid["omitted"], [])

    def test_currency_converted_with_the_fx_mail(self):
        mail = {"rule_mails": [{"kind": "Devisenfixing", "date": "01.05.2030", "reference": "T-1",
                                "text": "Fixing T-1\nFX-1: 0,9000 EUR je USD"}]}
        erp = {"1": {"material_number": "M1", "lead_time_production_weeks": 6, "price_conditions": [
                   {"valid_from": "01.01.2030", "valid_to": "31.12.2030", "currency": "USD", "fx_key": "FX-1",
                    "price_unit": "per 100", "scales": [{"from_quantity": 1, "price": "1.000,00"}]}]}}
        bid = calc.compute_bid("T-1", "2030-06-01", TENDER, SPEC, mail, erp)
        self.assertEqual(bid["positions"][0]["base_unit_price"], 9.0)   # 1000 USD / 100 x 0.90
