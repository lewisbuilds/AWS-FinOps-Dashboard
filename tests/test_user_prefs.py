import json
from pathlib import Path
from app.user_prefs import load_prefs, save_prefs, apply_threshold_overrides, override_required_tags, _principal_hash


def test_load_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    arn = "arn:aws:iam::123456789012:user/test"
    prefs = load_prefs(arn)
    assert 'overview_widgets' in prefs
    assert prefs['version'] == 1


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    arn = "arn:aws:iam::123456789012:user/test2"
    prefs = load_prefs(arn)
    prefs['overview_widgets'] = ['yesterday_cost']
    prefs['daily_cost_warning'] = 123.45
    save_prefs(arn, prefs)
    again = load_prefs(arn)
    assert again['overview_widgets'] == ['yesterday_cost']
    assert again['daily_cost_warning'] == 123.45


def test_threshold_override_logic():
    global_thresholds = {"daily_warning": 100.0, "monthly_warning": 1000.0, "anomaly_threshold": 0.2}
    prefs = {"daily_cost_warning": 50.0, "monthly_cost_warning": None}
    applied = apply_threshold_overrides(global_thresholds, prefs)
    assert applied['daily_warning'] == 50.0
    assert applied['monthly_warning'] == 1000.0  # unchanged


def test_tag_override_logic():
    global_tags = ['Environment', 'Owner']
    prefs = {"required_tag_keys": "Environment,Team"}
    tags = override_required_tags(global_tags, prefs)
    assert tags == ['Environment', 'Team']


def test_invalid_json_recovery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from app import user_prefs
    arn = "arn:aws:iam::123456789012:user/bad"
    # create corrupt file
    h = _principal_hash(arn)
    p = Path('.finops_prefs') / f"prefs-{h}.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text('{not json', encoding='utf-8')
    prefs = load_prefs(arn)
    assert 'overview_widgets' in prefs  # recovered defaults
