# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier festgehalten.

## [0.1.0] - 2026-10-03

Erste Fassung.

### Hinzugefügt
- **64 Anbieter** — 54 als deklaratives Manifest ohne eine Zeile
  Code, 10 als Python-Modul, wo die API eine Sitzung, eine Signatur oder ein
  Warten auf eine Aktion verlangt (Porkbun, DreamHost, DNSPod, Hetzner,
  Hetzner Cloud, netcup, OVH, Route 53, Aliyun, Google Cloud DNS).
- **Darunter zwei generische Anbieter** — Generisches DynDNS2 und ein eigener
  HTTP-Provider mit frei einstellbarer Methode, Authentifizierung,
  Parameternamen und Erfolgskriterium.
- **Zwei-Schritt-APIs bleiben Daten** — `lookup:` bindet Zone- und Record-IDs,
  bevor `request:` schreibt.
- **Mehrere Betriebsarten je Anbieter** — ein Manifest kann sie mit `modes:`
  beschreiben. Noch nutzt kein Anbieter das.
- **Vier IP-Quellen je Adressfamilie** — automatisch, aus einer
  Home-Assistant-Entität, feste Adresse oder gar nicht. Liefert eine Entität
  keinen brauchbaren Wert, bleibt der Eintrag unangetastet.
- **Eingefügte Update-URLs werden auf ihren Schlüssel reduziert** — wer die
  komplette URL des Anbieters einfügt, bekommt daraus die einzelnen Felder.
- **„Verbindung testen" prüft die Anmeldung**, wo die API einen lesenden Aufruf
  zulässt. Wo es nicht geht, steht das ausdrücklich dabei.
- **Nach dem Anlegen wird sofort aktualisiert**, statt bis zum nächsten
  Intervall zu warten.
- **Wechsel der Anmeldevariante** — beim Speichern werden die Zugangsdaten der
  nicht gewählten Variante gelöscht (Dyn, spdyn, Gigahost).
- **Doppelstack-Einträge** — Anbieter mit einem einzelnen `myip`-Parameter
  bekommen einen Aufruf je Adressfamilie.
- **Signaturen aus der Standardbibliothek** — AWS SigV4 und Aliyun HMAC-SHA1
  mit `hmac` und `hashlib`. Nur Google Cloud DNS erzwingt mit seinem
  RS256-JWT die einzige anbieterbedingte Abhängigkeit (`cryptography`).
- **Prüfung der Platzhalter beim Erzeugen** — jeder `{platzhalter}` im
  `request`-Block muss von einem Formularfeld, einem Laufzeitwert oder einer
  `lookup`-Bindung gedeckt sein, sonst schlägt `tools/manifest_merge.py` fehl.
- **Anbieter-Logos** — 57 der 64 Anbieter zeigen ihr eigenes Icon; für die
  übrigen stehen Initialen. `tools/fetch_logos.py` holt sie nach.
- **Info-Reiter und Changelog-Dialog** in Home Assistant, dazu Logo und Icon
  auf der App-Seite.

### Sicherheit und Robustheit
- Ein Prozess, kein offener Port: die Oberfläche läuft ausschließlich über
  Ingress. Eigenes AppArmor-Profil.
- Jede vom Nutzer angegebene Adresse wird gegen lokale Netze geprüft
  (inklusive Schutz vor DNS-Rebinding); Weiterleitungen werden nicht verfolgt.
- Gespeicherte Zugangsdaten werden aus Logs und Fehlermeldungen herausgefiltert.
- Ein einzelner kaputter Eintrag legt den Scheduler nicht lahm.
- Eine unlesbare Konfiguration beendet den Prozess nicht. Die App startet,
  zeigt den Grund, lässt die Datei unangetastet und speichert nichts.

### Dokumentation
- README mit Funktionsliste, Voraussetzungen, Installation über das
  App-Repository und Doku-Übersicht; je Anbieter eine eigene Seite.
- Erklärt, warum Zugangsdaten unverschlüsselt in `secrets.json` liegen und was
  das für Home-Assistant-Sicherungen bedeutet.
- Dynu: Hinweis, dass manuell gesetzte DNS-Einträge den Abgleich überschreiben
  können. ChangeIP: die Beschreibung nennt, was der Dienst noch bietet
  (bezahltes DDNS für eigene Domains).

### Bekannte Grenzen
- Auf einem echten Gerät erprobt sind bisher die einfachen Anbieter; alles
  andere ist gegen aufgezeichnete Antworten getestet.
- **Hetzner** — die Bestätigung einer Änderung wird über `/zones/actions/{id}`
  abgefragt, den dokumentierten Zonen-Endpunkt. Mit einem eigenen Konto nicht
  erprobt.
- **Dynu** — eine Gruppe wird als `group` gesendet, wie Dynu es dokumentiert.
  Gegen ein echtes Konto mit Gruppe nicht geprüft.
