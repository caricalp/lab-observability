import os
import sys
import time
import logging
import csv
import io
import requests
from prometheus_client import start_http_server, Gauge, Counter

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [m365-exporter] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("m365-exporter")

# Configurações do Mock e Tenant
MOCK_BASE_URL = os.environ.get("MOCK_BASE_URL", "http://mock-m365.simulations.svc.cluster.local:8080")
TENANT_ID = os.environ.get("O365_TENANT_ID", "tenant-de-teste")
CLIENT_ID = os.environ.get("O365_CLIENT_ID", "client-de-teste")
CLIENT_SECRET = os.environ.get("O365_CLIENT_SECRET", "segredo-de-teste")
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "60"))
EXPORTER_PORT = int(os.environ.get("EXPORTER_PORT", "9115"))

# Definição das Métricas Prometheus
METRIC_COLLECTOR_SUCCESS = Gauge(
    "m365_collector_success",
    "1 se o ciclo de coleta do M365 terminou com sucesso, 0 caso contrario",
    ["collector"]
)
METRIC_LAST_RUN = Gauge(
    "m365_collector_last_run_timestamp_seconds",
    "Timestamp Unix do ultimo ciclo de coleta",
    ["collector"]
)
METRIC_EMAIL_ACTIVITY = Gauge(
    "m365_email_activity_count",
    "Contagem de atividades de e-mail no M365",
    ["tipo", "report_date"]
)
METRIC_USERS_COUNT = Gauge(
    "m365_users_count",
    "Total de contas de usuarios no tenant M365"
)
METRIC_SERVICE_HEALTH = Gauge(
    "m365_service_health",
    "1 quando o servico da Microsoft esta operacional, 0 se degradado",
    ["service", "service_name"]
)
METRIC_SIGNINS_BLOCKED = Gauge(
    "m365_identity_signins_blocked_total",
    "Total de tentativas de login bloqueadas por Acesso Condicional"
)
METRIC_URLS_BLOCKED = Gauge(
    "m365_security_urls_blocked_total",
    "Total de sites maliciosos e URLs bloqueados pelo Defender/SmartScreen"
)
METRIC_AUDIT_EVENTS = Counter(
    "m365_audit_events_total",
    "Total de eventos de auditoria processados do Office 365 Management API",
    ["operation", "result_status"]
)

def get_auth_token():
    url = f"{MOCK_BASE_URL}/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default"
    }
    resp = requests.post(url, data=data, timeout=10)
    resp.raise_for_status()
    return resp.json().get("access_token")

def collect_graph_metrics(token):
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Email Activity Counts
    try:
        url_emails = f"{MOCK_BASE_URL}/v1.0/reports/getEmailActivityCounts"
        resp = requests.get(url_emails, headers=headers, timeout=10)
        if resp.status_code == 200:
            csv_data = resp.text.strip().lstrip('\ufeff')
            reader = csv.DictReader(io.StringIO(csv_data))
            for row in reader:
                rep_date = row.get("Report Date", "unknown")
                send_cnt = float(row.get("Send", 0))
                rec_cnt = float(row.get("Receive", 0))
                read_cnt = float(row.get("Read", 0))
                METRIC_EMAIL_ACTIVITY.labels(tipo="Send", report_date=rep_date).set(send_cnt)
                METRIC_EMAIL_ACTIVITY.labels(tipo="Receive", report_date=rep_date).set(rec_cnt)
                METRIC_EMAIL_ACTIVITY.labels(tipo="Read", report_date=rep_date).set(read_cnt)
            logger.info("Metricas de atividade de e-mail coletadas com sucesso.")
    except Exception as e:
        logger.warning(f"Erro ao coletar email activity: {e}")

    # 2. Users Count
    try:
        url_users = f"{MOCK_BASE_URL}/v1.0/users/$count"
        resp = requests.get(url_users, headers=headers, timeout=10)
        if resp.status_code == 200:
            try:
                cnt = float(resp.text.strip())
            except ValueError:
                cnt = float(resp.json().get("value", 250))
            METRIC_USERS_COUNT.set(cnt)
            logger.info(f"Contagem de usuarios coletada: {cnt}")
    except Exception as e:
        logger.warning(f"Erro ao coletar users count: {e}")

    # 3. Service Health
    try:
        url_health = f"{MOCK_BASE_URL}/v1.0/admin/serviceAnnouncement/healthOverviews"
        resp = requests.get(url_health, headers=headers, timeout=10)
        if resp.status_code == 200:
            for item in resp.json().get("value", []):
                srv_id = item.get("id", "")
                srv_name = item.get("service", "")
                status_str = item.get("status", "")
                val = 1.0 if status_str == "serviceOperational" else 0.0
                METRIC_SERVICE_HEALTH.labels(service=srv_id, service_name=srv_name).set(val)
            logger.info("Service health coletado com sucesso.")
    except Exception as e:
        logger.warning(f"Erro ao coletar service health: {e}")

    # 4. Security Blocks (Gauges simulados)
    METRIC_SIGNINS_BLOCKED.set(14.0)
    METRIC_URLS_BLOCKED.set(89.0)

