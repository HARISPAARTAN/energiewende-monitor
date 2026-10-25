"""Vendor the pinned PBIP/PBIR JSON schemas from microsoft/json-schemas (MIT) into tools/pbi/schemas/.

Usage: uv run python tools/pbi/vendor_schemas.py [--from <local json-schemas checkout>]
Without --from, the files are downloaded from raw.githubusercontent.com at the pinned commit.
"""

from __future__ import annotations

import argparse
import json
import shutil
import urllib.request
from pathlib import Path

COMMIT = "5e1199a15b80e3d51198fe017b1a6fb9bb0871a6"  # microsoft/json-schemas main, 2026-10-23
RAW = f"https://raw.githubusercontent.com/microsoft/json-schemas/{COMMIT}/"
OUT = Path(__file__).parent / "schemas"
FILES = [
    "LICENSE",
    "fabric/pbip/pbipProperties/1.0.0/schema.json",
    "fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
    "fabric/item/report/definitionProperties/2.0.0/schema.json",
    "fabric/item/report/definition/report/3.3.0/schema.json",
    "fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
    "fabric/item/report/definition/pagesMetadata/1.1.0/schema.json",
    "fabric/item/report/definition/page/2.1.0/schema.json",
    "fabric/item/report/definition/visualContainer/2.13.0/schema.json",
    "fabric/item/report/definition/bookmark/2.1.0/schema.json",
    "fabric/item/report/definition/bookmarksMetadata/1.0.0/schema.json",
    "fabric/item/report/definition/visualConfiguration/2.8.0/schema.json",
    "fabric/item/report/definition/visualConfiguration/2.8.0/schema-embedded.json",
    "fabric/item/report/definition/filterConfiguration/1.3.0/schema.json",
    "fabric/item/report/definition/filterConfiguration/1.3.0/schema-embedded.json",
    "fabric/item/report/definition/semanticQuery/1.4.0/schema.json",
    "fabric/item/report/definition/formattingObjectDefinitions/1.5.0/schema.json",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", type=Path, default=None)
    args = ap.parse_args()
    for rel in FILES:
        dest = OUT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if args.src:
            shutil.copyfile(args.src / rel, dest)
        else:
            with urllib.request.urlopen(RAW + rel, timeout=60) as resp:
                dest.write_bytes(resp.read())
        if rel.endswith(".json"):
            json.loads(dest.read_text(encoding="utf-8-sig"))  # fail early on a truncated download
        print("vendored", rel)


if __name__ == "__main__":
    main()
