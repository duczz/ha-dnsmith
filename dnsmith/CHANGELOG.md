# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden hier festgehalten.

## [Unveröffentlicht]

### Verbessert
- **Die öffentlichen Adressen oben in der Übersicht** brachen auf dem Handy um:
  eine volle IPv6-Adresse passte bei 20 px nicht in eine Zeile. Die Schrift
  wird jetzt kleiner, wenn der Platz nicht reicht (auf einem 375 px breiten
  Bildschirm etwa 13 px, auf breiten Bildschirmen bis 20 px), und die Adresse
  bleibt einzeilig.

## [0.1.3] - 2026-10-23

### Behoben
- **Wechselt ein Anbieter zwischen Störung und Ablehnung**, wie Dynu es bei
  einem Ausfall tat (Zeitüberschreitung, dann „badauth", dann wieder
  Zeitüberschreitung), begann die Wartezeit bei jedem Wechsel von vorn. Der
  Eintrag wurde dann über einen Tag lang alle 5 Minuten angefragt. Störungen
  und Ablehnungen werden jetzt getrennt gezählt und steigen beide weiter; erst
  ein Erfolg, eine Änderung am Eintrag oder ein Neustart der App setzt sie
  zurück. Ein Tippfehler nach einem Ausfall bleibt bei 5 Minuten, denn die
  Ablehnungen fangen bei null an.

- **Der Hinweis bei einer Zeitüberschreitung** riet, das Zeitlimit zu erhöhen.
  Das lässt sich nirgends einstellen. Jetzt steht dort „Der Anbieter hat nicht
  rechtzeitig geantwortet." ohne Handlungsempfehlung.

### Verbessert
- **Die Protokollzeile nennt, wie lange der Versuch gedauert hat**
  („failed after 12.5 s"), außer bei einem unerwarteten Fehler der App. So
  lässt sich ein langsam antwortender Anbieter von einem unterscheiden, der gar
  nicht antwortet.
- **Die Übersicht ist kompakter und der ganze Eintrag klickbar.** Ein Klick auf
  eine beliebige Stelle des Eintrags öffnet ihn, der Knopf „Bearbeiten"
  entfällt; ein Pfeil am Rand zeigt, dass der Eintrag anklickbar ist. Der
  Status steht als Marke hinter dem Namen, dazu ein farbiger Punkt links; die
  Zeile darunter nennt Anbieter, IP-Version, Zeitpunkt, bei einem
  fehlgeschlagenen Eintrag den nächsten Versuch und die aktuellen Adressen.
  Die Zeile wird beim Überfahren hervorgehoben. Die Fehlermeldung hat keinen
  Kasten mehr:
  „Was prüfen?" und „Technische Details" klappen darunter auf. Die Zahl der
  Einträge steht als Marke hinter der Überschrift („2 von 4 fehlerhaft"), die
  eigene Kachel dafür entfällt. **Einschränkung:** Text in der Zeile (etwa die
  Adressen) lässt sich nicht mehr mit der Maus markieren, weil die ganze Zeile
  klickbar ist; Strg+A und Kopieren funktionieren weiter.
- **Formulare etwas kompakter**, damit sie zur Übersicht passen: kleinere
  Abstände (Innenrand der Karten 16 statt 18 px, wie bei Home Assistants
  eigenen Karten) und niedrigere Eingabefelder. Die Knöpfe „Einstellungen
  speichern" und „Mit/Ohne Zugangsdaten exportieren" haben jetzt die Größe der
  Knöpfe in der Übersicht, die Export-Knöpfe sind nicht mehr unterstrichen. Auf
  breiten Bildschirmen stehen die Felder der Einstellungen in zwei Spalten, im
  Formular eines Eintrags die Karten „Adresse" und „Zugangsdaten" (die Auswahl
  des Anmeldeverfahrens und Kontrollkästchen mit Hilfetext nehmen die ganze
  Breite). Die Seite soll beim Wechsel zwischen Übersicht und Einstellungen
  nicht mehr seitlich springen (Platz für die Bildlaufleiste bleibt
  reserviert).
- **Ein gespeichertes Passwort oder ein gespeicherter Schlüssel** zeigt im Feld
  nur noch „Gespeichert — leer lassen, um es zu behalten". Die zusätzliche Zeile
  „•••••••• gespeichert" darunter entfällt, sie sagte dasselbe und blieb auch
  stehen, wenn man einen neuen Wert eintippte.

## [0.1.2] - 2026-10-21

### Geändert
- **Wiederholung nach Fehlern:** Bisher verdoppelte sich die Wartezeit nach
  jedem Fehlschlag bis auf sechs Stunden, gleich welcher Art. Fiel ein
  Anbieter nachts aus, blieb der Eintrag auch nach dessen Rückkehr bis zu
  sechs Stunden veraltet. Jetzt gilt: bei einer Störung (keine Antwort,
  Serverfehler, nicht lesbare Antwort) höchstens 30 Minuten; bei abgelehnten
  Zugangsdaten oder Angaben drei Versuche (sofort, nach 5, nach 10 Minuten),
  danach 30 und 60 Minuten, zuletzt alle zwei Stunden. Ein Wechsel der
  Fehlerart beginnt die Zählung neu.
- **Die Übersicht zeigt bei einem fehlgeschlagenen Eintrag, wann der nächste
  Versuch ansteht.**

### Verbessert
- **Jeder fehlgeschlagene Versuch steht im Protokoll der App**, mit Adresse,
  Anbieter, Fehlercode und der Wartezeit bis zum nächsten Versuch. Bisher
  blieb ein Ausfall über Nacht dort unsichtbar; nachvollziehen ließ er sich nur
  in der Oberfläche, solange die App lief. Der Text des Anbieters steht nicht
  im Protokoll.

## [0.1.1] - 2026-10-07

### Behoben
- **Adresse aus einer Home-Assistant-Entität:** der Zugriff auf
  `http://supervisor/core/api` braucht `homeassistant_api`, die App hatte nur
  `hassio_api` angefordert. Die ungenutzten Rechte `hassio_api` und
  `discovery` sind entfallen.
- **„Angaben prüfen" bei den zehn Anbietern mit eigenem Modul** (Porkbun,
  Hetzner, OVH, Route 53, …) meldete fälschlich „fehlt noch das
  Adapter-Modul".
- **Geänderte Einstellungen eines Eintrags** wurden erst bei der nächsten
  IP-Änderung angewendet, korrigierte Zugangsdaten warteten einen Backoff von
  bis zu sechs Stunden ab. Speichern aktualisiert jetzt sofort, wenn sich Felder
  oder Zugangsdaten geändert haben, und setzt Backoff und Sperre zurück.
- **Ohne bekannte IP-Adresse** wurde der Anbieter trotzdem aufgerufen (der
  eigene HTTP-Provider sendete die Anfrage ohne Adresse), und ein Ausfall der
  IP-Ermittlung verlängerte den Backoff aller Einträge. Jetzt bleibt der
  Eintrag unangetastet, der Grund steht in der Übersicht.
- **Eine kurz nicht ermittelbare Adressfamilie** (etwa IPv6) löste bei
  Doppelstack-Einträgen zwei unnötige Updates aus und landete als
  „vorherige Adresse" in der Historie.
- **Sperren des Anbieters** (`abuse`, `badagent`) wurden von „Aktualisieren"
  und „Alle aktualisieren" übergangen.
- **Derselbe Eintrag konnte zweimal gleichzeitig aktualisiert werden**, etwa
  direkt nach dem Anlegen, wenn gerade ein Durchlauf startete.
- **Die Übersicht blockierte die ganze Oberfläche**, solange die IP-Ermittlung
  lief — sie lief im Event-Loop statt in einem Worker-Thread.
- **Bei unlesbarer Konfiguration** antworteten Änderungen mit einem nackten
  „Internal Server Error" und wurden halb ausgeführt (Eintrag im Speicher,
  Zugangsdaten auf der Platte). Jetzt wird vorher abgelehnt, mit Begründung.
