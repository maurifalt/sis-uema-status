#!/usr/bin/env python3
"""
Verifica se o SIS-UEMA está no ar e salva o resultado em docs/data/history.json.

Esse script é pensado para rodar via GitHub Actions em intervalos regulares,
mas também funciona rodando localmente: `python scripts/check.py`.

Tudo pode ser sobrescrito por variáveis de ambiente (sem precisar editar o
código): SIS_URL, SIS_TIMEOUT, SIS_MAX_HISTORY, SIS_HISTORY_PATH e
SIS_EXPECTED_SNIPPET. Veja o README para detalhes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import urllib3

# Suprime o aviso "InsecureRequestWarning" — sabemos que estamos desativando
# a verificação de propósito, só como fallback de diagnóstico (ver check_site()).
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

__version__ = "1.1.0"

# ----------------------------------------------------------------------
# Configurações (defaults)
# ----------------------------------------------------------------------
DEFAULT_URL = "https://sis.sig.uema.br/sigaa/verTelaLogin.do"
DEFAULT_TIMEOUT_SECONDS = 15.0

# Quantos registros manter no histórico (evita o JSON crescer pra sempre).
# Ex: verificação a cada 5 min -> 2016 registros = últimos 7 dias.
DEFAULT_MAX_HISTORY_ENTRIES = 2016

# Caminho padrão do histórico. Pode ser sobrescrito por SIS_HISTORY_PATH.
_DEFAULT_HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "docs", "data", "history.json"
)

# Se o site normalmente mostra algum texto conhecido na tela de login
# (ex: "Sistema Integrado de Gestão"), você pode preencher aqui para
# detectar "falso positivo" (site responde 200 mas mostra erro/manutenção).
# Alternativa moderna sem editar o código: variável SIS_EXPECTED_SNIPPET.
EXPECTED_TEXT_SNIPPET = None  # ex: "Sistema Integrado de Gestão"

USER_AGENT = "SIS-UEMA-StatusChecker/1.1"


def default_history_path() -> str:
    """Caminho padrão para o arquivo de histórico."""
    return _DEFAULT_HISTORY_PATH


# ----------------------------------------------------------------------
# Helpers de configuração por ambiente
# ----------------------------------------------------------------------
def _env_float(name: str, default: float) -> float:
    """Lê um float do ambiente com fallback e validação (evita crash em runtime)."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        print(f"[aviso] {name}={raw!r} inválido; usando padrão {default}", file=sys.stderr)
        return default
    if value <= 0:
        print(f"[aviso] {name} deve ser positivo; usando padrão {default}", file=sys.stderr)
        return default
    return value


def _env_int(name: str, default: int) -> int:
    """Lê um inteiro do ambiente com fallback e validação."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        print(f"[aviso] {name}={raw!r} inválido; usando padrão {default}", file=sys.stderr)
        return default
    if value <= 0:
        print(f"[aviso] {name} deve ser positivo; usando padrão {default}", file=sys.stderr)
        return default
    return value


# ----------------------------------------------------------------------
# Configuração em tempo de execução
# ----------------------------------------------------------------------
class Config:
    """Configuração resolvida com precedência: argumento explícito > env > default."""

    def __init__(
        self,
        url: str | None = None,
        timeout: float | None = None,
        max_history_entries: int | None = None,
        history_path: str | None = None,
        expected_text_snippet: str | None = None,
    ):
        self.url = url or os.environ.get("SIS_URL") or DEFAULT_URL
        self.timeout = (
            timeout
            if timeout is not None
            else _env_float("SIS_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
        )
        self.max_history_entries = (
            max_history_entries
            if max_history_entries is not None
            else _env_int("SIS_MAX_HISTORY", DEFAULT_MAX_HISTORY_ENTRIES)
        )
        self.history_path = (
            history_path or os.environ.get("SIS_HISTORY_PATH") or default_history_path()
        )
        if expected_text_snippet is not None:
            self.expected_text_snippet = expected_text_snippet
        else:
            env_snippet = os.environ.get("SIS_EXPECTED_SNIPPET")
            self.expected_text_snippet = (
                env_snippet if env_snippet is not None else EXPECTED_TEXT_SNIPPET
            )


# ----------------------------------------------------------------------
# Persistência
# ----------------------------------------------------------------------
def load_history(path: str | None = None) -> list[dict[str, Any]]:
    """Lê o histórico; retorna [] se o arquivo não existe ou está corrompido."""
    path = path or default_history_path()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _atomic_write_json(path: str, data: Any) -> None:
    """Grava JSON de forma atômica (arquivo temporário + os.replace).

    Evita quebrar o histórico em caso de interrupção no meio da escrita —
    sem isso, um commit/processo morrendo no meio deixaria o arquivo truncado
    e forçaria um reinício do histórico do zero.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, target)


