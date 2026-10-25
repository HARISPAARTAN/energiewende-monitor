# Visual templates

Origin: https://github.com/microsoft/fabric-toolbox at commit `29264d36e5fdf483498faf97013ecf4dd0bd8a10`
(main, 2026-10-09). Three report folders were used (paths below `monitoring/`):

- `fabric-unified-admin-monitoring/src/FUAM_Core_Report.Report/definition/pages/` (FUAM)
- `fabric-cost-analysis/src/FCA_Core_Report.Report/definition/pages/` (FCA)
- `query-capacity-correlation/Template/Query Capacity Correlation.Report/` (QCC)

Source of each template (`SOURCES` in `tools/pbi/capture_templates.py`):

| Template | Source |
| --- | --- |
| `card` | FCA `df46552c6a3e07628f04/visuals/868e1c7e98e906177c84` |
| `lineChart` | QCC `definition/pages/dec6ca10089791a9a8a4/visuals/b3019a58595c63487980` |
| `stackedAreaChart` | FUAM `688e721a1b14ddc8d3bf/visuals/c3a103baf973b1389307` |
| `columnChart` | FUAM `b5d594eb912b41d58e08/visuals/b578a3168b812e4f8693` |
| `clusteredBarChart` | FUAM `8d39b414abb490008ab4/visuals/3a2389c850b5dd6638de` |
| `clusteredColumnChart` | FCA `ce90cb875cce385c58bf/visuals/6caac5df45468d874b6d` |
| `pivotTable` | FUAM `5e229a1d829e52ca29a0/visuals/a2f6b34ec53adbd98095` |
| `tableEx` | FCA `9e15d3671d9a3010bd29/visuals/fc0a449316d8eba4da1d` |
| `slicer` | FCA `85ebcf71ac1b1f9c1ef2/visuals/baacb70ed1417be32b31` |
| `scatterChart` | QCC `definition/pages/60a8309d95b9f8104e53/visuals/24bf8d23ffd9064054ee` |
| `textbox` | FCA `df46552c6a3e07628f04/visuals/05a172cf755d9e5899f4` |

The base theme `basetheme/Fluent2-CY26SU08.json` comes from the QCC report
(`StaticResources/SharedResources/BaseThemes/`). `bookmark.json` is built from the pinned bookmark schema.

Licence: MIT, Copyright (c) Microsoft Corporation. See `LICENSE-fabric-toolbox.txt` in this folder; the copyright
notice is kept.

Removed from each sample: query state, filters (`filterConfig`), formatting objects scoped by a selector, the
title and any data values (field references).

Internal visual type names: `columnChart` is the stacked column chart, `pivotTable` is the matrix visual.
