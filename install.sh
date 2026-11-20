#!/usr/bin/env bash
# Install the reviewer2-repellent skill (a SKILL.md folder) where agent CLIs look for user skills.
# Run with --help for the options; the help text is below in usage() so that it also works when piped.
set -euo pipefail

NAME=reviewer2-repellent
REPO_URL=${REVIEWER2_REPELLENT_REPO:-https://github.com/rossanoventurini/reviewer2-repellent.git}

usage() {
  cat <<'HELP'
Install the reviewer2-repellent skill where agent CLIs look for user skills:
  ~/.claude/skills   read by Claude Code
  ~/.agents/skills   the shared location, read by agents that support it, e.g. Codex and Gemini CLI
  ~/.gemini/antigravity-cli/skills   only if ~/.gemini/antigravity-cli exists
Other agents: point them at the installed skill folder (see the README).

  curl -fsSL https://raw.githubusercontent.com/rossanoventurini/reviewer2-repellent/main/install.sh | bash
  curl -fsSL .../install.sh | bash -s -- --uninstall      options work when piped too
  ./install.sh                 from a clone: symlink the skill (edits and git pull take effect)
  ./install.sh --copy          copy instead of symlinking
  ./install.sh --uninstall     remove what this script installed (nothing else)
  ./install.sh --dry-run       show what would be done
  ./install.sh --help          this text

Run without a clone, it clones the repository into $REVIEWER2_REPELLENT_HOME
(default ~/.local/share/reviewer2-repellent); run it again to update. Safe to run twice.
Override the target directories with SKILL_TARGETS="dir1 dir2 ..." and the repository
with REVIEWER2_REPELLENT_REPO=<git url or path>.
After installing: python3 <skill folder>/scripts/check_setup.py (what else is needed: LaTeX, poppler).
HELP
}

mode=link dry=0
for arg in "$@"; do
  case "$arg" in
    --copy) mode=copy ;;
    --uninstall) mode=uninstall ;;
    --dry-run) dry=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done
run() { if (( dry )); then echo "[dry-run] $*"; else "$@"; fi; }
say() { (( dry )) || echo "$@"; return 0; }

# Where the skill lives: this clone, or a managed clone fetched now.
here=""
if [[ -n ${BASH_SOURCE[0]:-} && -f ${BASH_SOURCE[0]} ]]; then
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [[ -n $here && -f $here/skills/$NAME/SKILL.md ]]; then
  root="$here"
else
  root="${REVIEWER2_REPELLENT_HOME:-$HOME/.local/share/$NAME}"
  if [[ $mode != uninstall ]]; then
    command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
    if [[ -d $root/.git ]]; then run git -C "$root" pull --ff-only --quiet
    else run git clone --depth 1 --quiet "$REPO_URL" "$root"; fi
  fi
fi
src="$root/skills/$NAME"

# ~/.claude/skills: Claude Code.
# ~/.agents/skills: the shared location; documented for Codex (USER scope) and Gemini CLI (alias of ~/.gemini/skills).
# ~/.gemini/antigravity-cli/skills: Antigravity CLI, only if it is installed.
targets="$HOME/.claude/skills $HOME/.agents/skills"
[[ -d $HOME/.gemini/antigravity-cli ]] && targets+=" $HOME/.gemini/antigravity-cli/skills"
targets="${SKILL_TARGETS:-$targets}"

for t in $targets; do
  dest="$t/$NAME"
  if [[ $mode == uninstall ]]; then
    if [[ -L $dest && $(readlink "$dest") == "$src" ]]; then run rm "$dest" && say "removed $dest"
    elif [[ -f $dest/.installed-by-reviewer2-repellent ]]; then run rm -rf "$dest" && say "removed $dest"
    fi
    continue
  fi
  if [[ -e $dest && ! -L $dest && ! -f $dest/.installed-by-reviewer2-repellent ]] ||
     [[ -L $dest && $(readlink "$dest") != "$src" ]]; then
    echo "skip $dest: exists and was not installed by this script" >&2; continue
  fi
  run mkdir -p "$t"
  if [[ $mode == link ]]; then
    [[ -d $dest && ! -L $dest ]] && run rm -rf "$dest"
    run ln -sfn "$src" "$dest" && say "linked $dest -> $src"
  else
    run rm -rf "$dest"
    run cp -R "$src" "$dest" && run touch "$dest/.installed-by-reviewer2-repellent" && say "copied $src -> $dest"
  fi
done

if [[ $mode == uninstall && $root != "$here" && -d $root/.git ]]; then
  echo "the clone in $root is left in place; delete it with: rm -rf $root"
fi
