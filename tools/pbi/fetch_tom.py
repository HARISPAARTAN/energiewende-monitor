"""Download Microsoft's Tabular Object Model client (NuGet) into build/tom/ for the optional TMDL parse test.

Usage: uv run python tools/pbi/fetch_tom.py   (needs the .NET 8 runtime for the test itself)
build/ is git-ignored; nothing from the package is committed.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

PKG = "microsoft.analysisservices.netcore.retail.amd64"
VERSION = "19.84.1"
URL = f"https://api.nuget.org/v3-flatcontainer/{PKG}/{VERSION}/{PKG}.{VERSION}.nupkg"
OUT = Path(__file__).resolve().parents[2] / "build" / "tom"


def main() -> None:
    with urllib.request.urlopen(URL, timeout=120) as resp:
        data = resp.read()
    OUT.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            parts = name.split("/")
            if len(parts) == 3 and parts[:2] == ["lib", "netcoreapp3.0"] and name.endswith(".dll"):
                (OUT / parts[2]).write_bytes(z.read(name))
                print("extracted", parts[2])


if __name__ == "__main__":
    main()
