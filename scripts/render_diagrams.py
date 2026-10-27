#!/usr/bin/env python3
"""Render every PlantUML block in the Markdown documentation to SVG and embed the image.

Usage (from the repository root):
    python scripts/render_diagrams.py                 # all *.md files
    python scripts/render_diagrams.py --check         # exit 1 if a page/image is out of date
    PLANTUML_JAR=~/tools/plantuml.jar python scripts/render_diagrams.py

Requirements: Java + plantuml.jar (path in $PLANTUML_JAR, or a `plantuml` command on PATH)
and Graphviz (`dot`).

What it does with each block
    ```plantuml            ![Title](../diagrams/<page>-<n>-<name>.svg)
    @startuml ...    ->    <details><summary>PlantUML source</summary>
    ```                    ```plantuml ... ```
                           </details>
The image is shown on GitHub and in every Markdown viewer; the source stays in the page
(folded) and remains the single source of truth. Running the script again only updates
the images - it is idempotent.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "diagrams"
MARK = "<!-- plantuml-source-sha1: {} -->"
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", ".pytest_cache"}

# optional "image + details" wrapper produced by this script, then the block itself
BLOCK = re.compile(
    r"(?:!\[[^\]]*\]\([^)]*\.svg\)\n\n<details><summary>PlantUML source</summary>\n\n)?"
    r"```plantuml\n(?P<src>.*?)```"
    r"(?:\n\n</details>)?",
    re.S)


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:40].strip("-") or "diagram"


def title_of(src: str) -> str:
    m = re.search(r"^title\s+(.+)$", src, re.M)
    if m:
        return m.group(1).strip()
    m = re.search(r"^@startuml\s+(\S+)", src, re.M)
    return m.group(1) if m else "Diagram"


def plantuml_cmd() -> list[str]:
    jar = os.environ.get("PLANTUML_JAR")
    if jar:
        return ["java", "-Djava.awt.headless=true", "-jar", os.path.expanduser(jar)]
    if shutil.which("plantuml"):
        return ["plantuml"]
    sys.exit("PlantUML not found: set PLANTUML_JAR=/path/to/plantuml.jar or install `plantuml`.")


def render(src: str, target: Path, cmd: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "d.puml"
        f.write_text(src, encoding="utf-8")
        r = subprocess.run(cmd + ["-tsvg", "-charset", "UTF-8", str(f)],
                           capture_output=True, text=True)
        svgs = list(Path(tmp).glob("*.svg"))     # named after "@startuml <name>" if given
        if r.returncode != 0 or len(svgs) != 1:
            raise RuntimeError(f"PlantUML failed for {target.name}:\n{r.stdout}{r.stderr}")
        target.write_bytes(svgs[0].read_bytes())


def process(md: Path, cmd: list[str] | None, check: bool) -> list[str]:
    text = md.read_text(encoding="utf-8")
    page = slug(md.stem)
    problems: list[str] = []
    n = 0

    def repl(m: re.Match) -> str:
        nonlocal n
        n += 1
        src = m.group("src")
        title = title_of(src)
        name = f"{page}-{n:02d}-{slug(title)}.svg"
        target = OUT / name
        digest = hashlib.sha1(src.encode("utf-8")).hexdigest()   # re-render only on change
        stale = not target.exists() or MARK.format(digest).encode() not in target.read_bytes()
        if stale:
            if check:
                problems.append(f"{md.relative_to(ROOT)}: {name} out of date")
            else:
                render(src, target, cmd)
                with target.open("ab") as f:
                    f.write(("\n" + MARK.format(digest) + "\n").encode())
        rel = os.path.relpath(target, md.parent).replace(os.sep, "/")
        alt = title.replace("[", "(").replace("]", ")")
        return (f"![{alt}]({rel})\n\n<details><summary>PlantUML source</summary>\n\n"
                f"```plantuml\n{src}```\n\n</details>")

    new = BLOCK.sub(repl, text)
    if new != text:
        if check:
            problems.append(f"{md.relative_to(ROOT)}: images not embedded")
        else:
            md.write_text(new, encoding="utf-8")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only report out-of-date pages/images")
    ap.add_argument("files", nargs="*", help="Markdown files (default: all in the repository)")
    a = ap.parse_args()
    files = [Path(f).resolve() for f in a.files] or sorted(
        p for p in ROOT.rglob("*.md") if not SKIP_DIRS & set(p.relative_to(ROOT).parts))
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = None if a.check else plantuml_cmd()
    problems, count = [], 0
    for md in files:
        before = md.read_text(encoding="utf-8").count("```plantuml")
        if not before:
            continue
        count += before
        problems += process(md, cmd, a.check)
    for p in problems:
        print(p)
    print(f"{count} diagram(s) in {len(files)} file(s); {'problems: ' + str(len(problems)) if a.check else 'done'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
