# SETUP: tools used by reviewer2-repellent

Instructions for an agent (or a person) preparing a machine to run this skill. Last updated: 2026-11-11 (requirements and sizes; apt/dnf package lists instead of texlive-full; light macOS path
with BasicTeX; Windows via WSL; animate's own dependencies; self-test builds a tiny changes.pdf).

**Rules for the agent**
- Check first, install second: run the check commands below and install only what is missing.
- **Never install anything without the user's consent.** Show the exact command and wait for a yes. If installing is
  blocked in your environment, give the user the command to run themselves (in Claude Code: `! <command>`).
- If an optional tool is missing and the user declines, go on: the scripts report the check as `SKIPPED` and the
  skill says who does it instead (usually you, the agent).
- Never install a tool that would send the manuscript to a third-party service. RefChecker sends only reference
  metadata, and only if run without LLM API keys (see below).

## 0. Quick start

From the skill's folder (the one holding this file; with the one-line install it is
`~/.local/share/reviewer2-repellent/skills/reviewer2-repellent`):

```
python3 scripts/check_setup.py              # what is installed, what is missing, and how to install it
python3 scripts/self_test.py --network      # runs the scripts on a tiny synthetic paper (about 30 s)
```

## Requirements and sizes

Sizes are approximate (they depend on the distribution, its version and what is already installed).

| | What | Disk (approx.) |
|---|---|---|
| Required | Python ≥ 3.9 (standard library only) | usually already there |
| Required | poppler (`pdftotext`, `pdfinfo`, `pdffonts`, `pdftoppm`) | ~ 50 MB with dependencies |
| Required | TeX with `latexmk`, `bibtex`/`biber` and the packages of section 2, plus whatever your paper uses. One of: | |
| | · macOS light: BasicTeX + the packages below | ~ 0.5-1 GB |
| | · macOS full: MacTeX | ~ 6 GB download, ~ 10 GB installed (TeX Live 2026 full measured here: 9.7 GB) |
| | · Debian/Ubuntu: the apt list below (not `texlive-full`) | ~ 1-1.5 GB |
| Optional | RefChecker (`uv tool install academic-refchecker`) | ~ 100-200 MB |
| Optional | its local DBLP database (computer-science papers) | ~ 4.5 GB, built once in ~ 20 min, refreshed monthly |
| Optional | MCP servers `mcp-dblp`, `arxiv-mcp-server`, run on demand by `uvx` | ~ 100 MB of cached packages |
| Optional | `exiftool` | ~ 25 MB |

**Network endpoints contacted.** `refs_check.py`: export.arxiv.org, arxiv.org, api.crossref.org, api.datacite.org,
doi.org (reference metadata only). `form_check.py`: the URLs printed in the paper (at most 20; `--offline` skips
them). RefChecker: Crossref, OpenAlex, arXiv, ACL Anthology, Semantic Scholar (the DBLP database is downloaded from
dblp.org when built). MCP servers: dblp.org, arxiv.org. The agent: web search and the venue's pages (and
web.archive.org) for the venue rules. `check_setup.py`: arXiv, Crossref, doi.org. The manuscript itself is never
sent anywhere by the scripts.

## Installing TeX and poppler, by system

**macOS, light (BasicTeX, ~ 0.5-1 GB).** BasicTeX lacks some packages the scripts use; `tlmgr` does not install
`animate`'s own dependencies, hence `zref ocgx2 media9` in the list:

```
brew install --cask basictex && brew install poppler     # then open a new terminal (PATH: /Library/TeX/texbin)
sudo tlmgr update --self
sudo tlmgr install latexmk ulem xcolor hyperref pgf widows-and-orphans animate zref ocgx2 media9
```

These are TeX Live package names (checked against the TeX Live 2026 package database). Your paper's own class and
packages may be missing too: when compilation stops with `File '<x>.sty' not found`, run `tlmgr search --global
--file <x>.sty` and `sudo tlmgr install` the package it names. **macOS, full (MacTeX, ~ 10 GB):**
`brew install --cask mactex-no-gui && brew install poppler`; nothing else to add.

**Debian/Ubuntu (also Windows through WSL).** `texlive-full` (several GB) is not needed:

