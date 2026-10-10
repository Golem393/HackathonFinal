"""Agent profiles: which model each sub-agent uses, whether it thinks, and how much it may do.

Thinking makes the hosted Qwen slower and far more expensive per step (measured on one click decision: 4.1 s and
114 output tokens with thinking, 1.6 s and 4 tokens without). Most browsing steps are simple, so:

    thinking = "off"    never think: logins, gates, fetching a TAN, filling known values
    thinking = "auto"   answer fast, think only after a step went wrong (failed action, page did not change,
                        repeated action, refused navigation) until a step succeeds again
    thinking = "on"     always think: reading rules, matching attributes, deciding what applies

Override any profile without code changes, e.g. locally:
    AGENT_PROFILES='{"mail": {"thinking": "on"}, "tender_submit": {"max_steps": 120}}'
"""
import json
import os
from dataclasses import dataclass, field, replace

import models


@dataclass(frozen=True)
class Profile:
    name: str
    thinking: str = "auto"          # "off" | "auto" | "on"
    model: str = models.QWEN_MODEL
    max_steps: int = 40             # a safety cap: deadlines are the real limit (a step costs ~3-5 s)
    keep_pages: int = 2             # full page views kept in context; older ones become stubs
    text_limit: int = 7000          # characters of page text per view (more via read_page offset)
    extra: dict = field(default_factory=dict)  # further request fields for this model

    def request_options(self, think: bool) -> dict:
        """Fields for chat.completions.create: the hosted Qwen (vLLM) switches thinking per request."""
        options = dict(self.extra)
        if self.model.startswith("qwen"):
            body = dict(options.pop("extra_body", {}))
            body["chat_template_kwargs"] = {**body.get("chat_template_kwargs", {}), "enable_thinking": think}
            options["extra_body"] = body
        return options


PROFILES = {
    # Logs in to the webmail at the start, in parallel, and gets it past its gates.
    "mail_login": Profile("mail_login", thinking="off", max_steps=12),
    # Logs in to a site (its own credentials) whenever a login form shows; hands access checks to site_gate.
    "site_login": Profile("site_login", thinking="off", max_steps=14),
    # Passes a site's access check (unlock slider, "not a robot", code shown on the page, terms, continue).
    "site_gate": Profile("site_gate", thinking="auto", max_steps=12),
    # Fetches one thing from the mailbox for another agent (TAN, address, a named mail).
    "mail": Profile("mail", thinking="auto", max_steps=25),
    # Reads approvals and rule mails (discount, Konditionsregeln, bonus bands...) and decides which applies.
    "mail_research": Profile("mail_research", thinking="auto", max_steps=80, keep_pages=2),
    # Walks the tender portal's submission flow and fills in values it is given.
    "tender_submit": Profile("tender_submit", thinking="auto", max_steps=90),
    # Reads the tender, bill of quantities and Q&A.
    "tender_research": Profile("tender_research", thinking="auto", max_steps=60, keep_pages=2),
    # Reads every bidder Q&A answer (quantity changes, withdrawals, amendments, keys, fees).
    "tender_qa": Profile("tender_qa", thinking="auto", max_steps=80, keep_pages=2, text_limit=10000),
    # Learns the ERP's navigation once and writes a site map for the others.
    "erp_scout": Profile("erp_scout", thinking="auto", max_steps=40),
    # Finds the active material matching one requirement (candidates, attributes, status).
    "erp_finder": Profile("erp_finder", thinking="auto", max_steps=50),
    # Reads one material's conditions, stock, lead times, carton, masses via the site map's pages.
    "erp_details": Profile("erp_details", thinking="auto", max_steps=35),
    # (older single-agent ERP flow) one position's material and commercial facts.
    "erp_position": Profile("erp_position", thinking="auto", max_steps=80),
    # Reads the current specification revision on the supplier portal.
    "spec": Profile("spec", thinking="auto", max_steps=70, keep_pages=2),
    # Anything else.
    "default": Profile("default", thinking="auto", max_steps=60),
}


def profile(name: str) -> Profile:
    """The named profile with any AGENT_PROFILES override applied; unknown names get the default's settings."""
    base = PROFILES.get(name) or replace(PROFILES["default"], name=name)
    try:
        override = json.loads(os.environ.get("AGENT_PROFILES") or "{}").get(name) or {}
    except ValueError:
        override = {}
    known = {k: v for k, v in override.items() if k in Profile.__dataclass_fields__ and k != "name"}
    return replace(base, **known)
