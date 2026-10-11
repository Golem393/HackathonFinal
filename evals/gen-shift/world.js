// gen-shift: the same job as the challenge, on websites that look and work differently, to test how far an agent
// generalizes. Every value here is made up for this eval. BRIEF.md states the rules; expected.json is the one answer.
//
// What differs from the public scenario (see README.md): another access check (hold, arithmetic, tiles), a mailbox
// with folders, lazy lists and attachments, the FX rate in a CSV attachment with decoys, the latest discount in the
// archive, a quantity corrected in a mail thread, an English ERP with lead times in days and a price per 10 pieces in
// USD (en-US number format), a configurator with a catalogue-number field.

export const scenarioDate = "2026-10-15"

export const bidder = {
  name: "Beispiel Hydraulik GmbH",
  vatId: "DE999000123",
  mailbox: "vertrieb@beispiel-hydraulik.example",
  domain: "beispiel-hydraulik.example",
}

export const tender = {
  reference: "VG-2026-0142",
  title: "Hydraulikzylinder für die Wehranlage Nord",
  buyer: { name: "Wasserverband Musterstadt", street: "Am Wehr 1", postalCode: "12345", city: "Musterstadt" },
  procedure: "Offenes Verfahren",
  publishedAt: "2026-10-01",
  deadline: "2026-11-20",
  currency: "EUR",
  positions: [
    { position: "10", text: "Hydraulikzylinder für Schütz 1, Flanschbefestigung", quantity: 12, unit: "Stk", requirementRef: "A-10" },
    { position: "20", text: "Hydraulikzylinder für die Revisionsklappe, Gelenkauge", quantity: 4, unit: "Stk", requirementRef: "A-20" },
    { position: "30", text: "Hydraulikzylinder für die Fischtreppe, Fußbefestigung", quantity: 20, unit: "Stk", requirementRef: "A-30" },
    { position: "40", text: "Hydraulikzylinder für den Rechenreiniger, Fußbefestigung", quantity: 15, unit: "Stk", requirementRef: "A-40" },
  ],
}

