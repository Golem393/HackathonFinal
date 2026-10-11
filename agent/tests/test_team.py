"""The team's code checks, with made-up references and records: the mail topic checklist and how topics are shared
among parallel mail agents."""
import asyncio
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import team  # noqa: E402

TOPICS = [{"topic": "Kursblatt", "sender": "geld", "gives": "exchange rate"},
          {"topic": "Staffelrabatt", "sender": "chef", "gives": "discount"}]


class Checklist(unittest.TestCase):
    def setUp(self):
        self.ledger = team.Ledger()
        self.site = SimpleNamespace(id="post", trail=[])
        self.topics = team.Topics(TOPICS, "AB-2030-11", "2030-03-10T09:00:00Z", self.site, self.ledger)

    def close(self, **kwargs) -> str:
        return asyncio.run(self.topics.close(**kwargs))

    def test_finish_is_refused_while_a_topic_is_open(self):
        self.assertIn("Kursblatt", asyncio.run(self.topics.check({})))

    def test_a_look_alike_reference_or_a_later_date_does_not_close_a_topic(self):
        self.ledger.add("post", "/m/1", "mail", {"subject": "Kursblatt AB-2030-11-A"})
        answer = self.close(topic="Kursblatt", outcome="recorded", subject="Kursblatt AB-2030-11-A",
                            reference_as_written="AB-2030-11-A", date="09.03.2030, 10:00", sender="geld@firma.example")
        self.assertIn("not exactly the tender reference", answer)
        self.ledger.add("post", "/m/4", "mail", {"subject": "Kursblatt AB-2030-11", "date": "11.03.2030, 08:00"})
        answer = self.close(topic="Kursblatt", outcome="recorded", subject="Kursblatt AB-2030-11",
                            reference_as_written="AB-2030-11", date="11.03.2030, 08:00", sender="geld@firma.example")
        self.assertIn("after the scenario date", answer)
        self.assertEqual(self.topics.open(), ["Kursblatt", "Staffelrabatt"])
        # the record says the date even when the agent does not
        answer = self.close(topic="Kursblatt", outcome="recorded", subject="Kursblatt AB-2030-11",
                            reference_as_written="AB-2030-11", sender="geld@firma.example")
        self.assertNotIn("Closed", answer)

    def test_the_message_with_the_given_date_is_checked_not_a_decoy_with_the_same_subject(self):
        self.ledger.add("post", "/m/5", "mail", {"subject": "Kursblatt AB-2030-11", "date": "12.03.2030 10:00"})
        self.ledger.add("post", "/m/6", "mail", {"subject": "Kursblatt AB-2030-11", "date": "08.03.2030 20:00"})
        answer = self.close(topic="Kursblatt", outcome="recorded", subject="Kursblatt AB-2030-11",
                            reference_as_written="AB-2030-11", date="08.03.2030 20:00", sender="geld@firma.example")
        self.assertIn("Closed Kursblatt", answer)

    def test_a_topic_closes_with_a_recorded_message_that_can_apply(self):
        answer = self.close(topic="kursblatt", outcome="recorded", subject="Kursblatt AB-2030-11",
                            reference_as_written="AB-2030-11", date="09.03.2030, 10:00", sender="geld@firma.example")
        self.assertIn("Record the message", answer)  # nothing recorded yet
        self.ledger.add("post", "/m/2", "mail", {"subject": "Kursblatt AB-2030-11", "rate": "1,1"})
        answer = self.close(topic="kursblatt", outcome="recorded", subject="Kursblatt AB-2030-11",
                            reference_as_written="AB-2030-11", date="09.03.2030, 10:00", sender="geld@firma.example")
        self.assertIn("Closed Kursblatt", answer)
        self.assertEqual(self.topics.open(), ["Staffelrabatt"])

    def test_a_reference_copied_with_a_typo_is_checked_once(self):
        self.ledger.add("post", "/m/7", "mail", {"subject": "Kursblatt AB-2030-12", "date": "08.03.2030",
                                                 "text": "für AB-2030-11, Lastenheft LS-AB-2030-11"})
        arguments = dict(topic="Kursblatt", outcome="recorded", subject="Kursblatt AB-2030-12",
                         reference_as_written="AB-2030-11", date="08.03.2030", sender="geld@firma.example")
        self.assertIn("writes the reference as AB-2030-12,", self.close(**arguments) + ",")

    def test_the_right_name_at_another_domain_is_questioned_once(self):
        for n in range(2):
            self.ledger.add("post", f"/m/{n}", "mail", {"sender": "chef@firma.example", "subject": f"Notiz {n}"})
        self.ledger.add("post", "/m/9", "mail", {"subject": "Staffelrabatt AB-2030-11", "date": "2030-03-01",
                                                 "sender": "chef@firma-example.net"})
        arguments = dict(topic="Staffelrabatt", outcome="recorded", subject="Staffelrabatt AB-2030-11",
                         reference_as_written="AB-2030-11", date="2030-03-01", sender="Chef <chef@firma-example.net>")
        self.assertIn("not at the bidder's mailbox domain firma.example", self.close(**arguments))
        self.assertIn("Closed", self.close(**arguments))

    def test_another_sender_is_questioned_once(self):
        self.ledger.add("post", "/m/3", "mail", {"subject": "Staffelrabatt AB-2030-11"})
        arguments = dict(topic="Staffelrabatt", outcome="recorded", subject="Staffelrabatt AB-2030-11",
                         reference_as_written="AB-2030-11", date="2030-03-01", sender="vertrieb@firma.example")
        self.assertIn("another sender", self.close(**arguments))
        self.assertIn("Closed", self.close(**arguments))

    def test_absent_needs_the_word_searched_as_the_brief_spells_it(self):
        self.site.trail += ["https://post.example/?box=in&q=AB-2030-11 Kursblatt"]
        self.assertIn("every folder", self.close(topic="Kursblatt", outcome="absent"))
        self.site.trail += ["https://post.example/?box=old&q=AB-2030-11 Kursblatt"]
        self.assertIn("Closed Kursblatt", self.close(topic="Kursblatt", outcome="absent", folders_searched=["in", "old"]))

    def test_a_transliterated_search_does_not_count(self):
        topics = team.Topics([{"topic": "Prüfbericht", "sender": ""}], "AB-2030-11", "2030-03-10", self.site,
                             self.ledger)
        self.site.trail += ["https://post.example/?box=in&q=AB-2030-11 Pruefbericht",
                            "https://post.example/?box=old&q=AB-2030-11 Pruefbericht"]
        answer = asyncio.run(topics.close(topic="Prüfbericht", outcome="absent"))
        self.assertIn("spells it 'Prüfbericht'", answer)
        asyncio.run(topics.close(topic="Prüfbericht", outcome="absent"))
        # refused twice at most: a website the check does not fit cannot trap the agent
        self.assertIn("Closed", asyncio.run(topics.close(topic="Prüfbericht", outcome="absent")))


