# ADR-001: SQL Server 2022 Developer als Speicher

Datum: 2026-10-25 · Status: angenommen

**Kontext.** Das Star-Schema braucht eine relationale Datenbank, die Power BI nativ anbindet und deren Dialekt
deutsche Microsoft-Stack-Arbeitgeber erwarten.

**Entscheidung.** SQL Server 2022 Developer Edition im Docker-Container (`mcr.microsoft.com/mssql/server:2022-latest`),
Zugriff über pyodbc und ODBC Driver 18. Derselbe Container läuft in GitHub Actions.

**Folgen.** T-SQL in Ladeskripten und Views; `AT TIME ZONE` wird nicht benötigt, weil die Ortszeit-Schlüssel in
Python entstehen. PostgreSQL wäre leichter, aber ohne T-SQL-Nachweis.
