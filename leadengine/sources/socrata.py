"""Socrata (SODA) open-data permits, e.g. Norfolk's data.norfolk.gov.

sources.yaml:
    norfolk-permits:
      type: socrata
      domain: data.norfolk.gov
      dataset: fahm-yuh4
      city: Norfolk
      date_field: issue_date      # optional; defaults to the :updated_at system field
      fields: {description: work_description}   # optional overrides
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable

from .base import Adapter, LeadInput, RawItem
from .permits_common import get, normalize_permit
from .base import clean

PAGE = 1000


class SocrataAdapter(Adapter):
    kind = "permit"

    @property
    def base_url(self) -> str:
        return f"https://{self.config['domain']}/resource/{self.config['dataset']}.json"

    def fetch(self, since: datetime) -> Iterable[RawItem]:
        date_field = self.config.get("date_field", ":updated_at")
        where = f"{date_field} > '{since.strftime('%Y-%m-%dT%H:%M:%S')}'"
        if self.config.get("where"):
            where = f"({where}) AND ({self.config['where']})"
        headers = {}
        token = self.config.get("app_token") or os.environ.get("SOCRATA_APP_TOKEN")
        if token:
            headers["X-App-Token"] = token
        max_rows = int(self.config.get("max_rows", 20000))
        offset = 0
        while offset < max_rows:
            params = {
                "$where": where,
                "$order": f"{date_field} DESC",
                "$limit": PAGE,
                "$offset": offset,
            }
            if date_field.startswith(":"):
                params["$select"] = f"*, {date_field}"
            resp = self.client.get(self.base_url, params=params, headers=headers)
            resp.raise_for_status()
            rows = resp.json()
            for row in rows:
                ext = clean(get(row, self.config, "external_id"))
                if ext:
                    yield RawItem(external_id=ext, payload=row)
            if len(rows) < PAGE:
                break
            offset += PAGE

    def normalize(self, payload: dict) -> LeadInput | None:
        return normalize_permit(
            payload, self.config, default_city=self.default_city, url_template=self.config.get("url_template")
        )

    def sample(self, limit: int = 5) -> list[dict]:
        resp = self.client.get(self.base_url, params={"$limit": limit, "$order": ":updated_at DESC"})
        resp.raise_for_status()
        return resp.json()
