# FocusPilot

FocusPilot is a local-first focus coach for Windows 10/11. It combines visible
focus sessions, per-session app choices, strict app guarding, browser relevance
checks through Gemini Free, an optional AI chat coach, local usage history,
focus scoring, gentle reminders, and parent-managed family reminders.

FocusPilot tracks only the foreground app name, visible window title, timestamps,
and idle duration during a session that you explicitly start. The optional
Chrome/Edge extension supplies only the active tab title and URL path; query
strings and fragments are stripped before any cloud request. FocusPilot never
records keystrokes, screenshots, file contents, passwords, or page contents.
The tracker and browser bridge stop when the session is paused or ended.

When opted in and configured with a Gemini API key, FocusPilot sends your session
goal, browser title, and website/path to the configured Gemini Free model for a
relevance check. Chat messages go to Gemini only when you press Send. Google's
free tier may use prompts to improve its products. The app does not fall back to
a paid model; quota or network failures use the local classifier instead.
Configure a free API key in **Settings → Gemini Free AI**. The key is encrypted
with Windows DPAPI for your Windows account and is omitted from data exports.
Use a Google AI Studio project with billing disabled: FocusPilot does not switch
models, but cannot inspect whether the API key's Google project has billing enabled.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer

## Install and run from source

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m focuspilot
```

The dashboard opens at launch. Closing it hides FocusPilot to the system tray;
choose **Open FocusPilot** or **Quit FocusPilot** from the tray menu.

To enable goal-aware browser checks, open `chrome://extensions` in Chrome or
`edge://extensions` in Edge, enable **Developer mode**, choose **Load unpacked**,
and select the `browser-extension` folder. The extension has no permission to
read page contents; it shares metadata with FocusPilot only during an active
session.

At session start, add one or more `.exe` apps and set the duration and mode.
Gentle/Normal sessions nudge when an unselected app is in use. Strict sessions
ask Windows to close unselected foreground apps; Windows shell, Task Manager,
Settings, lock, and security surfaces remain allowed. Process closing is
best-effort and never runs elevated.

## Build a Windows app bundle

```powershell
python -m pip install -e ".[installer]"
python -m PyInstaller --clean --noconfirm installer\focuspilot.spec
```

The portable bundle is written to `dist\FocusPilot`. If Inno Setup is installed
and `ISCC.exe` is on `PATH`, the script also creates
`dist\installer\FocusPilot-Setup.exe`. The installer offers autostart and asks
separately before deleting local FocusPilot data during uninstall.

## Test and lint

```powershell
pytest
ruff check .
mypy src
```

## Start with Windows

Turn on **Settings → Launch FocusPilot when I sign in**. At sign-in FocusPilot
starts with `--autostart`, opens the dashboard and asks **"What is this session
for?"**. Only one copy can run at a time; launching it again just brings the running
one to the front.

## How activity is judged

Rules look at the app and, for browsers, the *site* in the window title (YouTube in
Chrome is a distraction; LeetCode in Chrome is not). If the window title mentions a
word from your goal, it counts as on-task. "I'm on task" on a nudge saves a rule for
that site/app only, and your latest choice always wins. Time while you are idle for
2+ minutes is never counted as active or as drifting.

## Progress

Each session gives XP (1 per focused minute, +50 for finishing a planned block, +25
for a score of 85+), levels (level *n* needs 300 x *n* XP), a daily focus streak, six
achievements, and short coaching built only from your own numbers.

## Family mode

Parent settings are PIN protected (the PIN lockout survives restarts). Family mode is
visible to the child and provides time-limit, bedtime, allowlist, and blocklist
reminders. List entries match an app name (`chrome`), a type (`study`, `gaming`, ...)
or the window title. During a Child Mode session, pausing, ending, or quitting needs
the parent PIN. It does not silently block or terminate applications, lock the
workstation, or hide monitoring.

## Current boundaries

The classifier uses transparent local app/site rules, not an installed embedding model
or local LLM. Focus scores and activity categories are estimates and should not be
treated as objective judgments. Detailed per-app reports, watchdog protection, app
termination, and workstation locking are not implemented. Child time limits end the
current FocusPilot session with a visible reminder; they do not lock Windows. A
child with administrator rights can still stop the app, so use a standard Windows
account for the child. Session data stays on this device unless you opt in to
Gemini Free AI. With AI enabled, FocusPilot sends the session goal and sanitized
browser metadata for relevance checks; chat text is sent only when you press Send.
The browser extension communicates with FocusPilot over the local loopback
connection. FocusPilot does not use telemetry or send screenshots, keystrokes, or
page contents.
