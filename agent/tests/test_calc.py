"""The bid arithmetic against the brief's rules, with made-up numbers (none of them comes from a scenario)."""
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import calc  # noqa: E402

D = Decimal


def position(number="1", **overrides):
    base = {"position": number, "tender_quantity": 10, "material_number": "MAT-A",
            "price": {"currency": "EUR", "price_unit": 1, "scales": [{"min_quantity": 1, "price": "10.00"}]},
            "stock": 1000, "stock_lead_time_weeks": 1, "production_lead_time_weeks": 9}
    return {**base, **overrides}


def bid(*positions, **overrides):
    return {"tender_reference": "TEST-REF-1", "decision": "bid", "scenario_date": "2000-06-15T09:00:00Z",
            "positions": list(positions), **overrides}


class Numbers(unittest.TestCase):
    def test_german_and_plain_numbers(self):
        self.assertEqual(calc.dec("1.234,56"), D("1234.56"))
        self.assertEqual(calc.dec("1234.56"), D("1234.56"))
        self.assertEqual(calc.dec("12,5 %"), D("12.5"))
        self.assertEqual(calc.dec("1,234,567"), D("1234567"))
        self.assertEqual(calc.dec("EUR 0,0125"), D("0.0125"))
        self.assertIsNone(calc.dec("n/a"))

    def test_a_locale_tag_decides_what_a_lone_separator_means(self):
        self.assertEqual(calc.dec("123,456 (en-US)"), D("123456"))
        self.assertEqual(calc.dec("123.456 (de-DE)"), D("123456"))
        self.assertEqual(calc.dec("9,876.5 (en-US)"), D("9876.5"))
        self.assertEqual(calc.dec("1.234,5 (de-DE)"), D("1234.5"))
        self.assertEqual(calc.dec("Zahlenformat: en-US 42.25"), D("42.25"))

    def test_masses_in_grams_become_kilograms(self):
        self.assertEqual(calc.kilograms("1250 g"), D("1.25"))
        self.assertEqual(calc.kilograms("1250 g/Stück"), D("1.25"))
        self.assertEqual(calc.kilograms("1.25 kg"), D("1.25"))
        self.assertEqual(calc.kilograms("1.25"), D("1.25"))
        self.assertEqual(calc.kilograms(2), D("2"))

    def test_half_up_not_bankers_rounding(self):
        self.assertEqual(calc.money(D("2.345")), D("2.35"))
        self.assertEqual(calc.money(D("2.325")), D("2.33"))

    def test_german_format_for_the_forms(self):
        self.assertEqual(calc.german(1234.5), "1.234,50")
        self.assertEqual(calc.german(0.075), "0,08")
        self.assertEqual(calc.german(7, 0), "7")

    def test_dates_and_position_order(self):
        self.assertEqual(calc.day("03.02.2001"), "2001-02-03")
        self.assertLess(calc.stamp("03.02.2001, 09:05"), calc.stamp("2001-02-03T10:00:00Z"))
        self.assertEqual(sorted(["10", "2", "1.10", "1.2"], key=calc.position_key), ["1.2", "1.10", "2", "10"])


