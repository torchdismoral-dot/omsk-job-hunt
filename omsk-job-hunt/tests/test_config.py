import pathlib

from jobhunt.config import load_config

REPO_CONFIG = pathlib.Path(__file__).resolve().parents[1] / "config.yaml"

HH_SECTION = """
hh:
  enabled: false
  area_omsk: 68
  area_remote: 0
  max_pages_remote: 4
  delay_ms: 200
  search_period_days: 1
"""


def write_config(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_hh_defaults_without_section(tmp_path, monkeypatch):
    monkeypatch.delenv("HH_PROXY", raising=False)
    settings = load_config(write_config(tmp_path, "# пусто"))
    assert settings.sources.hh_enabled is True
    assert settings.sources.hh_area_omsk == 68
    assert settings.sources.hh_area_remote == 113
    assert settings.sources.hh_max_pages_omsk == 15
    assert settings.sources.hh_max_pages_remote == 12
    assert settings.sources.hh_delay_ms == 1500


def test_hh_section_overrides_defaults(tmp_path):
    settings = load_config(write_config(tmp_path, HH_SECTION))
    assert settings.sources.hh_enabled is False
    assert settings.sources.hh_area_remote == 0
    assert settings.sources.hh_max_pages_remote == 4
    assert settings.sources.hh_delay_ms == 200
    assert settings.sources.hh_search_period_days == 1


def test_hh_proxy_comes_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HH_PROXY", "http://user:pass@host:8080")
    settings = load_config(write_config(tmp_path, "#"))
    assert settings.hh_proxy == "http://user:pass@host:8080"


def test_hh_proxy_none_when_env_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("HH_PROXY", "")
    settings = load_config(write_config(tmp_path, "#"))
    assert settings.hh_proxy is None


def test_hh_proxy_env_name_is_configurable(tmp_path, monkeypatch):
    monkeypatch.delenv("HH_PROXY", raising=False)
    monkeypatch.setenv("MY_PROXY", "http://host:3128")
    path = write_config(tmp_path, "hh:\n  proxy_env: MY_PROXY\n")
    assert load_config(path).hh_proxy == "http://host:3128"


def test_shipped_config_enables_hh():
    settings = load_config(REPO_CONFIG)
    assert settings.sources.hh_enabled is True
    assert settings.sources.hh_base_url == "https://hh.ru"
    assert settings.sources.hh_area_remote == 113
