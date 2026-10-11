// The bidder's mailbox, built differently from the challenge's: a folder tree, a message list that loads more rows only
// when it is scrolled, senders shown by name (the address only in a message's header), a search over the current
// folder's subjects only, attachments as downloads, and drafts that were never sent. The tender portal delivers the
// signing TANs into the inbox with a function call; each run has its own copy of the mailbox.
import { bidder, folders, messages } from "../world.js"
import { germanDate, html, page, perRun, raw, send, sendJson, siteUrl } from "./html.js"

const PAGE_SIZE = 4
const boxOf = perRun(() => messages.map((message) => ({ ...message })))
const nav = () => [["/", "Postfach"], [`${siteUrl("erp")}/`, "ERP"]]
export const view = (title, body, signedIn) =>
  page({ site: "Werkpost 2", title, nav: nav(), body, accent: "#2f4f5a", signedIn })

/** The tender portal sends a signing TAN: a new message at the top of the run's inbox. */
export function deliverTan(login, tan, reference, count) {
  boxOf(login).push({
    id: `tan-${count}`, folder: "inbox", date: new Date().toISOString(),
    from: { name: "Vergabeportal Signaturdienst", address: "signatur@vergabeportal.example" },
    subject: `Signatur-TAN ${reference} (Anforderung ${count})`,
    body: `Ihre Signatur-TAN für ${reference}: ${tan}\n\nNur die zuletzt angeforderte TAN ist gültig.`,
  })
}

function listed(box, folder, query) {
  return box
    .filter((message) => message.folder === folder)
    .filter((message) => message.subject.toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => b.date.localeCompare(a.date))
}

const row = (message) =>
  html`<tr><td>${germanDate(message.date)}</td><td>${message.from.name}</td><td><a href="/messages/${message.id}">${message.subject}</a>${message.attachments?.length ? " 📎" : ""}</td></tr>`

const LAZY = `
const area = document.getElementById('list'), body = document.getElementById('rows')
let loading = false, done = false
area.addEventListener('scroll', async () => {
  if (loading || done || area.scrollTop + area.clientHeight < area.scrollHeight - 8) return
  loading = true
  const params = new URLSearchParams(location.search); params.set('offset', body.children.length)
  const reply = await fetch('/api/rows?' + params).then((r) => r.json())
  body.insertAdjacentHTML('beforeend', reply.html); done = !reply.more; loading = false
  if (done) document.getElementById('end').hidden = false
})`

function folderPage(box, folder, query) {
  const rows = listed(box, folder, query)
  const current = folders.find((item) => item.id === folder)
  return view(
    current.name,
    html`<div style="display:grid;grid-template-columns:200px 1fr;gap:20px">
      <nav aria-label="Ordner"><ul>${folders.map(
        (item) => html`<li><a href="/?folder=${item.id}">${item.id === folder ? html`<strong>${item.name}</strong>` : item.name}</a></li>`,
      )}</ul></nav>
      <section>
        <form method="get" action="/"><input type="hidden" name="folder" value="${folder}">
          <label>Betreff durchsuchen (nur dieser Ordner) <input name="q" value="${query}"></label><button type="submit">Suchen</button></form>
        <p>${rows.length} Nachrichten</p>
        <div id="list" style="height:170px;overflow-y:auto;border:1px solid #c8ced5" aria-label="Nachrichtenliste">
          <table><thead><tr><th>Datum</th><th>Von</th><th>Betreff</th></tr></thead>
          <tbody id="rows">${rows.slice(0, PAGE_SIZE).map(row)}</tbody></table>
          <p id="end" ${rows.length > PAGE_SIZE ? html`hidden` : ""}>Keine weiteren Nachrichten.</p>
        </div>
      </section></div><script>${raw(LAZY)}</script>`,
  )
}

function messagePage(message) {
  const folder = folders.find((item) => item.id === message.folder)
  return view(
    message.subject,
    html`${message.draft ? html`<p class="notice">Entwurf – diese Nachricht wurde nie gesendet.</p>` : ""}
    <dl><dt>Von</dt><dd>${message.from.name} &lt;${message.from.address}&gt;</dd><dt>An</dt><dd>${bidder.mailbox}</dd>
    <dt>Datum</dt><dd>${germanDate(message.date)}</dd><dt>Ordner</dt><dd>${folder.name}</dd></dl>
    <pre>${message.body}</pre>
    ${message.attachments?.length ? html`<h2>Anhänge</h2><ul>${message.attachments.map(
      (file) => html`<li><a href="/messages/${message.id}/attachments/${file.name}" download>${file.name}</a></li>`,
    )}</ul>` : ""}
    <p><a href="/?folder=${message.folder}">Zurück zu ${folder.name}</a></p>`,
  )
}

export async function mail(request, response, login) {
  const url = new URL(request.url, "http://mail")
  const box = boxOf(login)
  const folder = folders.some((item) => item.id === url.searchParams.get("folder")) ? url.searchParams.get("folder") : "inbox"
  const query = url.searchParams.get("q") ?? ""
  if (request.method === "GET" && url.pathname === "/") return send(response, 200, folderPage(box, folder, query))
  if (request.method === "GET" && url.pathname === "/api/rows") {
    const rows = listed(box, folder, query)
    const offset = Number(url.searchParams.get("offset") ?? 0)
    return sendJson(response, 200, {
      html: rows.slice(offset, offset + PAGE_SIZE).map((message) => row(message).text).join(""),
      more: offset + PAGE_SIZE < rows.length,
    })
  }
  const attachment = /^\/messages\/([\w-]+)\/attachments\/([\w.-]+)$/.exec(url.pathname)
  if (request.method === "GET" && attachment) {
    const file = box.find((item) => item.id === attachment[1])?.attachments?.find((item) => item.name === attachment[2])
    if (file) {
      response.writeHead(200, { "content-type": "text/csv; charset=utf-8", "content-disposition": `attachment; filename="${file.name}"` })
      return response.end(file.content)
    }
  }
  const id = /^\/messages\/([\w-]+)$/.exec(url.pathname)?.[1]
  const message = box.find((item) => item.id === id)
  if (request.method === "GET" && message) return send(response, 200, messagePage(message))
  return send(response, 404, view("Nicht gefunden", html`<p><a href="/">Zum Postfach</a></p>`))
}
