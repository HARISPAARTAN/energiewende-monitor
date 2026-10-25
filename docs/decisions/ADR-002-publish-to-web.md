# ADR-002: Veröffentlichung über Publish to web im eigenen Mandanten

Datum: 2026-10-25 · Status: angenommen

**Kontext.** Der Bericht soll ohne Anmeldung erreichbar sein. Private Microsoft-Konten können sich nicht am
Power-BI-Dienst anmelden; der Arbeitgeber-Mandant kommt für ein privates Portfolio nicht in Frage.

**Entscheidung.** Eigener Microsoft-Entra-Mandant über ein kostenloses Azure-Konto, Fabric (Free)-Lizenz,
Publish to web aus „Mein Arbeitsbereich“; die Mandanteneinstellung schaltet der Eigentümer selbst frei.

**Folgen.** Keine Row-Level-Security im veröffentlichten Modell (eine Variante ohne Rollen wird per Skript
erzeugt); nur Importmodus; die Daten sind öffentlich (offene Daten, unkritisch); Cache eine Stunde.