```
sudo apt-get install texlive-latex-extra texlive-fonts-recommended texlive-bibtex-extra texlive-plain-generic \
  texlive-pictures biber latexmk poppler-utils python3
```

Which package brings what (Debian follows the TeX Live collections): `hyperref`, `graphicx` -> texlive-latex-base;
`xcolor` -> texlive-latex-recommended; `ulem` -> texlive-plain-generic; `tikz` (pgf) -> texlive-pictures;
`widows-and-orphans`, `animate` (with `zref`, `ocgx2`, `media9`) -> texlive-latex-extra; `biblatex` ->
texlive-bibtex-extra; common fonts (`times`, `helvet`, `lmodern` metrics) -> texlive-fonts-recommended.
The annotated PDF does not use `marginfix`. A paper class outside these (e.g. some publishers' templates) may need
`texlive-publishers` or `texlive-science`.

**Fedora.** `sudo dnf install texlive-scheme-medium latexmk biber poppler-utils 'tex(tikz.sty)' 'tex(widows-and-orphans.sty)' 'tex(animate.sty)'`
(scheme-medium lacks pgf, widows-and-orphans and animate; `dnf install 'tex(<file>.sty)'` installs the package that
provides any missing file).

Linux is not tested by the authors yet (no Linux machine or container was available for this release): the lists
above come from the TeX Live package database, not from a test install. Reports are welcome (GitHub issues), with the
output of `python3 scripts/check_setup.py` and `python3 scripts/self_test.py`.

**Windows.** Use WSL (`wsl --install` gives Ubuntu) and follow the Debian/Ubuntu instructions inside it; run the
agent inside WSL too, so that it and the scripts see the same files. The skill itself can also be installed without
`install.sh` (the Claude Code plugin or `gh skill`, see the README), but `install.sh` and some of the commands the
skill runs need a POSIX shell (bash or zsh), and the scripts were never run on native Windows.

`check_setup.py` checks every tool below, the age of the local DBLP database, that `~/.local/bin` is on the PATH
and that arXiv, Crossref and doi.org are reachable, and prints, for each missing item, the exact install command for
this system. It installs nothing: show the commands to the user and run them only with consent (in Claude Code the
user can type `! <command>`). Exit code 1 means a required tool is missing. `self_test.py` compiles a one-page paper
with known problems and checks that the scripts find them; it needs no repository and no paper of yours.

## 1. Required

| Tool | Used for | Check | macOS (Homebrew) | Debian/Ubuntu |
|---|---|---|---|---|
| Python ≥ 3.9 (stdlib only) | all scripts | `python3 --version` | `brew install python` | `sudo apt-get install python3` |
| LaTeX with `latexmk`, `pdflatex` | compiling the paper | `latexmk -v`, `pdflatex --version` | MacTeX: `brew install --cask mactex-no-gui`, or BasicTeX (light path above) | the apt list above (not `texlive-full`) |
| poppler: `pdftotext`, `pdfinfo`, `pdffonts`, `pdftoppm` (and `pdftocairo` as a fallback) | compiled text, word positions (margins, font sizes), metadata, fonts, page images | `pdftotext -v` | `brew install poppler` | `sudo apt-get install poppler-utils` |
| `bibtex` or `biber` | the paper's bibliography | `bibtex --version` | comes with the TeX distribution | same |

A minimal TeX distribution (TinyTeX, BasicTeX) works if the paper's own packages are installed; install missing
ones with `tlmgr install <package>` (TinyTeX/BasicTeX/MacTeX; `sudo` for BasicTeX and MacTeX) when compilation
reports `File '<x>.sty' not found`. On Debian/Ubuntu, TeX Live from apt has no working `tlmgr`: install the apt
package instead (`apt-file search <x>.sty` names it, once `apt-file` is installed). `check_setup.py` prints the command that fits your system.

## 2. LaTeX packages used by the scripts (not by the paper)

| Package | Used for | Check | Install (TeX Live / Debian-Ubuntu) |
|---|---|---|---|
| `ulem`, `xcolor`, `hyperref`, `tikz` (pgf), `graphicx`; LaTeX 2020-10 or later (required) | the marks, margin notes, links, cover, logo and check boxes of the annotated PDF (`assets/r2changes.sty`, step 6) | `kpsewhich ulem.sty xcolor.sty hyperref.sty tikz.sty graphicx.sty` | `tlmgr install ulem xcolor hyperref pgf graphics` / texlive-plain-generic, texlive-latex-recommended, texlive-latex-base, texlive-pictures |
| `animate` (optional) | the summary page's strip plays one step at a time in Acrobat/Reader only; without `animate` (and in other viewers and in print) the static strip is shown and the build is otherwise identical (tested) | `kpsewhich animate.sty` | `tlmgr install animate zref ocgx2 media9` / texlive-latex-extra |
| `zref`, `ocgx2`, `media9` (required **if** `animate` is installed) | `animate.sty` loads `zref-abspage`, `ocgbase` and `pdfbase`; with `animate` present but one of these missing, the annotated PDF does not compile (`tlmgr install animate` alone does not add them, e.g. on BasicTeX) | `kpsewhich zref-abspage.sty ocgbase.sty pdfbase.sty` | `tlmgr install zref ocgx2 media9` / texlive-latex-extra |
| `widows-and-orphans` (recommended) | widow/orphan/page-break-hyphen diagnostic build in `form_check.py` | `kpsewhich widows-and-orphans.sty` | `tlmgr install widows-and-orphans` / texlive-latex-extra |

If `widows-and-orphans` is missing, `form_check.py` reports `SKIPPED | widows/orphans` and the agent looks at the page ends itself.

## 3. Optional (better checks, fewer tokens)

| Tool | Used for | Check | macOS | Debian/Ubuntu | If missing |
|---|---|---|---|---|---|
| RefChecker (`academic-refchecker`, recommended) | references exist and their metadata is right | `academic-refchecker --help` | `uv tool install academic-refchecker` (if `uv` is missing: `brew install uv`, or `curl -LsSf https://astral.sh/uv/install.sh \| sh`; uv puts tools in `~/.local/bin`: if that is not on the PATH, run `uv tool update-shell` and open a new terminal) | same | the skill's own reference script checks DOIs, arXiv IDs and DBLP; weaker |
| `xelatex`, `lualatex` | compiling papers that use `fontspec` or `unicode-math` (only those; other papers compile with `pdflatex`) | `xelatex --version`, `lualatex --version` | part of TeX Live / MacTeX (BasicTeX: `sudo tlmgr install xetex luatex`) | `sudo apt-get install texlive-xetex texlive-luatex` | such a paper does not compile; papers without `fontspec`/`unicode-math` are not affected |
| `pdftocairo` (poppler) | fallback for page images when `pdftoppm` fails | `pdftocairo -v` | `brew install poppler` | `sudo apt-get install poppler-utils` | `pdftoppm` alone is used |
| `exiftool` | author fields in figure files | `exiftool -ver` | `brew install exiftool` | `sudo apt-get install libimage-exiftool-perl` (Fedora: `perl-Image-ExifTool`) | `form_check.py` reads PDF figures with `pdfinfo` and scans other files for author fields |
| `open` (macOS) / `xdg-open` (Linux, xdg-utils) | `build_changes.py --open` opens changes.pdf when done | `command -v xdg-open` | comes with the OS | comes with the desktop (`sudo apt-get install xdg-utils`) | the agent gives the path of changes.pdf to open by hand |
| `unzip` | papers given as an Overleaf `.zip` | `unzip -v` | comes with the OS | `sudo apt-get install unzip` | the agent asks for the unpacked folder |

**RefChecker without LLMs.** Run it with the LLM keys unset, so that it only queries bibliographic databases, and
give it only the `.bib` (never the paper: its optional AI-text detection can use external services):
`env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u GOOGLE_API_KEY academic-refchecker --paper <file>.bib --dblp-db ~/.cache/refchecker/dblp.db --report-file refcheck.json --report-format json`.

**Local DBLP database (recommended for computer-science papers).** The dblp.org API blocks automated clients, so
RefChecker needs a local copy of DBLP to use it: about 4.5 GB, built once in about 20 minutes, refreshed monthly with
the same command: `academic-refchecker --dblp-db ~/.cache/refchecker/dblp.db --update-databases`. Without it,
RefChecker still checks Crossref, OpenAlex, arXiv and ACL Anthology, with weaker year/venue diagnosis.
A Semantic Scholar API key is optional (`SEMANTIC_SCHOLAR_API_KEY`): faster, fewer rate limits.

## 4. MCP servers (recommended: the reader checks every bibliography entry against its record)

The reader agent looks every cited entry up in DBLP (or the DOI record or arXiv) and compares the metadata; RefChecker
and `refs_check.py` give it a first sweep. Two MCP servers make the lookups cheap and exact. Both run locally through `uvx` (from `uv`, see above).

| Server | Used for | Claude Code (user scope) |
|---|---|---|
| `mcp-dblp` | DBLP records of computer-science papers: authors, venue, year, published version of a preprint, BibTeX (`MCP_DBLP_HOME` is the folder where it keeps its local index) | `claude mcp add -s user mcp-dblp -e MCP_DBLP_HOME=$HOME/.local/share/mcp-dblp -- uvx mcp-dblp` |
| `arxiv-mcp-server` | arXiv records: does an arXiv ID exist, and is it the cited paper | `claude mcp add -s user arxiv -- uvx arxiv-mcp-server` |

Check with `claude mcp list`. `check_setup.py` detects the servers only in Claude Code's configuration
(`~/.claude.json`, `./.mcp.json`); for any other agent it reports them as missing even when they are configured:
check there with the agent's own command or settings (e.g. `codex mcp list`, `gemini mcp list`, or the `mcpServers`
entry of its settings file), or ask the agent to list its MCP tools. To add them, give other agents the same two
stdio servers in their MCP configuration, e.g.