class Opened(unittest.TestCase):
    def test_a_topic_closes_only_with_a_message_the_agent_saw(self):
        class Tab:
            id, trail = "post", []

            def __init__(self):
                self.pages = ["Inbox: Staffelrabatt AB-2030-11 · 08.03.2030"]

            def has_seen(self, text):
                return any(text.lower() in page.lower() for page in self.pages)

        tab, ledger = Tab(), team.Ledger()
        topics = team.Topics([{"topic": "Kursblatt", "sender": ""}], "AB-2030-11", "2030-03-10", tab, ledger)
        ledger.add("post", "/m", "mail", {"subject": "Kursblatt AB-2030-11", "date": "08.03.2030", "rate": "0,92"})
        arguments = dict(topic="Kursblatt", outcome="recorded", subject="Kursblatt AB-2030-11",
                         reference_as_written="AB-2030-11", date="08.03.2030")
        self.assertIn("No page you have viewed shows", asyncio.run(topics.close(**arguments)))
        tab.pages.append("Kursblatt AB-2030-11 · 08.03.2030 · 1 XYZ = 1,2345 EUR")
        self.assertIn("Closed Kursblatt", asyncio.run(topics.close(**arguments)))


class PlanTopics(unittest.TestCase):
    BRIEF = ("Use the latest Zinsblatt message from kasse@ for the exchange rate. Authorized subjects/senders: "
             "Prüfbericht/labor, Kursblatt/geld.")

    def test_topics_take_the_brief_spelling_and_listed_subjects_are_added(self):
        topics = team.plan_topics([{"topic": "Pruefbericht", "sender": "labor", "feeds": "other"},
                                   {"topic": "Zinsblatt", "sender": "kasse", "feeds": "fx"},
                                   {"topic": "Staffelrabatt", "sender": "chef", "feeds": "discount"}], self.BRIEF)
        self.assertEqual([t["topic"] for t in topics], ["Prüfbericht", "Zinsblatt", "Staffelrabatt", "Kursblatt"])
        self.assertEqual(topics[-1]["sender"], "geld")

    def test_subjects_the_rules_name_as_messages_are_added_and_the_reference_is_no_topic(self):
        brief = ("Use the latest Zinsblatt message for the exact reference from kasse@ for the rate. Check the "
                 "Lagerliste message too.")
        topics = team.plan_topics([{"topic": "AB-7", "feeds": "other"}, {"topic": "AB-7", "feeds": "discount"}],
                                  brief, "AB-7")
        self.assertEqual([(t["topic"], t.get("sender", "")) for t in topics],
                         [("AB-7", ""), ("Zinsblatt", "kasse"), ("Lagerliste", "")])


