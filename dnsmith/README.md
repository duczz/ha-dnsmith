<p align="center">
<img src="https://raw.githubusercontent.com/duczz/ha-dnsmith/main/dnsmith/logo.png" width="360" alt="DNSmith">
</p>

**Dynamic DNS für 64 Anbieter — zentral in Home Assistant, ohne YAML.**

Dein Anschluss bekommt regelmäßig eine neue IP-Adresse, deine Domains sollen
trotzdem auf ihn zeigen. Statt pro Anbieter ein eigenes Werkzeug zu pflegen,
verwaltet DNSmith alle Einträge an einer Stelle: Anbieter aus der Liste wählen,
Zugangsdaten eintragen, fertig.

## Was du bekommst

- **64 Anbieter** — von DuckDNS und Dynu bis Cloudflare, Route 53 und Hetzner.
  Dazu ein generischer DynDNS2-Eintrag und ein frei konfigurierbarer
  HTTP-Provider für alles, was nicht in der Liste steht.
- **IPv4 und IPv6 gleichberechtigt** — ein Eintrag pflegt A, AAAA oder beides.
- **Vier Quellen für die IP-Adresse**, je Adressfamilie einstellbar: automatisch
  übers Internet, aus einer Home-Assistant-Entität (der Regelfall bei DS-Lite),
  feste Adresse, oder gar nicht.
- **Klartext statt Fehlercodes** — bei CGNAT oder DS-Lite sagt dir die
  Oberfläche, warum dein Anschluss trotz erfolgreichem Update nicht erreichbar
  ist. Statt „HTTP 401" steht dort, was abgelehnt wurde und was zu prüfen ist.
- **Schonend zum Anbieter** — aktualisiert nur bei echter IP-Änderung, mit
  Abklingzeit und Backoff. Sperren werden erkannt und abgewartet.

## Loslegen

1. **Starten**, dann **Öffnen** — die Oberfläche erscheint in der Seitenleiste
2. **+ Anbieter hinzufügen**, Zugangsdaten eintragen
3. **Verbindung testen**, dann **Eintrag anlegen**

Es gibt keine Konfiguration im Reiter nebenan und keine YAML-Datei. Alles läuft
über die Oberfläche.

## Gut zu wissen

- Die Oberfläche ist nur über Home Assistant erreichbar (Ingress). Es wird kein
  Port nach außen geöffnet.
- Zugangsdaten liegen getrennt von der Konfiguration, erscheinen in keinem
  Protokoll und sind im Export standardmäßig nicht enthalten.
- Findet DNSmith keine öffentliche IPv6-Adresse, liegt das fast immer an
  fehlendem IPv6 in Docker. Die Oberfläche zeigt dann selbst, was zu tun ist.

**Alles Weitere steht im Reiter „Dokumentation"** — Einrichten Schritt für
Schritt, IP-Quellen, IPv6, Zugangsdaten und Fehlersuche.

MIT-Lizenz.