```json
{"mcpServers": {
  "mcp-dblp": {"command": "uvx", "args": ["mcp-dblp"], "env": {"MCP_DBLP_HOME": "<home>/.local/share/mcp-dblp"}},
  "arxiv":    {"command": "uvx", "args": ["arxiv-mcp-server"]}
}}
```

Without them the agent looks the references up with web search (more tokens, less exact).

## 5. Verify the installation, and what the scripts do on your machine

```
python3 scripts/self_test.py --network       # from the skill's folder: all PASS
```

The self-test compiles a small paper and runs `form_check.py` on it, then builds a tiny annotated `changes.pdf`
(step 6, one fix) and checks that it compiles and holds the item's check box; if a LaTeX package is missing it names
it. Without `--network` it skips the reference check. About 15 s offline, about 30 s with `--network` (longer when arXiv is slow).

Developers, from the repository root: `python3 -I evals/tests/test_form_check.py` (17 adversarial fixtures) and
`python3 -I evals/tests/test_refs_check.py` (reference fixtures, needs internet), and `python3 -I evals/tests/test_step6.py` (corrected copy, annotated PDF and its driver; about 100 s with LaTeX).

A run on a paper, after compiling it:

```
python3 scripts/form_check.py <root>.tex --facts --blind double --pages 12
python3 scripts/refs_check.py <root>.tex          # start it first, in the background
```

