#!/usr/bin/env python3
"""Check the tools reviewer2-repellent uses and print, for each missing one, the command that installs it.

Usage: python3 check_setup.py
It installs nothing: the agent shows the commands to the user and runs them only with the user's consent.
The install commands fit this system: Homebrew + tlmgr on macOS, apt on Debian/Ubuntu (and WSL), dnf on Fedora,
tlmgr for any other TeX Live. See SETUP.md for what each tool is used for.
The MCP check reads Claude Code's configuration only (~/.claude.json, ./.mcp.json); other agents: see SETUP.md.
"""
import argparse
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import time
import urllib.request

MAC = platform.system() == "Darwin"
APT = not MAC and bool(shutil.which("apt-get"))
DNF = not MAC and not APT and bool(shutil.which("dnf"))
DBLP_DB = pathlib.Path.home() / ".cache" / "refchecker" / "dblp.db"


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return (r.stdout + r.stderr).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def pkg(mac, deb, fedora=None):
    if MAC:
        return mac
    if DNF and fedora:
        return fedora
    return deb


# LaTeX packages the scripts need: .sty -> (TeX Live package, Debian/Ubuntu package)
TEX_PKGS = {"ulem": ("ulem", "texlive-plain-generic"), "xcolor": ("xcolor", "texlive-latex-recommended"),
            "hyperref": ("hyperref", "texlive-latex-base"), "tikz": ("pgf", "texlive-pictures"),
            "graphicx": ("graphics", "texlive-latex-base"),
            "widows-and-orphans": ("widows-and-orphans", "texlive-latex-extra"),
            "animate": ("animate", "texlive-latex-extra"),
            # what animate.sty loads; tlmgr does not install them with it (BasicTeX)
            "zref-abspage": ("zref", "texlive-latex-extra"), "ocgbase": ("ocgx2", "texlive-latex-extra"),
            "pdfbase": ("media9", "texlive-latex-extra")}


def tex_install(stys):
    """The command that installs these .sty files on this system."""
    tl = sorted({TEX_PKGS[s][0] for s in stys})
    tex = shutil.which("kpsewhich") or ""
    if APT and (not tex or tex.startswith("/usr/bin")):
        return "sudo apt-get install " + " ".join(sorted({TEX_PKGS[s][1] for s in stys}))
    if DNF and (not tex or tex.startswith("/usr/bin")):
        return "sudo dnf install " + " ".join(f"'tex({s}.sty)'" for s in stys)
    root = run(["kpsewhich", "-var-value", "TEXMFROOT"]) if tex else None
    sudo = "sudo " if not (root and os.access(root, os.W_OK)) else ""
    return f"{sudo}tlmgr install " + " ".join(tl)


def kpse(sty):
    return run(["kpsewhich", sty + ".sty"]) if shutil.which("kpsewhich") else None


