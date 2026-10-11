# gen-hard: facts that need judgement

The challenge's job on the gen-shift websites, where finding a fact is not enough: each one has a twist that a
pipeline tuned to the public scenario tends to miss. Every value is made up; the BRIEF states every rule needed.

| Twist | gen-hard | Trap if missed |
| --- | --- | --- |
| Revision in force | B ● is in force; C ◐ is released but only from 01.05.2027 (C-40 needs DNV); D ◌ is a draft | C-40 → the DNV item |
| Units | from revision B the specification gives strokes in cm (30 cm); the ERP in mm | C-10 → the 50/30 mm item |
| Withdrawn change | position 20: 8 → 16 (archive, subject without the reference), then withdrawn (inbox) | qty 16, other price scale |
| Change in an attachment | position 30: 20 → 26 only in `aenderungsmitteilung-2.txt`; another lot's attachment changes other positions | qty 20, stock lead time, other scale |
| Price list validity | expired 2026 list (EUR) next to the 2027 list (CHF); a GBP list valid only from July | wrong currency or scale |
| Rate correction | April CSV says CHF 1.0820; a later mail with the subject "Korrektur" sets 1.0780; DKK only in the archived Q1 sheet (units per EUR); a bank's daily rates and a May preview are decoys | wrong EUR price |
| Reserved stock | position 10: 30 in stock but 22 reserved → production lead time | 1 week instead of 5 |
| Working days | 23 working days → 5 weeks | 4 weeks |
| Discount exclusion | 7 % on all positions except 30 (archive, subject without the reference); 5 % provisional; 12 % for lot L2; 9 % draft | discounted position 30 |
| Noise | 30 unrelated messages across folders; the list loads 4 rows at a time | slow or missed search |

Scoring (eval scorer): reference 5, discount 5, total 15, positions 75 (material 35 %, quantity 20 %, unit price 30 %,
lead time 15 %). `expected.json` is the one answer (Decimal, half up).

```sh
atira eval dev .
atira eval deploy . --no-preview
atira eval run gen-hard --package <run_or_sub_id> --repeats 1
```
