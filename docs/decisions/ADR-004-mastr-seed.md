# ADR-004: Marktstammdatenregister als aggregierter Seed

Datum: 2026-10-25 · Status: angenommen

**Entscheidung.** Der mehrere Gigabyte große MaStR-Gesamtexport wird einmal lokal mit open-mastr geladen und zu
`data/seed/kapazitaet_monat.csv` (Bundesland × Energieträger × Inbetriebnahmemonat) verdichtet. Nur der Seed
liegt im Repository; CI lädt ihn.

**Folgen.** Reproduzierbar ohne Download, nachvollziehbares Extraktionsdatum im Seed, keine Einzelanlagen im Repo.
