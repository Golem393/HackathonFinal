// gen-mix: the challenge's job with a mix of shifts in the data rather than in the websites: the facts that count sit
// in the mailbox archive, prices come in five currencies and five number formats, exchange rates are quoted in both
// directions in different documents, and lead times come in days or in weeks. Every value here is made up for this
// eval. BRIEF.md states the rules; expected.json is the one answer. See README.md for what differs.

export const scenarioDate = "2027-02-10"

export const bidder = {
  name: "Beispiel Hydraulik GmbH",
  vatId: "DE999000123",
  mailbox: "vertrieb@beispiel-hydraulik.example",
  domain: "beispiel-hydraulik.example",
}

export const tender = {
  reference: "VG-2027-0031",
  title: "Hydraulikzylinder für die Hafenkräne Süd",
  buyer: { name: "Hafenbetriebe Beispielhafen", street: "Kaistraße 7", postalCode: "23456", city: "Beispielhafen" },
  procedure: "Offenes Verfahren",
  publishedAt: "2027-01-15",
  deadline: "2027-03-05",
  currency: "EUR",
  positions: [
    { position: "10", text: "Hydraulikzylinder für die Greiferverriegelung, Flanschbefestigung", quantity: 8, unit: "Stk", requirementRef: "B-10" },
    { position: "20", text: "Hydraulikzylinder für die Auslegerklappe, Gelenkauge", quantity: 6, unit: "Stk", requirementRef: "B-20" },
    { position: "30", text: "Hydraulikzylinder für die Spreader-Ausrichtung, Fußbefestigung", quantity: 30, unit: "Stk", requirementRef: "B-30" },
    { position: "40", text: "Hydraulikzylinder für die Kabinentür, Flanschbefestigung", quantity: 50, unit: "Stk", requirementRef: "B-40" },
    { position: "50", text: "Hydraulikzylinder für die Schienenzange, Fußbefestigung", quantity: 2, unit: "Stk", requirementRef: "B-50" },
  ],
}

/** Revisions are listed oldest first; the status is only a symbol, explained in a legend. */
export const specification = {
  number: "TS-0031",
  title: "Technische Spezifikation Hydraulikzylinder Hafenkräne Süd",
  legend: { "●": "gültig (maßgeblich)", "○": "ersetzt", "◌": "Entwurf, nicht freigegeben" },
  revisions: [
    {
      revision: "A", date: "2027-01-10", symbol: "○", note: "Erstausgabe",
      requirements: [
        { ref: "B-10", bore: 50, stroke: 250, mounting: "Flansch", certification: null },
        { ref: "B-20", bore: 63, stroke: 400, mounting: "Gelenkauge", certification: null },
        { ref: "B-30", bore: 80, stroke: 320, mounting: "Fuß", certification: "ATEX" },
        { ref: "B-40", bore: 40, stroke: 160, mounting: "Flansch", certification: null },
        { ref: "B-50", bore: 100, stroke: 600, mounting: "Fuß", certification: null },
      ],
    },
    {
      revision: "B", date: "2027-01-28", symbol: "●", note: "B-20 und B-50: DNV-Zertifizierung gefordert",
      requirements: [
        { ref: "B-10", bore: 50, stroke: 250, mounting: "Flansch", certification: null },
        { ref: "B-20", bore: 63, stroke: 400, mounting: "Gelenkauge", certification: "DNV" },
        { ref: "B-30", bore: 80, stroke: 320, mounting: "Fuß", certification: "ATEX" },
        { ref: "B-40", bore: 40, stroke: 160, mounting: "Flansch", certification: null },
        { ref: "B-50", bore: 100, stroke: 600, mounting: "Fuß", certification: "DNV" },
      ],
    },
    {
      revision: "C", date: "2027-02-08", symbol: "◌", note: "Entwurf: B-40 Hub 200 mm (nicht freigegeben)",
      requirements: [
        { ref: "B-10", bore: 50, stroke: 250, mounting: "Flansch", certification: null },
        { ref: "B-20", bore: 63, stroke: 400, mounting: "Gelenkauge", certification: "DNV" },
        { ref: "B-30", bore: 80, stroke: 320, mounting: "Fuß", certification: "ATEX" },
        { ref: "B-40", bore: 40, stroke: 200, mounting: "Flansch", certification: null },
        { ref: "B-50", bore: 100, stroke: 600, mounting: "Fuß", certification: "DNV" },
      ],
    },
  ],
}

