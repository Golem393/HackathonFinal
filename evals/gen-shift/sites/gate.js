// A different access check than the challenge's: press and hold a button for two seconds, answer an arithmetic
// question written in words, and pick every tile that shows a given symbol. It guards a site's pages per run and
// comes back after every few page views, as checks on real portals do.
import { randomInt, randomUUID } from "node:crypto"
import { html, perRun, raw, readForm, redirect, send } from "./html.js"

const WORDS = ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf"]
const SYMBOLS = [
  ["⚙", "Zahnrad"], ["☀", "Sonne"], ["✈", "Flugzeug"], ["⚓", "Anker"], ["☂", "Schirm"], ["♣", "Kleeblatt"],
]
const VIEWS_PER_PASS = 5

const stateOf = perRun(() => ({}))

function newChallenge() {
  const a = randomInt(2, 9)
  const b = randomInt(2, 13 - a)
  const [symbol, symbolName] = SYMBOLS[randomInt(0, SYMBOLS.length)]
  const tiles = Array.from({ length: 9 }, () => SYMBOLS[randomInt(0, SYMBOLS.length)][0])
  for (const index of [randomInt(0, 3), randomInt(3, 6), randomInt(6, 9)]) tiles[index] = symbol   // at least 3
  return { nonce: randomUUID(), a, b, symbol, symbolName, tiles, held: null }
}

function gatePage(view, challenge, returnTo, error) {
  const tileButtons = challenge.tiles.map(
    (symbol, index) =>
      html`<button type="button" class="tile" data-index="${index}" aria-pressed="false" aria-label="Feld ${index + 1}: ${SYMBOLS.find(([s]) => s === symbol)[1]}">${symbol}</button>`,
  )
  const script = `
const hold = document.getElementById('hold'); let timer = null
const start = () => { hold.textContent = 'Halten …'; timer = setTimeout(() => {
  document.querySelector('input[name=held]').value = hold.dataset.nonce; hold.textContent = 'Gehalten ✓'; hold.disabled = true }, 2000) }
const stop = () => { if (!hold.disabled) { clearTimeout(timer); hold.textContent = 'Gedrückt halten (2 Sekunden)' } }
hold.addEventListener('pointerdown', start); hold.addEventListener('pointerup', stop); hold.addEventListener('pointerleave', stop)
document.querySelectorAll('.tile').forEach((tile) => tile.addEventListener('click', () => {
  tile.setAttribute('aria-pressed', tile.getAttribute('aria-pressed') === 'true' ? 'false' : 'true')
  tile.style.outline = tile.getAttribute('aria-pressed') === 'true' ? '3px solid #1a6' : ''
  document.querySelector('input[name=tiles]').value = [...document.querySelectorAll('.tile[aria-pressed=true]')]
    .map((t) => t.dataset.index).join(',') }))`
  return view(
    "Sicherheitsprüfung",
    html`${error ? html`<p role="alert">${error}</p>` : ""}
    <p>Bitte bestätigen Sie, dass Sie eine Person sind. Alle drei Schritte sind erforderlich.</p>
    <form method="post" action="/__check">
      <input type="hidden" name="returnTo" value="${returnTo}"><input type="hidden" name="held" value="">
      <input type="hidden" name="tiles" value="">
      <h2>1. Knopf gedrückt halten</h2>
      <button type="button" id="hold" data-nonce="${challenge.nonce}" style="padding:14px 28px">Gedrückt halten (2 Sekunden)</button>
      <h2>2. Rechenaufgabe</h2>
      <label>Wie viel ist ${WORDS[challenge.a]} plus ${WORDS[challenge.b]}? (in Ziffern) <input name="sum" autocomplete="off"></label>
      <h2>3. Bildauswahl</h2>
      <p>Wählen Sie alle Felder mit dem Symbol „${challenge.symbolName}“.</p>
      <div style="display:grid;grid-template-columns:repeat(3,64px);gap:6px">${tileButtons}</div>
      <p><button type="submit">Prüfung abschließen</button></p>
    </form><script>${raw(script)}</script>`,
  )
}

/**
 * Guards a site: true when it answered the request itself (the check page, or the check's form). Every page view of a
 * passed check counts; after VIEWS_PER_PASS views the check comes back.
 */
export async function gate(request, response, login, site, view) {
  const url = new URL(request.url, "http://site")
  const all = stateOf(login)
  const state = (all[site] ??= { passed: false, views: 0, challenge: newChallenge() })
  if (request.method === "POST" && url.pathname === "/__check") {
    const form = await readForm(request)
    const want = state.challenge.tiles.flatMap((symbol, index) => (symbol === state.challenge.symbol ? [String(index)] : []))
    const got = String(form.tiles ?? "").split(",").filter(Boolean).sort((a, b) => a - b)
    const problems = []
    if (form.held !== state.challenge.nonce) problems.push("Der Knopf wurde nicht lange genug gedrückt gehalten.")
    if (Number(form.sum) !== state.challenge.a + state.challenge.b) problems.push("Die Rechenaufgabe ist falsch gelöst.")
    if (got.join(",") !== want.join(",")) problems.push("Die Bildauswahl stimmt nicht.")
    if (problems.length) {
      state.challenge = newChallenge()
      send(response, 400, gatePage(view, state.challenge, form.returnTo || "/", problems.join(" ")))
      return true
    }
    Object.assign(state, { passed: true, views: 0, challenge: newChallenge() })
    redirect(response, form.returnTo && form.returnTo.startsWith("/") ? form.returnTo : "/")
    return true
  }
  if (request.method !== "GET") return false
  if (state.passed && state.views < VIEWS_PER_PASS) {
    state.views += 1
    return false
  }
  state.passed = false
  send(response, 200, gatePage(view, state.challenge, url.pathname + url.search))
  return true
}
