"""Accela Citizen Access (ACA) permit search, e.g. Chesapeake eBUILD.

ACA is an ASP.NET site with no public API, so this adapter drives a headless
Chromium (Playwright) through the anonymous "General Search" by date range and
parses the results grid. Requires the `browser` extra:

    pip install 'leadengine[browser]' && playwright install --with-deps chromium

sources.yaml:
    chesapeake-permits:
      type: accela
      base_url: https://aca-prod.accela.com/CHESAPEAKE
      module: Building
      city: Chesapeake
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import Adapter, LeadInput, RawItem, clean
from .permits_common import get, normalize_permit

log = logging.getLogger(__name__)

SEL_START = "#ctl00_PlaceHolderMain_generalSearchForm_txtGSStartDate"
SEL_END = "#ctl00_PlaceHolderMain_generalSearchForm_txtGSEndDate"
SEL_TYPE = "#ctl00_PlaceHolderMain_generalSearchForm_ddlGSPermitType"
SEL_SEARCH = "#ctl00_PlaceHolderMain_btnNewSearch"
SEL_GRID = "table[id$='gdvPermitList']"
SEL_NO_RESULTS = "#ctl00_PlaceHolderMain_RecordSearchResultInfo_noDataMessageForSearchResultList_messageBar"


def parse_aca_results(html: str, base_url: str) -> list[dict]:
    """Turn an ACA results grid into a list of {header: value} dicts."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(SEL_GRID)
    if table is None:
        return []
    header_row = table.select_one("tr.ACA_TabRow_Header") or table.find("tr")
    headers = [clean(th.get_text(" ")) or f"col{i}" for i, th in enumerate(header_row.find_all(["th", "td"]))]
    rows = []
    for tr in table.select("tr.ACA_TabRow_Odd, tr.ACA_TabRow_Even"):
        cells = tr.find_all("td")
        if not cells:
            continue
        row: dict = {}
        for header, td in zip(headers, cells):
            if header.lower() in ("", "select"):
                continue
            row[header] = clean(td.get_text(" "))
            link = td.find("a", href=True)
            if link and "CapDetail" in link["href"]:
                row["_url"] = urljoin(base_url + "/", link["href"])
        if any(row.values()):
            rows.append(row)
    return rows


class AccelaAdapter(Adapter):
    kind = "permit"

    def fetch(self, since: datetime) -> Iterable[RawItem]:
        try:
            from playwright.sync_api import TimeoutError as PWTimeout
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "Accela sources need Playwright: pip install 'leadengine[browser]' && "
                "playwright install --with-deps chromium (or build the Docker image with INSTALL_BROWSER=true)"
            ) from exc

        base = self.config["base_url"].rstrip("/")
        module = self.config.get("module", "Building")
        max_pages = int(self.config.get("max_pages", 20))
        # ACA rejects very wide date ranges; search in week-long windows.
        window = timedelta(days=int(self.config.get("window_days", 7)))
        end_all = datetime.now()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(user_agent=self.config.get("user_agent") or None)
            page.set_default_timeout(45_000)
            try:
                start = since
                while start < end_all:
                    end = min(start + window, end_all)
                    page.goto(f"{base}/Cap/CapHome.aspx?module={module}&TabName={module}")
                    page.fill(SEL_START, start.strftime("%m/%d/%Y"))
                    page.fill(SEL_END, end.strftime("%m/%d/%Y"))
                    if self.config.get("permit_type"):
                        page.select_option(SEL_TYPE, label=self.config["permit_type"])
                    page.click(SEL_SEARCH)
                    try:
                        page.wait_for_selector(f"{SEL_GRID}, {SEL_NO_RESULTS}")
                    except PWTimeout:
                        log.warning("%s: no results grid for %s-%s", self.source_id, start, end)
                        start = end
                        continue
                    for _ in range(max_pages):
                        for row in parse_aca_results(page.content(), base):
                            ext = clean(get(row, self._config_with_defaults(), "external_id"))
                            if ext:
                                yield RawItem(external_id=ext, payload=row)
                        nxt = page.locator(".aca_pagination a", has_text="Next")
                        if nxt.count() == 0:
                            break
                        nxt.first.click()
                        page.wait_for_load_state("networkidle")
                    start = end
            finally:
                browser.close()

    def _config_with_defaults(self) -> dict:
        config = dict(self.config)
        fields = {"external_id": "Record Number", "permit_type": "Record Type", "posted_at": "Date",
                  "description": ["Description", "Project Name"], "address": "Address"}
        fields.update(config.get("fields") or {})
        config["fields"] = fields
        return config

    def normalize(self, payload: dict) -> LeadInput | None:
        lead = normalize_permit(payload, self._config_with_defaults(), default_city=self.default_city)
        if lead and payload.get("_url"):
            lead.url = payload["_url"]
        return lead
