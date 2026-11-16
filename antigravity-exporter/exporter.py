import os
import sys
import time
import glob
import json
import logging
import requests
from prometheus_client import start_http_server, Counter, Gauge

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [antigravity-telemetry] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("antigravity-telemetry")

# Configurações de Ambiente
LOGS_DIR = os.environ.get("GEMINI_DIR", "/root/.gemini")
ALLOY_OTLP_URL = os.environ.get("ALLOY_OTLP_URL", "http://grafana-alloy.observability.svc.cluster.local:4318/v1/metrics")
EXPORTER_PORT = int(os.environ.get("EXPORTER_PORT", "9125"))
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "15"))

# ==============================================================================
# DEFINIÇÃO DAS MÉTRICAS PROMETHEUS (ANTIGRAVITY TELEMETRY)
# ==============================================================================

METRIC_TOKENS = Counter(
    "antigravity_token_usage_total",
    "Consumo total de tokens de LLM na Antigravity",
    ["model", "token_type"]
)

METRIC_REQUESTS = Counter(
    "antigravity_requests_total",
    "Total de requisicoes realizadas por modelo na Antigravity",
    ["model", "status"]
)

METRIC_ERRORS = Counter(
    "antigravity_errors_total",
    "Total de erros de API ou quota na Antigravity",
    ["error_type"]
)

METRIC_SESSIONS = Gauge(
    "antigravity_sessions_total",
    "Total de sessoes ativas registradas na Antigravity"
)

# Estado de leitura de arquivos (arquivo -> último offset lido)
file_offsets = {}

def send_otlp_metric(model, token_type, value):
    """Envia a métrica de consumo de token via OTLP JSON para o Grafana Alloy."""
    payload = {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "antigravity"}},
                        {"key": "deployment.environment", "value": {"stringValue": "production"}},
                        {"key": "host.name", "value": {"stringValue": "container"}}
                    ]
                },
                "scopeMetrics": [
                    {
                        "scope": {"name": "antigravity.telemetry", "version": "1.0"},
                        "metrics": [
                            {
                                "name": "antigravity_token_usage_total",
                                "description": "Consumo de tokens de LLM por modelo",
                                "unit": "1",
                                "sum": {
                                    "aggregationTemporality": 2,
                                    "isMonotonic": True,
                                    "dataPoints": [
                                        {
                                            "asInt": int(value),
                                            "timeUnixNano": str(int(time.time() * 1e9)),
                                            "attributes": [
                                                {"key": "model", "value": {"stringValue": model}},
                                                {"key": "token_type", "value": {"stringValue": token_type}}
                                            ]
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                ]
            }
        ]
    }
    try:
        requests.post(ALLOY_OTLP_URL, json=payload, headers={"Content-Type": "application/json"}, timeout=3)
    except Exception as e:
        logger.debug(f"Falha ao enviar metricas OTLP: {e}")

def process_file(file_path):
    last_offset = file_offsets.get(file_path, 0)
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            f.seek(last_offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    msg_type = data.get("type")
                    
                    if msg_type == "gemini":
                        model = data.get("model", "unknown-model")
                        tokens = data.get("tokens", {})
                        
                        METRIC_REQUESTS.labels(model=model, status="success").inc()
                        
                        for t_type in ["input", "output", "cached", "thoughts", "tool", "total"]:
                            val = tokens.get(t_type, 0)
                            if val:
                                METRIC_TOKENS.labels(model=model, token_type=t_type).inc(val)
                                send_otlp_metric(model, t_type, val)
                                
                        logger.info(f"[CONSUMO DETECTADO] Modelo={model} Tokens={tokens}")

                    elif msg_type == "error":
                        err_content = data.get("content", "")
                        err_type = "quota_exhausted" if "quota" in err_content.lower() else "api_error"
                        METRIC_ERRORS.labels(error_type=err_type).inc()
                        logger.warning(f"[ERRO DETECTADO] Tipo={err_type} Detalhe={err_content[:100]}")

                except Exception:
                    pass
            file_offsets[file_path] = f.tell()
    except Exception as e:
        logger.warning(f"Erro ao ler {file_path}: {e}")

def scan_sessions():
    search_pattern = os.path.join(LOGS_DIR, "tmp", "*", "chats", "*.jsonl")
    files = glob.glob(search_pattern)
    METRIC_SESSIONS.set(len(files))
    for f in files:
        process_file(f)

def main():
    logger.info(f"Iniciando Antigravity Telemetry Exporter na porta {EXPORTER_PORT}...")
    start_http_server(EXPORTER_PORT)
    logger.info(f"Endpoint Prometheus ativo em http://0.0.0.0:{EXPORTER_PORT}/metrics")
    logger.info(f"Despacho OTLP configurado para {ALLOY_OTLP_URL}")

    while True:
        try:
            scan_sessions()
        except Exception as e:
            logger.error(f"Erro durante varredura: {e}")
        time.sleep(SCRAPE_INTERVAL)

if __name__ == "__main__":
    main()
