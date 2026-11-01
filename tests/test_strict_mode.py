from focuspilot.system.strict_mode import is_allowed_app, normalize_app_name


def test_selected_apps_are_matched_by_executable_name_only() -> None:
    assert normalize_app_name(r"C:\Program Files\Code.exe") == "code.exe"
    assert is_allowed_app("CODE.EXE", [r"C:\Program Files\Code.exe"])
    assert not is_allowed_app("chrome.exe", ["Code.exe"])


def test_windows_recovery_and_security_tools_remain_available() -> None:
    for process in ("explorer.exe", "Taskmgr.exe", "SystemSettings.exe", "LockApp.exe"):
        assert is_allowed_app(process, [])