The last lines list `SKIPPED` checks: each names the missing tool or the unreachable service.

**Running times.** `form_check.py`: a few seconds, plus one extra `pdflatex` pass for the widow/orphan check (as
long as one compilation of the paper) and up to 20 link checks of 10 s at most each (`--offline` skips them).
`refs_check.py`: about 10 s per reference with RefChecker (a 120-reference paper takes about 20 minutes), a few
seconds with `--no-refchecker`.

**What runs on your files.** The scripts read the sources, the log and the compiled PDF, and compile copies of the
paper (latexmk with pdflatex, xelatex or lualatex) always with `-no-shell-escape`: no command written in the paper is
executed, even when a `latexmkrc` asks for shell escape (a paper that needs it, e.g. with `minted`, stops with an
error and the agent asks you). They write only to a temporary folder or the run's `work/` folder. Over the network
go only the reference metadata (titles, identifiers) and the URLs printed in the paper; the manuscript never leaves
the machine.

## 6. Tested environment

macOS (Apple silicon), TeX Live 2026 full (latexmk 4.88, pdfTeX 1.40.29), poppler 26.04, Python 3.14, uv 0.10.12,
RefChecker 3.1.11, mcp-dblp and arxiv-mcp-server via uvx. Also tested here: the build without `animate` (static
strip). Not yet tested: BasicTeX, TinyTeX, Linux (Debian/Ubuntu, Fedora), Windows/WSL; reports are welcome.
