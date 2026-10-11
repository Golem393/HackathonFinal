# Pitfalls: what goes wrong on the websites and how the agent handles it

Everything below was found by working through the public scenario by hand on 10 Oct 2026, page by page, then
computing the full answer twice (with `agent/calc.py` and independently) with identical results. It is written
generically on purpose: no tender reference, material, price or name from the public data appears here or in
`agent/`, because the final run uses other websites and data. The public specifics (values, URLs, the expected
answer) live in `notes/`, which git ignores.

Each item says what trips an agent up and where the agent deals with it: **code** (fixed behaviour in `web.py`,
`calc.py`, `submit.py`) or **prompt** (what the models are told in `prompts.py`).

## 1. Every website

| Pitfall | What happens | Handled by |
|---|---|---|
| Sessions expire after a few idle minutes | The next click lands on a login page; unsaved form steps are lost | prompt: call `login()` and continue; keep working without pauses |
| Cookie wall first | Nothing else is reachable until it is accepted | prompt: accept the necessary-cookies notice |
| Popups that come back on many pages (surveys, maintenance and mailbox notices) | They cover the page and swallow the next click; their "accept and continue" link leads elsewhere | code: click falls back to a DOM click after 2.5 s; prompt: close with × or the close button |
| Fake browser bar and fake download bar inside the page | Their links lead to decoy pages | prompt: decoy buttons exist, check each action's result |
| Invisible characters inside identifiers | A reference copied from the page does not match the brief | code: the view strips zero-width characters |
| A hidden decoy value next to the visible one (e.g. a second status code with `display:none`) | Reading the HTML gives two values | code: the view shows only what is rendered |
| Collapsed sections (▶ summaries) | Message bodies, document contents and form fields stay hidden | code: the view opens every `<details>`; `fill()` opens the section around a field |
| Frames inside frames | The content is two frames deep; the outer frames look empty | code: the view renders every frame of the page, and says when a frame needs `goto()` |
| Paged lists | A page number past the last one shows the last page again | prompt: stop when records repeat; read every page |
| Flaky "service temporarily unavailable" pages | One request fails at random | code: `goto()` retries server errors; prompt: reload |
| Numbers in two formats on the same site | "123,456 (en-US)" is 123456, "123.456 (de-DE)" is 123456 too; without the tag one of them is read as 123.456 | code: `calc.dec()` reads the locale tag; prompt: copy numbers with their format note |
| Dates in mixed formats (MM/TT next to TT/MM) and per-site time zones | The wrong revision or record looks newest | prompt: read the format given with each date; record times with zones |
| Look-alike references (an extra suffix) and future-dated records | A record that looks right does not apply | prompt (solver): exact reference, no later than the scenario date |

## 2. Tender portal

- The tender list has many tenders on several pages; search for the exact reference.
- Expressing interest may be needed before documents open.
- Each document has several "open" buttons in shuffled order; only one opens the document, the others lead to a
  survey or back to the list. Document contents sit in a collapsed "show content" section.
- The Q&A sits in a frame inside a frame, a few answers per page.
- **Each answer's date is hidden** behind a small control next to it (a receipt marker); the list shows the answer
  without its date. An agent that does not click it records "date not displayed" and cannot tell which change is
  the latest (seen in the first sandbox run).
- **Answer numbers are not chronological**: a lower number can be the newer answer. Quantities follow the latest
  *dated* change; a later answer can withdraw an earlier one by its number.
- Q&A answers also assign per position: condition group, packaging tariff key, delivery commitment key, shared
  setup pool, project bonus plan, a one-off setup fee, and technical amendments to a named specification revision
  and requirement. All of them feed the calculation.

## 3. Specification portal

- Documents open only after a release form: choose the purpose that grants the **binding** documents (archive copy
  and preview grant nothing), copy the receipt number shown on the page into its field, confirm the terms, request
  read access. A popup on the way offers a decoy link.
- The revision history mixes date formats, and the highest revision number is not the current one: the revision
  whose **status** says valid governs. The viewer opens the oldest revision by default.
- **Each revision's status is hidden behind a small "release status" button in its row**, the same pattern as the
  Q&A dates. In the second sandbox run the agent did not click it, guessed, named the wrong revision current and
  recorded its requirements before correcting itself. Prompt rule since then: a date or status that is not shown
  sits behind a control next to the record; click it, never guess.
- Each requirement page repeats a decoy line with placeholder values (e.g. an absurd stroke and pressure). The
  requirement's original wording is authoritative.
- A stroke can be a *usable* stroke: the ERP's nominal stroke is the usable stroke (after amendments) plus twice the
  end reserve from the revision-specific technical release mail. Without this step two requirements match nothing
  and the agent would wrongly declare no_bid.
- Pieces per set are stated with the requirement, not with the position.

## 4. ERP

- A notice page after every login: slider, robot checkbox, then copy the displayed receipt number, confirm the
  operating terms, continue. The idle timeout is very short: work through the gate and continue at once.
- Material search by catalogue group returns a short list in a popup region; an empty or broad search shows nothing.
- The search result line already carries pieces per carton, allocation mass, surcharge mass (both in **grams**) and
  the price index key.
- A material record spreads over tabs (basic, technical, planning). The planning tab holds the status: the visible
  value counts, a hidden one next to it is a decoy. **A blocked material can match every attribute** and is offered
  first later in the bid form.
- The stock overview shows physical stock *including* blocked inspection stock. Only freely usable stock counts;
  open the per-location view.
