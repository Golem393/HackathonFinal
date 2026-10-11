// gen-hard: the challenge's job where the facts need judgement, not only finding: a specification revision that is
// released but only in force later, strokes in centimetres, a quantity change that is withdrawn again, another one only
// in an attachment, price lists with validity periods, a corrected exchange rate, reserved stock, lead times in working
// days, a discount that excludes one position, and a mailbox full of noise whose subjects often omit the reference.
// Every value here is made up for this eval. BRIEF.md states the rules; expected.json is the one answer.

export const scenarioDate = "2027-04-14"

export const bidder = {
  name: "Beispiel Hydraulik GmbH",
  vatId: "DE999000123",
  mailbox: "vertrieb@beispiel-hydraulik.example",
  domain: "beispiel-hydraulik.example",
}

export const tender = {
  reference: "VG-2027-0058",
  title: "Hydraulikzylinder für die Klappbrücke Ost",
  buyer: { name: "Hafenbetriebe Beispielhafen", street: "Kaistraße 7", postalCode: "23456", city: "Beispielhafen" },
  procedure: "Offenes Verfahren",
  publishedAt: "2027-02-20",
  deadline: "2027-05-07",
  currency: "EUR",
  positions: [
    { position: "10", text: "Hydraulikzylinder für die Brückenverriegelung, Flanschbefestigung", quantity: 12, unit: "Stk", requirementRef: "C-10" },
    { position: "20", text: "Hydraulikzylinder für die Schrankenanlage, Gelenkauge", quantity: 8, unit: "Stk", requirementRef: "C-20" },
    { position: "30", text: "Hydraulikzylinder für den Klappenantrieb, Fußbefestigung", quantity: 20, unit: "Stk", requirementRef: "C-30" },
    { position: "40", text: "Hydraulikzylinder für die Notabsenkung, Fußbefestigung", quantity: 4, unit: "Stk", requirementRef: "C-40" },
  ],
}

