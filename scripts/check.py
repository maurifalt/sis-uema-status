#!/usr/bin/env python3
"""
Verifica se o SIS-UEMA está no ar e salva o resultado em docs/data/history.json.

Esse script é pensado para rodar via GitHub Actions em intervalos regulares,
mas também funciona rodando localmente: `python scripts/check.py`
"""

import json
import os
import time
from datetime import datetime, timezone

import requests
import urllib3

# Suprime o aviso "InsecureRequestWarning" — sabemos que estamos desativando
# a verificação de propósito, só como fallback de diagnóstico (ver check_site()).
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ----------------------------------------------------------------------
# Configurações
# ----------------------------------------------------------------------
URL = "https://sis.sig.uema.br/"
TIMEOUT_SECONDS = 15

# Quantos registros manter no histórico (evita o JSON crescer pra sempre).
# Ex: verificação a cada 5 min -> 2016 registros = últimos 7 dias.
MAX_HISTORY_ENTRIES = 2016

HISTORY_PATH = os.path.join(
    os.path.dirname(__file__), "..", "docs", "data", "history.json"
)

# Se o site normalmente mostra algum texto conhecido na tela de login
# (ex: "Sistema Integrado de Gestão"), você pode preencher aqui para
# detectar "falso positivo" (site responde 200 mas mostra erro/manutenção).
EXPECTED_TEXT_SNIPPET = None  # ex: "Sistema Integrado de Gestão"


def load_history():
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def check_site():
    start = time.time()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "down",
        "http_status": None,
        "latency_ms": None,
        "error": None,
    }

    try:
        response = requests.get(
            URL,
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": "SIS-UEMA-StatusChecker/1.0"},
            allow_redirects=True,
        )
        latency_ms = round((time.time() - start) * 1000)
        entry["http_status"] = response.status_code
        entry["latency_ms"] = latency_ms

        is_up = response.status_code < 500

        if is_up and EXPECTED_TEXT_SNIPPET:
            is_up = EXPECTED_TEXT_SNIPPET in response.text

        entry["status"] = "up" if is_up else "down"

    except requests.exceptions.Timeout:
        entry["error"] = "timeout"
    except requests.exceptions.SSLError:
        # O certificado do site está com problema (cadeia incompleta, expirado
        # etc.), mas isso não significa necessariamente que o site está fora
        # do ar. Tentamos de novo sem validar o certificado só para checar se
        # o servidor pelo menos responde.
        try:
            fallback_start = time.time()
            response = requests.get(
                URL,
                timeout=TIMEOUT_SECONDS,
                headers={"User-Agent": "SIS-UEMA-StatusChecker/1.0"},
                allow_redirects=True,
                verify=False,
            )
            latency_ms = round((time.time() - fallback_start) * 1000)
            entry["http_status"] = response.status_code
            entry["latency_ms"] = latency_ms
            entry["status"] = "up" if response.status_code < 500 else "down"
            entry["error"] = "ssl_certificate_invalid"
        except requests.exceptions.RequestException as e2:
            entry["error"] = f"ssl_error_and_unreachable: {e2}"
    except requests.exceptions.ConnectionError as e:
        entry["error"] = f"connection_error: {e}"
    except requests.exceptions.RequestException as e:
        entry["error"] = f"request_error: {e}"

    return entry


def main():
    history = load_history()
    entry = check_site()
    history.append(entry)

    # mantém só os últimos N registros
    if len(history) > MAX_HISTORY_ENTRIES:
        history = history[-MAX_HISTORY_ENTRIES:]

    save_history(history)

    print(f"[{entry['timestamp']}] status={entry['status']} "
          f"http={entry['http_status']} latency={entry['latency_ms']}ms "
          f"error={entry['error']}")


if __name__ == "__main__":
    main()