export const informationDocuments = [
  {
    id: "lieferantenleitfaden", number: "INF-001", title: "Leitfaden für Lieferanten",
    content: "Bitte halten Sie Ihre Kontaktdaten aktuell. Angebote reichen Sie ausschließlich über das Vergabeportal ein.",
  },
]

export const otherTenders = [
  { reference: "VG-2027-0013", title: "Hydraulikaggregate Schleuse West", buyer: "Hafenbetriebe Beispielhafen", deadline: "2027-02-26" },
  { reference: "VG-2027-0031-B", title: "Hydraulikzylinder Hafenkräne Süd – Los B (aufgehoben)", buyer: "Hafenbetriebe Beispielhafen", deadline: "2027-02-01" },
  { reference: "VG-2027-0044", title: "Hydrauliköl und Filter 2027", buyer: "Stadtwerke Beispielhafen", deadline: "2027-03-19" },
]

/** Mailbox folders, in the order the mailbox lists them. */
export const folders = [
  { id: "inbox", name: "Posteingang" },
  { id: "archive", name: "Archiv" },
  { id: "finance", name: "Ablage / Finanzen" },
  { id: "tech", name: "Ablage / Technik" },
  { id: "drafts", name: "Entwürfe" },
]

/** People shown by name in lists; the address appears only in a message's header. */
const person = (name, local) => ({ name, address: `${local}@${bidder.domain}` })
const buyerContact = { name: "Lars Petersen (Hafenbetriebe)", address: "einkauf@hafen-beispielhafen.example" }
const director = person("Miriam Vogt, Leitung Vertrieb", "leitung")
const finance = person("Finanzbuchhaltung", "finanzen")

