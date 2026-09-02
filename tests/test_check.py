"""Testes offline do verificador de status do SIS-UEMA (scripts/check.py).

Sem rede: requests.get é sempre mockado; os arquivos de histórico são criados
em tmp_path, nunca no repo.
"""

import json

import check
import requests


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


def make_config(tmp_path, **overrides):
    kwargs = dict(
        url="https://sis.example/login.do",
        timeout=5.0,
        max_history_entries=10,
        history_path=str(tmp_path),
        expected_text_snippet=None,
    )
    kwargs.update(overrides)
    return check.Config(**kwargs)


# ----------------------------------------------------------------------
# load_history / save_history / _atomic_write_json / trim_history
# ----------------------------------------------------------------------
def test_load_history_missing_file(tmp_path):
    missing = str(tmp_path / "nope.json")
    assert check.load_history(missing) == []


def test_load_history_corrupt_json(tmp_path):
    p = tmp_path / "history.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert check.load_history(str(p)) == []


def test_load_history_valid_and_roundtrip(tmp_path):
    p = tmp_path / "history.json"
    entries = [{"status": "up", "http_status": 200}]
    check.save_history(entries, str(p))
    assert p.exists()
    assert check.load_history(str(p)) == entries


def test_load_history_non_list_returns_empty(tmp_path):
    p = tmp_path / "history.json"
    p.write_text('{"status": "up"}', encoding="utf-8")
    assert check.load_history(str(p)) == []


def test_save_history_writes_valid_json_and_removes_tmp(tmp_path):
    p = tmp_path / "history.json"
    check.save_history([{"status": "down"}], str(p))
    assert json.loads(p.read_text(encoding="utf-8")) == [{"status": "down"}]
    assert not (tmp_path / "history.json.tmp").exists()


def test_save_history_creates_parent_dirs(tmp_path):
    p = tmp_path / "nested" / "more" / "history.json"
    check.save_history([], str(p))
    assert p.exists()


def test_atomic_write_preserves_utf8_nonascii(tmp_path):
    p = tmp_path / "history.json"
    check.save_history([{"error": "cadeia incompleta — teste"}], str(p))
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data[0]["error"] == "cadeia incompleta — teste"


def test_trim_history_no_truncate_within_limit():
    history = [{"i": i} for i in range(5)]
    assert check.trim_history(history, 10) == history


def test_trim_history_keeps_last_n():
    history = [{"i": i} for i in range(10)]
    trimmed = check.trim_history(history, 3)
    assert [e["i"] for e in trimmed] == [7, 8, 9]


# ----------------------------------------------------------------------
# check_site
# ----------------------------------------------------------------------
def test_check_site_up(monkeypatch, tmp_path):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResponse(200, "Sistema Integrado de Gestão")
    )
    entry = check.check_site(make_config(tmp_path))
    assert entry["status"] == "up"
    assert entry["http_status"] == 200
    assert isinstance(entry["latency_ms"], int)
    assert entry["error"] is None
    assert entry["timestamp"]


def test_check_site_server_error_down(monkeypatch, tmp_path):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(502, "Bad Gateway"))
    entry = check.check_site(make_config(tmp_path))
    assert entry["status"] == "down"
    assert entry["http_status"] == 502
    assert entry["error"] is None


