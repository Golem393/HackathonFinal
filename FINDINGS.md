# Why the agents failed, and the general fixes

What we learned from test runs and local runs, and how it was fixed in a way that should carry over to the final
run's private dataset (other websites, layouts, data). Rules for this file:

- **No values from the websites** (references, material numbers, keys, prices, quantities, logins, TANs, addresses).
  The package reviewer rejects copied scenario values in notes too. `tests/test_no_scenario_values.py` checks every
  tracked file against the facts of the last local run.
- Describe the **pattern** of the problem and a fix that does not depend on one site's layout or wording beyond what
  the task brief states for every scenario.

| # | Symptom | Root cause | General fix | Where |
| --- | --- | --- | --- | --- |
| 1 | Agent left its website and typed one site's login into another | Model navigated to another site's URL itself | Each agent is locked to its site; other systems only through tools (`ask_mailbox`) | `web_agent.act` goto |
| 2 | Final binding submission never happened | Browser confirm dialogs are dismissed by default | Dialogs are accepted and reported to the model | `web_agent.on_dialog` |
| 3 | Unlock gates looped (value set, page still locked) | Sliders that check for a real drag ignore a programmatic value | Sliders are moved by a real mouse drag | `web_agent.drag_slider` |
| 4 | Required checkbox invisible to the model | Styled checkboxes hide the real input | Checkbox state, `required`/`invalid` in the page view; click via the visible label | `OBSERVE_JS` |
| 5 | Code needed for a gate not in the page text | Text drawn on a canvas/image | Accessible names of images/canvases shown as `[image: …]` | `OBSERVE_JS` |
| 6 | Words not recognised in subjects and titles | Zero-width characters inside words | Invisible characters stripped from every page view | `INVISIBLE` |
| 7 | Clicks timed out behind popups | Informational popups cover the page | Covering popup closed (Escape / close button) and click retried, no model step; gates needing input left to the model | `web_agent.click`, `DISMISS_JS` |
| 8 | Agent typed into fake toolbars / download bars | Pages draw look-alike browser parts | Prompt rule: ignore look-alike browser parts | `SYSTEM` prompt |
| 9 | Paged lists cost one step per page; agents stopped before the last page | No paging helper | `read_all_pages(next_id)` on a model-chosen list | `web_agent.read_all_pages` |
| 10 | Files (CSV/ZIP/TXT) unreadable | Documents are downloads, not pages | `open_document` reads downloads and ZIP members; no download -> page view | `web_agent.open_document`, `documents.py` |
| 11 | Hung model calls stalled agents for minutes | One lost request waited the client's full timeout | Short per-attempt timeouts, growing on retry; finish cleanly when unreachable | `web_agent.call_model` |
| 12 | Found facts lost when an agent ran out of steps or time | Only `finish` produced the result | Notes are turned into the result format by one final call | `web_agent.finalize` |
| 13 | Slow steps everywhere | Thinking on every step | Profiles: thinking off / auto (only after a failed step) / on | `profiles.py` |
| 14 | Agents repeated the same action many times | Prompt rules alone were ignored | Code counts repeats and warns; "page did not change" note | `web_agent.run`, `act` |
| 15 | Quantity changes missed | One agent read positions and all Q&A pages within one budget | Separate Q&A agent with its own session | `research.QA_GOAL` |
| 16 | Amendment not applied | Q&A gave attribute names in site language with units | Attribute names and units normalized to our keys | `calculator.normalize_attributes` |
| 17 | Dates read in the wrong order | Mixed date formats with an order label | Parser follows labels like (DD/MM) / (MM/DD) | `calculator.day` |
| 18 | ERP agents all ran out of steps | Every tab rediscovered the ERP; one agent did everything per position; no clear stop | Scout learns navigation once (site map); finder per requirement; detail reader per material; explicit stop rules | `erp_agent.py` |
| 19 | Finder stopped at a blocked material | First candidate taken | Status checked; next candidate when blocked | `erp_agent.FINDER_GOAL` |
| 20 | Finder spent most steps "proving" a match | Uncertainty (usable travel without reserve) led to ERP-wide cross-checks | Stay in the catalogue group; usable travel without reserve: smallest nominal above, finish | `erp_agent.FINDER_GOAL` |
| 21 | A wrong no-bid would lose the whole bid | No match on an unresolved usable-travel requirement treated as "no material" | No-bid only from a final requirement and a finished search | `calculator.compute_bid` |
| 22 | Conditional discount set to 0 % | Threshold only checked when every price was known | A partial sum that reaches the minimum proves it | `calculator.approved_discount` |
| 23 | Logins and session expiries cost work-agent steps | Every agent logged in itself | Dedicated login agent per site on any password field, with per-site memory | `web_agent.delegate` |
| 24 | Access checks cost work-agent steps | Gates on many pages | Dedicated gate agent; only for gates still locked; all gate actions in one turn | `GATE_JS`, `GATE_GOAL` |
| 25 | Submission agent re-researched documents | Goal did not say research was done | Goal: research is done, go straight through the form | `agent.SUBMIT_GOAL` |
| 26 | Contact e-mail rejected on the form | Own mailbox address not handed over | Mail research returns the mailbox's own address; handed to the submission | `agent.solve` |
| 27 | Submission blocked ~10 min on one question about our own address | The answer was in a running agent's notes, but only final results were shared; the asking agent browsed through gates | `ask_mailbox` first answers from live notes (research, login, gate, earlier asks) with one call | `agent.answer_from_notes` |
| 28 | A hanging sub-agent kept the run alive past its time | No global limit | Hard stop of the whole solve shortly before the clock ends | `agent.main` |
| 29 | Positions without a converted price were left out of the bid | Calculator only kept fully priced positions | Every position with a known material goes in (quantity, material, lead time score on their own); unknown price = 0.00, noted | `calculator.compute_bid` |
| 30 | Foreign-currency prices unusable | No conversion | Rate from the latest FX rule mail by the condition's FX key; converted base price HALF_UP to cents | `calculator.fx_rate` |
| 31 | ERP waited for the full Q&A; only 3 tabs | Sequential phases, low parallelism | ERP starts with positions + specification, 6 tabs; requirements changed by the Q&A are searched again | `agent.erp_phase` |
| 32 | Calls slow with large context | Bulky tool results (paged lists, documents) stayed in context | All bulky results shrink like page views; smaller page text per view | `web_agent.shrink_old_pages`, `profiles.py` |
| 33 | Number formats mixed within one system | Each price record states its own format (e.g. en-US vs de-DE) | Agents convert with the stated format and also copy the shown text | `erp_agent.DETAILS_GOAL` |
| 34 | Rule mails found late or never | Mail agent spent its budget elsewhere; searches too narrow | Order: own address, then rules others need early, then approvals, then the rest; inbox and archive; fallback searches | `research.MAIL_RESEARCH_GOAL` |
| 35 | A position got no requirement, so no material and no quantity | The spec agent missed a requirement (viewer page numbering differs from the document) | Cross-check the spec against the requirement IDs the tender's positions reference; missing ones get a targeted follow-up search | `agent.spec_complete`, `research.SPEC_FOLLOWUP_GOAL` |
| 36 | An agent froze for good after a click during navigation | Page reads (`evaluate`, `title`, `content`) have no timeout; a navigating frame can hang them | Every page read has a 5-10 s limit; every action a hard ceiling (90 s, tools 600 s) and counts as failed | `web_agent.observe`, `run` |
| 37 | FX rate never found; searching the reference with the topic word found nothing | Rule mails are filed in the archive, with a look-alike (future-dated draft) next to the real one; the site's search help states how to search | Mail agents read the search help, search every folder and mailbox (inbox, archive, others), open every matching mail and check status, date and sender | `mail.COMMON` |
| 38 | Single mail agent never reached the rule mails | One agent, many topics, gates on every page | One login, then focused topic agents (fx, tech, approvals, rules) in parallel tabs | `mail.py` |
| 39 | Mails in a list were never seen | The list sits in a scroll area that loads rows only when scrolled; agents had no way to scroll | Scroll areas shown as controls; `scroll(id, to_end)` by mouse wheel until nothing new loads; prompt rule | `web_agent.scroll` |
| 40 | Mail body was cut off in a scrolling reading pane | Page observation was limited and HTML downloads were treated as navigation | `read_html` extracts the complete DOM and frames without scrolling; downloaded HTML is converted directly to text | `web_agent.read_html`, `documents.py` |

## Still open

- Webmail drafts / unsent previews can look like approvals: approvals must be sent records only.
- Rule mails (Konditionsregeln, Technikfreigabe, ...) are found late or not at all; the calculator's advanced
  components (`advanced_components`) are not implemented yet.
- The ERP scout runs out of steps before it has mapped stock, conditions and status pages: coverage before depth.
- Q&A rows reveal a hidden date only once per page render; read_all_pages may stop when the next control's label changes.