/** Revisions are listed oldest first; values are stored in mm, a revision may show strokes in cm. */
export const specification = {
  number: "TS-0058",
  title: "Technische Spezifikation Hydraulikzylinder Klappbrücke Ost",
  legend: {
    "●": "gültig (maßgeblich)",
    "○": "ersetzt",
    "◐": "freigegeben, gilt erst ab dem im Vermerk genannten Datum",
    "◌": "Entwurf, nicht freigegeben",
  },
  revisions: [
    {
      revision: "A", date: "2027-02-01", symbol: "○", strokeUnit: "mm", note: "Erstausgabe",
      requirements: [
        { ref: "C-10", bore: 50, stroke: 300, mounting: "Flansch", certification: null },
        { ref: "C-20", bore: 63, stroke: 250, mounting: "Gelenkauge", certification: null },
        { ref: "C-30", bore: 80, stroke: 400, mounting: "Fuß", certification: "DNV" },
        { ref: "C-40", bore: 100, stroke: 500, mounting: "Fuß", certification: null },
      ],
    },
    {
      revision: "B", date: "2027-03-10", symbol: "●", strokeUnit: "cm",
      note: "C-10: ATEX gefordert; Hubangaben ab dieser Revision in cm",
      requirements: [
        { ref: "C-10", bore: 50, stroke: 300, mounting: "Flansch", certification: "ATEX" },
        { ref: "C-20", bore: 63, stroke: 250, mounting: "Gelenkauge", certification: null },
        { ref: "C-30", bore: 80, stroke: 400, mounting: "Fuß", certification: "DNV" },
        { ref: "C-40", bore: 100, stroke: 500, mounting: "Fuß", certification: null },
      ],
    },
    {
      revision: "C", date: "2027-04-02", symbol: "◐", strokeUnit: "cm",
      note: "Gilt ab 01.05.2027: C-40 DNV-Zertifizierung gefordert",
      requirements: [
        { ref: "C-10", bore: 50, stroke: 300, mounting: "Flansch", certification: "ATEX" },
        { ref: "C-20", bore: 63, stroke: 250, mounting: "Gelenkauge", certification: null },
        { ref: "C-30", bore: 80, stroke: 400, mounting: "Fuß", certification: "DNV" },
        { ref: "C-40", bore: 100, stroke: 500, mounting: "Fuß", certification: "DNV" },
      ],
    },
    {
      revision: "D", date: "2027-04-12", symbol: "◌", strokeUnit: "cm", note: "Entwurf: C-20 Hub 28 cm (nicht freigegeben)",
      requirements: [
        { ref: "C-10", bore: 50, stroke: 300, mounting: "Flansch", certification: "ATEX" },
        { ref: "C-20", bore: 63, stroke: 280, mounting: "Gelenkauge", certification: null },
        { ref: "C-30", bore: 80, stroke: 400, mounting: "Fuß", certification: "DNV" },
        { ref: "C-40", bore: 100, stroke: 500, mounting: "Fuß", certification: "DNV" },
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
  { reference: "VG-2027-0058-L2", title: "Hydraulikzylinder Klappbrücke Ost – Los 2 (Ersatzteile)", buyer: "Hafenbetriebe Beispielhafen", deadline: "2027-05-07" },
  { reference: "VG-2027-0061", title: "Wartung Hydraulikanlagen 2027–2029", buyer: "Stadtwerke Beispielhafen", deadline: "2027-05-21" },
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
const bank = { name: "Nordbank Devisenservice", address: "devisen@nordbank.example" }

const facts = [
  // --- quantities: a change that is withdrawn again, and one that only an attachment states ---
  {
    id: "m-5101", folder: "archive", date: "2027-03-05T09:20:00Z", from: buyerContact,
    subject: "AW: Ihre Rückfrage vom 02.03.",
    body: "Sehr geehrte Damen und Herren,\n\nzu Ihrer Rückfrage zur Ausschreibung VG-2027-0058: Für Position 20 benötigen wir 16 Stück statt 8 Stück.\n\nMit freundlichen Grüßen\nLars Petersen",
  },
  {
    id: "m-5001", folder: "inbox", date: "2027-04-07T14:05:00Z", from: buyerContact,
    subject: "Rücknahme einer Mengenänderung",
    body: "Sehr geehrte Damen und Herren,\n\ndie Mengenänderung zu Position 20 der Ausschreibung VG-2027-0058 vom 05.03.2027 ziehen wir zurück. Für Position 20 gilt wieder die Menge des Leistungsverzeichnisses.\n\nMit freundlichen Grüßen\nLars Petersen",
  },
  {
    id: "m-5002", folder: "inbox", date: "2027-03-29T08:10:00Z", from: buyerContact,
    subject: "Änderungsmitteilung Nr. 2",
    body: "Sehr geehrte Damen und Herren,\n\nanbei unsere Änderungsmitteilung Nr. 2. Bitte berücksichtigen Sie sie in Ihrem Angebot.\n\nMit freundlichen Grüßen\nLars Petersen",
    attachments: [{
      name: "aenderungsmitteilung-2.txt",
      content: "Änderungsmitteilung Nr. 2 zur Ausschreibung VG-2027-0058\nDatum: 29.03.2027\n\nPosition 30: neue Menge 26 Stk (bisher 20 Stk)\n\nAlle übrigen Angaben bleiben unverändert.\n",
    }],
  },
  {
    id: "m-5003", folder: "inbox", date: "2027-04-09T10:30:00Z", from: buyerContact,
    subject: "Änderungsmitteilung Nr. 1 (Los 2)",
    body: "Sehr geehrte Damen und Herren,\n\nanbei die Änderungsmitteilung zu Los 2.\n\nMit freundlichen Grüßen\nLars Petersen",
    attachments: [{
      name: "aenderungsmitteilung-l2-1.txt",
      content: "Änderungsmitteilung Nr. 1 zur Ausschreibung VG-2027-0058-L2\nDatum: 09.04.2027\n\nPosition 10: neue Menge 40 Stk (bisher 12 Stk)\nPosition 30: neue Menge 5 Stk (bisher 2 Stk)\n",
    }],
  },
  // --- discount: provisional, final with an exclusion (archive), other references, a draft ---
  {
    id: "m-5004", folder: "inbox", date: "2027-03-01T08:00:00Z", from: director,
    subject: "Rabatt Klappbrücke (vorläufig)",
    body: "Hallo Vertrieb,\n\nfür VG-2027-0058 genehmige ich vorläufig 5 % Rabatt auf alle Positionen.\n\nMiriam Vogt",
  },
  {
    id: "m-5102", folder: "archive", date: "2027-04-08T17:45:00Z", from: director,
    subject: "Freigabe Konditionen Klappbrücke Ost",
    body: "Hallo Vertrieb,\n\nfür VG-2027-0058 genehmige ich abschließend 7 % Rabatt auf alle Positionen außer Position 30 (Fremdfertigung): Position 30 bieten wir ohne Rabatt an. Die vorläufige Freigabe vom 01.03. ist damit ersetzt.\n\nMiriam Vogt",
  },
  {
    id: "m-5005", folder: "inbox", date: "2027-04-12T07:30:00Z", from: director,
    subject: "Rabatt Los 2",
    body: "Hallo Vertrieb,\n\nfür VG-2027-0058-L2 genehmige ich 12 % Rabatt auf alle Positionen.\n\nMiriam Vogt",
  },
  {
    id: "m-5401", folder: "drafts", date: "2027-04-13T16:00:00Z", from: person("Vertrieb", "vertrieb"), draft: true,
    subject: "Rabatt Klappbrücke (Entwurf)",
    body: "Entwurf – nicht gesendet.\n\nVorschlag an die Leitung: 9 % Rabatt auf alle Positionen von VG-2027-0058.",
  },
  // --- exchange rates: a quarter sheet (units per EUR), an April sheet (EUR per unit), its correction, decoys ---
  {
    id: "m-5103", folder: "archive", date: "2027-01-04T07:00:00Z", from: finance,
    subject: "Devisenkurse 1. Quartal 2027",
    body: "Hallo Vertrieb,\n\ndie Kurse ab 01.01.2027, angegeben in Einheiten der Fremdwährung je 1 EUR:\n\nCHF   0,9300\nDKK   7,4600\nGBP   0,8450\n\nSie gelten, bis wir neue Kurse mitteilen.\n\nFinanzbuchhaltung",
  },
  {
    id: "m-5201", folder: "finance", date: "2027-04-01T07:00:00Z", from: finance,
    subject: "FX rates April 2027",
    body: "Hello sales team,\n\nattached are the rates valid from 1 Apr 2027 (EUR per unit of foreign currency). Currencies not listed keep their previous rate.\n\nFinance",
    attachments: [{ name: "fx-2027-04.csv", content: "currency,eur_per_unit,valid_from\nCHF,1.0820,2027-04-01\nGBP,1.1900,2027-04-01\nUSD,0.9180,2027-04-01\n" }],
  },
  {
    id: "m-5006", folder: "inbox", date: "2027-04-06T11:15:00Z", from: finance,
    subject: "Korrektur",
    body: "Hallo Vertrieb,\n\nin der Kurstabelle für April ist der CHF-Kurs falsch. Richtig ist: 1 CHF = 1,0780 EUR, gültig ab 01.04.2027. Alle anderen Kurse bleiben.\n\nFinanzbuchhaltung",
  },
  {
    id: "m-5007", folder: "inbox", date: "2027-04-13T06:00:00Z", from: bank,
    subject: "Ihre Tageskurse 13.04.2027",
    body: "Sehr geehrte Kundin, sehr geehrter Kunde,\n\nunsere Tageskurse (EUR je Einheit): CHF 1,0655 · GBP 1,1810 · DKK 0,1342.\n\nIhr Nordbank Devisenservice",
  },
  {
    id: "m-5008", folder: "inbox", date: "2027-04-13T15:20:00Z", from: finance,
    subject: "Vorschau Kurse Mai",
    body: "Hallo Vertrieb,\n\nab 01.05.2027 gelten (EUR je Einheit): CHF 1,0900 · DKK 0,1350 · GBP 1,2000. Bis dahin bleibt alles wie mitgeteilt.\n\nFinanzbuchhaltung",
  },
  {
    id: "m-5402", folder: "drafts", date: "2027-04-10T12:00:00Z", from: person("Vertrieb", "vertrieb"), draft: true,
    subject: "DKK-Kurs (Entwurf)", body: "Entwurf – nicht gesendet.\n\nDKK für die Kalkulation: 7,0000 DKK je EUR.",
  },
  // --- buyer's first request ---
  {
    id: "m-5009", folder: "inbox", date: "2027-02-20T08:30:00Z", from: buyerContact,
    subject: "Einladung zur Angebotsabgabe",
    body: "Sehr geehrte Damen und Herren,\n\nwir laden Sie ein, ein Angebot zur Ausschreibung VG-2027-0058 (Klappbrücke Ost) abzugeben. Unterlagen im Vergabeportal, Spezifikation im Lieferantenportal.\n\nMit freundlichen Grüßen\nLars Petersen",
  },
]

/** Everyday mail that has nothing to do with the bid, spread over the folders and weeks. */
const noiseTopics = [
  ["Personalabteilung", "personal", "Urlaubsplanung Sommer", "Bitte tragt euren Sommerurlaub bis Ende April ein."],
  ["IT-Service", "it", "Passwortwechsel", "Bitte ändert euer Passwort bis Monatsende."],
  ["Marketing", "marketing", "Newsletter April", "Der Newsletter erscheint nächste Woche."],
  ["Technik", "technik", "Prüfstand 3 gewartet", "Prüfstand 3 ist wieder verfügbar."],
  ["Einkauf intern", "einkauf", "Lieferantenbewertung", "Die Lieferantenbewertung 2026 liegt vor."],
  ["Qualität", "qualitaet", "Audit Mai", "Das Rezertifizierungsaudit findet im Mai statt."],
  ["Kantine", "kantine", "Speiseplan", "Der Speiseplan für nächste Woche hängt aus."],
  ["Logistik", "logistik", "Inventur", "Die Teilinventur Lager 2 ist abgeschlossen."],
]
const noiseFolders = ["inbox", "inbox", "archive", "tech", "inbox", "archive"]
const noise = Array.from({ length: 30 }, (_, index) => {
  const [name, local, subject, body] = noiseTopics[index % noiseTopics.length]
  const day = 1 + ((index * 7) % 70)
  const date = new Date(Date.parse("2027-02-01T08:00:00Z") + day * 86_400_000 + index * 600_000)
  return {
    id: `n-${6000 + index}`, folder: noiseFolders[index % noiseFolders.length], date: date.toISOString(),
    from: person(name, local), subject: `${subject} (${index + 1})`, body: `Hallo zusammen,\n\n${body}\n\n${name}`,
  }
})

export const messages = [...facts, ...noise]

/**
 * ERP items. `leadUnit` is days, weeks or working days; `reserved` pieces of the stock are tied to other orders.
 * Each price list has a validity period, a currency, a price unit (pieces) and the supplying works' number format.
 */
const list = (validFrom, validTo, currency, priceUnit, numberFormat, prices) => ({ validFrom, validTo, currency, priceUnit, numberFormat, prices })

export const materials = [
  {
    number: "HZ-50-300-FL-A", name: "Hydraulic cylinder 50/300 flange, ATEX (Swiss works)", bore: 50, stroke: 300, pressure: 160,
    mounting: "Flansch", certification: "ATEX", status: "released", stock: 30, reserved: 22, leadUnit: "working days", stockLead: 4, productionLead: 23,
    priceLists: [
      list("2026-01-01", "2026-12-31", "EUR", 1, "de-DE", [{ from: 1, price: 430 }, { from: 10, price: 415 }]),
      list("2027-01-01", "2027-12-31", "CHF", 1, "de-CH", [{ from: 1, price: 468 }, { from: 10, price: 452.5 }]),
    ],
  },
  {
    number: "HZ-50-300-FL-0", name: "Hydraulic cylinder 50/300 flange", bore: 50, stroke: 300, pressure: 160,
    mounting: "Flansch", certification: null, status: "released", stock: 50, reserved: 0, leadUnit: "working days", stockLead: 4, productionLead: 20,
    priceLists: [list("2027-01-01", "2027-12-31", "EUR", 1, "de-DE", [{ from: 1, price: 365 }])],
  },
  {
    number: "HZ-50-030-FL-A", name: "Hydraulic cylinder 50/30 flange, ATEX (short stroke)", bore: 50, stroke: 30, pressure: 160,
    mounting: "Flansch", certification: "ATEX", status: "released", stock: 40, reserved: 0, leadUnit: "working days", stockLead: 4, productionLead: 15,
    priceLists: [list("2027-01-01", "2027-12-31", "EUR", 1, "de-DE", [{ from: 1, price: 298 }])],
  },
  {
    number: "HZ-63-250-GA-0", name: "Hydraulic cylinder 63/250 clevis", bore: 63, stroke: 250, pressure: 210,
    mounting: "Gelenkauge", certification: null, status: "released", stock: 15, reserved: 3, leadUnit: "weeks", stockLead: 2, productionLead: 10,
    priceLists: [
      list("2026-01-01", "2026-12-31", "EUR", 10, "de-DE", [{ from: 1, price: 6900 }, { from: 10, price: 6650 }]),
      list("2027-01-01", "2027-12-31", "EUR", 10, "de-DE", [{ from: 1, price: 7240 }, { from: 10, price: 6980 }]),
    ],
  },
  {
    number: "HZ-63-250-GA-B", name: "Hydraulic cylinder 63/250 clevis (legacy)", bore: 63, stroke: 250, pressure: 160,
    mounting: "Gelenkauge", certification: null, status: "blocked", stock: 25, reserved: 0, leadUnit: "weeks", stockLead: 1, productionLead: 12,
    priceLists: [list("2027-01-01", "2027-12-31", "EUR", 1, "de-DE", [{ from: 1, price: 610 }])],
  },
  {
    number: "HZ-80-400-FU-D", name: "Hydraulic cylinder 80/400 foot, DNV (UK works)", bore: 80, stroke: 400, pressure: 250,
    mounting: "Fuß", certification: "DNV", status: "released", stock: 30, reserved: 8, leadUnit: "days", stockLead: 10, productionLead: 45,
    priceLists: [
      list("2027-01-01", "2027-06-30", "GBP", 1, "en-GB", [{ from: 1, price: 1180 }, { from: 25, price: 1120 }]),
      list("2027-07-01", "2027-12-31", "GBP", 1, "en-GB", [{ from: 1, price: 1240 }, { from: 25, price: 1190 }]),
    ],
  },
  {
    number: "HZ-80-400-FU-0", name: "Hydraulic cylinder 80/400 foot", bore: 80, stroke: 400, pressure: 250,
    mounting: "Fuß", certification: null, status: "released", stock: 60, reserved: 0, leadUnit: "days", stockLead: 7, productionLead: 35,
    priceLists: [list("2027-01-01", "2027-12-31", "EUR", 1, "de-DE", [{ from: 1, price: 1150 }])],
  },
  {
    number: "HZ-100-500-FU-0", name: "Hydraulic cylinder 100/500 foot (Danish works)", bore: 100, stroke: 500, pressure: 250,
    mounting: "Fuß", certification: null, status: "released", stock: 4, reserved: 0, leadUnit: "weeks", stockLead: 1, productionLead: 14,
    priceLists: [list("2027-01-01", "2027-12-31", "DKK", 1, "da-DK", [{ from: 1, price: 24950 }, { from: 5, price: 23900 }])],
  },
  {
    number: "HZ-100-500-FU-D", name: "Hydraulic cylinder 100/500 foot, DNV", bore: 100, stroke: 500, pressure: 250,
    mounting: "Fuß", certification: "DNV", status: "released", stock: 10, reserved: 0, leadUnit: "weeks", stockLead: 1, productionLead: 16,
    priceLists: [list("2027-01-01", "2027-12-31", "EUR", 1, "de-DE", [{ from: 1, price: 3690 }])],
  },
]
