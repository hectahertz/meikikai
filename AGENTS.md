# AGENTS.md

Repo-specific guidance for coding agents working on MeikiKai.

## Project scope

- MeikiKai is a macOS-only Japanese OCR popup dictionary built with PyQt6.
- Do not add Windows/Linux/cross-platform fallback code unless explicitly requested.
- Keep changes surgical and consistent with the existing local style.
- Preserve user data paths under `~/Library/Application Support/meikikai/` and logs under `~/Library/Logs/MeikiKai/`.

## Working tree safety

- The working tree may contain user changes. Do not revert, overwrite, stage, or commit unrelated files.
- Before committing, stage only files that belong to the requested change and review `git diff --cached`.

## Development commands

- Quick syntax validation:
  - `.venv/bin/python -m py_compile <files>`
- Run from source when needed:
  - `PYTHONPATH=src .venv/bin/python -m meikikai.main`
- Build, sign, install, and reopen the macOS app:
  - `scripts/build_install_macos.sh`

## macOS permissions and packaging notes

- Required macOS permissions include Screen Recording, Accessibility, and Input Monitoring.
- Media auto-pause uses synthetic macOS media key events and requires Accessibility permission.
- After rebuilding or re-signing the app, macOS TCC permissions can become stale. If Accessibility appears checked but media automation fails, remove MeikiKai from Accessibility and add/approve it again, then relaunch.
- The installed app bundle is `/Applications/MeikiKai.app` and bundle identifier is `dev.hectahertz.meikikai`.

## Validation guidance

- Prefer targeted validation over full builds for small edits.
- Use the full build/install script only when changing packaging, app startup behavior, bundled resources, permissions, or when explicitly requested.
