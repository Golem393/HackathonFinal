# gen-shift: does the agent generalize?

The challenge's job on websites that look and work differently from the public scenario. Every value is made up. Run an
agent on it and compare with its public score: where it drops, it was tuned to the public sites.

| Area | Public scenario | gen-shift |
| --- | --- | --- |
| Access check | slider, "not a robot" box, code from an image | press-and-hold button (2 s), arithmetic written in words, tile selection; comes back every 5 page views (mail, ERP) |
| Mailbox | inbox + archive, AND search | folder tree (Posteingang, Archiv, Ablage/Finanzen, Ablage/Technik, Entwürfe); list loads more rows only when scrolled; senders by name only; search = subjects of the current folder; attachments |
| FX rate | Devisenfixing mail | CSV attachment in Ablage/Finanzen; decoys: an unsent draft and a rate valid only after the scenario date |
| Discount | latest approval | the latest (final) approval sits in the archive; an older one in the inbox; a look-alike reference with a higher rate |
| Quantity | Q&A with withdrawals | mail thread: a change, then a correction (the latest counts) |
| ERP | German, SAP style | English, tabs (General, Logistics, Pricing), lead times in days, one price list per 10 pieces in USD with en-US numbers |
| Specification | revision marked "gültig" | status only as a symbol with a legend; opens the oldest revision; a newer draft revision exists |
| Tender portal | "Teilnahme bekunden", attribute cascade | "Interesse anmelden", "Angebot einreichen", catalogue-number field |

Scoring (eval scorer): reference 5, discount 5, total 15, positions 75 (material 35 %, quantity 20 %, unit price 30 %,
lead time 15 %). `expected.json` was checked end to end in `atira eval dev`: 100 points.

```sh
atira eval dev .                        # local, each answer scored
atira eval deploy .                     # upload (private to the team)
atira eval run . --package <run_or_sub_id or folder> --repeats 3
atira eval runs .
```
