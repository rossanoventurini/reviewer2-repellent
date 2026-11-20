#!/usr/bin/env python3
"""Print the prompt of a reference file with its placeholders filled.

Usage: python3 fill_prompt.py <skill>/references/<agent>.md KEY=VALUE [KEY=VALUE ...] > work/prompts/<agent>.txt
The prompt is the text after the file's first line that is exactly "---" (the lines before it are notes for the
coordinating agent). Every {KEY} is replaced by VALUE; the script fails if a placeholder is left unfilled or a KEY is
not used, so a typo in a key cannot go unnoticed. Python stdlib only.
"""
import re
import sys


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        sys.exit(0 if len(sys.argv) >= 2 else 2)
    try:
        text = open(sys.argv[1], encoding="utf-8").read()
    except OSError as e:
        sys.exit(f"cannot read the prompt file {sys.argv[1]!r}: {e.strerror}")
    parts = re.split(r"^---[ \t]*$\n?", text, maxsplit=1, flags=re.M)
    if len(parts) != 2:
        sys.exit(f"no '---' line in {sys.argv[1]}")
    prompt = parts[1].strip() + "\n"
    values = {}
    for arg in sys.argv[2:]:
        key, sep, value = arg.partition("=")
        if not sep or not re.fullmatch(r"[A-Z_]+", key):
            sys.exit(f"bad argument {arg!r}: use KEY=VALUE with KEY in capitals")
        values[key] = value
    unused = [k for k in values if "{" + k + "}" not in prompt]
    if unused:
        sys.exit(f"not a placeholder of this prompt: {', '.join(unused)}")
    for key, value in values.items():
        prompt = prompt.replace("{" + key + "}", value)
    left = sorted(set(re.findall(r"\{([A-Z_]{3,})\}", prompt)))
    if left:
        sys.exit(f"unfilled placeholders: {', '.join(left)}")
    sys.stdout.write(prompt)


if __name__ == "__main__":
    main()