class Counts(unittest.TestCase):
    def test_counts_group_thousands_where_amounts_would_read_decimals(self):
        self.assertEqual(calc.whole("1.000 ST"), 1000)
        self.assertEqual(calc.whole("1,250"), 1250)
        self.assertEqual(calc.whole("1.000.000"), 1000000)
        self.assertEqual(calc.whole("7"), 7)
        self.assertEqual(calc.whole("1,000 (en-US)"), 1000)
        self.assertEqual(calc.dec("1,250"), Decimal("1.250"))  # an amount keeps the decimal reading

    def test_a_condition_number_format_decides_an_ambiguous_scale(self):
        price = {"currency": "XYZ", "eur_per_currency_unit": "0.5", "price_unit": "100", "number_format": "de-DE",
                 "scales": [{"min_quantity": "1", "price": "123.456"}, {"min_quantity": "1.000", "price": "99.000"}]}
        self.assertEqual(calc.scale_price(price, 20), Decimal("617.28"))  # 123456 / 100 * 0.5
        self.assertEqual(calc.scale_price(price, 1000), Decimal("495.00"))
        plain = {"currency": "EUR", "price_unit": "1", "number_format": "de-DE", "scales": [{"min_quantity": "1",
                                                                                              "price": "1234.56"}]}
        self.assertEqual(calc.scale_price(plain, 1), Decimal("1234.56"))  # already plain: left alone

    def test_weeks_and_quantities_in_odd_shapes_never_break_the_bid(self):
        self.assertEqual([calc.weeks_of(v) for v in ("3 Wochen", "3.0", 2, "2,5", None)], [3, 3, 2, 3, None])
        line = {"quantity": 5, "material_number": "QX-1", "stock": "9", "stock_lead_time_weeks": "1 Woche",
                "production_lead_time_weeks": "6 Wochen"}
        self.assertEqual(calc.lead_time(line, {"QX-1": 5}), 1)
        self.assertEqual(calc.lead_time({**line, "stock": "2"}, {"QX-1": 5}), 6)
        self.assertEqual(calc.final_quantity({"tender_quantity": 20, "quantity_changes": [
            {"qa_number": "1", "date": "2030-01-01", "quantity": ""}]}), 20)
        self.assertEqual(calc.dec("1.234.567"), 1234567)

    def test_times_with_offsets_are_compared_in_utc(self):
        self.assertLess(calc.stamp("2030-05-04T23:30:00+02:00"), calc.stamp("2030-05-04T22:00:00Z"))
        self.assertEqual(calc.stamp("04.05.2030, 10:30"), "2030-05-04 10:30")


class Quantities(unittest.TestCase):
    def test_latest_dated_change_wins_and_withdrawn_answers_are_ignored(self):
        changes = [{"qa_number": "3", "date": "2000-01-05", "quantity": 30},
                   {"qa_number": "7", "date": "2000-01-09", "quantity": 70}]
        self.assertEqual(calc.final_quantity(position(quantity_changes=changes)), 70)
        self.assertEqual(calc.final_quantity(position(quantity_changes=changes, withdrawn_qa_numbers=["7"])), 30)
        self.assertEqual(calc.final_quantity(position(quantity_changes=changes, withdrawn_qa_numbers=["3", "7"])), 10)

    def test_sets_become_pieces(self):
        self.assertEqual(calc.final_quantity(position(tender_quantity=4, unit_is_set=True, pieces_per_set=3)), 12)


class Prices(unittest.TestCase):
    def test_highest_scale_not_above_the_quantity_per_piece_in_eur(self):
        price = {"currency": "XXX", "price_unit": 100, "eur_per_currency_unit": "0.5",
                 "scales": [{"min_quantity": 1, "price": "1000"}, {"min_quantity": 50, "price": "800"},
                            {"min_quantity": 500, "price": "600"}]}
        self.assertEqual(calc.scale_price(price, 49), D("5.00"))
        self.assertEqual(calc.scale_price(price, 50), D("4.00"))
        self.assertIsNone(calc.scale_price({**price, "eur_per_currency_unit": None}, 50))

    def test_metal_rate_by_inclusive_window_not_the_last_listed(self):
        index = {"rates": [{"valid_from": "2000-01-01", "valid_to": "2000-06-15", "eur_per_kg": "2.00"},
                           {"valid_from": "2000-06-16", "valid_to": "2000-12-31", "eur_per_kg": "3.00"}]}
        self.assertEqual(calc.metal_rate(index, "2000-06-15"), D("2.00"))
        self.assertEqual(calc.metal_rate(index, "2000-06-16"), D("3.00"))


