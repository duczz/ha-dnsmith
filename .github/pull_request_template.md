## Was ändert sich?

<!-- Für Nutzer, nicht für den Compiler: was merkt jemand, der DNSmith benutzt? -->

## Warum?

<!-- Bei einem neuen Python-Modul: warum reicht ein Manifest nicht? -->

## Geprüft

- [ ] `python3 tools/manifest_merge.py --check` läuft durch
- [ ] `bash tests/run.sh` ist grün
- [ ] erzeugte Dateien (`dnsmith/providers/*.yaml`, `docs/providers/*.md`) sind
      mit eingecheckt und nicht von Hand bearbeitet
- [ ] Eintrag unter „Unveröffentlicht" in `dnsmith/CHANGELOG.md`, falls sich für Nutzer
      etwas ändert
- [ ] keine echten Zugangsdaten im Diff, in den Tests oder in der Beschreibung

## Gegen ein echtes Konto getestet?

<!-- Optional, aber wertvoll: welcher Anbieter, welcher Record-Typ. -->
