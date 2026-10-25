"""Download Microsoft's ADOMD client for .NET (NuGet) into build/adomd/ for the optional live reconciliation.

Usage: uv run python tools/pbi/fetch_adomd.py   (needs the .NET 8 runtime and `uv sync --group pbi` for the test)
Alternative without this download: DAX Studio (winget install DaxStudio.DaxStudio) brings an ADOMD client that
tools/pbi/reconcile.py finds. build/ is git-ignored; nothing from the package is committed.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

PKG = "microsoft.analysisservices.adomdclient.netcore.retail.amd64"
VERSION = "19.84.1"
URL = f"https://api.nuget.org/v3-flatcontainer/{PKG}/{VERSION}/{PKG}.{VERSION}.nupkg"
OUT = Path(__file__).resolve().parents[2] / "build" / "adomd"


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
