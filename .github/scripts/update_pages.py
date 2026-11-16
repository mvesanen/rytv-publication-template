"""Place one publication on the Pages tree and refresh the catalog.

A release is copied to versions/<tag> and left there. The dev branch replaces
only the dev/ directory. The site root is a catalog, so a new publication
does not remove older ones.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Update the GitHub Pages tree.")
    parser.add_argument("site", type=Path)
    parser.add_argument("artefact", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dev", action="store_true")
    group.add_argument("--release", metavar="TAG")
    args = parser.parse_args(argv)
    target = "dev" if args.dev else version_folder(args.release)
    publish(args.site, args.artefact, target)


def version_folder(tag: str) -> str:
    name = tag[1:] if tag.startswith("v") and len(tag) > 1 and tag[1].isdigit() else tag
    if not name or name in {".", ".."} or any(character in name for character in "\\/"):
        raise SystemExit(f"release tag cannot be a Pages path: {tag}")
    return name


def publish(site: Path, artefact: Path, target: str) -> None:
    if not artefact.is_dir():
        raise SystemExit(f"missing artefact {artefact}")
    destination = site / "dev" if target == "dev" else site / "versions" / target
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(artefact, destination)
    (site / ".nojekyll").write_text("", encoding="utf-8")
    (site / "index.html").write_text(catalog(site), encoding="utf-8")
    print(f"pages target {destination.relative_to(site).as_posix()}")


def catalog(site: Path) -> str:
    versions = []
    version_root = site / "versions"
    if version_root.is_dir():
        for path in version_root.iterdir():
            if path.is_dir():
                versions.append(path.name)
    versions.sort(key=version_key, reverse=True)
    title = publication_title(site / "dev")
    if versions:
        title = publication_title(version_root / versions[0]) or title
    title = title or "RYTV-julkaisu"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="fi">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"  <title>{html.escape(title)}</title>\n"
        "  <style>\n"
        "    body { font-family: sans-serif; line-height: 1.5; max-width: 40rem; margin: 2rem auto; padding: 0 1rem; }\n"
        "    a { color: #0b3a66; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{html.escape(title)}</h1>\n"
        "  <p>Jokainen GitHub Release jää omalle polulleen. Juuri on luettelo, uusin ensin.</p>\n"
        f"{latest_section(site, versions)}\n"
        f"{version_list(site, versions)}\n"
        f"{dev_section(site)}\n"
        "</body>\n"
        "</html>\n"
    )


def latest_section(site: Path, versions: list[str]) -> str:
    if not versions:
        return "  <h2>Uusin julkaisu</h2>\n  <p>Ei vielä julkaistuja versioita.</p>\n"
    name = versions[0]
    return (
        "  <h2>Uusin julkaisu</h2>\n"
        f"  <p>{links(name, site / 'versions' / name)}</p>\n"
    )


def version_list(site: Path, versions: list[str]) -> str:
    if not versions:
        return ""
    items = "\n".join(
        f"    <li>{links(name, site / 'versions' / name)}</li>" for name in versions
    )
    return f"  <h2>Kaikki versiot</h2>\n  <ul>\n{items}\n  </ul>\n"


def dev_section(site: Path) -> str:
    publication = site / "dev"
    if (publication / "html" / "index.html").is_file():
        body = f"  <p>{links('dev', publication)}</p>\n"
    else:
        body = "  <p>dev-haaraa ei ole vielä julkaistu.</p>\n"
    return "  <h2>Kehitysversio</h2>\n" + body


def links(name: str, publication: Path) -> str:
    if publication.parent.name == "versions":
        prefix = f"versions/{publication.name}"
    else:
        prefix = publication.name
    label = html.escape(name)
    parts = [f"<strong>{label}</strong>", f'<a href="{prefix}/html/index.html">HTML</a>', f'<a href="{prefix}/publication.pdf">PDF</a>']
    for relative in machine_files(publication):
        filename = Path(relative).name
        parts.append(
            f'<a href="{prefix}/machine-readable/{html.escape(relative, quote=True)}">{html.escape(filename)}</a>'
        )
    return " · ".join(parts)


def machine_files(publication: Path) -> list[str]:
    index = publication / "publication-index.json"
    if not index.is_file():
        return []
    try:
        files = json.loads(index.read_text(encoding="utf-8")).get("machineReadable", [])
    except json.JSONDecodeError:
        return []
    return [str(item) for item in files]


def publication_title(publication: Path) -> str:
    index = publication / "publication-index.json"
    if not index.is_file():
        return ""
    try:
        return str(json.loads(index.read_text(encoding="utf-8")).get("title", ""))
    except json.JSONDecodeError:
        return ""


def version_key(name: str) -> tuple:
    pieces = []
    for piece in name.replace("-", ".").split("."):
        pieces.append((0, int(piece)) if piece.isdigit() else (1, piece))
    return tuple(pieces)


if __name__ == "__main__":
    main()