export const messages = [
  // --- inbox ---
  {
    id: "m-3001", folder: "inbox", date: "2027-01-18T08:30:00Z", from: buyerContact,
    subject: "Ausschreibung VG-2027-0031: Hydraulikzylinder Hafenkräne Süd",
    body: "Sehr geehrte Damen und Herren,\n\nwir laden Sie ein, ein Angebot zu VG-2027-0031 abzugeben. Leistungsverzeichnis und Spezifikation finden Sie in unseren Portalen. Mengenänderungen teilen wir Ihnen per E-Mail mit.\n\nMit freundlichen Grüßen\nLars Petersen",
  },
  {
    id: "m-3002", folder: "inbox", date: "2027-01-20T10:05:00Z", from: director,
    subject: "Rabatt VG-2027-0031 (vorläufig)",
    body: "Hallo Vertrieb,\n\nfür VG-2027-0031 genehmige ich vorläufig 5 % Rabatt auf alle Positionen. Die endgültige Freigabe folgt nach der Kalkulationsrunde.\n\nMiriam Vogt",
  },
  {
    id: "m-3003", folder: "inbox", date: "2027-02-09T07:40:00Z", from: director,
    subject: "Rabatt VG-2027-0031-B",
    body: "Hallo Vertrieb,\n\nfür das aufgehobene Los VG-2027-0031-B genehmige ich 8 % Rabatt, falls es neu ausgeschrieben wird.\n\nMiriam Vogt",
  },
  {
    id: "m-3004", folder: "inbox", date: "2027-02-06T13:15:00Z", from: buyerContact,
    subject: "Mengenänderung VG-2027-0031, Position 50",
    body: "Sehr geehrte Damen und Herren,\n\nzu VG-2027-0031: Für Position 50 benötigen wir 3 Stück statt 2 Stück. Alle übrigen Mengen bleiben unverändert, soweit nicht bereits mitgeteilt.\n\nMit freundlichen Grüßen\nLars Petersen",
  },
  {
    id: "m-3005", folder: "inbox", date: "2027-02-04T09:00:00Z", from: buyerContact,
    subject: "Mengenänderung VG-2027-0013, Position 10",
    body: "Sehr geehrte Damen und Herren,\n\nzu VG-2027-0013 (Schleuse West): Für Position 10 benötigen wir 40 Stück statt 25 Stück.\n\nMit freundlichen Grüßen\nLars Petersen",
  },
  {
    id: "m-3006", folder: "inbox", date: "2027-02-08T15:30:00Z", from: finance,
    subject: "Vorschau: Devisenkurse ab März 2027",
    body: "Hallo Vertrieb,\n\nzur Planung die Kurse, die ab 01.03.2027 gelten (EUR je 1 Einheit der Fremdwährung):\n\nCHF  1,0990\nGBP  1,2010\nPLN  0,2400\nSEK  0,0930\n\nBis dahin gelten die bisherigen Kurse.\n\nFinanzbuchhaltung",
  },
  {
    id: "m-3007", folder: "inbox", date: "2027-02-09T06:45:00Z", from: person("IT-Service", "it"),
    subject: "ERP: neue Preisanzeige", body: "Im ERP werden Preislisten jetzt in der Originalwährung und im Zahlenformat des Lieferwerks angezeigt.",
  },
  {
    id: "m-3008", folder: "inbox", date: "2027-02-02T11:00:00Z", from: person("Personalabteilung", "personal"),
    subject: "Betriebsausflug 2027", body: "Bitte meldet euch bis Ende Februar an.",
  },
  // --- archive ---
  {
    id: "m-3101", folder: "archive", date: "2027-01-25T14:20:00Z", from: buyerContact,
    subject: "Mengenänderung VG-2027-0031, Position 10",
    body: "Sehr geehrte Damen und Herren,\n\nzu VG-2027-0031: Für Position 10 benötigen wir 10 Stück statt 8 Stück.\n\nMit freundlichen Grüßen\nLars Petersen",
  },
  {
    id: "m-3102", folder: "archive", date: "2027-02-05T16:10:00Z", from: director,
    subject: "Rabatt VG-2027-0031 (final)",
    body: "Hallo Vertrieb,\n\nnach der Kalkulationsrunde genehmige ich für VG-2027-0031 abschließend 6 % Rabatt auf alle Positionen. Die vorläufige Freigabe vom 20.01. ist damit ersetzt.\n\nMiriam Vogt",
  },
  {
    id: "m-3103", folder: "archive", date: "2027-01-04T07:00:00Z", from: finance,
    subject: "Devisenkurse Januar 2027",
    body: "Hallo Vertrieb,\n\ndie Kurse für Angebote ab 01.01.2027, angegeben in Einheiten der Fremdwährung je 1 EUR:\n\nCHF   0,9310\nGBP   0,8420\nPLN   4,3150\nSEK  11,2000\n\nSie gelten, bis wir neue Kurse mitteilen.\n\nFinanzbuchhaltung",
  },
  {
    id: "m-3104", folder: "archive", date: "2026-12-14T09:00:00Z", from: director,
    subject: "Rabatt VG-2027-0013", body: "Für VG-2027-0013 genehmige ich 10 % Rabatt.",
  },
  {
    id: "m-3105", folder: "archive", date: "2026-12-20T12:00:00Z", from: person("Einkauf intern", "einkauf"),
    subject: "Rahmenvertrag Dichtungen 2027", body: "Der Rahmenvertrag ist um ein Jahr verlängert.",
  },
  // --- finance ---
  {
    id: "m-3201", folder: "finance", date: "2027-02-01T07:00:00Z", from: finance,
    subject: "FX rates February 2027",
    body: "Hello sales team,\n\nattached are the rates valid from 1 Feb 2027 (EUR per unit of foreign currency). Currencies not listed keep their previous rate.\n\nFinance",
    attachments: [{ name: "fx-2027-02.csv", content: "currency,eur_per_unit,valid_from\nCHF,1.0750,2027-02-01\nGBP,1.1880,2027-02-01\nUSD,0.9210,2027-02-01\n" }],
  },
  {
    id: "m-3202", folder: "finance", date: "2026-12-01T07:00:00Z", from: finance,
    subject: "FX rates December 2026",
    body: "Hello sales team,\n\nattached are the rates valid from 1 Dec 2026 (EUR per unit of foreign currency).\n\nFinance",
    attachments: [{ name: "fx-2026-12.csv", content: "currency,eur_per_unit,valid_from\nCHF,1.0610,2026-12-01\nGBP,1.1720,2026-12-01\nPLN,0.2290,2026-12-01\nSEK,0.0880,2026-12-01\n" }],
  },
  // --- tech ---
  {
    id: "m-3301", folder: "tech", date: "2027-01-29T10:00:00Z", from: person("Technik", "technik"),
    subject: "DNV-Zeugnisse Baureihen 63 und 100", body: "Die DNV-Zeugnisse für die Baureihen 63 und 100 liegen vor.",
  },
  // --- drafts ---
  {
    id: "m-3401", folder: "drafts", date: "2027-02-07T17:00:00Z", from: person("Vertrieb", "vertrieb"), draft: true,
    subject: "Rabatt VG-2027-0031 (Entwurf)",
    body: "Entwurf – nicht gesendet.\n\nVorschlag an die Leitung: 7 % Rabatt für VG-2027-0031.",
  },
  {
    id: "m-3402", folder: "drafts", date: "2027-02-03T12:00:00Z", from: person("Vertrieb", "vertrieb"), draft: true,
    subject: "PLN-Kurs Kalkulation (Entwurf)",
    body: "Entwurf – nicht gesendet.\n\nPLN für die Kalkulation: 4,0000 PLN je EUR.",
  },
]

