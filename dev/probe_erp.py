"""Dev-only scouting probe for the ERP: logs in with the scouting logins and maps its pages. Not part of the agent.

Usage, from the repo root, after `eval "$(atira scout --env)"`:

    uv run --no-sync python dev/probe_erp.py            # landing page plus every same-site link on it
    uv run --no-sync python dev/probe_erp.py /some/path # also snapshot these paths

Writes dev/out/erp/: one JSON per page (url, title, text, forms, links) and a screenshot, plus index.json.
Nothing here is copied into the agent: it only tells us how the ERP behaves, so we know what helpers to build.
"""
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

OUT = Path(__file__).parent / "out" / "erp"

PAGE_INFO_JS = """() => {
  const label = el => (el.labels && el.labels[0] && el.labels[0].innerText.trim()) || el.getAttribute('aria-label') || el.placeholder || '';
  return {
    title: document.title,
    text: document.body ? document.body.innerText : '',
    forms: [...document.forms].map(f => ({
      action: f.getAttribute('action'), method: (f.getAttribute('method') || 'get').toLowerCase(),
      fields: [...f.elements].filter(e => e.name || e.type === 'submit').map(e => ({
        tag: e.tagName.toLowerCase(), type: e.type, name: e.name, label: label(e),
        options: e.tagName === 'SELECT' ? [...e.options].map(o => o.value).slice(0, 30) : undefined,
      })),
    })),
    links: [...document.querySelectorAll('a[href]')].map(a => ({text: a.innerText.trim(), href: a.getAttribute('href')})),
    iframes: [...document.querySelectorAll('iframe')].map(f => f.getAttribute('src')),
  };
}"""


def erp_access() -> dict:
    raw = os.environ.get("CHALLENGE_SITE_ACCESS")
    if not raw:
        raise SystemExit('No scouting logins. Run: eval "$(atira scout --env)"')
    return next(site for site in json.loads(raw) if site.get("siteId") == "erp")


def slug(url: str) -> str:
    path = urlparse(url)
    return re.sub(r"[^A-Za-z0-9]+", "_", (path.path + "_" + path.query).strip("/_")) or "root"


async def snapshot(page, index: list) -> dict:
    info = await page.evaluate(PAGE_INFO_JS)
    info["url"] = page.url
    name = f"{len(index):02d}_{slug(page.url)}"[:80]
    (OUT / f"{name}.json").write_text(json.dumps(info, ensure_ascii=False, indent=2))
    await page.screenshot(path=OUT / f"{name}.png", full_page=True)
    index.append({"file": name, "url": page.url, "title": info["title"], "forms": len(info["forms"]),
                  "links": len(info["links"])})
    print(f"  {name}  {info['title']}  forms={len(info['forms'])} links={len(info['links'])}", flush=True)
    return info


async def main() -> None:
    site = erp_access()
    base = site["url"].rstrip("/")
    OUT.mkdir(parents=True, exist_ok=True)
    index: list = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=os.environ.get("HEADLESS") == "1")
        page = await (await browser.new_context(viewport={"width": 1280, "height": 800})).new_page()

        await page.goto(base + "/")
        await page.fill("input[name=username]", site["credentials"]["username"])
        await page.fill("input[name=password]", site["credentials"]["password"])
        started = time.time()
        await page.click("button[type=submit]")
        await page.wait_for_load_state("networkidle")
        print(f"Logged in: {page.url}", flush=True)

        landing = await snapshot(page, index)
        targets = []
        for link in landing["links"]:
            url = urljoin(page.url, link["href"])
            if urlparse(url).netloc == urlparse(base).netloc and "logout" not in url.lower() and url not in targets:
                targets.append(url)
        targets += [urljoin(base + "/", path.lstrip("/")) for path in sys.argv[1:]]

        for url in targets:
            try:
                await page.goto(url)
                await page.wait_for_load_state("networkidle")
                if "/login" in urlparse(page.url).path:
                    print(f"  session ended after {time.time() - started:.0f}s at {url}", flush=True)
                    index.append({"url": url, "session_expired_after_s": round(time.time() - started)})
                    break
                await snapshot(page, index)
            except Exception as error:  # keep mapping the rest
                print(f"  {url}: {error}", flush=True)
                index.append({"url": url, "error": str(error)})
        await browser.close()
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2))
    print(f"Wrote {len(index)} pages to {OUT}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
