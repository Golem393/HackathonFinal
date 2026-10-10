"""Mail research as focused sub-agents: one login, then one small agent per topic, each in its own tab of the same
logged-in mailbox session, all at once. A stuck topic no longer holds up the others, and each agent has a short goal
with a clear end (the old single mail agent ran out of steps before it reached the rule mails).

    mail-login       log in, get past checks, note the mailbox's own address
    mail-fx          Devisenfixing: currency rates by FX key            (needed for foreign-currency prices)
    mail-tech        Technikfreigabe: stroke end reserves by key        (needed for usable-travel requirements)
    mail-approvals   Rabattfreigabe from the sales director            (discount, its minimum order value)
    mail-rules       the other rule mails                               (clauses, packaging, delivery, setup, bonus, indices)

Results are merged into the MailFacts shape of contracts.py. Senders and subjects come from the task brief, which
states them for every scenario.
"""
import asyncio
import re

import telemetry
import web_agent
from contracts import MAIL_FORMAT
from web_agent import WebAgent

COMMON = """You research our sales mailbox (webmail) for the bid on tender reference {reference}. Scenario date:
{scenario_date}. Only records for EXACTLY this reference count (look-alikes such as "{reference}-A" do not); records
dated after the scenario date never apply. Drafts, local previews and unsent messages never count, whatever they say.
You are already logged in. First read the search field's help text on the page and follow it (how terms combine,
what to include, result limits). Mails are filed in different places: rule mails and older approvals are often in the
ARCHIVE. Search EVERY folder and mailbox the webmail offers (inbox, archive, any other folders, shared or team
mailboxes), each with the reference plus ONE topic word; read the whole result list (read_all_pages) and open EVERY
mail whose subject matches, since look-alikes exist. For each, check before you use it:
its status (a draft, local preview or unsent message never counts), its date (after the scenario date never counts)
and its sender. Copy subject, sender, date, status and body verbatim (tables as text), noting each find with `note`.
Look ONLY for what is asked below; finish as soon as you have it from inbox and archive.

{topic}

Finish with exactly this JSON shape (fill only what this task asks for, leave the rest empty):
{format}"""

TOPICS = {
    "fx": """Find the Devisenfixing mail(s) for this reference from finanzen@ (our mailbox domain): currency rates by
FX key (EUR per unit of a foreign currency). Put each as a rule mail with kind "Devisenfixing".""",
    "tech": """Find the Technikfreigabe mail(s) for this reference from technik@ (our mailbox domain): end reserves by
key for strokes given as usable travel. Put each as a rule mail with kind "Technikfreigabe".""",
    "approvals": """Find every discount approval (Rabattfreigabe) for this reference from the sales director (leitung@
plus our mailbox domain), with any minimum order value it requires. Also note this mailbox's own address.""",
    "rules": """Find these rule mails for this reference (local part @ our mailbox domain): Konditionsregeln from
kalkulation@, Verpackungstarife from logistik@, Terminfreigabe from logistik@, Rüstpools from kalkulation@,
Projektbonus from finanzen@, Preisindizes from kalkulation@. Put each as a rule mail with its kind.""",
}

ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


class MailResearch:
    """Runs the mail sub-agents and keeps them, so their notes can be read live (ask_mailbox answers from them)."""

    def __init__(self, page, site: dict, reference: str, scenario_date: str):
        self.page, self.site = page, site
        self.reference, self.scenario_date = reference, scenario_date
        self.agents: list[WebAgent] = []
        self.results: dict[str, dict] = {}

    def notes(self) -> list[str]:
        """Everything noted in the mailbox so far, by every mail agent (also while they run), logins and gates."""
        notes = [n for agent in self.agents for n in agent.notes]
        for memory in (web_agent.LOGIN_NOTES, web_agent.GATE_NOTES):
            notes += memory.get(self.site["url"], [])
        return notes

    async def topic(self, name: str, deadline: float | None) -> dict:
        page = await self.page.context.new_page()
        agent = WebAgent(page, self.site, label=f"mail-{name}", profile="mail_topic")
        self.agents.append(agent)
        goal = COMMON.format(reference=self.reference, scenario_date=self.scenario_date, topic=TOPICS[name],
                             format=MAIL_FORMAT)
        try:
            result = await agent.run(goal, deadline=deadline)
        except Exception as error:
            telemetry.tracker(f"mail-{name}").event("errors", f"mail-{name} failed: {str(error)[:200]}")
            result = {"error": str(error)[:200]}
        self.results[name] = result
        return result

    async def run(self, deadline: float | None, topics=("fx", "tech", "approvals", "rules")) -> dict:
        """Log in once on the main tab, then all topics in parallel tabs of that session; merged MailFacts."""
        login = WebAgent(self.page, self.site, label="mail-login", profile="site_login")
        self.agents.append(login)
        await login.run(web_agent.LOGIN_GOAL + "\nAlso note this mailbox's own address if the page shows it.",
                        deadline=deadline)
        await asyncio.gather(*(self.topic(name, deadline) for name in topics))
        return self.merged()

    def merged(self) -> dict:
        facts = {"approvals": [], "rule_mails": [], "notes": self.notes()}
        for result in self.results.values():
            facts["approvals"] += [a for a in result.get("approvals") or [] if a not in facts["approvals"]]
            facts["rule_mails"] += [r for r in result.get("rule_mails") or [] if r not in facts["rule_mails"]]
            for key in ("mailbox_address", "bidder_domain"):
                facts.setdefault(key, None)
                facts[key] = facts[key] or result.get(key)
        if not facts.get("mailbox_address"):   # often only in a note ("logged in as ...")
            found = next((m for n in facts["notes"] for m in ADDRESS.findall(str(n))
                          if "logged" in n.lower() or "angemeldet" in n.lower() or "own" in n.lower()), None)
            facts["mailbox_address"] = found
        if facts.get("mailbox_address") and not facts.get("bidder_domain"):
            facts["bidder_domain"] = facts["mailbox_address"].split("@", 1)[1]
        facts["topics"] = {name: ("incomplete" if r.get("incomplete") or r.get("error") else "done")
                           for name, r in self.results.items()}
        return facts
