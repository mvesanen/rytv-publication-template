"""Place one publication on the Pages tree and refresh the catalog.

A release is copied to versions/<tag> and left there. The dev branch replaces
only the dev/ directory. The site root is a catalog, so a new publication
does not remove older ones.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import urllib.request
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
    publish(args.site, args.artefact, target, revision, args.repository)


def version_folder(tag: str) -> str:
    name = tag[1:] if tag.startswith("v") and len(tag) > 1 and tag[1].isdigit() else tag
    if not name or name in {".", ".."} or any(character in name for character in "\\/"):
        raise SystemExit(f"release tag cannot be a Pages path: {tag}")
    return name


def publish(
    site: Path,
    artefact: Path,
    target: str,
    revision: dict | None = None,
    repository: str | None = None,
) -> None:
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
    notes = github_release_notes(repository)
    store_release_notes(site, notes)
    (site / "index.html").write_text(catalog(site, notes), encoding="utf-8")
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


def github_release_notes(repository: str | None) -> dict[str, dict]:
    if not repository or not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
        return {}
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "rytv-builder"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.github.com/repos/{repository}/releases?per_page=100"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
            releases = json.loads(response.read().decode())
    except Exception as error:
        print(f"warning: could not read GitHub releases: {error}")
        return {}
    notes = {}
    for release in releases:
        tag = str(release.get("tag_name") or "")
        try:
            folder = version_folder(tag)
        except SystemExit:
            continue
        notes[folder] = {
            "time": display_iso(str(release.get("published_at") or "")),
            "title": release_title(release, folder, tag),
        }
    return notes


def release_title(release: dict, folder: str, tag: str) -> str:
    body = str(release.get("body") or "").strip()
    name = str(release.get("name") or "").strip()
    if body:
        if name and name not in {folder, tag}:
            return f"{name}\n{body}"
        return body
    if name and name not in {folder, tag}:
        return name
    return ""


def display_iso(raw: str) -> str:
    if "T" not in raw:
        return display_time(raw) if raw else ""
    date, clock = raw.split("T", 1)
    zone = "UTC" if clock.endswith("Z") else ""
    clock = clock.rstrip("Z").split("+", 1)[0]
    if clock.count(":") == 2:
        clock = clock.rsplit(":", 1)[0]
    return f"{date} {clock}" + (f" {zone}" if zone else "")


def store_release_notes(site: Path, notes: dict[str, dict]) -> None:
    for folder, info in notes.items():
        destination = site / "versions" / folder
        if not destination.is_dir():
            continue
        payload = json.dumps(info, ensure_ascii=False, indent=2) + "\n"
        target = destination / "release.json"
        if target.is_file() and target.read_text(encoding="utf-8") == payload:
            continue
        target.write_text(payload, encoding="utf-8")


def catalog(site: Path, notes: dict[str, dict] | None = None) -> str:
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
    notes = notes or {}
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
        "    .release-note { margin: 0.2rem 0 0.8rem; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{html.escape(title)}</h1>\n"
        "  <p>Jokainen GitHub Release jää omalle polulleen. Juuri on luettelo, uusin ensin.</p>\n"
        f"{latest_section(site, versions, notes)}\n"
        f"{version_list(site, versions, notes)}\n"
        f"{dev_section(site)}\n"
        "</body>\n"
        "</html>\n"
    )


def latest_section(site: Path, versions: list[str], notes: dict[str, dict]) -> str:
    if not versions:
        return "  <h2>Uusin julkaisu</h2>\n  <p>Ei vielä julkaistuja versioita.</p>\n"
    name = versions[0]
    return (
        "  <h2>Uusin julkaisu</h2>\n"
        f"{version_entry(site, name, notes)}"
    )


def version_list(site: Path, versions: list[str], notes: dict[str, dict]) -> str:
    if not versions:
        return ""
    items = "\n".join(
        f"    <li>\n{version_entry(site, name, notes)}    </li>" for name in versions
    )
    return f"  <h2>Kaikki versiot</h2>\n  <ul>\n{items}\n  </ul>\n"


def version_entry(site: Path, name: str, notes: dict[str, dict]) -> str:
    publication = site / "versions" / name
    return f"  <p>{links(name, publication)}</p>\n{release_note(publication, notes.get(name))}"


def release_note(publication: Path, info: dict | None) -> str:
    if not info:
        path = publication / "release.json"
        if not path.is_file():
            return ""
        try:
            info = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ""
    when = html.escape(str(info.get("time") or ""))
    title = html.escape(str(info.get("title") or "")).replace("\n", "<br>")
    parts = [part for part in (when, title) if part]
    if not parts:
        return ""
    return f'  <p class="release-note">{"<br>".join(parts)}</p>\n'


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
