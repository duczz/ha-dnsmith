# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier festgehalten.

Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
die Versionierung an [Semantic Versioning](https://semver.org/lang/de/).
Die Versionsnummer steht in [`config.yaml`](config.yaml); der
Supervisor bietet ein Update an, sobald sie sich erhöht.

## Geplant

- **RFC 2136 („nsupdate")** für selbst betriebene DNS-Server (BIND, PowerDNS,
  Knot, Technitium). Entschieden, aber noch nicht gebaut — Begründung und
  Bedingungen stehen in `decisions.md` im Brain.
- **Die Anmeldevariante am Eintrag speichern.** Wer einen Cloudflare-Eintrag
  mit „E-Mail und Global API Key" bearbeitet, bekommt im Formular die
  Standardvariante vorgewählt und muss sie von Hand zurückstellen.

## [0.1.0] - unveröffentlicht

Erste Fassung. Im Lauf dieser Version ist die frühere Go-Engine entfallen;
an ihre Stelle trat eine eigene, datengetriebene Anbieterschicht in Python.

### Hinzugefügt
- **64 Anbieter** — 54 als deklaratives Manifest ohne eine Zeile
  Code, 10 als Python-Modul, wo die API eine Sitzung, eine Signatur oder ein
  Warten auf eine Aktion verlangt (Porkbun, DreamHost, DNSPod, Hetzner,
  netcup, OVH, Route 53, Aliyun, Google Cloud DNS).
- **Zwei generische Anbieter** — Generisches DynDNS2 und ein eigener
  HTTP-Provider mit frei einstellbarer Methode, Authentifizierung,
  Parameternamen und Erfolgskriterium.
- **Zwei-Schritt-APIs bleiben Daten** — `lookup:` bindet Zone- und Record-IDs,
  bevor `request:` schreibt. Das ersetzt rund achtzehn fast gleiche Module.
- **Vier IP-Quellen je Adressfamilie** — automatisch, aus einer
  Home-Assistant-Entität, feste Adresse oder gar nicht. Liefert eine Entität
  keinen brauchbaren Wert, bleibt der Eintrag unangetastet.
- **Eingefügte Update-URLs werden auf ihren Schlüssel reduziert** — wer die
  komplette URL des Anbieters einfügt, bekommt daraus die einzelnen Felder.
- **Signaturen aus der Standardbibliothek** — AWS SigV4 und Aliyun HMAC-SHA1
  mit `hmac` und `hashlib`. Nur Google Cloud DNS erzwingt mit seinem
  RS256-JWT die einzige anbieterbedingte Abhängigkeit (`cryptography`).
- **Prüfung der Platzhalter beim Erzeugen** — jeder `{platzhalter}` im
  `request`-Block muss von einem Formularfeld, einem Laufzeitwert oder einer
  `lookup`-Bindung gedeckt sein, sonst schlägt `tools/manifest_merge.py` fehl.
- Eigenes AppArmor-Profil, Prüfung jeder vom Nutzer angegebenen Adresse gegen
  lokale Netze (inklusive Schutz vor DNS-Rebinding), keine Verfolgung von
  Weiterleitungen.
- **Anbieter-Logos** — 57 der 64 Anbieter zeigen ihr eigenes Icon; für die
  übrigen stehen Initialen. `tools/fetch_logos.py` holt sie nach.
- **Info-Reiter und Changelog-Dialog** in Home Assistant, dazu Logo und Icon
  auf der App-Seite.

### Geändert
- **Die Go-Engine ist entfallen.** Die App besteht aus einem Prozess; das Image
  enthält keinen übersetzten Fremdcode mehr, und der Build schlägt fehl, wenn
  Reste davon auftauchen.
- **„Verbindung testen" prüft die Anmeldung**, wo die API einen lesenden Aufruf
  zulässt — vorher wurde nur geprüft, ob die Adresse erreichbar ist. Wo es
  nicht geht, steht das ausdrücklich dabei.
- **Nach dem Anlegen wird sofort aktualisiert**, statt bis zum nächsten
  Intervall zu warten.
- Konfigurationsformat 2: die nie benutzten Felder `resolver`, `notifications`,
  `http_providers`, `dns_providers`, `prefix_source` und `suffix` werden beim
  Laden entfernt. Bestehende Konfigurationen wandern automatisch mit.

### Dokumentation
- README nach GitHub-Üblichkeiten aufgebaut: Badges, Funktionsliste,
  Voraussetzungen, Installation über das App-Repository, Doku-Übersicht,
  Hilfe-Abschnitt.
- `CONTRIBUTING.md`, `SECURITY.md` und dieses Changelog ergänzt, dazu Issue-
  und Pull-Request-Vorlagen, Dependabot und ein Linter-Lauf für
  `config.yaml`/`build.yaml`.
- Erklärt, warum Zugangsdaten unverschlüsselt in `secrets.json` liegen und was
  das für Home-Assistant-Sicherungen bedeutet.

### Behoben

Ein Durchgang über den gesamten Quelltext hat fünf Fehler gefunden, die alle
still versagten — niemand hätte etwas bemerkt, bis es zu spät war:

- **Zugangsdaten wurden in keinem Logeintrag maskiert.** Der Filter hing an
  einem Elternlogger; Python fragt bei Weiterleitung nur die Handler, nie
  deren Filter. Dazu protokollierte httpx jede Anfrage samt vollständiger URL,
  in der bei mehreren Anbietern der Token steht.
- **Ein fehlgeschlagenes Update konnte als Erfolg gelten.** Der HTTP-Status
  wurde nicht geprüft, sobald ein Manifest eine Body-Regel trug, und die
  Bestätigung wurde als Teilstring gesucht — „Invalid token" enthält „ok".
- **Ein einziger kaputter Eintrag legte den Scheduler lahm.** Eine Ausnahme,
  die kein `AdapterError` war — etwa ein DNS-Aussetzer — beendete den ganzen
  Durchlauf, und der Eintrag blieb für immer fällig.
- **Die Abklingzeit war wirkungslos.** Der Zeitpunkt des letzten
  Schreibvorgangs wurde gelesen, aber nie gesetzt.
- **Löschen konnte Zugangsdaten verwaisen lassen**, und der Verbindungstest
  übernahm die gespeicherten Daten eines beliebigen Eintrags, ohne zu prüfen,
  ob er zum angefragten Anbieter gehört.

Weiteres:
- **Eine unlesbare Konfiguration beendet den Prozess nicht mehr.** Die App
  startet, zeigt den Grund an, lässt die Datei unangetastet und speichert
  nichts — vorher konnten dabei alle Zugangsdaten als verwaist gelöscht werden.
- **Doppelstack-Einträge wurden nur halb aktualisiert.** Anbieter mit einem
  einzelnen `myip`-Parameter bekommen jetzt einen Aufruf je Adressfamilie.
- **Typen im JSON-Rumpf blieben erhalten.** TTL ging als `"300"` statt `300`
  hinaus, und Cloudflares `proxied` als `"false"` — eine Zeichenkette, die in
  vielen Sprachen wahr ist.
- **Aliyun aktualisierte den falschen Eintrag.** `RRKeyWord` ist eine Suche,
  kein Filter; die Auswahl vergleicht jetzt Name und Typ genau.
- **Hetzner** spricht die Cloud-DNS-API statt der abgelegten Schnittstelle.
- **OpenDNS-Dauerupdates und Dubletten im Verlauf** behoben.
