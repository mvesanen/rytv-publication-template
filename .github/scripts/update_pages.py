"""Place one publication on the Pages tree and refresh the catalog.

A release is copied to versions/<tag> and left there. The dev branch replaces
only the dev/ directory. The site root is a catalog, so a new publication
does not remove older ones.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Update the GitHub Pages tree.")
    parser.add_argument("site", type=Path)
    parser.add_argument("artefact", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dev", action="store_true")
    group.add_argument("--release", metavar="TAG")
    parser.add_argument("--source", type=Path, help="Git checkout whose latest commit is shown on the dev preview")
    parser.add_argument("--repository", help="GitHub owner/name used to link the commit")
    args = parser.parse_args(argv)
    target = "dev" if args.dev else version_folder(args.release)
    revision = read_commit(args.source, args.repository) if args.dev and args.source else None
    publish(args.site, args.artefact, target, revision)


def version_folder(tag: str) -> str:
    name = tag[1:] if tag.startswith("v") and len(tag) > 1 and tag[1].isdigit() else tag
    if not name or name in {".", ".."} or any(character in name for character in "\\/"):
        raise SystemExit(f"release tag cannot be a Pages path: {tag}")
    return name


def publish(site: Path, artefact: Path, target: str, revision: dict | None = None) -> None:
    if not artefact.is_dir():
        raise SystemExit(f"missing artefact {artefact}")
    destination = site / "dev" if target == "dev" else site / "versions" / target
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(artefact, destination)
    if target == "dev" and revision is not None:
        (destination / "revision.json").write_text(
            json.dumps(revision, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        html_path = destination / "html" / "index.html"
        if html_path.is_file():
            stamp_dev_html(html_path, revision)
    (site / ".nojekyll").write_text("", encoding="utf-8")
    (site / "index.html").write_text(catalog(site), encoding="utf-8")
    print(f"pages target {destination.relative_to(site).as_posix()}")


def read_commit(source: Path, repository: str | None) -> dict:
    result = subprocess.run(
        ["git", "-C", str(source), "log", "-1", "--format=%H%n%ai%n%s"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SystemExit(f"could not read the latest commit in {source}: {detail}")
    commit_hash, commit_time, message = (result.stdout.splitlines() + ["", "", ""])[:3]
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit_hash):
        raise SystemExit(f"unexpected commit hash: {commit_hash}")
    revision = {
        "hash": commit_hash,
        "short": commit_hash[:7],
        "time": display_time(commit_time),
        "message": message or "(ei kommenttia)",
    }
    if repository and re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        revision["url"] = f"https://github.com/{repository}/commit/{commit_hash}"
    return revision


def display_time(raw: str) -> str:
    parts = raw.split()
    if len(parts) >= 2 and parts[1].count(":") == 2:
        minute = parts[1].rsplit(":", 1)[0]
        zone = " ".join(parts[2:])
        return f"{parts[0]} {minute}" + (f" {zone}" if zone else "")
    return raw


def stamp_dev_html(html_path: Path, revision: dict) -> None:
    note = f'<p class="rytv-revision">{revision_text(revision)}</p>\n'
    text = html_path.read_text(encoding="utf-8")
    match = re.search(r"<body[^>]*>", text)
    if match is None:
        html_path.write_text(note + text, encoding="utf-8")
        return
    insert_at = match.end()
    html_path.write_text(text[:insert_at] + "\n" + note + text[insert_at:], encoding="utf-8")


def revision_text(revision: dict) -> str:
    short = html.escape(str(revision.get("short", "")))
    when = html.escape(str(revision.get("time", "")))
    message = html.escape(str(revision.get("message", "")))
    hash_html = f"<code>{short}</code>"
    url = str(revision.get("url", ""))
    if url.startswith("https://github.com/") and " " not in url:
        hash_html = f'<a href="{html.escape(url, quote=True)}">{hash_html}</a>'
    return f"{hash_html} · {when} · {message}"


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
        "    code { font-family: ui-monospace, monospace; }\n"
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
        body = f"  <p>{links('dev', publication)}</p>\n{revision_note(publication)}"
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


def revision_note(publication: Path) -> str:
    path = publication / "revision.json"
    if not path.is_file():
        return ""
    try:
        revision = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return f"  <p>{revision_text(revision)}</p>\n"


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
