# Provider-Manifeste

Ein Manifest beschreibt einen DDNS-Anbieter so vollständig, dass die
Oberfläche sein Formular allein daraus erzeugen kann. Es gibt kein zweites
Verzeichnis, keine Sonderfälle im Frontend und keine Provider-Namen im Code.

## Eine Quelle

Früher hatte ein Manifest zwei Hälften: eine erzeugte und eine von Hand
geschriebene, damals "Overlay" genannt, weil sie über die erzeugte Hälfte
gelegt wurde. Die erzeugte Hälfte ist weg, also ist `src/<id>.yaml` jetzt die
vollständige Quelle und der einzige Ort, an dem jemand etwas ändert.

`tools/manifest_merge.py` prüft die Quelldatei gegen
`schemas/provider-manifest-v1.json` und schreibt `<id>.yaml`. Die erzeugten
Dateien nie von Hand anfassen.

## Wer den Eintrag aktualisiert

`engine.adapter` sagt es:

- **`native`** — DNSmith führt den Aufruf aus, den der `request`-Block
  beschreibt. Kein Code. Das ist der Normalfall.
- **`python`** — der Anbieter braucht mehr als einen Aufruf (Zone suchen,
  dann Record schreiben) oder eine Signatur. `engine.module` nennt das Modul
  unter `hub/dnsmith_hub/adapters/providers/`.
- **`unported`** — DNSmith kennt den Anbieter, kann ihn aber noch nicht
  aktualisieren. Das Formular erscheint, in der Liste steht „noch nicht
  verfügbar". Ein Übergangszustand, kein Dauerzustand.

## Der request-Block

```yaml
engine:
  adapter: native
  protocol: dyndns2
request:
  url: https://api.example.com/nic/update
  auth: {mode: basic, username: "{username}", password: "{password}"}
  params:
    hostname: "{hostname}"
    myip: "{ipv4}"
    myipv6: "{ipv6}"
  success: {vocabulary: dyndns2}
```

`{name}` ist entweder ein Feld dieses Providers oder einer der Werte, die
DNSmith selbst liefert: `ip`, `ipv4`, `ipv6`, `hostname`, `domain`, `owner`,
`zone`. Alles andere lehnt `manifest_merge.py` ab — das ist der Vertrag, der
früher `maps_to` gegen den Go-Code geprüft hat.

Ein Parameter, dessen Wert leer bleibt, wird weggelassen und nicht leer
gesendet: mehrere Anbieter lesen `myipv6=` als „AAAA-Record löschen".

```
src/cloudflare.yaml ──manifest_merge.py──> providers/cloudflare.yaml
                                │
                                └────────> docs/providers/cloudflare.md
```

**`<id>.yaml` niemals von Hand bearbeiten.** Die Dateien werden überschrieben,
und `manifest_merge.py --check` schlägt in CI fehl, wenn es doch jemand tut.

## Eine Quelldatei schreiben

```yaml
name: Netcup
description: Deutscher Hoster; DNS-Updates über die CCP-API.
website: https://www.netcup.de
categories: [dns_provider, german]
popular: false

fields:
  - id: customer_number
    type: text
    label: Kundennummer
    help: Steht im Customer Control Panel oben neben deinem Namen.
```

Die Reihenfolge der Felder in der Quelldatei bestimmt die Reihenfolge im
Formular.

Drei Dinge gehören **nicht** in die Quelldatei, weil sie beim Erzeugen
gesetzt werden: `schema_version`, `id` und `generated`.

## Sich ausschließende Zugangsdaten

Manche Anbieter akzeptieren mehrere Anmeldeverfahren, die sich gegenseitig
ausschließen. Cloudflare ist der klarste Fall: API-Token **oder** E-Mail plus
Global Key **oder** User Service Key. Die Upstream-Dokumentation listet alle
vier Felder unter „Compulsory parameters" — wörtlich genommen ergibt das ein
Formular, das niemand ausfüllen kann.

Dafür gibt es `auth.one_of`:

```yaml
auth:
  one_of:
    - id: api_token
      label: API-Token
      recommended: true
      fields: [token]
      hint: >
        Token mit der Berechtigung Zone → DNS → Edit, beschränkt auf genau
        diese Zone.
    - id: global_key
      label: E-Mail und Global API Key
      deprecated: true
      fields: [email, key]
```

Das Merge-Werkzeug entfernt `required` von allen Feldern, die zu einer
Variante gehören — die Variante macht sie erforderlich, nicht das Feld für
sich. Die UI zeigt zuerst die Auswahl, dann nur deren Felder.

Der `hint` ist der Ort für Berechtigungsempfehlungen. Er steht direkt am Feld,
nicht in einer Dokumentation, die niemand liest.

## Abhängige Felder

```yaml
  - id: app_key
    type: secret
    label: Application Key
    when: { field: mode, equals: api }
```

OVH braucht das: sein `mode` entscheidet, welche Zugangsdaten überhaupt
gelten.

## Feldtypen

| Typ | Darstellung |
|---|---|
| `text` | einzeiliges Eingabefeld |
| `secret` | maskiert, wird nie zurückgegeben |
| `multiline_secret` | maskiertes Textfeld, für JSON-Zugangsdaten wie bei GCP |
| `email`, `hostname`, `domain`, `url` | Text mit passender Validierung |
| `integer` | Zahl, optional mit `validate.min` und `validate.max` |
| `boolean` | Schalter |
| `select` | Auswahl, braucht `options` |
| `duration` | Zeitangabe wie `5m` |
| `ipv6_prefix` | IPv6-Präfix wie `::1/64` |

Ob ein generiertes Feld als `secret` gilt, entscheidet eine exakte
Namensliste, keine Teilzeichenkette: `access_key_id` ist eine Kennung und
bleibt sichtbar, damit man prüfen kann, was man eingefügt hat.

## Warum `maps_to` existiert

```yaml
  - id: token
    maps_to: api_token
```

`id` ist der Name, unter dem DNSmith den Wert speichert — er muss stabil
bleiben, sonst verlieren gespeicherte Records ihren Wert. `maps_to` ist
dagegen nur noch für Altlasten da; im `request`-Block steht ohnehin der Name,
den der Anbieter sehen soll.

## Aktualisieren

```bash
python3 tools/manifest_merge.py
python3 tools/gen_docs.py
python3 -m unittest discover -s tests -t .
```

Die Contract-Tests sind der eigentliche Schutz. Sie prüfen, dass jeder
Platzhalter im `request`-Block von einem Feld oder einem Laufzeitwert gedeckt
ist. Fehlt einer, schlägt der Test fehl — statt dass der Aufruf mit einem
leeren Zugangsdatum hinausgeht und die Updates betroffener Benutzer
stillschweigend aufhören zu funktionieren.
