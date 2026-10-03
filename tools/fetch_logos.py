#!/usr/bin/env python3
"""Fetch each provider's own icon into dnsmith/frontend/assets/logos/.

WHERE THE ICONS COME FROM

Every provider has a website, and every website has an icon — that is the
only source that covers all 60 rather than the handful of big brands a
curated icon set carries. So this reads the `website:` of each manifest,
looks at what that page declares as its icon, and takes the best one it
offers.

The websites come from the BRANDS table in tools/manifest_merge.py, and each
was checked against the provider's own site. That check is what makes this
safe to automate: a wrong domain would quietly put an unrelated company's
logo next to a provider's name, and nobody would notice, because a logo that
loads looks correct.

WHY THE FILES ARE NOT COMMITTED

These are third-party marks. Showing one beside the name of the service it
identifies is ordinary nominative use; shipping 60 of them inside an
MIT-licensed repository is a different question, and one this project does
not need to answer. dnsmith/frontend/assets/logos/ is git-ignored, and the
add-on renders initials for every provider whose icon is absent — which is
also what happens on a machine that has never run this script.

Usage:
    python3 tools/fetch_logos.py              fetch what is reachable
    python3 tools/fetch_logos.py --clean      delete fetched icons first
    python3 tools/fetch_logos.py --only duckdns,ipv64

Needs network access to the providers' own sites. The sandbox this project
was largely built in has none, so the result has never been seen here: treat
the first run as the first look.

Only the standard library is used. If Pillow happens to be installed, .ico
files are converted to .png; without it they are kept as .ico, which every
current browser renders anyway.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFESTS = ROOT / "dnsmith" / "providers"
OUT = ROOT / "dnsmith" / "frontend" / "assets" / "logos"

# Some providers answer a bare script with a block page or a 403. A normal
# browser User-Agent is not a trick here — the request is for a public icon
# from a page a browser would load anyway.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
}

TIMEOUT = 15

# What a real icon looks like on the wire. A site that answers a missing
# favicon with its 404 page — and plenty do — returns HTML with status 200,
# so the content type alone is not enough and the magic bytes decide.
MAGIC: list[tuple[bytes, str]] = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\x00\x00\x01\x00", "ico"),
    (b"GIF8", "gif"),
    (b"RIFF", "webp"),  # RIFF....WEBP; checked further below
    (b"\xff\xd8\xff", "jpg"),
]


class IconLinks(HTMLParser):
    """Collects <link rel=...icon...> from a page head."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str, str]] = []  # (rel, href, sizes)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return
        values = {key.lower(): (value or "") for key, value in attrs}
        rel = values.get("rel", "").lower()
        if "icon" not in rel:
            return
        href = values.get("href", "").strip()
        if href:
            self.links.append((rel, href, values.get("sizes", "")))


def get(url: str) -> tuple[bytes, str] | None:
    """Fetch a URL. Returns (body, content_type) or None."""
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            # 2 MB is far more than any icon and stops a redirect to a video
            # from filling the disk.
            return response.read(2_000_000), response.headers.get_content_type()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
        return None


def sniff(body: bytes, content_type: str) -> str | None:
    """Decide the file extension, or None if this is not an image."""
    head = body[:64]
    if b"<svg" in body[:2000].lower() or content_type == "image/svg+xml":
        # An SVG that is really an HTML error page would not contain <svg.
        return "svg" if b"<svg" in body[:2000].lower() else None
    for prefix, extension in MAGIC:
        if head.startswith(prefix):
            if extension == "webp" and b"WEBP" not in head[:16]:
                continue
            return extension
    return None


def score(rel: str, sizes: str, href: str) -> tuple[int, int]:
    """Rank candidate icons: vector first, then the largest raster.

    An apple-touch-icon is ranked highly on purpose. It is required to be a
    decent-sized square PNG, whereas /favicon.ico is often a 16px relic that
    turns to mush on a 34px tile.
    """
    if href.lower().endswith(".svg") or "mask-icon" in rel:
        return (3, 0)

    largest = 0
    for match in re.finditer(r"(\d+)x(\d+)", sizes or ""):
        largest = max(largest, int(match.group(1)))
    if "apple-touch-icon" in rel:
        return (2, largest or 180)
    return (1, largest)


