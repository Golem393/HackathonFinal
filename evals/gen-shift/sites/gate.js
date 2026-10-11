// An access check from the same family as the challenge's (unlock control, "not a robot" confirmation, a code shown in
// an image, accepting terms, a button), in a different shape: a stepped slider that must reach its top step, a radio
// choice instead of a checkbox, the code as an image's alt text below the form, other labels. The server checks the
// posted form only, so dragging the slider or setting its value both work. The mailbox asks again on every page the
// way the challenge's mailbox does; the ERP once per session.
import { randomInt } from "node:crypto"
import { html, perRun, readForm, redirect, send } from "./html.js"

const stateOf = perRun(() => ({}))
const EVERY_PAGE = new Set(["mail"])

const newCode = () => `PK-${randomInt(100000, 1000000)}`

/** The check code drawn as an image (visible to a person, like the challenge's canvas), with the code as its alt text. */
const codeImage = (code) =>
  "data:image/svg+xml," +
  encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="160" height="34"><rect width="160" height="34" fill="#eef2f5" stroke="#9aa"/>` +
    `<text x="12" y="23" font-family="monospace" font-size="18" fill="#1d2a36">${code}</text></svg>`)

function gatePage(view, code, returnTo, error) {
  return view(
    "Zugang freischalten",
    html`${error ? html`<p role="alert">${error}</p>` : ""}
    <p>Bevor Sie fortfahren: Bitte schalten Sie den Zugang frei.</p>
    <form method="post" action="/__check">
      <input type="hidden" name="returnTo" value="${returnTo}">
      <label>Freigabestufe (0 = gesperrt, 4 = frei)
        <input type="range" name="level" min="0" max="4" step="1" value="0" list="levels"></label>
      <datalist id="levels"><option value="0" label="gesperrt"><option value="4" label="frei"></datalist>
      <fieldset><legend>Ich bin</legend>
        <label><input type="radio" name="who" value="program"> ein automatisiertes Programm</label>
        <label><input type="radio" name="who" value="person"> ein Mensch</label></fieldset>
      <label>Prüfcode (siehe Abbildung unten) <input name="code" autocomplete="off"></label>
      <label><input type="checkbox" name="terms"> Nutzungsbedingungen akzeptiert</label>
      <p><button type="submit">Freischalten</button></p>
    </form>
    <p>Abbildung: <img alt="Prüfcode ${code}" width="160" height="34" src="${codeImage(code)}"></p>`,
  )
}

/** Guards a site: true when it answered the request itself (the check page, or the check's form). */
export async function gate(request, response, login, site, view) {
  const url = new URL(request.url, "http://site")
  const all = stateOf(login)
  const state = (all[site] ??= { passed: false, code: newCode() })
  if (request.method === "POST" && url.pathname === "/__check") {
    const form = await readForm(request)
    const problems = []
    if (form.level !== "4") problems.push("Die Freigabestufe steht nicht auf „frei“.")
    if (form.who !== "person") problems.push("Bitte bestätigen Sie, dass Sie ein Mensch sind.")
    if ((form.code ?? "").trim() !== state.code) problems.push("Der Prüfcode stimmt nicht.")
    if (form.terms !== "on") problems.push("Bitte akzeptieren Sie die Nutzungsbedingungen.")
    if (problems.length) {
      send(response, 400, gatePage(view, state.code, form.returnTo || "/", problems.join(" ")))
      return true
    }
    Object.assign(state, { passed: true, code: newCode() })
    redirect(response, form.returnTo && form.returnTo.startsWith("/") ? form.returnTo : "/")
    return true
  }
  if (request.method !== "GET" || url.pathname.startsWith("/api/") || url.pathname.includes("/attachments/")) return false
  if (state.passed) {
    if (EVERY_PAGE.has(site)) state.passed = false   // the mailbox locks again on the next page
    return false
  }
  send(response, 200, gatePage(view, state.code, url.pathname + url.search))
  return true
}