class OutsideParty(unittest.TestCase):
    def test_the_buyers_messages_are_found_by_sender_not_by_a_topic_word(self):
        ledger = team.Ledger()
        site = SimpleNamespace(id="post", trail=[], credentials={"username": "vertrieb@firma.example"})
        topics = team.Topics([{"topic": "Käufer", "sender": "", "feeds": "quantity"}], "AB-2030-11",
                             "2030-03-10T09:00:00Z", site, ledger)
        site.trail += ["https://post.example/?folder=inbox&q=AB-2030-11", "https://post.example/?folder=archive&q=AB-2030-11"]
        self.assertIn("Closed", asyncio.run(topics.close(topic="Käufer", outcome="absent",
                                                          folders_searched=["inbox", "archive"])))
        topics = team.Topics([{"topic": "Käufer", "sender": "", "feeds": "quantity"}], "AB-2030-11",
                             "2030-03-10T09:00:00Z", site, ledger)
        ledger.add("post", "/m/7", "buyer message", {"subject": "AW: Anfrage AB-2030-11", "date": "08.03.2030 11:00",
                                                     "change": "Position 3: 14 Stück"}, agent="post")
        answer = asyncio.run(topics.close(topic="Käufer", outcome="recorded", subject="AW: Anfrage AB-2030-11",
                                          reference_as_written="AB-2030-11", date="08.03.2030 11:00",
                                          sender="einkauf@kunde.example"))
        self.assertIn("Closed", answer)  # an outside party's address is expected, not another sender's


class Delegation(unittest.TestCase):
    def test_a_part_is_delegated_once_and_its_helper_starts_where_the_lead_is(self):
        asyncio.run(self.check())

    async def check(self):
        started = []

        async def fake_investigate(site, task, the_plan, ledger, deadline, **kwargs):
            started.append((kwargs["name"], kwargs["first_view"]))

        class Tab:
            async def goto(self, url):
                return f"view of {url}"

        class Lead:
            id, page = "werk", SimpleNamespace(url="https://werk.example/search?q=KG-17")

            async def spawn(self):
                return Tab()

        ledger = team.Ledger()
        ledger.add("spec", "/r", "requirement", {"id": "R-2", "group": "KG-17"})
        helpers = []
        original, team.investigate = team.investigate, fake_investigate
        try:
            [(_, delegate)] = team.helper_tools(Lead(), {}, {}, ledger, time.time() + 300, helpers)
            self.assertIn("works on this", await delegate("requirement R-2, group KG-17, positions 3 and 4"))
            self.assertIn("already has KG-17, R-2", await delegate("group KG-17 for R-2"))
            self.assertIn("exactly as the other agents recorded", await delegate("requirement R-5, group KG-99"))
            self.assertIn("exactly as the other agents recorded", await delegate("requirement R-2, group pending"))
            await asyncio.gather(*helpers)
        finally:
            team.investigate = original
        self.assertEqual(started, [("werk-2", "view of https://werk.example/search?q=KG-17")])