def candidates(site: str) -> list[str]:
    """Icon URLs to try for a site, best first."""
    urls: list[str] = []

    page = get(site)
    if page and page[1] in ("text/html", "application/xhtml+xml"):
        parser = IconLinks()
        try:
            parser.feed(page[0].decode("utf-8", "replace"))
        except Exception:  # a malformed page must not stop the run
            pass
        ranked = sorted(parser.links, key=lambda item: score(*item), reverse=True)
        urls.extend(urllib.parse.urljoin(site, href) for _, href, _ in ranked)

    # The conventional location, which many sites serve without declaring it.
    root = urllib.parse.urlsplit(site)
    urls.append(urllib.parse.urlunsplit((root.scheme, root.netloc, "/favicon.ico", "", "")))

    seen: set[str] = set()
    return [url for url in urls if not (url in seen or seen.add(url))]


def to_png(path: pathlib.Path) -> pathlib.Path:
    """Convert an .ico to .png when Pillow is available; otherwise leave it."""
    if path.suffix != ".ico":
        return path
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError:
        return path
    try:
        with Image.open(path) as image:
            # An .ico holds several sizes; take the largest.
            if getattr(image, "n_frames", 1) > 1:
                sizes = sorted(image.ico.sizes())
                image = image.ico.getimage(sizes[-1])
            target = path.with_suffix(".png")
            image.convert("RGBA").save(target)
        path.unlink()
        return target
    except Exception:
        return path


def manifests(only: set[str] | None) -> list[tuple[str, str]]:
    """(provider id, website) for every manifest that names one."""
    found = []
    for path in sorted(MANIFESTS.glob("*.yaml")):
        provider_id = path.stem
        if only and provider_id not in only:
            continue
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^website:\s*(\S+)\s*$", text, re.MULTILINE)
        if match:
            found.append((provider_id, match.group(1).strip("\"'")))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true",
                    help="delete every fetched icon first - only useful when you are "
                         "sure the run will succeed, because nothing restores them")
    parser.add_argument("--only", help="comma-separated provider ids")
    args = parser.parse_args()

    if args.clean and OUT.is_dir():
        for existing in OUT.iterdir():
            existing.unlink()

    OUT.mkdir(parents=True, exist_ok=True)
    only = {part.strip() for part in args.only.split(",")} if args.only else None

    targets = manifests(only)
    if not targets:
        print("no manifests with a website: — nothing to do", file=sys.stderr)
        return 1

    hits: list[str] = []
    misses: list[str] = []

    for provider_id, site in targets:
        # Fetch first, replace second. The earlier order deleted the existing
        # icon before trying, so a run without network - or a provider that
        # briefly answers with something unusable - wiped the whole directory
        # and left every provider with its initials. Icons are not in anyone's
        # backup of this repository twice, so the loss was real.
        saved = None
        for url in candidates(site):
            fetched = get(url)
            if not fetched:
                continue
            extension = sniff(*fetched)
            if not extension:
                continue
            for existing in OUT.glob(f"{provider_id}.*"):
                existing.unlink()
            saved = OUT / f"{provider_id}.{extension}"
            saved.write_bytes(fetched[0])
            saved = to_png(saved)
            break

        if saved:
            hits.append(f"{provider_id:<14} {saved.name:<20} {saved.stat().st_size:>7} B")
            print(f"  ok   {hits[-1]}")
        else:
            misses.append(provider_id)
            print(f"  --   {provider_id:<14} no usable icon at {site}")

    print()
    print(f"{len(hits)} icons fetched, {len(misses)} providers keep their initials")
    if misses:
        print("  " + ", ".join(misses))
    print()
    print(f"Written to {OUT}")
    print("Rebuild the app so the icons land in the image.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
