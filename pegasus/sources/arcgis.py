"""ArcGIS Feature Service permits, e.g. Virginia Beach's open-data portal.

sources.yaml:
    vb-permits:
      type: arcgis
      url: https://services2.arcgis.com/.../FeatureServer/0
      city: Virginia Beach
      date_field: ApplicationDate
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .base import Adapter, LeadInput, RawItem, clean
from .permits_common import get, normalize_permit

PAGE = 1000


class ArcGISAdapter(Adapter):
    kind = "permit"

    @property
    def query_url(self) -> str:
        return self.config["url"].rstrip("/") + "/query"

    def fetch(self, since: datetime) -> Iterable[RawItem]:
        date_field = self.config.get("date_field")
        where = f"{date_field} >= TIMESTAMP '{since.strftime('%Y-%m-%d %H:%M:%S')}'" if date_field else "1=1"
        if self.config.get("where"):
            where = f"({where}) AND ({self.config['where']})"
        max_rows = int(self.config.get("max_rows", 20000))
        offset = 0
        while offset < max_rows:
            params = {
                "where": where,
                "outFields": "*",
                "outSR": 4326,
                "returnGeometry": "true",
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": PAGE,
            }
            if date_field:
                params["orderByFields"] = f"{date_field} DESC"
            resp = self.client.get(self.query_url, params=params)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"ArcGIS error: {data['error']}")
            features = data.get("features", [])
            for feat in features:
                row = dict(feat.get("attributes") or {})
                geom = feat.get("geometry") or {}
                if "x" in geom and "y" in geom:
                    row["_lng"], row["_lat"] = geom["x"], geom["y"]
                ext = clean(get(row, self.config, "external_id"))
                if ext:
                    yield RawItem(external_id=ext, payload=row)
            if not data.get("exceededTransferLimit") and len(features) < PAGE:
                break
            offset += len(features) or PAGE

    def normalize(self, payload: dict) -> LeadInput | None:
        config = dict(self.config)
        fields = dict(config.get("fields") or {})
        fields.setdefault("lat", "_lat")
        fields.setdefault("lng", "_lng")
        config["fields"] = fields
        return normalize_permit(
            payload, config, default_city=self.default_city, url_template=self.config.get("url_template")
        )

    def sample(self, limit: int = 5) -> list[dict]:
        resp = self.client.get(
            self.query_url,
            params={"where": "1=1", "outFields": "*", "f": "json", "resultRecordCount": limit},
        )
        resp.raise_for_status()
        return [f.get("attributes", {}) for f in resp.json().get("features", [])]