- **Ein per API leer gesendetes Pflicht-Geheimnis** bestand die Prüfung und
  wurde dann gelöscht — der Eintrag scheiterte danach an jedem Update.
- **Eine URL ins lokale Netz** (eigener HTTP-Provider, generisches DynDNS2)
  wurde beim Speichern angenommen und scheiterte erst bei jedem Update; die
  Ablehnung erschien dann als „unbekannter Fehler" mit Stacktrace im Protokoll.
- **Fehlermarker eines Manifests** wurden als Teilzeichenkette gesucht und
  konnten in längeren Wörtern anschlagen; jetzt wie die Erfolgsmarker als Wort.
- **ZoneEdit** meldet jede Ablehnung mit HTTP 200; alles außer drei bekannten
  Texten galt als Erfolg.
- **Ungültige Intervalle** wie „5 min" wurden gespeichert und stillschweigend
  als fünf Minuten ausgeführt; jetzt werden sie mit Hinweis abgelehnt.
- **Die Protokollstufe** ließ sich nirgends einstellen, obwohl die Doku darauf
  verwies.

### Sicherheit
- **Die Oberfläche antwortet nur noch dem Ingress-Gateway.** Bisher konnte
  jede andere App im internen Netz von Home Assistant Port 8099 direkt
  erreichen — ohne Anmeldung, inklusive Export mit allen Zugangsdaten.
  Weiterleitungs-Header werden nicht mehr vertraut.

### Verbessert
- **Ausweichen auf die nächste Adresse:** hat ein Anbieter A- und
  AAAA-Einträge und der Container keine IPv6-Route, wird nach einem
  fehlgeschlagenen Verbindungsaufbau die nächste geprüfte Adresse versucht.
- **User-Agent mit Version** (`DNSmith/0.1.1 (+…)`), wie DynDNS2 und No-IP es
  verlangen.
- **Einträge pausieren:** Schalter „Eintrag aktiv" in der Bearbeitungsansicht.
- **Die Übersicht zeigt die aktuelle Adresse** jedes Eintrags.
- **Optionale Protokollstufe** (`log_level`) im Reiter „Konfiguration".

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