- Price conditions: validity window, currency with an exchange-rate key, a price unit (per 100 pieces), a number
  format, and the quantity scales in a separate view. A material can have several condition records on further
  pages (e.g. last year's); pick the one valid on the scenario date.

| Handled by | Where |
|---|---|
| Unit and format conversion, scale choice, FX, rounding | code: `calc.py` (`dec`, `kilograms`, `scale_price`) |
| Visible status only | code: view |
| Opening tabs, drill-downs, scale views and further records; recording status and free stock | prompt: `FACTS`, `ERP_EXTRA` |
| Blocked materials never qualify; free stock only; grams to kilograms | prompt: `SOLVER`; schema descriptions in `team.py`; code fallback in `calc.kilograms` |

## 5. Mail

- Two folders. **Half of the relevant mails are in the archive**, and the archive lists nothing until searched.
- Search combines words with AND: the exact reference plus one topic word, in each folder.
- The message list and the reading pane each have a slider and robot checkbox, and **every message has its own lock
  again** inside. Opening a message on its own page needs only that one unlock.
- **Every message carries a decoy box** ("local preview / unsent draft", "draft value 99 %", "no approval",
  "not sent"). It is the mail client's widget, not the message. An agent that believes it throws away valid
  approvals.
- The real text is the collapsed "original" section; in some messages it sits further down a scroll box after a
  transport header ("original follows").
- Sender and date come from the envelope / full headers. Authorized senders are a given local part at the bidder's
  own domain; look-alike references, future-dated records and messages that say "this is not a discount approval"
  never apply. Of several approvals, only the latest dated one counts, even when an older one is more generous.
- Mail times are in the mailbox's local zone, not UTC.

## 6. Calculation (all in `calc.py`, covered by `tests/test_calc.py`)

- Quantity: latest dated change, withdrawn answers ignored, sets × pieces per set.
- Base price: the scale with the highest minimum quantity not above the position's quantity, per piece (price unit),
  converted to EUR with the fixing and rounded half up; this EUR price is used everywhere after.
- Discount: the latest approval; its minimum order value is checked on the undiscounted base value; a condition
  group decides whether the discount hits the base only, base plus mass surcharge, or nothing.
- Metal surcharge: surcharge mass (kg) × the index rate whose validity window contains the scenario date (not the
  last rate listed).
- Setup: ordinary fee plus the share of the shared pool (by quantity × allocation mass, cents by largest remainder),
  reported in the surcharge, never discounted.
- Packaging: cartons rounded up per position × tariff, never discounted, never changes the quantity.
- Project bonus: marginal bands on the members' undiscounted goods value, split by largest remainder in cents.
- Lead time: a delivery commitment applies only when pooled demand for its material is within its ceiling
  (inclusive); otherwise stock delivery when free stock covers the pooled demand, else production.
- Final unit price from unrounded parts, rounded once; total = Σ quantity × rounded unit price.

## 7. Bid form

| Step | Pitfall | Handled by |
|---|---|---|
| Bid type | The secondary-bid option is **preselected** | prompt: check every preselected choice |
| Positions | Asked for in a **different order** than the bill of quantities | prompt: each step names its position |
| Configurator | One attribute at a time, each applied with a reload; the material list can offer a **blocked** material first | prompt: apply step by step, select the exact material number |
| Price breakdown | Fields sit in a collapsed section | code: view and `fill()` open it |
| "Add position" | Adds an extra position, which costs points | prompt: never add positions |
| Conditions | The form shows a **gross** amount including VAT | prompt: enter the net total |
| Declarations | Besides "tender documents acknowledged" there is a box for **applying your own terms** | prompt: tick only what the brief asks for |
| Review | Checkpoint headings in shuffled order | prompt: compare the summary with the bid |
| TAN | The page says which **request number** it sent; the mailbox may hold TANs of other requests; only the newest TAN is valid, for 5 minutes | code: `get_tan(request=…)` passes the number to the TAN reader; prompt: open exactly that message, retry with a new request if refused |
| Final confirmation | A native browser confirm dialog | code: dialogs are accepted automatically (`page.on("dialog")`) |

## 8. What went wrong in the first sandbox run (10 Oct, quality 10 of 100)

The run signed a bid on the right tender in 12 minutes: the decision and the reference scored (5 + 5), the TAN step
worked (the submitter passed the request number, the TAN reader opened exactly that mail). Everything else scored 0,
because **every position was left out**.

| What went wrong | Why | Fix |
|---|---|---|
| The ERP agent gave up in the first minutes | It started before the specification agent had recorded the catalogue groups, tried a generic search word (which lists nothing) and called finish; it was sent back twice, then allowed to stop | `wait_for_notes()` tool: it waits for the requirements instead of finishing; up to 6 refusals for the ERP agent; prompt: generic words list nothing, the catalogue groups are the keys |
| Only one of four materials found, without a price | When the groups arrived (about minute 5) the ERP agent had too little time left | investigation runs until 10:30 instead of 9:00 |
| The follow-up round never ran | The solver finished around minute 10:30; the follow-up needed 160 s before the bid form had to start at minute 12 | the bid form starts at minute 14 at the latest (the empty form and TAN took about a minute; a full one about four); the follow-up is 75 s with a 30 s margin |
| All five positions omitted | `calc.py` dropped every position without a valid price | a position with a known material and quantity is entered at unit price 0: material, quantity and lead time still score (45 % of each position) |
| Discount 0 instead of the approved percentage | With no prices, the order value was 0 and failed the approval's minimum order value | with prices missing, the order value is unknown and the approved percentage is used |
| Q&A dates not recorded | Hidden behind a receipt marker per answer (section 2) | prompt: click the control that reveals a missing date |
| A model call after the submission failed with "expired run token" | Submitting ends the run, the proxy then refuses calls | harmless; the bid was already signed |

## 9. Seen in the second sandbox run (with the fixes from section 8)

| Observation | Risk | Next fix |
|---|---|---|
| The ERP agent used `wait_for_notes("requirement")` and started searching as soon as the first catalogue group arrived | – (the fix works) | – |
| The mail agent finished after recording only the discount approvals; refused twice, the third finish was accepted | Condition rules, index, technical release (end reserves!), packaging, delivery, FX, bonus, setup pool all missing | more refusals for every investigator, and a check of what each site's agent recorded against the fact list before accepting finish |
| Model calls of more than 60 s ("the model did not answer in time") on several agents | Three stalls in a row stop an agent; slow calls eat the 20 minutes | measure call latency per run; fall back to a second model or a shorter prompt when calls stall |
| The spec agent first named the superseded revision as current (it read the status column wrong, next to a "release status" button), recorded its requirements, then corrected itself in a later record | The solver gets contradictory records; the wrong revision changes strokes and makes materials not match | solver prompt: a later explicit correction replaces earlier records; recording revisions as one table (number, date, status) before any requirement |
| The ERP agent collected everything (stock, prices, lead times) for a **blocked** candidate before looking at the active one | Wasted minutes on a material that can never qualify | ERP prompt: read the status first, skip conditions and stock of blocked candidates |
| Q&A dates were recorded for some answers after the date-reveal hint, not all | Quantity changes without dates fall back to answer numbers, which are not chronological | check in code: a quantity change without a date is flagged to the solver |
| The CLI timed out on upload, but the server had created the run, in fact **two** (one failed on the platform, one ran); the retry added a third | Duplicate runs: double cost, confusion about which run is which | after a timeout, list every new test run (`atira status`) and compare each one's package id (`atira package <run>`) with ours before retrying |
| A run ended after 33 s with "The platform failed, not your agent system. This run doesn't count" | – (platform side) | start it again |

Results: run #2 quality 15 (decision, reference, discount), run #2b quality 10 (identical package, run in parallel).

| Also found in runs #2 / #2b | Effect | Fix (for run #3) |
|---|---|---|
| **The bid table gave the submitter only the material number**, but the form's configurator asks for bore, stroke, mounting and certification first; the submitter guessed values for the wrong position, gave up and omitted every position | 3 computed positions (material, quantity, one correct lead time) never reached the form | the table now carries each position's configurator values (the material's attributes, else the requirement's); prompt: choose them in order, the closest value above if not offered exactly |
| Positions with a correct quantity but no material were dropped | Quantity points (15 % each) lost on every such position | `calc.py` enters every position with a quantity; the submitter picks the material the configurator offers |
| Run #2b had no priced position at all, so the discount fell to 0 | 5 points | with no priced position the approved percentage stands |
| The mail agent stopped after the approvals | Most price inputs missing | 4 refusals for every investigator (6 for the ERP); prompt: search every topic in every folder before finishing |
| The ERP agent read prices and stock for blocked and non-matching candidates, clicked through menus for every view, and stalled on transient error pages | Too few materials priced | prompt: status first, details only for active matches, open known views directly by address, reload error pages at once |
| A follow-up ERP agent saw pages "truncated" and "unavailable" | Stock and prices unread | same as above; watch in run #3 |

### Run #3 (quality 24.1)

First position points: 01.01 scored 9.1 of 13 (material, quantity, base price, lead time, bonus 0 all right).

| Found in run #3 | Effect | Next fix |
|---|---|---|
| **The submitter could not drive the configurator**: it filled several configurator selects at once or before they unlocked, re-applied, called "failed" (refused), and finally omitted four of five positions; the form took about 8 minutes | Four computed positions (correct materials and quantities) never reached the form | a configurator helper in code: one tool call per position with the values in order; code selects each, applies, waits for the next field and selects the material |
| No time guard in the submission | If the form had taken one minute longer, no signed bid at all (quality 0) | code: with about 3 minutes left, omit unfinished positions and go to the signing step |
| The ERP agent called `wait_for_notes("requirement")` once, got the first requirement, and never re-read the notes: it believed only one catalogue group existed | Only one material priced | when an investigator tries to finish, the refusal shows the other agents' newest records (e.g. all catalogue groups) |
| The mail agent searched a topic in the inbox only, found nothing ("0 messages") and moved on | Packaging tariff, condition rules, technical release, real price index missing | a topic checklist per folder in code or prompt; a 0-hit inbox search must be repeated in the archive |
| The tender agent clicked "ask a new question" and landed in a question form | Minutes lost; it reported being "trapped" | prompt: links that start a new question or message are dead ends for the investigation |
| `total_consistency` scored 0 although the one entered position's quantity × unit price equals the total | 5 points | find out what the check needs (probably every tender position entered) |
| Model calls of more than 60 s again on several agents | Minutes lost | smaller page views in the bid form; measure latency |

Built for run #4 (`run_0bf61df5ff1a56b9`):

- **`configure()` tool** (`web.py`, submitter only): the whole configurator chain in one call. Each field is found by
  its own label, the value is chosen (exact text or value, else the only option starting with it, else the next larger
  number offered), the apply button is clicked, and the code waits for the next field to unlock. It stops at the first
  impossible step and lists what is offered. Tested offline against a made-up cascading form (`tests/test_web.py`).
- **Time guard** (`llm.Agent(warn_at=…)`, used in `submit.py`): three minutes before the submitter's deadline it is
  told to omit what is not entered and sign; "failed" stays refused while more than 90 s remain.
- **Team news on refusal** (`Ledger.digest`, `Agent(news=…)`): when an investigator tries to finish early, the refusal
  lists every record of the other agents in one line each, so the ERP agent sees all catalogue groups.
- **Mail checklist** (prompt): a topic with no hits in one folder is searched in the other folders before moving on.
- **Dead-end links** (prompt): links that start a new question, message, survey or request are not followed.
- Submitter prompt: at most a few actions per position, then omit it and go on.

### Run #4 (failed on the platform side, does not count)

The platform failed after 12.8 minutes ("The platform failed, not your agent system"; its API answered 503 at the
same time) and restarted the run by itself (`run_7194ca1737cc2ce0`, same code). Two failures of our own before that:

| Found in run #4 | Effect | Fix (built after run #4) |
|---|---|---|
| The ERP agent tried to finish seven times while waiting for the requirements; the six refusals ran out in five minutes and the seventh finish was accepted just as the requirements arrived | Nothing priced at all | an agent that waits for others (the ERP) is refused for as long as the team investigates (up to 90 s before its deadline), not a fixed number of times |
| The mail browser went silent right after the automatic login: the first page view never returned (the platform was failing; a page that stops answering scripts does the same) | No mail facts at all; the same hang would have blocked the follow-up round and the TAN reader, so no signed bid | every frame's view times out after 15 s and says "does not respond"; every tool call times out (90 s; `configure` 150 s, `get_tan` 200 s) and tells the model to use the new `fresh_tab()`; the TAN reader always starts in a fresh tab; a follow-up agent on a stuck page starts in a fresh tab; the whole follow-up round has a time limit |
| The team digest cut each record at 200 characters | A requirement's catalogue group, written after its attributes, could be cut off | 500 characters per record, newest records kept when the digest is long |

Both fixes are covered by offline tests (`tests/test_web.py`: a page that freezes for good, a tool that never
returns).

The automatic restart of run #4 (`run_7194ca1737cc2ce0`, the code before these fixes) had the best investigation so
far (three materials priced, stock, lead times), then stopped making model calls during the follow-up round for
eight minutes, exactly the hang the follow-up time limit now prevents, and was cancelled.

### Run #5 (`run_94b520117a1d7447`, with every fix above), seen during the run

Going right: all four needed materials found (the blocked candidate and an expired price condition recognized), 50
records after investigating (run #3: 38), Q&A dates, the right revision, the discount approval with both decoys
rejected, the exact metal index, the delivery commitments, the setup pool; no agent hung, and the ERP agent kept
working instead of giving up.

| Going wrong in run #5 | Effect | Next fix |
|---|---|---|
| The ERP agent priced materials for a requirement that **no position refers to** (the spec lists one requirement more than the bill of quantities uses) and a candidate that does not match | Minutes spent on records nobody needs, while one needed material still lacked its details | ERP prompt: look up only the requirements the tender's positions refer to (the notes show which), in position order |
| The mail agent did not find the **currency fixing** before the solver ran | Two of four materials are priced in a foreign currency: without the fixing their base prices (and everything built on them) cannot be computed | the mail checklist must cover the currency fixing early: every price in a foreign currency needs it |
| The **technical release** (end reserves), packaging tariffs, condition rules and project bonus were still missing at the end of investigating | Nominal strokes, packaging, discount scope and bonus fall back to the follow-up round, which has 75 s | mail: work the topic list in a fixed order (approvals, technical release, currency, tariffs, commitments, conditions, indices, pools, bonus), one search per topic per folder, before any second look |
| The spec agent lost about two minutes to model calls that did not answer within 60 s, then wandered between pages | The ERP agent waited, since its searches depend on the spec's catalogue groups | ask a stalled model call again after about 25 s instead of 60 s; spec prompt: open the document register and the exact reference's specification directly |

**Result: quality 44.1** (run #3: 24.1), signed after 14 min 45 s. `configure()` worked in the real form: four
positions went through with material and quantity, plus the withdrawn-answer check (5). Position points 24.05.

| Found in the result of run #5 | Effect | Next fix |
|---|---|---|
| **`type()` clicks the element when it cannot type into it**: the submitter called `type` with empty text on a button (the "omit position" button), and the fallback clicked it | Positions 01.01 and 01.03 omitted without the model meaning to; 01.03 was re-entered, 01.01 was lost (about 8–13 points) | `type()` only types into text fields; on anything else it returns an error and clicks nothing |
| The net total included a position that was then omitted in the form | Total consistency 0 (5 points) | the bid table shows each position's line total; the submitter enters the sum of the positions actually entered |
| 01.01's quantity came out as the original (24) instead of the latest dated change (25) | Quantity and the price tier wrong | the solver must pass every quantity change with its date (the code picks the latest) |
| Delivery commitments recorded but not applied to their positions | Three lead times wrong | solver: map each position's commitment key from the clarifications to the commitment mail's material, ceiling and weeks |
| One-off setup fees from the clarifications not passed | Surcharges wrong where a setup fee applies | solver prompt: each position's setup fee from the clarifications |
| No currency fixing, packaging tariff or project bonus from the mail | No base or unit price for the three foreign-currency positions; packaging and bonus wrong | mail: derive the topic list from the brief's authorized subjects and senders, work it in order in every folder |

Built for run #6: `type()` refuses anything but text fields (tested: typing into a button presses nothing); the
bid table has a line total per position and the submitter enters the sum of the positions actually entered; the
solver prompt asks per position for every dated quantity change, setup fee, condition group, tariff, commitment and
pool/bonus membership; the mail agent builds its topic list from the brief's authorized subjects, currency fixing and
technical release first; the ERP looks up only the requirements the positions use; a stalled model call is asked
again after 30 s instead of 60 (four stalls in a row stop an agent instead of three).

### Run #6 (`run_d4e4d16d7c4cd738`), seen during the run

Going right: the spec agent recorded all requirements within 2.5 minutes (no model stalls); the mail agent found the
condition rules, delivery commitments, project bonus, packaging tariff and the exact metal index; the solver passed
the dated quantity change, setup fees, condition groups, tariffs and commitments; **position 01.01 came out fully
right** (unit price equal to the hand-computed one); lead times right on all five positions.

| Going wrong in run #6 | Effect | Next fix |
|---|---|---|
| **The ERP again priced materials nobody needs**: the candidates of the requirement no position uses, and a candidate whose stroke does not match, despite the prompt rule from run #5 | Minutes of ERP time, a full record set for materials that can never be in the bid | not a prompt matter only: give the ERP agent the list of requirements the positions use (from the bill of quantities in the ledger) in its refusal news, and have it record a candidate's details only after its attributes match |
| **The ERP session expired while the agent waited** in `wait_for_notes()`; the page became the login form and the agent typed its catalogue searches into the **password field** ("•••" in the platform's browser log), concluded "the search does not work" and lost several minutes | Prices arrived late; the run nearly missed the ERP entirely | keep the session alive while waiting (fetch the current page in the background every ~20 s); `type()` refuses password fields with "your session expired, call login()" |
| The mail agent still found neither the **currency fixing** nor the **technical release** nor the **setup pool** message | No base or unit prices for the three foreign-currency positions; setup pool shares and the project bonus split wrong | these three sit in the archive folder only: the mail prompt must say that a topic with no inbox hit is searched in the archive before the agent moves on (it did search the archive for some topics, not for these) |

**Result: quality 71.2** (run #5: 44.1), signed after 11.5 minutes. All five positions entered (the `type()` fix),
total consistency scored (5), position 01.01 full marks (13 of 13), position points 46.15 of 65. What is left
(28.8 points) hangs almost entirely on the three archive mails above: the currency fixing (base and unit prices of
three positions, the bonus split), the setup pool (three surcharges and the 5-point index-window check, which needs
every surcharge right) and the technical release (stroke derivation without guessing).

Why the mail agent missed them: it searched for a **transliterated topic word** ("ue" instead of "ü"); the mail
search matches words literally, so the archive search returned nothing, and it concluded the message did not exist.
The same search with the brief's spelling finds it at once.

Built for run #7: the mail prompt demands the brief's exact spelling (umlauts and ß), inbox then archive for every
topic, and currency fixing, setup pools and technical release first; `wait_for_notes()` and every refused finish
keep the website's session alive with a background request (`Site.keep_alive`, tested against a local server: the
session cookie goes along, the page is untouched); `type()` refuses password fields with "your session has
probably expired, call login()" (tested); the ERP prompt says to type the group key into the text search, to look up
only the requirements the positions use, and to record a candidate's details only after its attributes match.

### Run #7 (`run_8389c3e690efdf9e`): quality 67.3

The mail agent now searched the archive with the brief's spelling and found the setup pool, technical release,
condition rules and packaging tariff; the setup pool shares came out exactly right; the solver excluded the blocked
candidate on its own; no hangs, no password-field mistakes. But it recorded only the **look-alike price index** and
the **future-dated currency fixing** (the decoys), and its 75-second follow-up found neither real one. Without the
metal rate every surcharge was wrong (index-window check 0) and 01.01's unit price too, so the run scored slightly
below run #6 (71.2), which had found the index but not the pool.

| Found in run #7 | Effect | Next fix |
|---|---|---|
| **The mail agent's coverage varies from run to run**: run #6 found the index but not the pool, run #7 the pool but not the index; prompt rules do not make it complete | 5–10 points swing per run on surcharges, the index check and unit prices | a topic checklist enforced in code: at the start the agent lists its topics from the brief; finish is refused until every topic is marked searched in every folder (found or not found) |
| Decoys found first (look-alike reference, future date) end the agent's search for that topic | The real record is never opened | prompt: a decoy found is not the topic done; keep looking for the exact reference dated no later than the scenario date |
| The ERP status meaning sits in a hidden tooltip ("01 released · 03 blocked"); the view did not show it, the agent called a blocked material "the exact match" | The solver caught it this time; a risk of losing a whole position | the view shows each control's accessible description (tooltip text) next to it |
| The submitter entered one position's surcharge value in another position's field | Small: the value was wrong anyway this time | prompt: before "Weiter", compare the step's position number with the table row |

### Diagnosis of runs #5–#7 (six analysts plus a synthesis) and what was built for run #8

Findings, checked against the logs, the score breakdowns and the hand-checked answer:

- **Nearly every point lost in runs #6 and #7 is a mail fact never recorded.** The solver and `calc.py` are correct:
  replaying the logged run-6 and run-7 inputs with only the missing mail facts added gives exactly 100. The value of
  each fact, all else right: currency fixing about 20, metal index about 23, setup pool about 18, bonus bands about 13.
- **Time was never the limit.** The runs signed after 11.5–14.7 of 20 minutes. The mail agent quit 4.5–7 minutes
  before its window closed, because `finish` was accepted after 4 generic refusals. The ERP worked alone until about
  minute 9.
- **Coverage per topic:**
  - The currency fixing was missed in all three runs: it is archive-only, next to a future-dated decoy with the same
    subject.
  - Decoys found first ended a topic (a look-alike reference, a later date).
  - A transliterated search word found nothing, 12 times in a row.
- **The 75-second follow-up recovered no mail fact in 3 of 3 runs.** It had no site instructions, started on a stale or
  dead-end page, searched key codes in the inbox only, and had no login check.
- **ERP:** no wrong value reached the solver, but 35–40% of its time went to blocked, unused or non-matching
  materials. In run #7 the active alternative to a blocked first hit came at about minute 9, so a wrong no_bid was one
  step away.
- **Investigators had a hidden cap of 150 model steps**, where refused finishes count as steps.
- **The submitter is unreliable:**
  - Run #5 signed with a position omitted and a total that still included it.
  - Run #7 entered one position's row on another's step and skipped fields, and requested 3 TANs.
  - Run #6 was perfect.
- **The platform log loses the first 2–3 minutes of agent output.** It also had no timestamps.

Built (all offline-tested; real run-6 and run-7 records replayed through the checks; nothing run on the live sites
yet):

| Fix | What it does | Fails open how |
|---|---|---|
| Mail topics from the brief | The plan lists every mail topic in the brief's own spelling (a transliterated word is snapped back) and adds every "Subject/sender" pair the brief lists | Unknown words are kept, at most 12 topics |
| Parallel mail tabs | Up to 3 mail agents, about 3 topics each, in tabs of one browser; each tab keeps its own popups | Fewer tabs: topics dealt out again |
| Topic checklist in code | `close_topic` refuses a look-alike reference (its own record shows it), a message dated after the scenario date, an unrecorded message, and "absent" when the search trail does not show the word searched (in two places); `finish` is refused while topics are open | Each check refuses a topic at most twice |
| Gap rounds during the investigation | When the mail agents are done (or 3.5 min before the end): a quick solve; inputs the rules need but that are still empty (foreign currency without rate, masses without index, pool without fee, bonus members without bands, groups without scope) send a fresh mail agent after the matching topic | At most 2 rounds; nothing after the window |
| Follow-up rebuilt | New tab, login, the site's own instructions, the mail checklist for the missing topics; length from the slack (75–210 s) | Bounded by the submission start |
| Submission guard | Before a step is left: does it hold its own row, completely (0,00 included)? Before the TAN: does the summary show each position's material and unit price and the right net total? | One refusal per problem, silent when the layout does not fit, never under 150 s |
| no_bid check | A no_bid stands only if a second look at the candidate list of the group confirms it | Bid with the material empty otherwise |
| ERP helpers | `delegate()` per requirement: deduplicated, starting where the lead is, stopped at the hard stop; logins serialized per browser | At most 3 helpers |
| Safety | Solver hard deadline; investigators bounded by time (400 steps); no typing into password fields via `fill()`; no made-up hosts; keep-alive between phases; select by option text | — |
| Private-data guards | api submission returns the answer; TAN site from the plan; TANs without digits; counts like "1.000"; the condition's number format; ISO times with offsets | Public answer unchanged (re-verified) |
| Logging | Elapsed time on every line, schedule repeated at the end, one compact line per record, exit reason per agent, first line of key tool results | — |

Watch in run #8's log:
- `[team] mail topics` should list all of the brief's topics.
- Each mail agent's `topics:` line should show every topic closed with a real message, not "absent".
- `[team] gap check` should show no gaps, or gaps that a `mail+N` agent then filled.
- Look for `[submit] step check` and `summary check` refusals, and whether they were right.
- `stopped:` lines should give each agent's exit reason.
- Check whether three mail tabs and ERP helpers work side by side: locks, sessions, 503s, model stalls.

### Run #8 (`run_86e8c173d8488a04`): quality 91.8, 15:42 min, $0.50

What worked:
- **Mail: 9 of 9 topics on the right messages by minute 2:06**, from three parallel tabs. This includes the
  archive-only currency fixing next to its future-dated decoy, and the exact price index next to its look-alike.
- **Gap checks** (2:12 and 7:14) found nothing missing.
- **The follow-up worked.** The solver rejected one message whose subject the agent had copied with a typo. A fresh
  `mail+` agent re-read it with the right subject in 29 seconds, and the second solve used it.
- **ERP:** the helpers found 2 of the 4 needed materials in parallel; all four were complete by about minute 5
  (minute 9 in run #7).
- **Every field of 4 of 5 positions was right.** So were the discount, withdrawn answer and index window, and the
  summary check caught a wrong total before the TAN.

| Went wrong in run #8 | Effect | Next fix |
|---|---|---|
| **The ERP lead recorded a price it never opened** ("HZ price" while on another material's page; repeating-digit numbers) after being refused 28 times with "not yet" | 01.01 base and unit price wrong, and the total: 8.25 points | `record()` checks that the identifiers it names appear on the page on screen (refuses once, asks to open that record's page); refusals stop after a few in a row bring no new record |
| The lead delegated one requirement with a made-up catalogue group and attributes (found nowhere in the records) | One helper wasted; the lead covered it itself by luck | `delegate()` refuses a job whose group key does not appear in another agent's record |
| The ERP lead first recorded the blocked material as "01 released" (it took the status legend in the tooltip for the value), and corrected it later | Could have cost a position | prompt: a legend explains the codes; the value shown next to the record is the status |
| The step guard took a lead-time dropdown ("3 Wochen") for a missing value, on all 5 steps | 5 needless refusals; the model read them as form validation errors and tried to give up | read the leading number of a dropdown text |
| The submitter took the form's shuffled position order for an error and tried to finish as "failed" 6 times; the refusal text then listed "summary" problems on a step page | Minutes lost; nearly unsigned | summary check only on the signing page; refusal: "the order is shuffled, each step names its position"; any problem the form cannot fix: sign anyway (a signed bid with an error scores, an unsigned one scores nothing); submitter at effort low |
| The submitter typed one position's line total as the order's net total; caught only at the summary, then a loop of 8 minutes until it found the way back | Nearly unsigned | check the total field on the conditions step before it is left (the guard knows the entered total) |
| configure(): the apply button reloaded the page during the fallback click, and the timeout aborted the chain | 25 s, one retry | treat a fallback-click timeout during navigation as applied and continue |
| The ERP lead stayed refused until minute 9 although done at about minute 7 | 2–3 minutes and tokens | the no-progress cap above ends it; then the investigation ends early |

### Run #9 (`run_d139751a5574091b`): quality 67, but the computed answer was exactly right

For the first time every field of every position and the total (356949.62) were right, thanks to the follow-up
(two mail topics and two materials recovered in it). The bid form then lost 33 points.

| Went wrong in run #9 | Effect | Fix for run #10 |
|---|---|---|
| The plan (low effort) listed the tender reference as a topic and left out the two subjects the rules name as "the latest X message" | Condition rules and price index found only in the follow-up | `plan_topics` also takes "<Subject> message (from x@)" from the brief; the reference alone stays a topic only for the approval |
| The new "let finished agents go" rule released the ERP lead before it had looked up two requirements (it had delegated three, one of them unused) | Two materials only in the follow-up | an agent is released only after a gap check lists nothing missing for its website |
| After the first gap check, the run waited 3.5 minutes with every agent done | Time only | the wait is skipped when everyone is done |
| **The submitter tried to finish as "failed" three times; the second refusal said "enter any position still open, or omit it", and it omitted position 01.05** | 13 points for the position, plus the total, consistency, withdrawn-answer and index-window checks: 33 points | the submitter has no "failed" finish at all; a refused finish on a position's step names that position and gives its row; omitting is mentioned only by the wrap-up warning 3 minutes before the end |

Lesson: never offer the model a way out (a "failed" status, an "omit" option) while there is time; it takes it.

### Run #10 (`run_c8b22d389e2cb503`): quality 80.1, the bid form perfect

The form worked: three attempts to stop were each answered with the step's position row, every field was entered,
the total was consistent, the bid was signed. All lost points come from one wrong value.

| Went wrong in run #10 | Effect | Fix for run #11 |
|---|---|---|
| **A mail agent closed two topics with records written without opening the messages** (the approval's date copied, the inbox named for archive-only messages); one held an exchange rate of 0.92 for a message that gives another rate. The value check missed it: a short decimal | Base and unit price of the three foreign-currency positions, the bonus split, the total: 19.9 points | `close_topic` refuses a message whose subject (or topic word) is on no page that agent viewed; short decimals ("0,92") are checked; a record whose only values are unseen and include a decimal is refused |
| The ERP lead delegated before any requirement was recorded (helpers ended with nothing), a helper opened a catalogue group as a material number and quit, and the lead looked up a requirement no position uses | Three materials late; one in the 75-second follow-up | `delegate()` needs the requirement and its group as other agents recorded them, and refuses requirements the tender's records never name; only running helpers count; helpers are refused twice before they may stop; the gap check sends an agent after missing facts of every website, not only the mailbox |
| Two mail topics closed as "absent" although both messages are in the archive | Caught by the gap check; recovered in 35–60 s each | — (the gap check handled it) |

### Run #11 (`run_644527a83fe7f01d`): quality 100, 11:23 min

Every check full. What carried it:
- All 9 mail topics, from the brief's "Subject/sender" list and its "the latest X message" wording.
- The checklist, plus the gap check that re-sent agents after two wrong "absent" closes and one doubtful rate.
- ERP helpers with real requirement keys, and a gap agent for the last material.
- `record()` refusing values no page showed.
- A submitter without a way to give up.

The computed answer matched the hand-checked one at 8:49, with no follow-up needed.

Still seen in run #11, worth fixing later (none cost points):
- A gap agent recorded single-digit lead times it had probably not opened: one-digit numbers are not checked. The
  delivery commitment governed that position anyway. Idea: check "number + unit" phrases ("2 Wochen") against the
  pages that agent viewed.
- The ERP lead started a helper for a requirement no position uses; the job also named a used one, so the check let
  it through. Harmless.
- At one position the form's fields read empty after every fill for about 40 s, and the platform log showed the
  typing masked ("•••"); the submitter got through and the summary matched. A fallback that retypes with real
  keystrokes when a fill does not stick is written but not in the 100-point version
  (`out/pending-keystroke-fallback.txt`).

### Run #12 (`run_947c0bdd59c7c62b`): every agent on the hosted Qwen 3.8 Flash Next, quality 0

The same code as run #11, with every model call on Qwen (the patch is in `out/qwen-experiment.patch`, branch `qwen`):
- Mail was perfect again (9 of 9), but took until minute 7:37 instead of about 3.
- The ERP never completed a material: one helper spent five minutes on an unused requirement after mapping it to a
  position that does not exist.
- 13 calls stalled past 30 s.
- The first gap check and the final solver (one long answer over the whole ledger) never answered, so the run fell
  back to the empty bid. The TAN came too late, and nothing was signed.
- Cost $0.45 for 383 calls, against $0.49 for 710 calls with GPT-6.

Lesson: with our current prompt and view sizes Qwen is slower per call, much slower on long answers, and not
cheaper. Smaller calls first (the token audit); then Qwen may be worth a second try, for the browsing steps only.

### Runs #13–#15: the generalization batch, all three at quality 100

| Run | Code | Time | Cost | Calls | Input tokens |
|---|---|---|---|---|---|
| #11 `run_644527a83fe7f01d` | first 100 (baseline) | 11:23 | $0.488 | 710 | 3.45M |
| #13 `run_806cef94890b9968` | generalization batch | 12:35 | $0.547 | 634 | 3.44M |
| #14 `run_4d2c4328eab0e6e1` | + safe cuts | 10:40 | $0.534 | 603 | 3.64M |
| #15 `run_f09397d28eb17b0c` | + ERP-lead loop changes | 14:00 | $0.562 | 626 | 3.96M |

- Run #13: the model used `drag(to=…)` with the slider itself as the target, which moves nothing, and spent about
  three minutes on one access check. `to` is now used only for a different element and only without `dx`.
- Run #14: fewer calls but a higher cost than run #11. The generalization text made every call longer, and the safe
  cuts mostly removed cached tokens, which are cheap. The token audit says about half the input is a cached static
  prefix that is needed; the real lever is fewer calls, not shorter prompts.
- Run #15: the specification agent crashed on a password field's keypress that timed out after 30 s, and the crash
  showed only at the end. Fixes: timeouts and try/except in the login, a 60 s limit on opening a site with a
  fresh-tab fallback, and crash logging as soon as a task fails. The ERP lead also stayed long after its facts were
  in; it is now released once the gap check hands its remaining gaps to other agents.
- Leaderboard: among the teams at 100 the rank goes by cost × time. Run #11 is still the submitted one.

### Run #16 (`run_840d332b75e42ec3`): quality 100, 10:39, $0.371, 549 calls, 2.58M input tokens

The cheapest run so far (cost × time 237, against 333 for run #11). It was submitted from the website as
`sub_e66ee1b64e409aff`, so it is the version the final run uses until a newer submission passes review.
- The new keystroke fallback in `fill()` told the truth where the old code said "Filled.": in fresh tabs a popup
  covered the search field, and once the TAN field. Its message was a raw click timeout; it now says that something
  covers the field.
- A false "the value may span several fields" came back when a field already held the value (a repeated search).
- A review of everything since run #14 (four lenses, a skeptic per finding) confirmed 28 defects in this code:
  - two serious: the TAN memo sent a second TAN reader away from the right message; the no-bid cleanup read "gesperrt"
    in a status legend as a blocked material;
  - the rest small, mostly private-only formats: a number annotated "German format" read 100× too large, a day unit
    applied to a week number, a fixing equation split at the wrong "=", same-day future records.
  All are fixed for run #17 (`out/snapshots/run17-review-fixes`); the calculation gives the same answer as before on
  all 25 logged real inputs.
- The platform's `atira logs` keeps only about the last 600 lines; follow a run live to keep the whole log.

### Run #17 (`run_9653c867947f3421`): quality 100, 15:08, $0.513, 674 calls

The review fixes held. Slower for three reasons:
- Requirement A-5 slipped between the ERP lead and its helpers: all three helpers were busy, the lead was told to do it
  itself and never did; the gap check handed it to a gap agent, which recorded a near-miss (325 mm stroke instead of
  300). The solver caught it and a 200 s follow-up found the right material.
- The tender portal finished at 1:31, was refused four times and recorded the same Q&A again in other shapes (one
  refusal did find an answer the first pass missed, so the refusals stay).
- The submitter asked for a TAN before requesting one; the reader returned a delivery key (`TZ-…`) from the Q&A as
  the "TAN", which cost 1.5 minutes before the deadline.

### Run #18 (`run_224cbeba74e07e49`): quality 64.9, 15:46, $0.491, 819 calls

With a queue for delegated parts (when all helpers are busy) and the lead held while a part is unrecorded:
- The queue also ran the lead's vague jobs ("continue with A-1 to A-5", "if not already …"): seven helpers. One of
  them recorded the active material as blocked and the blocked one as active; the solver followed the newest records
  and bid the blocked material for 01.01.
- The submitter clicked "omit this position" one click after a step opened and lost 01.02; every finish was then told
  "the summary differs", so it went back and forth for minutes before signing.

Fixed after this run: a delegation that overlaps a part a helper works on or has recorded is refused; records that
disagree on a material's status are listed for the solver and verified in the follow-up round; an "omit" click or
tick on a position the bid has values for is stopped once; the summary differences are named once, after that the
submitter is told to sign as it is; a TAN equal to an identifier the team recorded is refused, and get_tan without a
request number first reminds the submitter to request one.

Lesson: more agents cost more tokens and add chances to misread; parallelism only pays where it does not duplicate.

## 10. Watch list for the private dataset

The private run uses other software, layouts, site names and data, and splits the facts differently across the
sites. Everything that worked here because of how the public sites happen to look is fragile:

- **Which site holds which fact is not fixed.** The specification could be in the ERP or arrive by mail, the Q&A
  could sit in a document, approvals could be in a portal. The plan step names site kinds from the brief; the
  investigators must record every fact type they meet, not only "their" kind.
- **Gates will look different.** Other unlock widgets, other receipt or reference codes to copy, terms in another
  wording. The prompts describe gates by purpose, not by label; keep it that way.
- **Decoys will be different.** A hidden value, a preview box, a look-alike record, a future-dated record, a
  superseded revision shown first: expect the same kinds in new disguises.
- **Search may not be by catalogue group.** It could be by attributes, a material class or free text with filters.
  `wait_for_notes("requirement")` assumes the ERP depends on requirements from another site; on the private data the
  dependency could run the other way.
- **Number, date and unit formats will differ.** Locale tags may be missing; prices per 1000 or per carton; masses in
  kg; dates with month names. `calc.dec` only knows "(en-US)" and "(de-DE)" tags.
- **The TAN may arrive elsewhere** (another mailbox, a page, a document) with another way of naming the request.
- **The bid form will differ.** Other steps, other order, other preselected traps, another declaration that adds
  terms. The submitter follows the brief's submission section; nothing in code names a form field.
- **No-bid may be the right answer.** One requirement with no active match means no_bid; it has not been tested end
  to end yet.

## 11. Generalization backlog (after the public run reaches 100)

- Grep the package for anything public-specific (values, labels, URL paths); today: none.
- Replace the remaining public-shaped assumptions: the "erp" special case for refusals, the "requirement" topic in the
  ERP prompt, the fixed site kinds in the plan schema.
- Make the fact checklist explicit in code (from the brief's rules) and let each investigator see which facts are
  still missing team-wide, instead of each agent deciding alone when it is done.
- Parallelize per-requirement ERP lookups (several tabs) once the groups are known.
- Test a no_bid scenario and a scenario where facts sit on unexpected sites, with made-up pages.
- Speed and cost only after quality is flat: smaller views, fewer screenshots, cheaper model for form filling.

## 12. Testing notes

- The scouting logins are shared by every team. Other teams' agents request TANs about once a minute, so a TAN
  read by hand is usually superseded before it is entered. A scouting submission is never scored anyway; test the
  signing step in a sandbox run, which has its own logins.
- Offline checks: `uv run --no-sync python -m unittest discover -s tests` (calculation, number formats, the page
  view against a page with the same kinds of traps, the run contract).
- After a local or sandbox run, compare the logged answer field by field with `notes/expected-public-1.json`
  (local only, never committed).

### Runs #20–#25 and the final choice (2026-10-11)

Three team-built practice evals (gen-shift, gen-mix, gen-hard) were the first worlds unlike the public one:

| Code | Public | gen-shift | gen-mix | gen-hard |
|---|---|---|---|---|
| #16 | 100 | 0 | 65.5 | – |
| #22 (run #20 + four small fixes) | 100, 100 | 81.3, 81.3 | 70 | 61.6 |
| #23 (+ buyer messages by sender) | 73.8 | 100, 0 | 76 | 61.6 |
| **#24 (+ no-bid derivation guard): final pick, best of 3** | **100** | **100** | **100** | 61.6 |
| #25 (+ mail without the reference; experiment) | 100 | 100 | 77.5 | 61.6 |

What the evals taught:
- A hold button that relabels itself shrinks away from the pointer: press again where it is while held.
- A code can be only in an image's alt text: the page view shows image text alternatives.
- The submitter must always sign a bid with gaps; "must be complete" made it refuse and score 0.
- Quantity changes can arrive as buyer mail inside general messages ("Anfrage …", "AW: …"): a topic found by sender.
- Both wrong no-bids (public #21: 5, gen-shift #23: 0) came from an uncertain derived stroke ruling out a candidate
  that matched as written; a no-bid needs a finished re-check of the materials and must not rest on such a derivation.
- Rate sheets that apply to every tender carry no reference (gen-hard); a reference-only search never finds them.
- The platform changed the final to "your pick, else your best on the public leaderboard": pick explicitly.
- More agents cost more tokens and add chances to misread; runs vary, so one run proves little.
