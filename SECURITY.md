# Sicherheit

DNSmith nimmt fremde Zugangsdaten entgegen und ruft damit Adressen auf, die der
Nutzer selbst angibt. Beides ist heikel genug, dass Meldungen einen eigenen Weg
verdienen.

## Unterstützte Versionen

Das Projekt ist in einer frühen Fassung. Korrekturen gibt es nur für die
jeweils aktuelle Version auf `main`.

| Version | Unterstützt |
|---|---|
| 0.1.x | ✅ |

## Eine Schwachstelle melden

**Bitte kein öffentliches Issue anlegen.**

Nutze stattdessen [GitHub Security Advisories](https://github.com/duczz/ha-dnsmith/security/advisories/new)
— das öffnet einen privaten Kanal zwischen dir und dem Maintainer.

Hilfreich ist:

- was du erreichen konntest, und mit welchen Schritten
- welche Fassung (Versionsnummer aus dem App-Reiter oder `dnsmith/config.yaml`)
- ob ein bestimmter Anbieter beteiligt ist

Du bekommst innerhalb von 14 Tagen eine Rückmeldung. Wenn du möchtest, wirst du
im Advisory genannt.

## Wogegen DNSmith absichtlich schützt

- **Kein Sprungbrett ins Heimnetz.** Jede vom Nutzer angegebene Adresse wird vor
  dem Aufruf aufgelöst und gegen private, lokale und Loopback-Bereiche geprüft.
  Die geprüfte Adresse wird festgehalten, damit ein zweiter DNS-Aufruf nicht
  doch noch woanders hinzeigt. Weiterleitungen werden nicht verfolgt.
- **Zugangsdaten verlassen die App nicht.** Sie erscheinen in keiner Antwort der
  Oberfläche, in keinem Protokoll — auch nicht in Stacktraces — und sind im
  Export standardmäßig nicht enthalten.
- **Kein offener Port.** Die Oberfläche läuft ausschließlich über Ingress. Es
  gibt kein `host_network`, kein `privileged`, und ein eigenes AppArmor-Profil
  begrenzt den Prozess. Schreibbar sind nur `/config/dnsmith` und `/data`.

## Wogegen DNSmith nicht schützt

- **Dateizugriff auf die Home-Assistant-Instanz.** `secrets.json` liegt
  unverschlüsselt auf der Platte (Rechte 0600), genau wie Home Assistant seine
  eigenen Zugangsdaten ablegt. Die Begründung steht im
  [Handbuch](dnsmith/DOCS.md#warum-sie-nicht-verschlüsselt-sind).
- **Sicherungen.** Mit `backup: hot` sind die Zugangsdaten in
  Home-Assistant-Sicherungen enthalten. Wer eine Sicherung außer Haus gibt,
  sollte die verschlüsselten Sicherungen von Home Assistant verwenden.
- **Wer Zugriff auf die Oberfläche hat**, kann Einträge anlegen und ändern.
  Ingress erbt die Anmeldung von Home Assistant; wer dort angemeldet ist, ist es
  auch hier.

## Beim Melden von Fehlern

Häng keine echten Zugangsdaten an ein Issue. Der Export der Konfiguration
enthält sie standardmäßig nicht — wenn du ihn ausdrücklich mit Zugangsdaten
erzeugst, ist er im Klartext lesbar und gehört nicht in ein öffentliches Issue.
