<p align="center">
<img src="https://raw.githubusercontent.com/duczz/ha-dnsmith/main/dnsmith/logo.png" width="360" alt="DNSmith">
</p>

Alle deine Dynamic-DNS-Einträge an einer Stelle. Diese Seite erklärt das
Einrichten, woher die IP-Adressen kommen und was zu tun ist, wenn etwas
klemmt.

## Einrichten

1. App installieren und starten.
2. Auf **Öffnen** klicken — die Oberfläche läuft über Ingress, es ist kein
   Port nach außen offen.
3. **+ Anbieter hinzufügen**, Anbieter suchen, Zugangsdaten eintragen.
4. **Verbindung testen**, dann **Eintrag anlegen**.

Es gibt keine YAML-Konfiguration. Alles läuft über die Oberfläche.

## Was DNSmith unterstützt

64 Anbieter sind in DNSmith hinterlegt, alle mit eigenem Formular. Dazu
kommen zwei generische Einträge für alles, was nicht eigens aufgeführt ist:

- **Generisches DynDNS2** für jeden Dienst, der das klassische Protokoll
  spricht — Update-URL, Benutzername, Passwort.
- **Eigener HTTP-Provider** für alles Übrige: Methode, Authentifizierung,
  Parameternamen und Erfolgskriterium sind frei einstellbar.

Damit lässt sich praktisch jeder Anbieter anbinden, auch wenn er nicht in der
Liste steht.

## Woher die IP-Adressen kommen

Normalerweise ermittelt DNSmith beide Adressen selbst über das Internet. Unter
**Einstellungen → Woher die IP-Adressen kommen** lässt sich das je
Adressfamilie ändern:

- **Automatisch** — der Normalfall.
- **Aus einer Home-Assistant-Entität** — für Anschlüsse, bei denen der
  Container die Adresse nicht selbst sehen kann. Bei DS-Lite ist das der
  Regelfall: keine öffentliche IPv4, und oft keine IPv6-Route im Container,
  obwohl die Router-Integration die externe Adresse längst kennt. Die Entität
  muss die Adresse als Zustand enthalten.
- **Feste Adresse** — für Anschlüsse mit fester IP.
- **Nicht verwenden** — diese Familie wird gar nicht aktualisiert.

Liefert eine Entität gerade keinen Wert oder etwas, das keine öffentliche
Adresse ist, lässt DNSmith den Eintrag **unangetastet** und schreibt den Grund
in die Übersicht. Einen Eintrag auf etwas Falsches zu setzen wäre schlimmer,
als ihn kurz veralten zu lassen.

## IPv6

IPv6 ist gleichberechtigt, nicht nachgerüstet. Ein Eintrag kann A, AAAA oder
beides pflegen.

**Wenn keine öffentliche IPv6-Adresse gefunden wird**, liegt das fast immer
daran, dass Docker in Home Assistant kein IPv6 hat. Bei Installationen ab
Mitte 2025 ist es voreingestellt; ältere brauchen einmalig:

```
ha docker options --enable-ipv6=true
```

danach einen Neustart des Hosts. DNSmith zeigt diesen Hinweis auch selbst an,
wenn es die Situation erkennt.

## Was die Oberfläche erklärt, statt es dich suchen zu lassen

- **CGNAT.** Liegt deine IPv4 im Bereich 100.64.0.0/10, teilst du sie dir mit
  anderen Kunden. Der DNS-Eintrag lässt sich aktualisieren, erreichbar wird
  dein Anschluss über IPv4 trotzdem nicht. DNSmith sagt das, statt dich
  stundenlang Ports prüfen zu lassen.
- **DS-Lite.** Keine IPv4, aber IPv6: DNSmith schlägt vor, betroffene Einträge
  auf „Nur IPv6“ umzustellen, statt IPv4-Updates dauerhaft scheitern zu lassen.
- **Fehler mit nächstem Schritt.** Statt „HTTP 401“ steht dort, was abgelehnt
  wurde und was zu prüfen ist. Die Originalmeldung bleibt aufklappbar.

## Zugangsdaten

- liegen getrennt von der Konfiguration in `/config/dnsmith/secrets.json`
  mit Rechten 0600,
- werden von der Oberfläche nie zurückgegeben — ein gespeichertes Feld zeigt
  „gespeichert“, nicht den Wert,
- erscheinen in keinem Log; ein Filter entfernt sie auch aus Fehlermeldungen
  und Stacktraces,
- sind im Export standardmäßig **nicht** enthalten. Ein Export mit
  Zugangsdaten ist im Klartext lesbar — behandle ihn wie ein Passwort.

