# gen-mix: does the agent's reasoning generalize?

The challenge's job, on the gen-shift websites, with the shifts moved into the data. Every value is made up. Where
gen-shift asks "can it use different websites", gen-mix asks "can it read facts that are filed, formatted and quoted
differently".

| Area | Public scenario | gen-mix |
| --- | --- | --- |
| Where facts sit | mostly the inbox | the final discount and one quantity change only in the archive; another quantity change in the inbox; the rates for two currencies only in an archived mail |
| Currencies | EUR, one foreign currency | EUR, CHF, GBP, PLN, SEK on the price lists; USD only as noise on a rate sheet |
| Number formats | German | de-CH (1'234.50), en-GB (1,234.50), pl-PL and sv-SE (1 234,50), fr-FR (1 234,50 with a narrow space), de-DE |
| Price units | per piece | per 1, per 10 and per 100 pieces |
| Exchange rates | one rate, EUR per unit | three sheets: January (archive, German, units per EUR), February (finance folder, English CSV, EUR per unit, only CHF and GBP: PLN and SEK keep January's rate), a March preview not yet valid; decoys: December sheet, an unsent draft |
| Discount | latest approval | provisional 5 % (inbox) → final 6 % (archive); 8 % for the look-alike reference VG-2027-0031-B (newest); 7 % in a draft |
| Quantity | Q&A | two changes in different folders for different positions, and one for another tender |
| Lead time | weeks | days (rounded up to whole weeks) or weeks, per item |
| Specification | revision marked "gültig" | symbol + legend; the gültig revision adds DNV to two requirements; a draft changes a stroke |

The access check, mailbox, ERP, customer portal and tender portal work like gen-shift's (see `../gen-shift/README.md`);
the ERP shows lead times with their unit and the portal offers lead times of 1–16 weeks.

Scoring (eval scorer): reference 5, discount 5, total 15, positions 75 (material 35 %, quantity 20 %, unit price 30 %,
lead time 15 %). `expected.json` is the one answer (computed with Decimal, half up).

```sh
atira eval dev .                        # local, each answer scored
atira eval deploy . --no-preview        # upload (private to the team)
atira eval run gen-mix --package <run_or_sub_id> --repeats 1
atira eval runs gen-mix
```
