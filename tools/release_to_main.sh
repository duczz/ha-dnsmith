#!/usr/bin/env bash
# Bringt den Release-Commit eines Tags auf main. Aufruf im Checkout des Tags
# (Tiefe 2: der Release-Commit und sein Elternteil), `origin` zeigt auf das Repo:
#
#     bash tools/release_to_main.sh v0.1.6
#
# Der Release-Commit R entsteht im Workflow "Release vorbereiten" auf dem Zweig
# release/X.Y.Z. Er setzt Version und datiert den CHANGELOG; der Tag zeigt auf
# ihn. Home Assistant liest main, also sieht es R erst, wenn dieses Skript R auf
# main bringt - und das darf erst laufen, wenn beide Images auf ghcr.io liegen.
#
# main darf seit R^ (dem Stand, aus dem R entstand) weitergelaufen sein (Doku,
# Tests, Code für das nächste Release: der Supervisor zieht ohnehin das Image),
# nur nicht im CHANGELOG und in config.yaml. Den CHANGELOG zeigt HA von main, und
# "Unveröffentlicht" bekäme sonst Einträge datiert, die nicht im Image stecken.
# config.yaml liest der Supervisor ganz von main: eine neue Architektur oder
# Option ginge sonst mit dem alten Image live.
#
#   main == R^            R wird per Fast-Forward main (Tag und main gleich)
#   main weitergelaufen   R wird auf main gepickt (gleicher Inhalt und Datum)
#   CHANGELOG/config.yaml auf main geändert, oder main schon höher: Abbruch
#   main steht schon auf der Version: nichts zu tun
#
# Danach wird der Zweig release/X.Y.Z gelöscht, wenn er noch auf R zeigt.
set -euo pipefail

tag="${1:?Aufruf: release_to_main.sh vX.Y.Z}"
version="${tag#v}"
release="$(git rev-parse HEAD)"

if ! base="$(git rev-parse --verify -q "${release}^")"; then
  echo "::error::Der Elternteil von ${tag} fehlt (Checkout mit fetch-depth: 2?)"
  exit 1
fi

git fetch --depth=1 origin +refs/heads/main:refs/remotes/origin/main
main="$(git rev-parse origin/main)"

main_config="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/main-config.yaml"
git show origin/main:dnsmith/config.yaml > "${main_config}"

if grep -qx "version: \"${version}\"" "${main_config}"; then
  echo "main steht schon auf ${version}"
  exit 0
fi

if ! git diff --quiet "${base}" "${main}" -- dnsmith/CHANGELOG.md dnsmith/config.yaml; then
  echo "::error::CHANGELOG oder config.yaml auf main haben sich seit dem Stand geändert, aus dem ${tag} entstand. Die Version kommt nicht automatisch auf main: prüfen, was dazukam, dann von Hand den Release-Commit ${release} auf main bringen (cherry-pick), pushen."
  exit 1
fi

# Der Tag liegt auf R: R trägt die Version, main muss kleiner sein.
python3 tools/set_version.py "${tag}" --verify --against "${main_config}"

if [ "${main}" = "${base}" ]; then
  git push origin "${release}:refs/heads/main"
else
  git config user.name "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  git checkout -q "${main}"
  git cherry-pick "${release}"
  git push origin HEAD:refs/heads/main
fi

branch="release/${version}"
on_remote="$(git ls-remote --heads origin "${branch}" | cut -f1)"
if [ "${on_remote}" = "${release}" ]; then
  git push origin --delete "${branch}" || echo "::warning::Zweig ${branch} nicht gelöscht"
fi
