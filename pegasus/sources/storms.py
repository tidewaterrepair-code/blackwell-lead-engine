"""NOAA Storm Prediction Center local storm reports (hail, wind, tornado): free, nationwide.

Each report becomes an area signal (with a radius) that predicts roofing, siding,
gutter, fence, tree and restoration work for every customer whose territory it hits.

sources.yaml:
    noaa-storms:
      type: noaa_storms
      kind: storm
      days: [today, yesterday]
      min_hail_inches: 1.0
      min_wind_mph: 58
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .base import Adapter, LeadInput, RawItem

SPC_URL = "https://www.spc.noaa.gov/climo/reports/{day}_filtered_{kind}.csv"
KINDS = {"hail": ("Size", 5.0), "wind": ("Speed", 5.0), "torn": ("F_Scale", 3.0)}


class NOAAStormsAdapter(Adapter):
    kind = "storm"

    def fetch(self, since: datetime) -> Iterable[RawItem]:
        today = datetime.now(timezone.utc).date()
        for day in self.config.get("days", ["today", "yesterday"]):
            report_date = today if day == "today" else today - timedelta(days=1)
            for kind in KINDS:
                resp = self.client.get(SPC_URL.format(day=day, kind=kind))
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
                for row in csv.DictReader(io.StringIO(resp.text)):
                    if not row.get("Lat") or not row.get("Lon"):
                        continue
                    row = {**row, "_type": kind, "_date": report_date.isoformat()}
                    ext = f"{report_date}:{kind}:{row.get('Time')}:{row['Lat']}:{row['Lon']}"
                    yield RawItem(external_id=ext, payload=row)

    def normalize(self, payload: dict) -> LeadInput | None:
        kind = payload["_type"]
        magnitude_field, radius = KINDS[kind]
        raw = (payload.get(magnitude_field) or "").strip()
        try:
            lat, lng = float(payload["Lat"]), float(payload["Lon"])
        except (TypeError, ValueError):
            return None
        place = f"{(payload.get('Location') or '').title()}, {payload.get('State', '')}".strip(", ")
        if kind == "hail":
            inches = int(raw) / 100 if raw.isdigit() else None  # SPC reports hail in hundredths of an inch
            if inches is not None and inches < float(self.config.get("min_hail_inches", 1.0)):
                return None
            title = f"Hail {inches:.2f} in near {place}" if inches else f"Hail near {place}"
        elif kind == "wind":
            mph = int(raw) if raw.isdigit() else None
            if mph is not None and mph < int(self.config.get("min_wind_mph", 58)):
                return None
            title = f"Damaging wind {mph} mph near {place}" if mph else f"Damaging thunderstorm wind near {place}"
        else:
            title = f"Tornado ({raw or 'EF?'}) near {place}"
            radius = 3.0
        time_str = (payload.get("Time") or "0000").zfill(4)
        try:
            when = datetime.fromisoformat(payload["_date"]).replace(hour=int(time_str[:2]) % 24,
                                                                     minute=int(time_str[2:]) % 60)
        except ValueError:
            when = datetime.fromisoformat(payload["_date"])
        return LeadInput(
            external_id=f"{payload['_date']}:{kind}:{payload.get('Time')}:{payload['Lat']}:{payload['Lon']}",
            kind="storm", title=title, description=payload.get("Comments"), lat=lat, lng=lng,
            radius_miles=radius, state=(payload.get("State") or "")[:2] or None,
            city=(payload.get("Location") or "").title() or None, posted_at=when,
            url="https://www.spc.noaa.gov/climo/reports/today.html",
            hints=["hail" if kind == "hail" else ("tornado" if kind == "torn" else "thunderstorm wind")],
        )