Für Cloudflare empfiehlt die Oberfläche ausdrücklich ein API-Token mit der
Berechtigung `Zone → DNS → Edit`, beschränkt auf die betroffene Zone, statt
des Global API Key. Der Hinweis steht direkt am Feld.

### Warum sie nicht verschlüsselt sind

`secrets.json` liegt im Klartext auf der Platte. Das ist kein Versehen,
sondern die gleiche Entscheidung, die Home Assistant selbst trifft:

- Add-on-Optionen legt der Supervisor unverschlüsselt in `/data/options.json`
  ab. Der Schema-Typ `password` maskiert das Feld nur in der Oberfläche.
  Einen Secret-Store oder Schlüsseldienst gibt es in der Add-on-API nicht.
- Home Assistant Core speichert sämtliche Integrations-Zugangsdaten im
  Klartext in `/config/.storage/core.config_entries`.

Ein Schlüssel müsste auf demselben Datenträger neben den Daten liegen, damit
DNSmith ohne Zutun starten kann — und DNSmith muss das echte Passwort bei
jeder Aktualisierung an den Anbieter senden. Verschlüsselung wäre also
Verschleierung, kein Schutz. Wer Dateizugriff auf die Instanz hat, hat
ohnehin `secrets.yaml`, Auth-Tokens und alle Integrationen.

Geschützt wird stattdessen alles, was leichter abfließt: Werte erscheinen
nicht in API-Antworten, nicht in Logs und nicht im Export.

### Zugangsdaten im Backup

`backup: hot` bedeutet, dass `secrets.json` in Home-Assistant-Backups
enthalten ist — im Klartext. Das ist gewollt: ohne die Datei wäre ein Restore
unbrauchbar, und das Backup enthält ohnehin `secrets.yaml` und alle
Integrations-Zugangsdaten. Wer ein Backup außer Haus gibt, nutzt die
verschlüsselten Backups von Home Assistant.

## Sicherheit

- kein `host_network`, keine offenen Ports, kein `privileged`
- eigenes AppArmor-Profil; schreibbar sind nur `/config/dnsmith` und `/data`
- kein zweiter Prozess, kein interner Netzwerk-Port
- keine vom Nutzer angegebene URL darf ins lokale Netz zeigen:
  jede aufgelöste Adresse wird geprüft, Weiterleitungen werden nicht verfolgt

## Aufbau

Ein Prozess in einem Container. Was ein Anbieter technisch verlangt, steht als
Daten im jeweiligen Provider-Manifest und nicht in Programmcode; nur Anbieter,
deren API eine Sitzung oder eine Signatur braucht, haben ein eigenes Modul.

Schlägt ein Update fehl, betrifft das nur den einen Eintrag: die Oberfläche
bleibt erreichbar und zeigt den Grund.

Verzeichnisaufbau und Entwicklung stehen in der
[README auf GitHub](https://github.com/duczz/ha-dnsmith#-aufbau).

## Aktualisieren

Den Ordner `dnsmith` auf dem Home-Assistant-Gerät **ersetzen, nicht
überkopieren** — also erst löschen, dann die neue Fassung hineinlegen, und
anschließend die App neu bauen.

Der Grund ist unangenehm konkret: Kopieren überschreibt, was es findet, und
lässt stehen, was in der neuen Fassung fehlt. Eine gelöschte Datei
verschwindet dabei nicht. Sie landet über das Dockerfile wieder im Image und
wird gestartet, obwohl sie längst nicht mehr zum Projekt gehört.

## Fehlersuche

**„Die gespeicherte Konfiguration konnte nicht gelesen werden"** — DNSmith
startet dann trotzdem, zeigt aber keine Einträge und speichert nichts. Die
Datei unter `/config/dnsmith/config.json` bleibt dabei unangetastet; der
Hinweis nennt den Grund. Häufigste Ursachen sind eine von Hand bearbeitete
Datei und eine Sicherung aus einer neueren DNSmith-Fassung. Nach dem
Reparieren die App neu starten.

**Ein Eintrag bleibt auf „noch kein Update"** — DNSmith aktualisiert nur bei
tatsächlicher IP-Änderung. Über **Aktualisieren** lässt sich ein Update
erzwingen.

**Der Anbieter sperrt den Zugang** — meist die Folge wiederholter Updates mit
unveränderter Adresse. Intervall verlängern und warten, bis die Sperre
ausläuft.

## Lizenz

MIT. Hinweise zu Anbieter-Icons und Marken stehen in NOTICE.
