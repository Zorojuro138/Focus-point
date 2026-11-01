import json
from datetime import datetime

from focuspilot.child.parent_auth import ParentPinVerifier, hash_pin, verify_pin
from focuspilot.child.policy_engine import evaluate_child_policy


def test_child_policy_warns_near_daily_limit() -> None:
    result = evaluate_child_policy(
        daily_usage_s=7200 - 60,
        daily_limit_min=120,
        bedtime_start="21:00",
        bedtime_end="07:00",
        now=datetime(2026, 10, 31, 14, 0),
        process_name="browser.exe",
    )

    assert result.status == "limit_warning"


def test_child_policy_respects_overnight_bedtime() -> None:
    result = evaluate_child_policy(
        daily_usage_s=0,
        daily_limit_min=120,
        bedtime_start="21:00",
        bedtime_end="07:00",
        now=datetime(2026, 10, 31, 22, 0),
        process_name="browser.exe",
    )

    assert result.status == "bedtime_warning"


def test_parent_pin_is_hashed_and_verifiable() -> None:
    encoded = hash_pin("1234")

    assert encoded != "1234"
    assert verify_pin("1234", encoded)
    assert not verify_pin("0000", encoded)


def test_parent_pin_locks_after_five_failed_attempts() -> None:
    clock = [0.0]
    verifier = ParentPinVerifier(clock=lambda: clock[0])
    encoded = hash_pin("1234")

    for _ in range(5):
        assert not verifier.verify("0000", encoded)
    assert verifier.locked_seconds == 300
    assert not verifier.verify("1234", encoded)

    clock[0] = 300
    assert verifier.verify("1234", encoded)


def _policy(**overrides):
    values = {
        "daily_usage_s": 0,
        "daily_limit_min": 120,
        "bedtime_start": "21:00",
        "bedtime_end": "07:00",
        "now": datetime(2026, 10, 31, 14, 0),
        "process_name": "chrome.exe",
    }
    values.update(overrides)
    return evaluate_child_policy(**values)


def test_identical_bedtime_times_mean_no_screen_free_period() -> None:
    assert _policy(bedtime_start="21:00", bedtime_end="21:00").status == "allowed"
    assert _policy(bedtime_start="00:00", bedtime_end="00:00").status == "allowed"


def test_default_young_child_allowlist_does_not_flag_every_app() -> None:
    from focuspilot.child.profiles import load_age_profiles

    allowlist = json.dumps(load_age_profiles()["5-7"]["allowlist"])

    study_app = _policy(
        process_name="anki.exe", category="study", window_title="Anki", allowlist_json=allowlist
    )
    game = _policy(
        process_name="steam.exe", category="gaming", window_title="Steam", allowlist_json=allowlist
    )

    assert study_app.status == "allowed"
    assert game.status == "allowlist_warning"


def test_blocklist_can_match_a_category() -> None:
    result = _policy(process_name="steam.exe", category="gaming", blocklist_json='["gaming"]')

    assert result.status == "app_warning"


def test_own_app_is_exempt_from_app_lists() -> None:
    result = _policy(process_name="python.exe", allowlist_json='["study"]', exempt=True)

    assert result.status == "allowed"


def test_corrupt_rule_lists_do_not_crash() -> None:
    assert _policy(allowlist_json="{not json", blocklist_json="42").status == "allowed"


def test_limit_reached() -> None:
    assert _policy(daily_usage_s=7200).status == "limit_reached"


def test_wrong_pin_with_garbage_hash_is_rejected_not_raised() -> None:
    assert verify_pin("1234", "not-a-real-hash") is False


def test_pin_lockout_survives_a_restart() -> None:
    class Store:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get(self, key: str, default: str = "") -> str:
            return self.data.get(key, default)

        def put(self, key: str, value: str) -> None:
            self.data[key] = value

    store = Store()
    encoded = hash_pin("1234")
    first = ParentPinVerifier(clock=lambda: 100.0, store=store)
    for _ in range(5):
        first.verify("0000", encoded)

    restarted = ParentPinVerifier(clock=lambda: 110.0, store=store)
    assert restarted.locked_seconds > 0
    assert not restarted.verify("1234", encoded)