/** ERP items. Lead times in `leadUnit` (days or weeks); prices per `priceUnit` pieces in `currency`, shown in `numberFormat`. */
export const materials = [
  {
    number: "HZ-50-250-FL-C", name: "Hydraulic cylinder 50/250 flange (Swiss works)", bore: 50, stroke: 250, pressure: 160,
    mounting: "Flansch", certification: null, status: "released", stock: 4, leadUnit: "days", stockLead: 9, productionLead: 38,
    currency: "CHF", priceUnit: 1, numberFormat: "de-CH", prices: [{ from: 1, price: 512.4 }, { from: 10, price: 489.95 }],
  },
  {
    number: "HZ-50-250-FL-E", name: "Hydraulic cylinder 50/250 flange (old series)", bore: 50, stroke: 250, pressure: 160,
    mounting: "Flansch", certification: null, status: "blocked", stock: 30, leadUnit: "days", stockLead: 5, productionLead: 35,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 455 }],
  },
  {
    number: "HZ-63-400-GA-D", name: "Hydraulic cylinder 63/400 clevis, DNV (UK works)", bore: 63, stroke: 400, pressure: 210,
    mounting: "Gelenkauge", certification: "DNV", status: "released", stock: 10, leadUnit: "weeks", stockLead: 3, productionLead: 12,
    currency: "GBP", priceUnit: 1, numberFormat: "en-GB", prices: [{ from: 1, price: 845 }, { from: 5, price: 812.5 }],
  },
  {
    number: "HZ-63-400-GA-0", name: "Hydraulic cylinder 63/400 clevis", bore: 63, stroke: 400, pressure: 210,
    mounting: "Gelenkauge", certification: null, status: "released", stock: 20, leadUnit: "weeks", stockLead: 2, productionLead: 8,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 790 }],
  },
  {
    number: "HZ-80-320-FU-A", name: "Hydraulic cylinder 80/320 foot, ATEX (Polish works)", bore: 80, stroke: 320, pressure: 250,
    mounting: "Fuß", certification: "ATEX", status: "released", stock: 12, leadUnit: "days", stockLead: 14, productionLead: 63,
    currency: "PLN", priceUnit: 10, numberFormat: "pl-PL", prices: [{ from: 1, price: 61250 }, { from: 25, price: 58900 }],
  },
  {
    number: "HZ-80-320-FU-0", name: "Hydraulic cylinder 80/320 foot", bore: 80, stroke: 320, pressure: 250,
    mounting: "Fuß", certification: null, status: "released", stock: 40, leadUnit: "days", stockLead: 7, productionLead: 49,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 1290 }],
  },
  {
    number: "HZ-40-160-FL-0", name: "Hydraulic cylinder 40/160 flange (French works)", bore: 40, stroke: 160, pressure: 160,
    mounting: "Flansch", certification: null, status: "released", stock: 60, leadUnit: "days", stockLead: 5, productionLead: 30,
    currency: "EUR", priceUnit: 100, numberFormat: "fr-FR", prices: [{ from: 1, price: 18950 }, { from: 50, price: 17800 }],
  },
  {
    number: "HZ-40-200-FL-0", name: "Hydraulic cylinder 40/200 flange", bore: 40, stroke: 200, pressure: 160,
    mounting: "Flansch", certification: null, status: "released", stock: 80, leadUnit: "days", stockLead: 5, productionLead: 30,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 199 }],
  },
  {
    number: "HZ-100-600-FU-D", name: "Hydraulic cylinder 100/600 foot, DNV (Swedish works)", bore: 100, stroke: 600, pressure: 250,
    mounting: "Fuß", certification: "DNV", status: "released", stock: 0, leadUnit: "days", stockLead: 7, productionLead: 77,
    currency: "SEK", priceUnit: 1, numberFormat: "sv-SE", prices: [{ from: 1, price: 41500 }, { from: 5, price: 39800 }],
  },
  {
    number: "HZ-100-600-FU-X", name: "Hydraulic cylinder 100/600 foot, DNV (discontinued)", bore: 100, stroke: 600, pressure: 250,
    mounting: "Fuß", certification: "DNV", status: "blocked", stock: 6, leadUnit: "days", stockLead: 7, productionLead: 70,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 3100 }],
  },
]