def main():
    argparse.ArgumentParser(description="Check the tools reviewer2-repellent uses and print, for each "
                            "missing one, the command that installs it (it installs nothing). Exit code 1 if a "
                            "required tool is missing.").parse_args()
    rows = []  # (level, name, ok, detail, install)

    rows.append(("required", "Python >= 3.9", sys.version_info >= (3, 9), platform.python_version(),
                 pkg("brew install python", "sudo apt-get install python3")))
    tex_cmd = pkg("brew install --cask mactex-no-gui   # or the light path: brew install --cask basictex (SETUP.md)",
                  "sudo apt-get install texlive-latex-extra texlive-fonts-recommended texlive-bibtex-extra "
                  "texlive-plain-generic texlive-pictures biber latexmk",
                  "sudo dnf install texlive-scheme-medium latexmk biber 'tex(widows-and-orphans.sty)' "
                  "'tex(animate.sty)' 'tex(tikz.sty)'")
    if not (MAC or APT or DNF):
        tex_cmd = "install TeX Live (https://tug.org/texlive/), then: tlmgr install latexmk"
    for tool in ("latexmk", "pdflatex"):
        rows.append(("required", tool, bool(shutil.which(tool)), shutil.which(tool) or "",
                     "tlmgr install latexmk" if tool == "latexmk" and shutil.which("pdflatex")
                     and shutil.which("tlmgr") and not (APT or DNF) else tex_cmd))
    for tool in ("pdftotext", "pdfinfo", "pdffonts", "pdftoppm"):
        rows.append(("required", tool, bool(shutil.which(tool)), shutil.which(tool) or "",
                     pkg("brew install poppler", "sudo apt-get install poppler-utils", "sudo dnf install poppler-utils")))

    rows.append(("optional", "pdftocairo (fallback for page images)", bool(shutil.which("pdftocairo")),
                 shutil.which("pdftocairo") or "",
                 pkg("brew install poppler", "sudo apt-get install poppler-utils", "sudo dnf install poppler-utils")))
    for tool, deb in (("xelatex", "texlive-xetex"), ("lualatex", "texlive-luatex")):
        rows.append(("optional", f"{tool} (only for papers that use fontspec/unicode-math)", bool(shutil.which(tool)),
                     shutil.which(tool) or "",
                     pkg("part of MacTeX (BasicTeX: sudo tlmgr install " + tool[:-5] + "tex)",
                         f"sudo apt-get install {deb}", f"sudo dnf install {deb}")))

    bib = shutil.which("bibtex") or shutil.which("biber")
    rows.append(("required", "bibtex or biber", bool(bib), bib or "", "comes with the TeX distribution"))

    for sty in ("ulem", "xcolor", "hyperref", "tikz", "graphicx"):
        p = kpse(sty)
        rows.append(("required", f"LaTeX package {sty} (annotated PDF)", bool(p), p or "", tex_install([sty])))
    an = kpse("animate")
    rows.append(("optional", "LaTeX package animate (the summary's strip plays in Acrobat; without it: static)",
                 bool(an), an or "", tex_install(["animate", "zref-abspage", "ocgbase", "pdfbase"])))
    if an:  # animate.sty loads these: if one is missing the annotated PDF does not compile at all
        deps = [s for s in ("zref-abspage", "ocgbase", "pdfbase") if not kpse(s)]
        rows.append(("required", "packages animate loads (zref, ocgx2, media9): the annotated PDF fails without them",
                     not deps, "missing: " + ", ".join(d + ".sty" for d in deps) if deps else "",
                     tex_install(deps) if deps else ""))
    wo = kpse("widows-and-orphans")
    rows.append(("recommended", "LaTeX package widows-and-orphans", bool(wo), wo or "",
                 tex_install(["widows-and-orphans"])))

    rc = shutil.which("academic-refchecker")
    uv = shutil.which("uv")
    rows.append(("recommended", "RefChecker (academic-refchecker)", bool(rc), rc or "",
                 "uv tool install academic-refchecker" if uv else
                 pkg("brew install uv && uv tool install academic-refchecker",
                     "curl -LsSf https://astral.sh/uv/install.sh | sh && uv tool install academic-refchecker")))
    if rc:
        import re
        m = re.search(r"academic-refchecker v?([\d.]+)", run(["uv", "tool", "list"]) or "") if uv else None
        rows.append(("info", "RefChecker version (tested: 3.1.11)", True, m.group(1) if m else "unknown", ""))
    size = f"{DBLP_DB.stat().st_size / 2**30:.1f} GB" if DBLP_DB.is_file() else ""
    age = (time.time() - DBLP_DB.stat().st_mtime) / 86400 if DBLP_DB.is_file() else None
    fresh = age is not None and age <= 45
    rows.append(("recommended", "local DBLP database for RefChecker (refreshed in the last 45 days)", fresh,
                 f"{DBLP_DB} {size}" + (f", {age:.0f} days old" if age is not None else ""),
                 f"academic-refchecker --dblp-db {DBLP_DB} --update-databases   # ~20 min, ~4.5 GB, once a month"))
    local_bin = str(pathlib.Path.home() / ".local" / "bin")
    on_path = local_bin in os.environ.get("PATH", "").split(os.pathsep)
    rows.append(("recommended", "~/.local/bin on PATH (uv tools)", on_path or not uv, "" if on_path else local_bin,
                 "uv tool update-shell   # then open a new terminal"))
    uvx = shutil.which("uvx")
    rows.append(("recommended", "uvx (runs the MCP servers)", bool(uvx), uvx or "", "installed with uv (see RefChecker)"))


    servers = {}
    for cfg in (pathlib.Path.home() / ".claude.json", pathlib.Path.cwd() / ".mcp.json"):
        try:
            import json
            data = json.loads(cfg.read_text())
        except (OSError, ValueError):
            continue
        stack = [data]
        while stack:  # mcpServers may sit at the top level or under a project entry
            o = stack.pop()
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "mcpServers" and isinstance(v, dict):
                        servers.update({n: json.dumps(c) for n, c in v.items()})
                    else:
                        stack.append(v)
    has = lambda word: any(word in (n + c).lower() for n, c in servers.items())
    # only Claude Code's configuration is read; other agents keep MCP servers elsewhere (SETUP.md section 4)
    note = "(Claude Code configuration only)" if shutil.which("claude") else \
        "(Claude Code not found: this check reads only its configuration; check your agent's MCP settings)"
    rows.append(("recommended", "MCP server mcp-dblp", has("mcp-dblp"), note,
                 "claude mcp add -s user mcp-dblp -e MCP_DBLP_HOME=$HOME/.local/share/mcp-dblp -- uvx mcp-dblp"))
    rows.append(("recommended", "MCP server arxiv-mcp-server", has("arxiv-mcp-server"), note,
                 "claude mcp add -s user arxiv -- uvx arxiv-mcp-server"))

    rows.append(("optional", "exiftool", bool(shutil.which("exiftool")), shutil.which("exiftool") or "",
                 pkg("brew install exiftool", "sudo apt-get install libimage-exiftool-perl",
                     "sudo dnf install perl-Image-ExifTool")))
    opener = shutil.which("open" if MAC else "xdg-open")
    rows.append(("optional", "open/xdg-open (opens changes.pdf when done)", bool(opener), opener or "",
                 pkg("comes with macOS", "sudo apt-get install xdg-utils", "sudo dnf install xdg-utils")))
    rows.append(("optional", "unzip (papers given as an Overleaf .zip)", bool(shutil.which("unzip")),
                 shutil.which("unzip") or "", pkg("comes with macOS", "sudo apt-get install unzip",
                                                  "sudo dnf install unzip")))

    for host in ("https://export.arxiv.org/api/query?id_list=1706.03762", "https://api.crossref.org/works?rows=0",
                 "https://doi.org/api/handles/10.1145/362384.362685"):
        ok, err = False, ""
        for attempt in range(2):  # one retry: a single timeout or reset should not report the host as unreachable
            try:
                req = urllib.request.Request(host, headers={"User-Agent": "reviewer2-repellent-setup"})
                urllib.request.urlopen(req, timeout=10).read(100)
                ok, err = True, ""
                break
            except Exception as e:  # any network problem
                err = type(e).__name__
                if attempt == 0:
                    time.sleep(2)
        rows.append(("recommended", f"network: {host.split('/')[2]} reachable (reference checks)", ok,
                     f"failed twice: {err}" if err else "",
                     "check the connection or proxy; refs_check.py reports SKIPPED otherwise"))

    missing = [r for r in rows if not r[2]]
    for level, name, ok, detail, _ in rows:
        print(f"{'OK     ' if ok else 'MISSING'} | {level:11} | {name} {('— ' + detail) if detail else ''}")
    if os.environ.get("SEMANTIC_SCHOLAR_API_KEY"):
        print("OK      | optional    | SEMANTIC_SCHOLAR_API_KEY set (faster RefChecker)")
    if missing:
        # sudo commands and the long DBLP build are for the user (`! <command>`); everything else the agent runs itself
        user = [r for r in missing if r[4].lstrip().startswith("sudo ") or "--update-databases" in r[4]
                or "(BasicTeX: sudo" in r[4]]
        agent = [r for r in missing if r not in user and r[4].split(" ")[0] in
                 ("brew", "uv", "claude", "tlmgr", "curl", "pip", "pipx", "uvx", "python3")]
        if agent:
            print("\nTHE AGENT RUNS THESE ITSELF, after ONE yes from the user for the whole list (no sudo, short):")
            for level, name, _, _, install in agent:
                print(f"  [{level}] {name}:  {install}")
        if user:
            print("\nTHE USER RUNS THESE (sudo or long): show them as one copyable block, each line prefixed with `! `:")
            for level, name, _, _, install in user:
                print(f"  [{level}] {name}:\n! {install}")
    else:
        print("\nEverything is installed.")
    print("\nSelf-test of the scripts: python3 " + str(pathlib.Path(__file__).with_name("self_test.py")) + " --network")
    return 1 if any(r[0] == "required" for r in missing) else 0


if __name__ == "__main__":
    sys.exit(main())