def test_check_site_timeout(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(requests, "get", boom)
    entry = check.check_site(make_config(tmp_path))
    assert entry["status"] == "down"
    assert entry["http_status"] is None
    assert entry["error"] == "timeout"


def test_check_site_connection_error(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(requests, "get", boom)
    entry = check.check_site(make_config(tmp_path))
    assert entry["status"] == "down"
    assert entry["error"].startswith("connection_error:")


def test_check_site_generic_request_error(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise requests.exceptions.TooManyRedirects("loop")

    monkeypatch.setattr(requests, "get", boom)
    entry = check.check_site(make_config(tmp_path))
    assert entry["status"] == "down"
    assert entry["error"].startswith("request_error:")


def test_check_site_snippet_absent_marks_down(monkeypatch, tmp_path):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResponse(200, "Página de manutenção")
    )
    entry = check.check_site(
        make_config(tmp_path, expected_text_snippet="Sistema Integrado de Gestão")
    )
    assert entry["status"] == "down"


def test_check_site_snippet_present_marks_up(monkeypatch, tmp_path):
    monkeypatch.setattr(
        requests, "get", lambda *a, **k: FakeResponse(200, "Sistema Integrado de Gestão")
    )
    entry = check.check_site(
        make_config(tmp_path, expected_text_snippet="Sistema Integrado de Gestão")
    )
    assert entry["status"] == "up"


def test_check_site_ssl_fallback_reachable(monkeypatch, tmp_path):
    # verify=True falha com SSLError; verify=False responde 200.
    def fake_get(url, **kwargs):
        if kwargs.get("verify", True):
            raise requests.exceptions.SSLError("bad cert")
        return FakeResponse(200, "Sistema Integrado de Gestão")

    monkeypatch.setattr(requests, "get", fake_get)
    entry = check.check_site(make_config(tmp_path))
    assert entry["status"] == "up"
    assert entry["http_status"] == 200
    assert entry["error"] == "ssl_certificate_invalid"


def test_check_site_ssl_fallback_honors_snippet(monkeypatch, tmp_path):
    def fake_get(url, **kwargs):
        if kwargs.get("verify", True):
            raise requests.exceptions.SSLError("bad cert")
        return FakeResponse(200, "Página de manutenção")

    monkeypatch.setattr(requests, "get", fake_get)
    entry = check.check_site(
        make_config(tmp_path, expected_text_snippet="Sistema Integrado de Gestão")
    )
    assert entry["status"] == "down"
    assert entry["error"] == "ssl_certificate_invalid"


def test_check_site_ssl_and_unreachable(monkeypatch, tmp_path):
    def fake_get(url, **kwargs):
        if kwargs.get("verify", True):
            raise requests.exceptions.SSLError("bad cert")
        raise requests.exceptions.ConnectionError("down too")

    monkeypatch.setattr(requests, "get", fake_get)
    entry = check.check_site(make_config(tmp_path))
    assert entry["status"] == "down"
    assert entry["error"].startswith("ssl_error_and_unreachable:")


# ----------------------------------------------------------------------
# Config por variável de ambiente
# ----------------------------------------------------------------------
def test_config_defaults(tmp_path):
    c = check.Config()
    assert c.url == check.DEFAULT_URL
    assert c.timeout == check.DEFAULT_TIMEOUT_SECONDS
    assert c.max_history_entries == check.DEFAULT_MAX_HISTORY_ENTRIES
    assert c.history_path == check.default_history_path()
    assert c.expected_text_snippet is check.EXPECTED_TEXT_SNIPPET


def test_config_url_explicit_beats_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SIS_URL", "https://env.example")
    c = check.Config(url="https://explicit.example")
    assert c.url == "https://explicit.example"


def test_config_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("SIS_URL", "https://env.example/login.do")
    monkeypatch.setenv("SIS_TIMEOUT", "7.5")
    monkeypatch.setenv("SIS_MAX_HISTORY", "42")
    monkeypatch.setenv("SIS_HISTORY_PATH", str(tmp_path / "env.json"))
    monkeypatch.setenv("SIS_EXPECTED_SNIPPET", "Sistema Integrado de Gestão")
    c = check.Config()
    assert c.url == "https://env.example/login.do"
    assert c.timeout == 7.5
    assert c.max_history_entries == 42
    assert c.history_path == str(tmp_path / "env.json")
    assert c.expected_text_snippet == "Sistema Integrado de Gestão"


def test_config_invalid_env_falls_back(monkeypatch, capsys):
    monkeypatch.setenv("SIS_TIMEOUT", "abc")
    monkeypatch.setenv("SIS_MAX_HISTORY", "-3")
    c = check.Config()
    assert c.timeout == check.DEFAULT_TIMEOUT_SECONDS
    assert c.max_history_entries == check.DEFAULT_MAX_HISTORY_ENTRIES
    err = capsys.readouterr().err
    assert "SIS_TIMEOUT" in err and "SIS_MAX_HISTORY" in err


def test_config_snippet_precedence(monkeypatch):
    # constante do módulo é o fallback final
    monkeypatch.delenv("SIS_EXPECTED_SNIPPET", raising=False)
    check.EXPECTED_TEXT_SNIPPET = "Legacy Snippet"
    try:
        assert check.Config().expected_text_snippet == "Legacy Snippet"
        # explícito vence a constante
        assert check.Config(expected_text_snippet="Explicit").expected_text_snippet == "Explicit"
    finally:
        check.EXPECTED_TEXT_SNIPPET = None


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def test_version(monkeypatch, capsys):
    assert check.main(["--version"]) == 0
    out = capsys.readouterr().out.strip()
    assert out == f"sis-uema-status {check.__version__}"


def test_default_main_appends_entry(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SIS_HISTORY_PATH", str(tmp_path / "h.json"))
    monkeypatch.setattr(check, "check_site", lambda *a, **k: {"status": "up", "http_status": 200})
    assert check.main([]) == 0
    data = json.loads((tmp_path / "h.json").read_text(encoding="utf-8"))
    assert len(data) == 1 and data[0]["status"] == "up"
    assert "status=up" in capsys.readouterr().out


def test_main_trims_history(monkeypatch, tmp_path):
    monkeypatch.setenv("SIS_HISTORY_PATH", str(tmp_path / "h.json"))
    check.save_history([{"status": "up"} for _ in range(50)], str(tmp_path / "h.json"))
    monkeypatch.setattr(check, "check_site", lambda *a, **k: {"status": "down"})
    monkeypatch.setenv("SIS_MAX_HISTORY", "10")
    assert check.main([]) == 0
    data = json.loads((tmp_path / "h.json").read_text(encoding="utf-8"))
    assert len(data) == 10


def test_dry_run_does_not_write(monkeypatch, tmp_path):
    monkeypatch.setenv("SIS_HISTORY_PATH", str(tmp_path / "h.json"))
    monkeypatch.setattr(check, "check_site", lambda *a, **k: {"status": "up"})
    assert check.main(["--dry-run"]) == 0
    assert not (tmp_path / "h.json").exists()


def test_history_flag_prints_entries(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SIS_HISTORY_PATH", str(tmp_path / "h.json"))
    pairs = [("up", 200), ("down", 500), ("up", 200), ("down", None)]
    history = [
        {
            "timestamp": f"2026-09-01T0{i}:00:00+00:00",
            "status": s,
            "http_status": st,
            "latency_ms": 1,
            "error": None,
        }
        for i, (s, st) in enumerate(pairs)
    ]
    check.save_history(history, str(tmp_path / "h.json"))
    assert check.main(["--history", "2"]) == 0
    out = capsys.readouterr().out
    assert "status=up" in out and "status=down" in out
    assert out.count("status=") == 2


def test_history_json_flag(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SIS_HISTORY_PATH", str(tmp_path / "h.json"))
    check.save_history([{"status": "up"}], str(tmp_path / "h.json"))
    assert check.main(["--history-json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == [{"status": "up"}]


def test_check_flag_is_default(monkeypatch, tmp_path):
    # --check equivalente ao comportamento padrão (registra no histórico)
    monkeypatch.setenv("SIS_HISTORY_PATH", str(tmp_path / "h.json"))
    monkeypatch.setattr(check, "check_site", lambda *a, **k: {"status": "up"})
    assert check.main(["--check"]) == 0
    assert (tmp_path / "h.json").exists()