class Grounding(unittest.TestCase):
    def test_values_no_page_showed_are_refused_then_marked_unverified(self):
        class Shown:
            id, page = "werk", SimpleNamespace(url="https://werk.example/x")
            seen = set(team.web.amounts("Preis 1.234,56 EUR ab 25 Stück, je 100 Stück 456,78"))

            def unseen(self, text):
                return [d for d in team.web.amounts(text) if d not in self.seen]

        ledger = team.Ledger()
        record = next(function for schema, function in team.record_tools(Shown(), ledger, "werk")
                      if schema["function"]["name"] == "record")
        self.assertIn("Recorded", asyncio.run(record("price", {"price": "1234.56", "per": "100"})))
        answer = asyncio.run(record("price", {"scales": ["333.111", "321.222", "310.333"]}))
        self.assertIn("Nothing was recorded", answer)
        asyncio.run(record("price", {"scales": ["333.111", "321.222", "310.333"]}))
        self.assertIn("unverified", asyncio.run(record("price", {"scales": ["333.111", "321.222", "310.333"]})))
        self.assertEqual(len(ledger.entries), 2)
        self.assertIn("unverified", ledger.entries[-1])
        # a lone rate no page showed is refused too
        self.assertIn("Nothing was recorded", asyncio.run(record("fixing", {"rate": "0,92", "currency": "XYZ"})))
        self.assertIn("Recorded", asyncio.run(record("fixing", {"rate": "456,78"})))  # shown on a page

    def test_an_agent_is_let_go_once_refusing_brings_nothing_new(self):
        ledger = team.Ledger()
        enough = team.enough_refusing(ledger, "werk")
        self.assertFalse(enough())  # it has recorded nothing of its own: it may be waiting for others
        ledger.add("werk", "/m", "material", {"price": "1234.56"}, agent="werk")
        self.assertFalse(enough())  # no gap check yet: nobody knows its part is complete
        ledger.latest_inputs = {"missing": [{"fact": "price of QX-2", "site_id": "werk"}]}
        self.assertFalse(enough())  # the gap check still wants something from this website
        ledger.latest_inputs = {"missing": [{"fact": "a rate", "site_id": "post"}]}
        self.assertFalse(enough())
        ledger.add("spec", "/r", "requirement", {"stroke": "489"}, agent="spec")
        self.assertFalse(enough())  # something new arrived
        self.assertFalse(enough())
        self.assertTrue(enough())  # twice nothing new


class UnusedRequirement(unittest.TestCase):
    def test_a_requirement_no_position_uses_is_not_delegated(self):
        async def check():
            ledger = team.Ledger()
            ledger.add("portal", "/lv", "positions", [{"tender": "AB-77", "position": "1", "requirement": "R-2"}])
            ledger.add("spec", "/r", "requirement", [{"id": "R-2", "group": "KG-17"}, {"id": "R-3", "group": "KG-33"}])
            plan = {"tender_reference": "AB-77",
                    "sites": [{"site_id": "portal", "kind": "tender"}, {"site_id": "spec", "kind": "specification"}]}
            lead = SimpleNamespace(id="werk", page=SimpleNamespace(url="https://werk.example/"))
            [(_, delegate)] = team.helper_tools(lead, {}, plan, ledger, time.time() + 300, [])
            return await delegate("tender AB-77: requirement R-3, group KG-33")  # the reference proves nothing
        self.assertIn("No position of the tender refers", asyncio.run(check()))


class HandedGaps(unittest.TestCase):
    def test_a_lead_is_let_go_once_its_open_gaps_have_their_own_agents(self):
        async def check():
            ledger = team.Ledger()
            ledger.add("werk", "/m", "material", {"price": "1234.56"}, agent="werk")
            ledger.latest_inputs = {"missing": [{"fact": "price of QX-2", "site_id": "werk"}]}
            enough = team.enough_refusing(ledger, "werk")
            self.assertFalse(enough())  # nobody has the gap: keep working
            job = asyncio.get_running_loop().create_future()  # a follow-up still working on it
            ledger.handed["werk"] = [("price of QX-2", job, "werk+g1")]
            results = [enough(), enough(), enough()]
            self.assertTrue(results[-1])  # idle twice with the gap in other hands
            job.set_result(None)  # the follow-up ended without recording anything: the gap is back
            self.assertFalse(team.enough_refusing(ledger, "werk")())
            ledger.add("werk", "/m2", "material", {"price of QX-2": "88.00"}, agent="werk+g1")
            fresh = team.enough_refusing(ledger, "werk")
            self.assertTrue([fresh(), fresh(), fresh()][-1])
        asyncio.run(check())