/** Revisions are listed oldest first; the status is only a symbol, explained in a legend. */
export const specification = {
  number: "TS-0142",
  title: "Technische Spezifikation Hydraulikzylinder Wehranlage Nord",
  legend: { "●": "gültig (maßgeblich)", "○": "ersetzt", "◌": "Entwurf, nicht freigegeben" },
  revisions: [
    {
      revision: "A", date: "2026-09-15", symbol: "○", note: "Erstausgabe",
      requirements: [
        { ref: "A-10", bore: 50, stroke: 200, mounting: "Flansch", certification: "ATEX" },
        { ref: "A-20", bore: 63, stroke: 300, mounting: "Gelenkauge", certification: null },
        { ref: "A-30", bore: 80, stroke: 500, mounting: "Fuß", certification: null },
        { ref: "A-40", bore: 40, stroke: 200, mounting: "Fuß", certification: null },
      ],
    },
    {
      revision: "B", date: "2026-10-02", symbol: "●", note: "A-20: Hub 320 mm; A-30: DNV gefordert; A-40: Hub 250 mm",
      requirements: [
        { ref: "A-10", bore: 50, stroke: 200, mounting: "Flansch", certification: "ATEX" },
        { ref: "A-20", bore: 63, stroke: 320, mounting: "Gelenkauge", certification: null },
        { ref: "A-30", bore: 80, stroke: 500, mounting: "Fuß", certification: "DNV" },
        { ref: "A-40", bore: 40, stroke: 250, mounting: "Fuß", certification: null },
      ],
    },
    {
      revision: "C", date: "2026-10-12", symbol: "◌", note: "Entwurf: A-10 Hub 220 mm (nicht freigegeben)",
      requirements: [
        { ref: "A-10", bore: 50, stroke: 220, mounting: "Flansch", certification: "ATEX" },
        { ref: "A-20", bore: 63, stroke: 320, mounting: "Gelenkauge", certification: null },
        { ref: "A-30", bore: 80, stroke: 500, mounting: "Fuß", certification: "DNV" },
        { ref: "A-40", bore: 40, stroke: 250, mounting: "Fuß", certification: null },
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
  { reference: "VG-2026-0099", title: "Pumpenersatzteile Klärwerk Ost", buyer: "Stadtwerke Musterstadt", deadline: "2026-10-30" },
  { reference: "VG-2026-0142-A", title: "Hydraulikzylinder Wehranlage Nord – Los A (aufgehoben)", buyer: "Wasserverband Musterstadt", deadline: "2026-10-10" },
  { reference: "VG-2026-0157", title: "Schmierstoffe Fuhrpark 2027", buyer: "Wasserverband Musterstadt", deadline: "2026-12-04" },
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
const buyerContact = { name: "Petra Brandt (Wasserverband)", address: "einkauf@wv-musterstadt.example" }

export const messages = [
  {
    id: "m-2001", folder: "inbox", date: "2026-10-05T09:12:00Z", from: buyerContact,
    subject: "Anfrage VG-2026-0142: Hydraulikzylinder Wehranlage Nord",
    body: `Sehr geehrte Damen und Herren,\n\nwir bitten um Ihr Angebot zur Ausschreibung VG-2026-0142. Das Leistungsverzeichnis finden Sie im Vergabeportal.\n\nÄnderung: Für Position 30 benötigen wir 24 Stück statt 20 Stück.\n\nMit freundlichen Grüßen\nPetra Brandt`,
  },
  {
    id: "m-2002", folder: "inbox", date: "2026-10-09T11:40:00Z", from: buyerContact,
    subject: "AW: Anfrage VG-2026-0142: Hydraulikzylinder Wehranlage Nord",
    body: `Sehr geehrte Damen und Herren,\n\nKorrektur zu unserer Nachricht vom 05.10.: Für Position 30 gilt nun eine Menge von 22 Stück. Die frühere Angabe (24 Stück) ist damit überholt. Alle anderen Mengen bleiben wie im Leistungsverzeichnis.\n\nMit freundlichen Grüßen\nPetra Brandt\n\n> Änderung: Für Position 30 benötigen wir 24 Stück statt 20 Stück.`,
  },
  {
    id: "m-2003", folder: "inbox", date: "2026-10-03T08:00:00Z", from: person("Jonas Keller, Leitung Vertrieb", "leitung"),
    subject: "Rabatt VG-2026-0142",
    body: "Hallo Vertrieb,\n\nfür VG-2026-0142 genehmige ich vorläufig 3,5 % Rabatt auf alle Positionen.\n\nJonas Keller",
  },
  {
    id: "m-2004", folder: "inbox", date: "2026-10-13T07:15:00Z", from: person("Jonas Keller, Leitung Vertrieb", "leitung"),
    subject: "Rabatt VG-2026-0142-A",
    body: "Hallo Vertrieb,\n\nfür das aufgehobene Los VG-2026-0142-A genehmige ich 9 % Rabatt.\n\nJonas Keller",
  },
  {
    id: "m-2005", folder: "inbox", date: "2026-10-14T06:30:00Z", from: person("IT-Service", "it"),
    subject: "Wartungsfenster ERP", body: "Das ERP ist am Samstag von 6 bis 8 Uhr nicht erreichbar.",
  },
  {
    id: "m-2006", folder: "inbox", date: "2026-10-11T10:00:00Z", from: person("Marketing", "marketing"),
    subject: "Messe Hydraulik 2027", body: "Bitte tragt euch für den Messestand ein.",
  },
  {
    id: "m-2101", folder: "archive", date: "2026-10-10T16:20:00Z", from: person("Jonas Keller, Leitung Vertrieb", "leitung"),
    subject: "Rabatt VG-2026-0142 (final)",
    body: "Hallo Vertrieb,\n\nnach Rücksprache mit der Kalkulation genehmige ich für VG-2026-0142 abschließend 4 % Rabatt auf alle Positionen. Die vorläufige Freigabe vom 03.10. ist damit ersetzt.\n\nJonas Keller",
  },
  {
    id: "m-2102", folder: "archive", date: "2026-09-28T09:00:00Z", from: person("Einkauf intern", "einkauf"),
    subject: "Rahmenvertrag Dichtungen", body: "Der Rahmenvertrag ist verlängert.",
  },
  {
    id: "m-2103", folder: "archive", date: "2026-09-20T12:00:00Z", from: person("Jonas Keller, Leitung Vertrieb", "leitung"),
    subject: "Rabatt VG-2026-0099", body: "Für VG-2026-0099 genehmige ich 10 % Rabatt.",
  },
  {
    id: "m-2201", folder: "finance", date: "2026-10-01T07:00:00Z", from: person("Finanzbuchhaltung", "finanzen"),
    subject: "Devisenkurse Oktober (VG-2026-0142)",
    body: "Hallo Vertrieb,\n\nanbei die Umrechnungskurse für Angebote zu VG-2026-0142. Maßgeblich ist der Kurs zum Schlüssel des Konditionssatzes.\n\nFinanzbuchhaltung",
    attachments: [{ name: "kurse-2026-10.csv", content: "Schlüssel;Währung;EUR je Einheit;gültig ab\nFX-77;USD;0,9150;2026-10-01\nFX-78;CHF;1,0420;2026-10-01\n" }],
  },
  {
    id: "m-2202", folder: "finance", date: "2026-11-02T07:00:00Z", from: person("Finanzbuchhaltung", "finanzen"),
    subject: "Devisenkurse November (VG-2026-0142)",
    body: "Hallo Vertrieb,\n\nanbei die Kurse ab November.\n\nFinanzbuchhaltung",
    attachments: [{ name: "kurse-2026-11.csv", content: "Schlüssel;Währung;EUR je Einheit;gültig ab\nFX-77;USD;0,9400;2026-11-01\n" }],
  },
  {
    id: "m-2301", folder: "tech", date: "2026-10-06T13:00:00Z", from: person("Technik", "technik"),
    subject: "Prüfzeugnisse DNV", body: "Die DNV-Zeugnisse für die 80er-Baureihe liegen vor.",
  },
  {
    id: "m-2401", folder: "drafts", date: "2026-10-12T15:00:00Z", from: person("Vertrieb", "vertrieb"), draft: true,
    subject: "Devisenkurs USD (Entwurf)",
    body: "Entwurf – nicht gesendet.\n\nUSD-Kurs für Kalkulation: 0,8800 EUR je USD (FX-77).",
  },
]

/** ERP items. Lead times in days; prices per `priceUnit` pieces in `currency`, shown in `numberFormat`. */
export const materials = [
  {
    number: "HZ-50-200-FL-A", name: "Hydraulic cylinder 50/200 flange, ATEX", bore: 50, stroke: 200, pressure: 160,
    mounting: "Flansch", certification: "ATEX", status: "released", stock: 40, stockDays: 14, productionDays: 56,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 412.8 }, { from: 10, price: 389.9 }],
  },
  {
    number: "HZ-50-200-FL-0", name: "Hydraulic cylinder 50/200 flange", bore: 50, stroke: 200, pressure: 160,
    mounting: "Flansch", certification: null, status: "released", stock: 5, stockDays: 14, productionDays: 42,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 365 }],
  },
  {
    number: "HZ-63-320-GA-0", name: "Hydraulic cylinder 63/320 clevis", bore: 63, stroke: 320, pressure: 210,
    mounting: "Gelenkauge", certification: null, status: "released", stock: 2, stockDays: 21, productionDays: 70,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 689.5 }, { from: 5, price: 655 }],
  },
  {
    number: "HZ-63-320-GA-9", name: "Hydraulic cylinder 63/320 clevis (legacy)", bore: 63, stroke: 320, pressure: 160,
    mounting: "Gelenkauge", certification: null, status: "blocked", stock: 12, stockDays: 7, productionDays: 84,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 540 }],
  },
  {
    number: "HZ-80-500-FU-D", name: "Hydraulic cylinder 80/500 foot, DNV", bore: 80, stroke: 500, pressure: 250,
    mounting: "Fuß", certification: "DNV", status: "released", stock: 30, stockDays: 28, productionDays: 84,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 1240 }, { from: 25, price: 1180 }],
  },
  {
    number: "HZ-80-500-FL-D", name: "Hydraulic cylinder 80/500 flange, DNV", bore: 80, stroke: 500, pressure: 250,
    mounting: "Flansch", certification: "DNV", status: "released", stock: 8, stockDays: 28, productionDays: 84,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 1295 }],
  },
  {
    number: "HZ-40-250-FU-U", name: "Hydraulic cylinder 40/250 foot (US series)", bore: 40, stroke: 250, pressure: 160,
    mounting: "Fuß", certification: null, status: "released", stock: 10, stockDays: 14, productionDays: 42,
    currency: "USD", fxKey: "FX-77", priceUnit: 10, numberFormat: "en-US",
    prices: [{ from: 1, price: 3200 }, { from: 20, price: 3000 }],
  },
  {
    number: "HZ-40-250-FU-X", name: "Hydraulic cylinder 40/250 foot (discontinued)", bore: 40, stroke: 250, pressure: 160,
    mounting: "Fuß", certification: null, status: "blocked", stock: 50, stockDays: 7, productionDays: 42,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 240 }],
  },
  {
    number: "HZ-40-200-FU-0", name: "Hydraulic cylinder 40/200 foot", bore: 40, stroke: 200, pressure: 160,
    mounting: "Fuß", certification: null, status: "released", stock: 20, stockDays: 14, productionDays: 42,
    currency: "EUR", priceUnit: 1, numberFormat: "de-DE", prices: [{ from: 1, price: 260 }],
  },
]
