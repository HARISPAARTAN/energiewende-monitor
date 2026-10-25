# Vendored PBIP/PBIR JSON schemas

Origin: https://github.com/microsoft/json-schemas at commit `5e1199a15b80e3d51198fe017b1a6fb9bb0871a6`
(main, 2026-10-23). The files keep their upstream paths below `fabric/`.

Licence: MIT, Copyright (c) Microsoft Corporation. See `LICENSE` in this folder.

Pinned versions:

| Schema | Version |
| --- | --- |
| pbip / pbipProperties | 1.0.0 |
| semanticModel / definitionProperties (`definition.pbism`) | 1.0.0 |
| report / definitionProperties (`definition.pbir`) | 2.0.0 |
| report / definition / report | 3.3.0 |
| report / definition / versionMetadata | 1.0.0 |
| report / definition / pagesMetadata | 1.1.0 |
| report / definition / page | 2.1.0 |
| report / definition / visualContainer | 2.13.0 |
| report / definition / bookmark | 2.1.0 |
| report / definition / bookmarksMetadata | 1.0.0 |
| visualConfiguration (with embedded variant) | 2.8.0 |
| filterConfiguration (with embedded variant) | 1.3.0 |
| semanticQuery | 1.4.0 |
| formattingObjectDefinitions | 1.5.0 |

How to update: change `COMMIT` and `FILES` in `tools/pbi/vendor_schemas.py`, rerun
`uv run python tools/pbi/vendor_schemas.py`, update `tools/pbi/schema_versions.json`, then run
`uv run pytest tests/pbi -m pbi -q`.