class QueuedParts(unittest.TestCase):
    def test_a_part_waits_for_the_next_free_helper(self):
        asyncio.run(self.check())

    async def check(self):
        started, release = [], asyncio.Event()

        async def fake_investigate(site, task, the_plan, ledger, deadline, **kwargs):
            started.append(kwargs["name"])
            await release.wait()

        class Tab:
            async def goto(self, url):
                return "view"

        class Lead:
            id, page = "werk", SimpleNamespace(url="https://werk.example/")

            async def spawn(self):
                return Tab()

        ledger = team.Ledger()
        ledger.add("spec", "/r", "requirement", {"id": "R-2", "group": "KG-17"})
        ledger.add("spec", "/r", "requirement", {"id": "R-3", "group": "KG-18"})
        helpers, parts = [], []
        original, places = team.investigate, team.HELPERS
        team.investigate, team.HELPERS = fake_investigate, 1
        try:
            [(_, delegate)] = team.helper_tools(Lead(), {}, {}, ledger, time.time() + 300, helpers, parts)
            self.assertIn("works on this", await delegate("requirement R-2, group KG-17"))
            self.assertIn("queued", await delegate("requirement R-3, group KG-18"))
            self.assertIn("already has KG-18, R-3", await delegate("group KG-18 for R-3"))  # queued counts as taken
            await asyncio.sleep(0.1)
            self.assertEqual(started, ["werk-2"])  # one place: the second part waits
            release.set()
            await asyncio.wait_for(asyncio.gather(*helpers), 10)
            self.assertEqual(started, ["werk-2", "werk-3"])
        finally:
            team.investigate, team.HELPERS = original, places
        self.assertEqual([part["keys"] for part in parts], [{"R-2", "KG-17"}, {"R-3", "KG-18"}])

    def test_the_reference_and_a_shared_revision_do_not_make_parts_overlap(self):
        async def check():
            async def fake_investigate(site, task, the_plan, ledger, deadline, **kwargs):
                await asyncio.sleep(0.05)

            class Tab:
                async def goto(self, url):
                    return "view"

            class Lead:
                id, page = "werk", SimpleNamespace(url="https://werk.example/")

                async def spawn(self):
                    return Tab()

            plan = {"tender_reference": "AB-2030-11", "sites": [{"site_id": "tp", "kind": "tender"},
                                                                {"site_id": "spec", "kind": "specification"}]}
            ledger = team.Ledger()
            ledger.add("tp", "/t", "tender", {"reference": "AB-2030-11", "positions": [{"number": "1", "requirement": "Q-1"},
                                                                       {"number": "2", "requirement": "Q-2"}]})
            for requirement, group in (("Q-1", "KG-17"), ("Q-2", "KG-18")):
                ledger.add("spec", "/r", "requirement", {"requirement": {"id": requirement, "revision": "RV-77",
                                                                         "catalogue_group": group}})
            self.assertEqual(team.part_ids(ledger, plan), {"Q-1", "Q-2", "KG-17", "KG-18"})
            original, team.investigate = team.investigate, fake_investigate
            try:
                [(_, delegate)] = team.helper_tools(Lead(), {}, plan, ledger, time.time() + 300, [], [])
                self.assertIn("works on this", await delegate("AB-2030-11 RV-77: requirement Q-1, group KG-17"))
                self.assertIn("works on this", await delegate("AB-2030-11 RV-77: requirement Q-2, group KG-18"))
                self.assertIn("already has KG-18, Q-2", await delegate("AB-2030-11 RV-77: KG-18 for Q-2 again"))
            finally:
                team.investigate = original
        asyncio.run(check())

    def test_a_part_without_a_material_record_holds_the_lead(self):
        ledger = team.Ledger()
        ledger.add("werk", "/n", "ERP issue", "groups noted: KG-18 still to do", agent="werk")
        self.assertFalse(team.material_record(ledger.entries[-1], "werk", {"R-3", "KG-18"}))  # a note, no material
        ledger.add("werk", "/m", "material", {"material": "QX-9", "group": "KG-18"}, agent="werk-3")
        self.assertTrue(team.material_record(ledger.entries[-1], "werk", {"R-3", "KG-18"}))
        self.assertFalse(team.material_record(ledger.entries[-1], "other", {"R-3", "KG-18"}))
        ledger.add("werk", "/p", "price", {"material": "QX-1", "price": "1234.56"}, agent="werk")
        ledger.latest_inputs = {"missing": []}
        open_now = ["requirement R-4, group KG-19"]
        enough = team.enough_refusing(ledger, "werk", pending=lambda: open_now)
        self.assertFalse(any([enough(), enough(), enough()]))  # an open part: never let go
        open_now.clear()
        self.assertTrue([enough(), enough(), enough()][-1])


