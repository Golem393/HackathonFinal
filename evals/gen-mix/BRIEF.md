# Prepare a tender response

You work in sales for Beispiel Hydraulik GmbH (USt-IdNr. DE999000123). Prepare one net EUR bid for the Hafenbetriebe
Beispielhafen's tender VG-2027-0031, "Hydraulikzylinder für die Hafenkräne Süd". The scenario date is 2027-02-10.

Four websites hold what you need: the tender portal (`tender-portal`) with the tender and its Leistungsverzeichnis, the
buyer's customer portal (`customer-portal`) with the technical specification, the ERP (`erp`) with the materials and
their prices, and the sales mailbox (`mail`). Obsolete documents, drafts, archived messages and records for other
tenders are present; a message keeps its meaning wherever it is filed.

## Rules

1. Quantity: use the Leistungsverzeichnis quantity, unless a message from the buyer changes it for this tender; for
   each position the latest such message counts.
2. Material: each position names a requirement of the technical specification; only its current (gültig) revision
   counts. Choose the released ERP material whose bore, stroke, mounting and certification match that requirement
   exactly. Blocked materials do not qualify.
3. Unit price: take the material's price scale with the highest minimum quantity no greater than the quantity, per
   piece (a price list may state its price for several pieces, in the number format of the supplying works). A price
   in another currency is converted to EUR with the exchange rate from the finance department (finanzen@ plus our
   mailbox domain) for that currency: the latest rate already valid on the scenario date. Rate sheets quote either EUR
   per unit of the currency or units of the currency per EUR; each sheet says which. Round the converted per-piece
   price half up to the cent. Then apply the approved discount and round the unit price half up to the cent.
4. Discount: the most recent approval from the sales director (leitung@ plus our mailbox domain) for exactly this
   tender reference; approvals for other references do not apply. Drafts never count.
5. Lead time in whole weeks: delivery from stock when the stock covers the quantity, otherwise the production lead
   time. A lead time in days is rounded up to whole weeks.
6. Total: the sum of quantity times unit price, rounded to the cent.

## Submission

On the tender portal, open the tender, register your interest, then submit the bid. Register with the company name
Beispiel Hydraulik GmbH, the USt-IdNr. DE999000123 and a contact e-mail, choose Hauptangebot, enter each position's
catalogue number, the quantity, the discounted net unit price (German format, 1.234,56) and the lead time. Enter the
discount and the net total, acknowledge the tender documents, request a signing TAN, read it in the mailbox, enter it
and confirm "Angebot verbindlich abgeben" in the browser dialog. One submission ends the run.