class Allocation(unittest.TestCase):
    def test_largest_remainder_with_ties_by_ascending_position(self):
        self.assertEqual(calc.allocate(D("1.00"), {"2": D(1), "1": D(1), "3": D(1)}),
                         {"1": D("0.34"), "2": D("0.33"), "3": D("0.33")})

    def test_other_cent_rules(self):
        weights = {"1": D(1), "2": D(2), "3": D(1)}
        self.assertEqual(calc.allocate(D("0.03"), weights, "remainder_to_last"),
                         {"1": D("0.00"), "2": D("0.01"), "3": D("0.02")})
        self.assertEqual(sum(calc.allocate(D("10.01"), weights, "remainder_to_largest_share").values()), D("10.01"))

    def test_marginal_bonus_bands(self):
        bands = [{"from_eur": "0", "to_eur": "1000", "percent": "1"}, {"from_eur": "1000", "to_eur": None, "percent": "2"}]
        self.assertEqual(calc.project_bonus(bands, D("1500")), D("20.00"))
        self.assertEqual(calc.project_bonus(bands, D("500")), D("5.00"))


class TheBid(unittest.TestCase):
    def test_total_is_the_sum_of_quantity_times_rounded_unit_price(self):
        answer, _ = calc.compute(bid(position("1", tender_quantity=3, price={
            "currency": "EUR", "price_unit": 1, "scales": [{"min_quantity": 1, "price": "3.333"}]})))
        [line] = answer["positions"]
        self.assertEqual(line["base_unit_price"], 3.33)
        self.assertEqual(answer["total_net"], 9.99)

    def test_discount_threshold_is_inclusive_and_failing_it_means_zero(self):
        approval = {"percent": "10", "min_order_value_eur": "100.00"}
        answer, _ = calc.compute(bid(position(), discount_approval=approval))
        self.assertEqual((answer["discount_percent"], answer["positions"][0]["unit_price"]), (10.0, 9.0))
        answer, _ = calc.compute(bid(position(), discount_approval={**approval, "min_order_value_eur": "100.01"}))
        self.assertEqual((answer["discount_percent"], answer["positions"][0]["unit_price"]), (0.0, 10.0))

    def test_discount_scope_surcharge_setup_packaging_and_bonus(self):
        line = position(tender_quantity=8, surcharge_mass_kg="0.5", setup_fee="4.00", pieces_per_carton=3,
                        carton_tariff_eur="1.50", condition_group="G", discount_scope="base_and_surcharge",
                        project_bonus_member=True)
        answer, _ = calc.compute(bid(line, discount_approval={"percent": "10"},
                                     metal_index={"rates": [{"eur_per_kg": "2.00"}]},
                                     project_bonus={"bands": [{"from_eur": "0", "to_eur": None, "percent": "5"}]}))
        [result] = answer["positions"]
        # base 10.00 -> 9.00, mass 1.00 -> 0.90, setup 4.00 / 8, 3 cartons x 1.50 / 8, bonus 5 % of 80.00 = 4.00 / 8
        self.assertEqual(result["unit_price"], 10.46)
        self.assertEqual(result["surcharge_per_unit"], 1.50)
        self.assertEqual(result["packaging_per_unit"], 0.56)
        self.assertEqual(result["rebate_total"], 4.00)
        answer, _ = calc.compute(bid({**line, "discount_scope": "none"}, discount_approval={"percent": "10"},
                                     metal_index={"rates": [{"eur_per_kg": "2.00"}]}))
        self.assertEqual(answer["positions"][0]["unit_price"], 12.06)

    def test_without_a_condition_group_the_discount_is_on_the_base_only(self):
        line = position(surcharge_mass_kg="1", discount_scope="none")
        answer, _ = calc.compute(bid(line, discount_approval={"percent": "10"}, metal_index={"rates": [{"eur_per_kg": "2"}]}))
        self.assertEqual(answer["positions"][0]["unit_price"], 11.0)

    def test_shared_setup_pool_is_split_by_quantity_times_allocation_mass(self):
        first = position("1", tender_quantity=10, setup_pool_key="P", allocation_mass_kg="1")
        second = position("2", tender_quantity=10, setup_pool_key="P", allocation_mass_kg="3")
        answer, _ = calc.compute(bid(first, second, setup_pools=[{"key": "P", "fee_eur": "40.00"}]))
        self.assertEqual([p["surcharge_per_unit"] for p in answer["positions"]], [1.0, 3.0])

    def test_stock_is_pooled_per_material_and_commitments_have_a_ceiling(self):
        first, second = position("1", tender_quantity=600), position("2", tender_quantity=600)
        answer, _ = calc.compute(bid(first, second))
        self.assertEqual([p["lead_time_weeks"] for p in answer["positions"]], [9, 9])
        commitment = {"material_number": "MAT-A", "ceiling_pieces": 1200, "lead_time_weeks": 4}
        answer, _ = calc.compute(bid({**first, "delivery_commitment": commitment}, second))
        self.assertEqual([p["lead_time_weeks"] for p in answer["positions"]], [4, 9])
        answer, _ = calc.compute(bid({**first, "delivery_commitment": {**commitment, "ceiling_pieces": 1199}}, second))
        self.assertEqual(answer["positions"][0]["lead_time_weeks"], 9)

    def test_a_position_without_a_quantity_is_left_out(self):
        answer, log = calc.compute(bid(position("1"), position("2", tender_quantity=None)))
        self.assertEqual([p["position"] for p in answer["positions"]], ["1"])
        self.assertTrue(any("omitted" in line for line in log))

    def test_a_position_without_a_material_is_still_entered_for_its_quantity(self):
        answer, _ = calc.compute(bid(position("1"), position("2", material_number=None, stock=None,
                                                            stock_lead_time_weeks=None,
                                                            production_lead_time_weeks=None)))
        second = answer["positions"][1]
        self.assertEqual((second["material_number"], second["quantity"], second["unit_price"]), (None, 10, 0.0))
        self.assertIsNone(second["lead_time_weeks"])

    def test_without_any_price_the_approved_discount_stands(self):
        answer, _ = calc.compute(bid(position("1", price={}), discount_approval={"percent": 4,
                                                                            "min_order_value_eur": "1"}))
        self.assertEqual(answer["discount_percent"], 4.0)

    def test_the_submitter_sees_configurator_values_and_placeholders(self):
        import submit
        answer, _ = calc.compute(bid(position("1", material_number=None, stock=None, stock_lead_time_weeks=None,
                                              production_lead_time_weeks=None, price={})))
        text = submit.table(answer, [], {"1": {"bore": "11", "stroke": "222", "mounting": "Clamp"}})
        self.assertIn("bore 11 / stroke 222 / mounting Clamp", text)
        self.assertIn("(choose: the material the configurator offers", text)
        self.assertIn("(unknown: choose any)", text)
        self.assertIn("(leave empty)", text)

    def test_the_submitter_sees_each_line_total(self):
        import submit
        answer, _ = calc.compute(bid(position("1"), position("2", tender_quantity=3)))
        text = submit.table(answer, [])
        self.assertIn("| 100,00 |", text)  # 10 x 10,00 (no discount approval in this bid)
        self.assertIn("| 30,00 |", text)  # 3 x 10,00

    def test_a_position_without_a_price_is_still_entered_for_its_other_fields(self):
        answer, _ = calc.compute(bid(position("1"), position("2", price={}),
                                     discount_approval={"percent": 5, "min_order_value_eur": "1000000"}))
        second = answer["positions"][1]
        self.assertEqual((second["material_number"], second["quantity"], second["unit_price"]), ("MAT-A", 10, 0.0))
        self.assertIsNone(second["base_unit_price"])
        self.assertEqual(answer["total_net"], 100.0 * 0.95)  # 10 x 9.50 for the priced one, nothing for the other
        self.assertEqual(answer["discount_percent"], 5.0)  # the order value is unknown: the approval stands

    def test_no_bid_has_no_positions_and_a_conditional_approval_gives_zero(self):
        answer, _ = calc.compute(bid(position(), decision="no_bid",
                                     discount_approval={"percent": "5", "min_order_value_eur": "1"}))
        self.assertEqual((answer["positions"], answer["total_net"], answer["discount_percent"]), ([], 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
