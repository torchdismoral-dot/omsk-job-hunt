import logging
import sys

import pytest

from jobhunt.bot.app import setup_logging
from jobhunt.config import load_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("ADMIN_ID", raising=False)
    monkeypatch.chdir(tmp_path)
    yield


def stream_handlers():
    return [h for h in logging.getLogger().handlers if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)]


def file_handlers():
    return [h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler)]


def test_logging_goes_to_stdout(tmp_path):
    setup_logging(str(tmp_path / "bot.log"))
    streams = stream_handlers()
    assert streams, "нет потокового хендлера: PaaS не увидит логи"
    assert streams[0].stream is sys.stdout
    for handler in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(handler)


def test_unwritable_log_file_does_not_crash(tmp_path):
    setup_logging(str(tmp_path))  # каталог вместо файла: open() упадёт с OSError
    assert stream_handlers(), "логирование в stdout должно остаться"
    assert not file_handlers()
    for handler in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(handler)


def test_empty_log_path_skips_file(tmp_path):
    setup_logging("")
    assert stream_handlers()
    assert not file_handlers()
    for handler in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(handler)


def test_pythonw_without_stdout_still_logs_to_file(tmp_path, monkeypatch):
    # Планировщик Windows запускает бота через pythonw: sys.stdout and sys.stderr are None.
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    setup_logging(str(tmp_path / "bot.log"))
    assert file_handlers(), "без stdout логи обязаны идти в файл"
    logging.getLogger("probe").info("строка в файл")
    assert "строка в файл" in (tmp_path / "bot.log").read_text(encoding="utf-8")
    for handler in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(handler)


def write_config(tmp_path, admin_line="admin_id: 111"):
    (tmp_path / "config.yaml").write_text(admin_line + "\n", encoding="utf-8")
    return tmp_path / "config.yaml"


def test_admin_id_from_env_beats_config(tmp_path, monkeypatch):
    path = write_config(tmp_path, "admin_id: 111")
    monkeypatch.setenv("ADMIN_ID", "222")
    assert load_config(path).admin_id == 222


def test_admin_id_from_config_when_env_absent(tmp_path):
    path = write_config(tmp_path, "admin_id: 111")
    assert load_config(path).admin_id == 111


def test_invalid_admin_id_is_none(tmp_path, monkeypatch):
    path = write_config(tmp_path, "admin_id: 111")
    monkeypatch.setenv("ADMIN_ID", "not-a-number")
    assert load_config(path).admin_id is None


def test_no_admin_id_anywhere(tmp_path):
    path = write_config(tmp_path, "# пусто")
    assert load_config(path).admin_id is None
