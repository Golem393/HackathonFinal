// The bidder's ERP, in English and built differently from the challenge's: an item search, lead times in days, and
// price lists with their own currency, price unit (per 1 or per 10 pieces) and number format (de-DE or en-US).
import { bidder, materials } from "../world.js"
import { html, page, send, siteUrl } from "./html.js"

const nav = () => [["/", "Item master"], [`${siteUrl("mail")}/`, "Mail"]]
export const view = (title, body, signedIn) =>
  page({ site: `ERP · ${bidder.name}`, title, nav: nav(), body, accent: "#5b4a2f", signedIn })

const formatted = (value, format) =>
  value.toLocaleString(format, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export async function erp(request, response) {
  const url = new URL(request.url, "http://erp")
  if (request.method === "GET" && url.pathname === "/") {
    const query = (url.searchParams.get("q") ?? "").trim().toLowerCase()
    const rows = query ? materials.filter((item) => `${item.number} ${item.name}`.toLowerCase().includes(query)) : []
    return send(
      response,
      200,
      view(
        "Item master",
        html`<form method="get" action="/"><label>Item number or description <input name="q" value="${url.searchParams.get("q") ?? ""}"></label><button type="submit">Search</button></form>
        ${query ? html`<p>${rows.length} items</p><table><thead><tr><th>Item</th><th>Description</th></tr></thead><tbody>${rows.map(
          (item) => html`<tr><td><a href="/items/${item.number}">${item.number}</a></td><td>${item.name}</td></tr>`,
        )}</tbody></table>` : html`<p>Enter a search term (e.g. a bore/stroke such as "50/200").</p>`}`,
      ),
    )
  }
  const number = /^\/items\/([\w-]+)$/.exec(url.pathname)?.[1]
  const item = materials.find((candidate) => candidate.number === number)
  if (request.method === "GET" && item) {
    const tab = url.searchParams.get("tab") ?? "general"
    const tabs = html`<p><a href="/items/${item.number}">General</a> · <a href="/items/${item.number}?tab=logistics">Logistics</a> · <a href="/items/${item.number}?tab=pricing">Pricing</a></p>`
    const body =
      tab === "logistics"
        ? html`<dl><dt>Unrestricted stock</dt><dd>${item.stock} pcs</dd><dt>Delivery from stock</dt><dd>${item.stockDays} days</dd>
            <dt>Production lead time</dt><dd>${item.productionDays} days</dd></dl>`
        : tab === "pricing"
          ? html`<dl><dt>Currency</dt><dd>${item.currency}${item.fxKey ? html` · FX key ${item.fxKey}` : ""}</dd>
              <dt>Price unit</dt><dd>${item.priceUnit} pcs</dd><dt>Number format</dt><dd>${item.numberFormat}</dd>
              <dt>Valid</dt><dd>2026-01-01 to 2026-12-31</dd></dl>
              <table><thead><tr><th>From quantity</th><th>Net price per price unit</th></tr></thead><tbody>${item.prices.map(
                (scale) => html`<tr><td>${scale.from} pcs</td><td>${formatted(scale.price, item.numberFormat)} ${item.currency}</td></tr>`,
              )}</tbody></table>`
          : html`<dl><dt>Status</dt><dd>${item.status}</dd><dt>Bore</dt><dd>${item.bore} mm</dd><dt>Stroke</dt><dd>${item.stroke} mm</dd>
              <dt>Operating pressure</dt><dd>${item.pressure} bar</dd><dt>Mounting</dt><dd>${item.mounting}</dd>
              <dt>Certification</dt><dd>${item.certification ?? "none"}</dd></dl>
              <p class="notice">Status codes: released = may be sold · blocked = must not be offered</p>`
    return send(response, 200, view(`${item.number} · ${item.name}`, html`${tabs}${body}<p><a href="/">Back to item master</a></p>`))
  }
  return send(response, 404, view("Not found", html`<p><a href="/">Item master</a></p>`))
}
