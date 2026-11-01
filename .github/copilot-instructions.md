# FocusPilot project instructions

Build FocusPilot as a Windows 10/11 desktop app using Python 3.11+ and PySide6.
Follow the architecture and data model in the attached FocusPilot build prompt.
Implement it incrementally, phase by phase, with pytest coverage for core logic.

Privacy and safety requirements:

- Keep session data local by default; do not add telemetry. Any optional network
  feature must be explicitly opt-in, disclose exactly what is sent and to whom,
  and send only the minimum required data.
- Track only foreground process/window title, timestamps, and idle state.
- Never capture keystrokes, screenshots, file contents, or passwords.
- Obtain clear consent before tracking; always show a tray icon while tracking.
- Child Mode must be transparent to the child and require parent consent.
- Keep tracking and AI work off the UI thread.
