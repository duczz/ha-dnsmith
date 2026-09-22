#!/usr/bin/env bash
#
# Build the DNSmith app and smoke-test it — the same build Home Assistant's
# Supervisor performs, but on a machine where you can watch it.
#
# Run this in WSL (or any Linux with Docker) from the repository root:
#
#     bash scripts/test-build.sh
#
# It builds the image, starts the container, waits for the hub, checks that
# it came up, that the API answers, and that nothing from the retired Go
# engine survived into the image, then removes everything. Nothing is left
# behind and nothing is published.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ADDON="$REPO/dnsmith"
IMAGE="dnsmith-local-test"
CONTAINER="dnsmith-local-test"
PORT="${DNSMITH_TEST_PORT:-18099}"
WORK="$(mktemp -d)"

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
step()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

failures=0
check() {
  local what="$1"; shift
  if "$@" >/dev/null 2>&1; then
    green "  ok    $what"
  else
    red   "  FEHLT $what"
    failures=$((failures + 1))
  fi
}

# --- prerequisites ----------------------------------------------------------
step "Voraussetzungen"

if ! command -v docker >/dev/null 2>&1; then
  red "Docker ist nicht installiert oder nicht im PATH."
  echo "In WSL: Docker Desktop installieren und unter Settings → Resources →"
  echo "WSL Integration für diese Distribution einschalten."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  red "Docker läuft nicht. Docker Desktop starten und erneut versuchen."
  exit 1
fi
green "  ok    Docker erreichbar"

# The Supervisor picks the base image per architecture from build.yaml. This
# script tests the architecture you are on.
case "$(uname -m)" in
  x86_64)  ARCH=amd64 ;;
  aarch64|arm64) ARCH=aarch64 ;;
  *) red "Nicht unterstützte Architektur: $(uname -m)"; exit 1 ;;
esac

# Only the "<arch>: " prefix is stripped. A greedy "s/.*: *//" would cut at
# the colon inside the image tag and yield "3.12-alpine3.24" as the whole
# image name.
BUILD_FROM="$(sed -n "s|^[[:space:]]*${ARCH}:[[:space:]]*||p" "$ADDON/build.yaml" | head -1)"
if [ -z "$BUILD_FROM" ]; then
  red "Kein build_from für $ARCH in build.yaml gefunden."
  exit 1
fi
green "  ok    Architektur $ARCH, Basis-Image $BUILD_FROM"

# --- build ------------------------------------------------------------------
step "Image bauen (beim ersten Mal einige Minuten)"

if ! docker build \
      --build-arg "BUILD_FROM=$BUILD_FROM" \
      --tag "$IMAGE" \
      --progress plain \
      "$ADDON"; then
  red "Der Build ist fehlgeschlagen. Die letzte Zeile oben sagt, woran."
  exit 1
fi
green "Build erfolgreich"

# --- run --------------------------------------------------------------------
step "Container starten"

mkdir -p "$WORK/config" "$WORK/data"

# The Supervisor always writes this file; bashio reads it in the service
# scripts. Without it the container would fail in a way that only happens
# outside Home Assistant, which would be a misleading test result.
echo '{}' > "$WORK/data/options.json"

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
if ! docker run -d --name "$CONTAINER" \
      -p "127.0.0.1:$PORT:8099" \
      -v "$WORK/config:/config" \
      -v "$WORK/data:/data" \
      "$IMAGE" >/dev/null; then
  red "Der Container liess sich nicht starten."
  exit 1
fi

printf "  warte auf den Hub"
ready=0
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then ready=1; break; fi
  printf "."
  sleep 1
done
echo

if [ "$ready" -ne 1 ]; then
  red "Der Hub hat nicht geantwortet. Protokoll:"
  docker logs "$CONTAINER" 2>&1 | tail -40
  exit 1
fi
green "  ok    Hub antwortet auf Port $PORT"

# --- checks -----------------------------------------------------------------
step "Prüfungen"

check "Oberfläche wird ausgeliefert" \
  curl -fsS "http://127.0.0.1:$PORT/"
check "Provider-Katalog erreichbar" \
  curl -fsS "http://127.0.0.1:$PORT/api/v1/providers"
check "Cloudflare-Formular wird erzeugt" \
  curl -fsS "http://127.0.0.1:$PORT/api/v1/providers/cloudflare"
check "Record-Liste erreichbar" \
  curl -fsS "http://127.0.0.1:$PORT/api/v1/records"

providers="$(curl -fsS "http://127.0.0.1:$PORT/api/v1/providers" 2>/dev/null \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["total"])' 2>/dev/null || echo 0)"
if [ "${providers:-0}" -ge 60 ]; then
  green "  ok    $providers Provider geladen"
else
  red   "  FEHLT nur ${providers:-0} Provider geladen, erwartet mindestens 60"
  failures=$((failures + 1))
fi

# Die alte Go-Engine ist weg - und das muss im gebauten Image auch so sein.
#
# Diese beiden Pruefungen sind bewusst umgedreht worden. Frueher haben sie
# verlangt, dass das Engine-Binary da ist; jetzt verlangen sie, dass es weg
# ist. Der Grund ist ein echter Vorfall: wird der Ordner auf dem HA-Geraet
# ueberkopiert statt ersetzt, ueberlebt der alte s6-Dienst dnsmith-engine im
# Zielordner, landet ueber "COPY rootfs/ /" wieder im Image und startet dort
# alle elf Sekunden neu:
#
#     ./run: line 31: /usr/local/bin/dnsmith-engine: No such file or directory
#     WARNING: DDNS-Engine beendet (Code 127), wird neu gestartet
#
# Das faellt nur im Protokoll auf, und zwar erst auf dem Geraet. Hier faellt
# es beim Bauen auf.
if docker exec "$CONTAINER" sh -c 'command -v dnsmith-engine' >/dev/null 2>&1; then
  red   "  FEHLT Engine-Binary liegt noch im Image - der Ordner wurde ueberkopiert statt ersetzt"
  failures=$((failures + 1))
