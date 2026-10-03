# Tests

```bash
bash tests/run.sh
```

unittest, kein pytest: die Suiten sollen auf einem nackten Python laufen.

## Was ohne Installation läuft

Vier der sechs Suiten brauchen nur PyYAML und jsonschema:

- `test_manifests.py` — der Platzhalter-Vertrag und die Eigenschaften, die für
  jedes Provider-Manifest gelten müssen
- `test_native_executor.py` — der deklarative Executor für sich
- `test_provider_requests.py` — was jeder portierte Anbieter tatsächlich
  sendet, samt Endpunkt-Tabelle
- `test_provider_modules.py` — die neun Provider-Module; nur ihre
  Google-Cloud-DNS-Tests brauchen zusätzlich `cryptography` (siehe unten)

Das ist der Teil, der die Provider-Manifeste absichert — also genau der Teil,
den man beim Portieren eines Anbieters braucht.

## Was die Hub-Abhängigkeiten braucht

`test_hub.py` und `test_api.py` fahren den echten Hub hoch und brauchen
dieselben Pakete wie er:

```bash
pip install --break-system-packages -r dnsmith/hub/requirements.txt
```

Ohne sie melden sich beide als *skipped* statt als Fehler. Ein roter Lauf,
der nur bedeutet "hier fehlt ein Paket", sagt nichts über den Code — und wer
ihn oft sieht, gewöhnt sich an rote Läufe.

Geht der Paketindex nicht (in der HA-Umgebung oft der Fall), laufen sie im
gebauten Add-on-Container, wo die Pakete ohnehin liegen.

Die Google-Cloud-DNS-Tests brauchen zusätzlich `cryptography` — sie erzeugen
einen Schlüssel, lassen das Modul damit signieren und prüfen die Signatur
gegen den öffentlichen Schlüssel. Fehlt das Paket, überspringen sie sich.

## Keine echten Zugangsdaten

Kein Test spricht mit einem Anbieter. Die Anfragen gehen an einen
aufzeichnenden Platzhalter, und die Antworten sind Fixtures, die den echten
APIs nachgebildet sind — mit ihren Eigenheiten, nicht geglättet: IDs mal als
Zahl, mal als Zeichenkette, Namen mit und ohne abschließenden Punkt.
