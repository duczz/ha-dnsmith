# Beitragen

Danke, dass du dir das ansiehst. Dieses Projekt hat eine ungewöhnliche Regel,
die alles andere erklärt:

> **Ein Anbieter ist eine Datei, kein Programm.**

Was ein DDNS-Dienst technisch verlangt, steht als Daten in einem Manifest.
Daraus entstehen das Formular in der Oberfläche, die Anbieterseite in der
Dokumentation und der Aufruf selbst. Neuer Python-Code ist die Ausnahme und
braucht eine Begründung.

## Einen Anbieter hinzufügen

Das ist der häufigste Beitrag und braucht in der Regel keine Zeile Code.

1. **Quelldatei schreiben** — `dnsmith/providers/src/<id>.yaml`. Das ist die
   vollständige Quelle; die Datei `dnsmith/providers/<id>.yaml` wird erzeugt und
   nie von Hand angefasst. Der Aufbau steht in
   [`dnsmith/providers/README.md`](dnsmith/providers/README.md).
2. **Erzeugen und prüfen**
   ```bash
   python3 tools/manifest_merge.py
   ```
   Das prüft gegen `schemas/provider-manifest-v1.json` und erzwingt den
   Platzhalter-Vertrag: jeder `{platzhalter}` im `request`-Block muss von einem
   Formularfeld, einem Laufzeitwert oder einer `lookup`-Bindung gedeckt sein.
3. **Anbieterseite erzeugen**
   ```bash
   python3 tools/gen_docs.py
   ```
4. **Endpunkt eintragen** in `tests/test_provider_requests.py`. Die Tabelle dort
   ist absichtlich eine zweite Kopie von Host und Pfad: wer versehentlich die
   URL im Manifest ändert, bemerkt es dadurch.
5. **Tests laufen lassen**
   ```bash
   bash tests/run.sh
   ```

Braucht der Anbieter zwei Schritte — erst die Zone oder die Record-ID holen,
dann schreiben —, ist das **kein** Grund für ein Modul. Dafür gibt es den
`lookup:`-Block; er bleibt Daten.

## Wann ein Python-Modul gerechtfertigt ist

Nur wenn sich der Vorgang nicht als Abfolge von Aufrufen hinschreiben lässt:
eine Sitzung, die aufgebaut werden muss, eine kryptografische Signatur, ein
Warten auf eine asynchrone Aktion. Dann:

- Modul unter `dnsmith/hub/dnsmith_hub/adapters/providers/` anlegen
- **den Grund in den Kopf des Moduls schreiben.** Ein Modul ohne gültigen Grund
  gehört zurück ins Manifest
- `engine.adapter: python` und `engine.module` in der Quelldatei setzen
- den Fall in `tests/test_provider_modules.py` abdecken

## Abhängigkeiten

Eine neue Abhängigkeit in `dnsmith/hub/requirements.txt` braucht einen Grund,
der über „praktisch" hinausgeht. Route 53 und Aliyun signieren mit `hmac` und
`hashlib` aus der Standardbibliothek; nur Google Cloud DNS erzwingt mit seinem
RS256-JWT die einzige anbieterbedingte Abhängigkeit. Die App läuft auf
Alpine/musl — alles, was sich nicht ohne Übersetzer installieren lässt, macht
den Build spürbar langsamer.

## Tests

```bash
bash tests/run.sh                 # alle Suiten
bash scripts/test-build.sh        # baut das Image und prüft es (Docker/WSL)
```

unittest, kein pytest: die Suiten sollen auf einem nackten Python laufen. Drei
der fünf brauchen nur PyYAML und jsonschema, die beiden übrigen fahren den Hub
hoch und überspringen sich, wenn seine Abhängigkeiten fehlen — siehe
[`tests/README.md`](tests/README.md).

**Kein Test spricht mit einem echten Anbieter.** Wer einen neuen Anbieter gegen
ein echtes Konto geprüft hat, schreibt das gern in die Pull-Request-Beschreibung
— aber nicht in einen Test.

## Commits

Die Historie folgt [Conventional Commits](https://www.conventionalcommits.org/de/):

```
feat(provider): Google Cloud DNS - 60 von 60
fix(ui): "Verbindung testen" tut jetzt etwas
docs: Upstream-Doku-Verweis ueberall entfernen
```

Die Betreffzeile sagt, was sich für den Nutzer ändert, nicht welche Datei
angefasst wurde. Die Sprache im Projekt ist Deutsch für alles, was Nutzer lesen,
und Englisch für Bezeichner im Code.

## Pull Requests

- gegen `main`
- `python3 tools/manifest_merge.py --check` und `bash tests/run.sh` müssen grün
  sein — die Prüfungen in GitHub Actions laufen genau das
- erzeugte Dateien (`dnsmith/providers/*.yaml`, `docs/providers/*.md`) mit
  einchecken, aber nicht von Hand bearbeiten
- einen Eintrag unter „Unveröffentlicht" in [CHANGELOG.md](dnsmith/CHANGELOG.md), wenn
  sich für Nutzer etwas ändert

## Sicherheit

Schwachstellen **nicht** als Issue melden — siehe [SECURITY.md](SECURITY.md).
Und: keine echten Zugangsdaten in Issues, Pull Requests oder Tests.