def save_history(history: list[dict[str, Any]], path: str | None = None) -> None:
    """Grava o histórico inteiro no arquivo (escrita atômica)."""
    _atomic_write_json(path or default_history_path(), history)


def trim_history(history: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Mantém apenas os últimos `limit` registros."""
    if limit > 0 and len(history) > limit:
        return history[-limit:]
    return history


# ----------------------------------------------------------------------
# Verificação do site
# ----------------------------------------------------------------------
def _request(config: Config, verify: bool = True):
    """Faz o GET e retorna (http_status, latency_ms, body_text)."""
    start = time.time()
    response = requests.get(
        config.url,
        timeout=config.timeout,
        headers={"User-Agent": USER_AGENT},
        allow_redirects=True,
        verify=verify,
    )
    latency_ms = round((time.time() - start) * 1000)
    return response.status_code, latency_ms, response.text


def _decide_up(status: int, body: str, expected_snippet: str | None) -> bool:
    """Um site está "up" se responde < 500 e, quando configurado, contém o texto
    esperado da tela de login (para não confundir página de manutenção com normal)."""
    is_up = status < 500
    if is_up and expected_snippet:
        is_up = expected_snippet in body
    return is_up


def check_site(config: Config | None = None) -> dict[str, Any]:
    """Verifica a disponibilidade do site e devolve uma entrada de histórico."""
    config = config or Config()
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "down",
        "http_status": None,
        "latency_ms": None,
        "error": None,
    }

    try:
        status, latency, body = _request(config, verify=True)
    except requests.exceptions.Timeout:
        entry["error"] = "timeout"
        return entry
    except requests.exceptions.SSLError:
        # O certificado do site está com problema (cadeia incompleta, expirado
        # etc.), mas isso não significa necessariamente que o site está fora
        # do ar. Tentamos de novo sem validar o certificado só para checar se
        # o servidor pelo menos responde.
        try:
            status, latency, body = _request(config, verify=False)
        except requests.exceptions.RequestException as e2:
            entry["error"] = f"ssl_error_and_unreachable: {e2}"
            return entry
        entry["http_status"] = status
        entry["latency_ms"] = latency
        entry["status"] = "up" if _decide_up(status, body, config.expected_text_snippet) else "down"
        entry["error"] = "ssl_certificate_invalid"
        return entry
    except requests.exceptions.ConnectionError as e:
        entry["error"] = f"connection_error: {e}"
        return entry
    except requests.exceptions.RequestException as e:
        entry["error"] = f"request_error: {e}"
        return entry

    entry["http_status"] = status
    entry["latency_ms"] = latency
    entry["status"] = "up" if _decide_up(status, body, config.expected_text_snippet) else "down"
    return entry


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check",
        description="Verifica a disponibilidade do SIS-UEMA e mantém docs/data/history.json.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verifica agora e registra no histórico (comportamento padrão)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="verifica agora sem alterar o histórico (não grava nada)",
    )
    parser.add_argument(
        "--history",
        nargs="?",
        const=10,
        type=int,
        metavar="N",
        help="mostra as últimas N entradas do histórico (padrão: 10)",
    )
    parser.add_argument(
        "--history-json",
        action="store_true",
        help="imprime o histórico completo como JSON em stdout",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="mostra a versão e sai",
    )
    return parser


def _format_entry(entry: dict[str, Any]) -> str:
    ts = entry.get("timestamp", "?")
    status = entry.get("status", "?")
    http = entry.get("http_status")
    latency = entry.get("latency_ms")
    error = entry.get("error")
    return f"{ts} status={status} http={http} latency={latency}ms error={error}"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = Config()

    if args.version:
        print(f"sis-uema-status {__version__}")
        return 0

    if args.history_json:
        print(json.dumps(load_history(config.history_path), ensure_ascii=False, indent=2))
        return 0

    if args.history is not None:
        history = load_history(config.history_path)
        print("\n".join(_format_entry(e) for e in history[-args.history:]))
        return 0

    # default: check (grava) — a menos que --dry-run
    entry = check_site(config)
    if not args.dry_run:
        history = load_history(config.history_path)
        history.append(entry)
        history = trim_history(history, config.max_history_entries)
        save_history(history, config.history_path)

    print(_format_entry(entry))
    return 0


if __name__ == "__main__":
    sys.exit(main())
