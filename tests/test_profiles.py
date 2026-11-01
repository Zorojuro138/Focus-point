from focuspilot.child.profiles import load_age_profiles


def test_loads_documented_family_defaults() -> None:
    profiles = load_age_profiles()

    assert profiles["5-7"]["daily_limit_min"] == 60
    assert profiles["11-13"]["bedtime_start"] == "21:30"
    assert profiles["14-17"]["daily_limit_min"] == 180


def test_default_allowlists_use_categories_that_the_classifier_produces() -> None:
    valid = {"study", "design", "writing", "research", "coding", "video", "gaming"}
    for profile in load_age_profiles().values():
        assert set(profile["allowlist"]) <= valid