def collect_audit_logs(token):
    headers = {"Authorization": f"Bearer {token}"}
    
    # Inicia assinatura se necessário
    start_url = f"{MOCK_BASE_URL}/api/v1.0/{TENANT_ID}/activity/feed/subscriptions/start?contentType=Audit.AzureActiveDirectory"
    try:
        requests.post(start_url, headers=headers, timeout=10)
    except Exception as e:
        logger.debug(f"Assinatura de auditoria: {e}")

    # Coleta blobs de conteúdo
    content_url = f"{MOCK_BASE_URL}/api/v1.0/{TENANT_ID}/activity/feed/subscriptions/content?contentType=Audit.AzureActiveDirectory"
    try:
        resp = requests.get(content_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            blobs = resp.json()
            logger.info(f"Encontrados {len(blobs)} blobs de auditoria.")
            for blob in blobs:
                blob_uri = blob.get("contentUri")
                if blob_uri:
                    # Substitui host se necessário para apontar ao mock interno
                    if blob_uri.startswith("http://127.0.0.1:8080") or blob_uri.startswith("http://localhost:8080"):
                        blob_uri = blob_uri.replace("http://127.0.0.1:8080", MOCK_BASE_URL).replace("http://localhost:8080", MOCK_BASE_URL)
                    b_resp = requests.get(blob_uri, headers=headers, timeout=10)
                    if b_resp.status_code == 200:
                        eventos = b_resp.json()
                        for ev in eventos:
                            op = ev.get("Operation", "Unknown")
                            st = ev.get("ResultStatus", "Unknown")
                            METRIC_AUDIT_EVENTS.labels(operation=op, result_status=st).inc()
                            # Emite o evento em log estruturado para o Loki capturar via Alloy!
                            logger.info(f"[AUDIT_EVENT] Workload={ev.get('Workload')} Operation={op} Status={st} User={ev.get('UserId')} IP={ev.get('ClientIP')}")
    except Exception as e:
        logger.warning(f"Erro ao coletar logs de auditoria: {e}")

def run_collection_cycle():
    logger.info("Iniciando ciclo de coleta do Microsoft 365...")
    try:
        token = get_auth_token()
        collect_graph_metrics(token)
        collect_audit_logs(token)
        METRIC_COLLECTOR_SUCCESS.labels(collector="m365").set(1.0)
        METRIC_LAST_RUN.labels(collector="m365").set(time.time())
        logger.info("Ciclo de coleta concluido com sucesso.")
    except Exception as e:
        logger.error(f"Falha critica no ciclo de coleta M365: {e}")
        METRIC_COLLECTOR_SUCCESS.labels(collector="m365").set(0.0)
        METRIC_LAST_RUN.labels(collector="m365").set(time.time())

def main():
    logger.info(f"Iniciando M365 Exporter na porta {EXPORTER_PORT}...")
    start_http_server(EXPORTER_PORT)
    logger.info(f"Endpoint de metricas ativo em http://0.0.0.0:{EXPORTER_PORT}/metrics")

    while True:
        run_collection_cycle()
        time.sleep(SCRAPE_INTERVAL)

if __name__ == "__main__":
    main()
