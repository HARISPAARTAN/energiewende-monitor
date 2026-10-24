"""Capture one weekly SMARD chunk per configured series as a test fixture.

Usage: uv run python tools/capture_fixtures.py --week-start 2025-10-20
The week start is a Monday in Europe/Berlin local time. Series whose index has no chunk for that week
(for example Kernenergie after 2023) are skipped with a note.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime

from ewmonitor.config import load_settings
from ewmonitor.ingest import series_specs
from ewmonitor.smard import SmardClient
from ewmonitor.timekeys import BERLIN


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week-start", required=True, help="Monday, local date YYYY-MM-DD")
    args = parser.parse_args()
    monday = date.fromisoformat(args.week_start)
    ts_ms = int(datetime(monday.year, monday.month, monday.day, tzinfo=BERLIN).timestamp() * 1000)
    settings = load_settings()
    out = settings.fixtures_dir / "smard"
    out.mkdir(parents=True, exist_ok=True)
    client = SmardClient(settings.smard.base_url, out)
    for spec in series_specs(settings):
        index = client.fetch_index(spec.filter_id, spec.region, spec.resolution)
        if ts_ms not in index:
            print(f"skip {spec}: index has no chunk starting {monday} ({ts_ms})")
            continue
        path = client.download_chunk(spec.filter_id, spec.region, spec.resolution, ts_ms, force=True)
        print(f"saved {path.name}")


if __name__ == "__main__":
    main()