class RequirementMapping(unittest.TestCase):
    def test_a_position_must_use_the_requirement_the_tender_names(self):
        plan = {"sites": [{"site_id": "portal", "kind": "tender"}, {"site_id": "spec", "kind": "specification"}]}
        ledger = team.Ledger()
        ledger.add("portal", "/t", "tender", {"positions": [{"number": "02.01", "requirement": "Q-7"},
                                                            {"number": "02.02", "requirement": "Q-9"}]})
        ledger.add("portal", "/qa", "Q&A", [{"no": "4711", "text": "Position 02.02: Gruppe K-1"}])  # no requirement
        ledger.add("spec", "/s", "specification", {"number": "02.02", "requirement": "Q-8"})  # not the tender's word
        inputs = {"positions": [{"position": "2.1", "requirement": {"id": "Q-7"}},
                                {"position": "02.02", "requirement": {"id": "Q-8"}}]}
        self.assertEqual(team.requirement_mismatches(inputs, ledger, plan),
                         ["position 02.02 uses requirement Q-8, but the tender's latest records name Q-9 for it"])
        ledger.add("portal", "/t2", "tender", {"positions_corrected": [{"number": "02.02", "requirement": "Q-8"}]})
        self.assertEqual(team.requirement_mismatches(inputs, ledger, plan), [])  # the latest record counts


class HungStart(unittest.TestCase):
    def test_a_start_that_hangs_moves_to_a_fresh_tab(self):
        class Stuck:
            id, url = "spec", "https://spec.example/"

            async def goto(self, url):
                await asyncio.sleep(60)

            async def fresh_tab(self, url=None):
                return "Fresh start page"

        team.ENTER_SECONDS, saved = 0.2, team.ENTER_SECONDS
        try:
            self.assertEqual(asyncio.run(team.enter(Stuck())), "Fresh start page")
        finally:
            team.ENTER_SECONDS = saved


class Groups(unittest.TestCase):
    def test_topics_are_dealt_out_about_three_per_agent(self):
        topics = [{"topic": str(number)} for number in range(9)]
        groups = team.topic_groups(topics)
        self.assertEqual(len(groups), 3)
        self.assertEqual(sorted(t["topic"] for group in groups for t in group), [str(n) for n in range(9)])
        self.assertEqual(len(team.topic_groups(topics[:3])), 1)
        self.assertEqual(team.topic_groups([]), [])


class BlockedStatus(unittest.TestCase):
    def test_only_the_materials_own_status_counts(self):
        for active in ("01 (status key: 01 freigegeben · 03 gesperrt)", "01 freigegeben (active); QX-77 03 gesperrt",
                       "01 active; 03 blocked", "nicht gesperrt", "aktiv", ""):
            self.assertFalse(team.blocked(active), active)
        for dead in ("03 gesperrt", "gesperrt (03)", "inactive", "nicht freigegeben", "blocked; see legend"):
            self.assertTrue(team.blocked(dead), dead)

    def test_a_confused_no_bid_naming_active_materials_becomes_a_bid(self):
        ledger = team.Ledger()
        inputs = {"decision": "no_bid", "positions": [
            {"position": "1", "requirement": {"id": "R-1", "catalogue_group": "GR-1"}, "material_number": "QX-11",
             "material_attributes": {"status": "01 freigegeben (status key: 01 freigegeben · 03 gesperrt)"}}]}
        team.normalize_no_bid(inputs, ledger)
        self.assertEqual(inputs["positions"][0]["material_number"], "QX-11")
        self.assertFalse(team.no_bid_shown(inputs))


if __name__ == "__main__":
    unittest.main()