else
  green "  ok    kein Engine-Binary im Image"
fi

services="$(docker exec "$CONTAINER" \
  sh -c 'ls /etc/s6-overlay/s6-rc.d/user/contents.d 2>/dev/null' 2>/dev/null | tr '\n' ' ')"
if [ "$(printf '%s' "$services" | tr -d ' ')" = "dnsmith-hub" ]; then
  green "  ok    genau ein Dienst startet: dnsmith-hub"
else
  red   "  FEHLT unerwartete Dienste im Image: $services"
  red   "        Erwartet wird nur dnsmith-hub. Alles andere stammt aus einem alten Ordner."
  failures=$((failures + 1))
fi

processes="$(docker exec "$CONTAINER" sh -c 'ps -o args= 2>/dev/null' 2>/dev/null || true)"
if printf '%s' "$processes" | grep -q 'dnsmith-engine'; then
  red   "  FEHLT ein Engine-Prozess laeuft noch"
  failures=$((failures + 1))
else
  green "  ok    kein Engine-Prozess"
fi

# readyz sagt seit dem Umbau etwas anderes: nicht mehr "der zweite Prozess
# lebt", sondern "es ist eine oeffentliche Adresse bekannt". Im Container mit
# Netzzugang ist das ready, ohne degraded - beides ist ein gueltiges Ergebnis,
# nur eine Antwort muss kommen.
ready_body="$(curl -fsS "http://127.0.0.1:$PORT/readyz" 2>/dev/null || true)"
if printf '%s' "$ready_body" | grep -q '"status"'; then
  green "  ok    Bereitschaft gemeldet: $ready_body"
else
  red   "  FEHLT keine Bereitschaftsantwort: $ready_body"
  failures=$((failures + 1))
fi

# --- a real record, end to end ---------------------------------------------
step "Einen Eintrag anlegen (ohne echten Anbieter-Zugriff)"

created="$(curl -fsS -X POST "http://127.0.0.1:$PORT/api/v1/records" \
  -H 'Content-Type: application/json' \
  -d '{"provider_id":"duckdns","domain":"pruefung.duckdns.org","owner":"@",
       "ip_version":"ipv4","label":"Build-Test",
       "values":{"token":"00000000-0000-0000-0000-000000000000"}}' 2>/dev/null || true)"

if printf '%s' "$created" | grep -q '"id"'; then
  green "  ok    Eintrag angelegt"

  if printf '%s' "$created" | grep -q '00000000-0000-0000-0000-000000000000'; then
    red "  FEHLT die Antwort enthält den Token im Klartext"
    failures=$((failures + 1))
  else
    green "  ok    der Token taucht in der Antwort nicht auf"
  fi

  # Es gibt keine Engine-Konfiguration mehr, in die der Token wandern
  # koennte. Er gehoert jetzt genau an eine Stelle: in den Zugangsdaten-
  # Speicher, und sonst nirgends im Dateisystem.
  if docker exec "$CONTAINER" sh -c \
      'grep -q 00000000-0000-0000-0000-000000000000 /config/dnsmith/secrets.json' 2>/dev/null; then
    green "  ok    der Token steht im Zugangsdaten-Speicher (dort gehört er hin)"
  else
    red "  FEHLT der Token wurde nicht gespeichert"
    failures=$((failures + 1))
  fi

  stray="$(docker exec "$CONTAINER" sh -c \
    'grep -rl 00000000-0000-0000-0000-000000000000 /data /config 2>/dev/null \
     | grep -v "^/config/dnsmith/secrets.json$"' 2>/dev/null || true)"
  if [ -n "$stray" ]; then
    red "  FEHLT der Token liegt auch woanders: $stray"
    failures=$((failures + 1))
  else
    green "  ok    der Token liegt nirgends sonst"
  fi

  mode="$(docker exec "$CONTAINER" sh -c \
    'stat -c %a /config/dnsmith/secrets.json 2>/dev/null' 2>/dev/null || true)"
  if [ "$mode" = "600" ]; then
    green "  ok    secrets.json hat Rechte 600"
  else
    red "  FEHLT secrets.json hat Rechte ${mode:-unbekannt}, erwartet 600"
    failures=$((failures + 1))
  fi
else
  red "  FEHLT Eintrag liess sich nicht anlegen: $created"
  failures=$((failures + 1))
fi

# --- verdict ----------------------------------------------------------------
step "Ergebnis"

if [ "$failures" -eq 0 ]; then
  green "Alles in Ordnung. Das Image baut und läuft."
  echo
  echo "Die Oberfläche lässt sich jetzt ansehen — der Container läuft noch,"
  echo "solange dieses Skript läuft. Zum Anschauen stattdessen:"
  echo
  echo "    docker run --rm -p 8099:8099 $IMAGE"
  echo "    # dann http://localhost:8099 öffnen"
  echo
  exit 0
fi

red "$failures Prüfung(en) fehlgeschlagen."
echo
echo "Vollständiges Protokoll des Containers:"
docker logs "$CONTAINER" 2>&1 | tail -60
exit 1
