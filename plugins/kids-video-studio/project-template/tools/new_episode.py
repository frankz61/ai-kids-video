"""Scaffold a new episode folder from an existing one (source files only, no build outputs).

Usage: python tools/new_episode.py ep02_animals [--from ep01_colors] [--output-name ep02_fenlos_animal_friends]

Copies the editable sources; you then rewrite the script, voice lines, H5 scenes, H3 shots and ORDER.
"""
import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ["audio/tts.py", "h5/index.html", "h5/assets/hero.png", "h3/prompts.json", "h3/gen_frames.py", "assemble.py"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("slug", help="new folder name under episodes/, e.g. ep02_animals")
    p.add_argument("--from", dest="src", default="ep01_colors")
    p.add_argument("--output-name", help="final video file name without extension (default: the slug)")
    a = p.parse_args()

    src, dst = ROOT / "episodes" / a.src, ROOT / "episodes" / a.slug
    if dst.exists():
        raise SystemExit(f"{dst} already exists")
    for rel in SOURCES:
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, dst / rel)
    (dst / "script").mkdir()
    asm = dst / "assemble.py"
    text, n = re.subn(r'OUTPUT_NAME = "[^"]*"', f'OUTPUT_NAME = "{a.output_name or a.slug}"', asm.read_text(encoding="utf-8"))
    if n != 1:
        raise SystemExit("could not set OUTPUT_NAME in assemble.py")
    asm.write_text(text, encoding="utf-8", newline="\n")
    print(f"created {dst}")
    for rel in SOURCES:
        print("  ", rel)
    print("next: write script/script_v1_draft.md, then follow .agents/skills/kids-english-episode/SKILL.md")


if __name__ == "__main__":
    main()
