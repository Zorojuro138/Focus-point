# What was fixed (review of the Copilot-built version)

Run `pytest` (100 tests), `ruff check .` and `mypy src` to verify. Highlights:

## Wrong results
- YouTube/Instagram/Netflix/Facebook in a browser counted as ON-TASK for coding and study goals.
- "git" matched "Digital Photos", "word" matched "password", "edge" matched "knowledge".
- Goal category "other" made real work (VS Code) count as off-task.
- "I'm on task" whitelisted the whole browser forever; a later choice never replaced an earlier one.
- Planned breaks were still recorded (and scored) as distractions.
- Time before going idle (up to 2 min) and the gap at every app switch were counted wrongly.
- Dashboard/history showed UTC times as if local; the parent dashboard included the child's usage.
- Away-from-keyboard users were nudged for whatever was left on screen.

## Child Mode
- Default 5-7 and 8-10 profiles warned on EVERY app (allowlist held descriptions, not app names).
- Equal bedtime start/end meant permanently "bedtime".
- A resumed child session lost Child Mode; pause/end/quit needed no PIN; no PIN confirmation on setup.
- PIN lockout reset on restart; non-wrong-PIN argon2 errors crashed.

## Reliability
- Nudge popups could appear behind other windows; popups leaked memory; modal boxes re-entered the event loop.
- Autostart used python.exe (console flash) and passed `-m focuspilot` to the packaged exe.
- No single-instance guard (autostart + manual launch = two trackers on one database).
- Lock screen / no foreground window spammed errors; tracker logged the same error every 2 s.
- Windows sign-out could be blocked by the hide-to-tray close handler.
- Corrupt quiet-hours/retention settings crashed tracking/startup; empty goals were accepted.

## Added (were in the spec, missing in the build)
- Tray toast for level-1 nudges, always-on-top popups, "Take a breath" level-3 prompt.
- XP, levels, daily streak, 6 achievements, coaching text, Progress card on Insights.
- "What is this session for?" prompt when started by Windows (`--autostart`).
- SQLite WAL + foreign keys; installer removes its Run entry on uninstall; UPX disabled.
