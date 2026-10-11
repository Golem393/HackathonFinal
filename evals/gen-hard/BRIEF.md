# Prepare a tender response

You work in sales for Beispiel Hydraulik GmbH (USt-IdNr. DE999000123). Prepare one net EUR bid for the Hafenbetriebe
Beispielhafen's tender VG-2027-0058, "Hydraulikzylinder für die Klappbrücke Ost". The scenario date is 2027-04-14.

Four websites hold what you need: the tender portal (`tender-portal`) with the tender and its Leistungsverzeichnis, the
buyer's customer portal (`customer-portal`) with the technical specification, the ERP (`erp`) with the materials and
their prices, and the sales mailbox (`mail`). The mailbox is busy: obsolete messages, drafts, archived messages,
attachments and records for other tenders and lots are present; a message keeps its meaning wherever it is filed, and a
subject need not name the tender.

## Rules

1. Quantity: use the Leistungsverzeichnis quantity, unless the buyer changes it for this tender (in a message or in a
   document attached to one); for each position the latest such statement counts, and a withdrawn change no longer
   applies.
2. Material: each position names a requirement of the technical specification. Use the revision in force on the
   scenario date; a revision may be released but only in force from a later date, and drafts never count. Choose the
   released ERP material whose bore, stroke, mounting and certification match that requirement exactly (mind the units).
   Blocked materials do not qualify.
3. Unit price: take the material's price list valid on the scenario date, and in it the price scale with the highest
   minimum quantity no greater than the quantity, per piece (a price list may state its price for several pieces, in
   the number format of the supplying works). A price in another currency is converted to EUR with the exchange rate
   from our finance department (finanzen@ plus our mailbox domain) for that currency: the latest rate already valid on
   the scenario date, taking any correction into account. Rate sheets quote either EUR per unit of the currency or
   units of the currency per EUR; each sheet says which. Round the converted per-piece price half up to the cent.
   Then apply the approved discount to the positions it covers and round the unit price half up to the cent.
4. Discount: the most recent approval from the sales director (leitung@ plus our mailbox domain) for exactly this
   tender reference; approvals for other references or lots do not apply. Drafts never count. An approval may exclude
   positions: those are offered without discount. The bid's discount is the approved percentage.
5. Lead time in whole weeks: delivery from stock when the stock not reserved for other orders covers the quantity,
   otherwise the production lead time. A lead time in days is rounded up to whole weeks (7 days); one in working days
   likewise (5 working days).
6. Total: the sum of quantity times unit price, rounded to the cent.

## Submission

On the tender portal, open the tender, register your interest, then submit the bid. Register with the company name
Beispiel Hydraulik GmbH, the USt-IdNr. DE999000123 and a contact e-mail, choose Hauptangebot, enter each position's
catalogue number, the quantity, the net unit price (after any discount; German format, 1.234,56) and the lead time.
Enter the discount and the net total, acknowledge the tender documents, request a signing TAN, read it in the mailbox,
enter it and confirm "Angebot verbindlich abgeben" in the browser dialog. One submission ends the run.
