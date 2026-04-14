#!/bin/bash
# Block skill usage when gstack is not installed globally OR project-locally.
# Checks for either ~/.claude/skills/gstack/bin (global install) or
# $PWD/.claude/skills/gstack/bin (vendored/project-local install). Allows
# skill usage when gstack is available in either location.

GSTACK_PATH=""
for candidate in "$HOME/.claude/skills/gstack/bin" "$PWD/.claude/skills/gstack/bin"; do
  if [ -d "$candidate" ]; then
    GSTACK_PATH="$candidate"
    break
  fi
done

if [ -z "$GSTACK_PATH" ]; then
  cat >&2 <<'MSG'
BLOCKED: gstack is not installed.

gstack is required for AI-assisted work in this repo.

Install globally (recommended):
  git clone --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack
  cd ~/.claude/skills/gstack && ./setup --team

Or install project-locally at ./.claude/skills/gstack/.

Then restart your AI coding tool.
MSG
  echo '{"permissionDecision":"deny","message":"gstack is required but not installed. See stderr for install instructions."}'
  exit 0
fi

echo '{}'
