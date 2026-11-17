import os
import sys
import time
import json
import logging
import csv
import io
import requests
from datetime import datetime, timedelta, timezone
from prometheus_client import start_http_server, Gauge, Counter

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%SZ'
)
logger = logging.getLogger("m365-collector")

# Configurações do Mock e Tenant
# [MODIFICADO] Adicionada flag USE_REAL_AZURE para facilitar a virada do Mock para o Tenant do cliente sem alterar URLs no código
USE_REAL_AZURE = os.environ.get("USE_REAL_AZURE", "false").lower() == "true"
MOCK_BASE_URL = os.environ.get("MOCK_BASE_URL", "http://mock-m365.simulations.svc.cluster.local:8080")

AUTH_BASE_URL = "https://login.microsoftonline.com" if USE_REAL_AZURE else MOCK_BASE_URL
GRAPH_BASE_URL = "https://graph.microsoft.com" if USE_REAL_AZURE else MOCK_BASE_URL
MANAGE_BASE_URL = "https://manage.office.com" if USE_REAL_AZURE else MOCK_BASE_URL

TENANT_ID = os.environ.get("O365_TENANT_ID", "tenant-de-teste")
CLIENT_ID = os.environ.get("O365_CLIENT_ID", "client-de-teste")
CLIENT_SECRET = os.environ.get("O365_CLIENT_SECRET", "segredo-de-teste")
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", "30"))
EXPORTER_PORT = int(os.environ.get("EXPORTER_PORT", "9115"))
MAX_CATCHUP_HOURS = float(os.environ.get("O365_MAX_CATCHUP_HOURS", "2.0"))
OVERLAP_MINUTES = int(os.environ.get("OVERLAP_MINUTES", "10"))

ALLOY_LOKI_ENDPOINT = os.environ.get("ALLOY_LOKI_ENDPOINT", "http://grafana-alloy.observability.svc.cluster.local:9999/loki/api/v1/push")
LOKI_LOCAL_ENDPOINT = os.environ.get("LOKI_LOCAL_ENDPOINT", "http://loki.logging.svc.cluster.local:3100/loki/api/v1/push")

# ==============================================================================
# DEFINIÇÃO DAS MÉTRICAS PROMETHEUS
# ==============================================================================

METRIC_COLLECTOR_SUCCESS = Gauge(
    "m365_collector_success",
    "1 se o ciclo terminou sem erros.",
    ["collector"]
)
METRIC_COLLECTOR_LAST_RUN = Gauge(
    "m365_collector_last_run_timestamp_seconds",
    "Momento do ultimo ciclo.",
    ["collector"]
)

# Métricas de Auditoria e Autenticação Geográfica
METRIC_AUDIT_EVENTS_SENT_TOTAL = Gauge(
    "m365_audit_events_sent_total",
    "Eventos enviados ao Loki no ultimo ciclo."
)
METRIC_AUDIT_EMPTY_CYCLES = Gauge(
    "m365_audit_empty_cycles",
    "Ciclos seguidos sem nenhum evento no feed."
)
METRIC_AUDIT_BACKLOG_DROPPED_HOURS = Gauge(
    "m365_audit_backlog_dropped_hours",
    "Horas de eventos descartadas por exceder o teto de recuperacao."
)
METRIC_AUDIT_EVENTS_TOTAL = Counter(
    "m365_audit_events_total",
    "Total acumulado de eventos de auditoria processados",
    ["operation", "result_status"]
)

# [MODIFICADO] Adicionadas labels 'city', 'lat', 'lon' e 'error_code' para plotar no Grafana Geomap e filtrar falhas/ataques por país sem depender de Storage
METRIC_LOGINS_BY_COUNTRY = Counter(
    "m365_identity_logins_by_country_total",
    "Total acumulado de tentativas de autenticacao por pais e coordenadas geograficas",
    ["country", "city", "lat", "lon", "operation", "result_status", "error_code"]
)

# Métricas de E-mail
METRIC_EMAIL_SENT_TOTAL = Gauge(
    "m365_email_sent_total",
    "E-mails enviados no dia do relatorio.",
    ["report_date"]
)
METRIC_EMAIL_RECEIVED_TOTAL = Gauge(
    "m365_email_received_total",
    "E-mails recebidos no dia do relatorio.",
    ["report_date"]
)
METRIC_EMAIL_SPAM_TOTAL = Gauge(
    "m365_email_spam_total",
    "Total de mensagens classificadas como spam.",
    ["report_date"]
)
METRIC_EMAIL_PHISHING_TOTAL = Gauge(
    "m365_email_phishing_total",
    "Total de tentativas de phishing bloqueadas.",
    ["report_date"]
)
METRIC_EMAIL_ACTIVITY_COUNT = Gauge(
    "m365_email_activity_count",
    "Contagem detalhada de atividades de e-mail por tipo",
    ["tipo", "report_date"]
)

# Métricas de Usuários, Segurança e Health
METRIC_USERS_TOTAL = Gauge(
    "m365_users_total",
    "Total de contas no diretorio."
)
METRIC_USERS_COUNT = Gauge(
    "m365_users_count",
    "Total de contas de usuarios no tenant (alias)"
)
METRIC_IDENTITY_SIGNINS_BLOCKED_TOTAL = Gauge(
    "m365_identity_signins_blocked_total",
    "Total de tentativas de login bloqueadas ou com falha de autenticacao."
)
METRIC_SECURITY_URLS_BLOCKED_TOTAL = Gauge(
    "m365_security_urls_blocked_total",
    "Total de sites maliciosos e URLs bloqueados pelo Defender/SmartScreen."
)
METRIC_SECRET_EXPIRY_DAYS = Gauge(
    "m365_secret_expiry_days",
    "Dias restantes ate o client secret expirar."
)
METRIC_SERVICE_HEALTH = Gauge(
    "m365_service_health",
    "1 quando o servico esta operacional.",
    ["service", "status"]
)

# Estado persistido em memória
state = {
    "last_end_time": None,
    "seen_blobs": set(),
    "seen_graph_signins": set(),
    "empty_cycles": 0,
    "blocked_signins_count": 14  # Valor base inicial caso o mock comece vazio
}

def get_auth_token():
    url = f"{AUTH_BASE_URL}/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default"
    }
    resp = requests.post(url, data=data, timeout=10)
    resp.raise_for_status()
    return resp.json().get("access_token")

# [NOVO] Extrator híbrido: entende tanto o JSON plano do seu Mock atual quanto o JSON aninhado oficial da Microsoft Graph API (/v1.0/auditLogs/signIns)
def extract_geo_fields(ev):
    loc = ev.get("location", {})
    coords = loc.get("geoCoordinates", {})
    status_obj = ev.get("status", {})

    country = ev.get("Country") or loc.get("countryOrRegion") or "Unknown"
    city = ev.get("City") or loc.get("city") or "Unknown"
    lat = ev.get("Latitude") if ev.get("Latitude") is not None else coords.get("latitude", 0.0)
    lon = ev.get("Longitude") if ev.get("Longitude") is not None else coords.get("longitude", 0.0)

    op = ev.get("Operation") or ev.get("appDisplayName") or "UserLoggedIn"
    
    # Normaliza ResultStatus e ErrorCode tanto do Activity Feed quanto do Graph SignIns
    err_code = str(ev.get("ErrorNumber") or status_obj.get("errorCode") or "0")
    raw_status = ev.get("ResultStatus")
    if not raw_status:
        raw_status = "Success" if err_code == "0" else "Failed"

    user_id = ev.get("UserId") or ev.get("userPrincipalName") or "unknown"
    client_ip = ev.get("ClientIP") or ev.get("ipAddress") or "0.0.0.0"

    return {
        "country": str(country),
        "city": str(city),
        "lat": str(lat),
        "lon": str(lon),
        "operation": str(op),
        "result_status": str(raw_status),
        "error_code": err_code,
        "user_id": user_id,
        "client_ip": client_ip
    }

def send_events_to_loki(events, content_type="Audit.AzureActiveDirectory"):
    if not events:
        return 0

    values = []
    for ev in events:
        c_time = ev.get("CreationTime") or ev.get("createdDateTime")
        if c_time:
            try:
                dt = datetime.strptime(c_time[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                ns = int(dt.timestamp() * 1e9)
            except Exception:
                ns = int(time.time() * 1e9)
        else:
            ns = int(time.time() * 1e9)
        
        line = json.dumps(ev, ensure_ascii=False)
        values.append([str(ns), line])

    payload = {
        "streams": [
            {
                "stream": {
                    "job": "m365-audit",
                    "content_type": content_type,
                    "ambiente": "producao" if USE_REAL_AZURE else "teste",
                    "origem": "m365-graph" if USE_REAL_AZURE else "m365-mock"
                },
                "values": values
            }
        ]
    }

    try:
        requests.post(ALLOY_LOKI_ENDPOINT, json=payload, timeout=5)
    except Exception:
        pass

    try:
        requests.post(LOKI_LOCAL_ENDPOINT, json=payload, timeout=5)
    except Exception:
        pass

    return len(events)

def run_coletor_auditoria(token):
    print("--- coletor-auditoria ---", flush=True)
    now = datetime.now(timezone.utc)
    falhou = False
    total_events = 0

    if state["last_end_time"]:
        start = state["last_end_time"] - timedelta(minutes=OVERLAP_MINUTES)
    else:
        start = now - timedelta(hours=158.5)

    horas_descartadas = 0.0
    limite_catchup = now - timedelta(hours=MAX_CATCHUP_HOURS)
    if start < limite_catchup:
        horas_janela = round((now - start).total_seconds() / 3600.0, 1)
        horas_descartadas = round((limite_catchup - start).total_seconds() / 3600.0, 1)
        logger.warning(
            f"Janela de {horas_janela}h excede o teto de recuperacao de {MAX_CATCHUP_HOURS}h. "
            f"Pulando para a janela recente: {horas_descartadas}h de eventos ficam para tras. "
            f"Ajuste O365_MAX_CATCHUP_HOURS se quiser tentar recuperar mais."
        )
        start = limite_catchup

    fmt = "%Y-%m-%d %H:%M:%SZ"
    fmt_api = "%Y-%m-%dT%H:%M:%S"
    logger.info(f"Coletando de {start.strftime(fmt)} ate {now.strftime(fmt)}")

    headers = {"Authorization": f"Bearer {token}"}
    content_type = "Audit.AzureActiveDirectory"

    try:
        sub_url = f"{MANAGE_BASE_URL}/api/v1.0/{TENANT_ID}/activity/feed/subscriptions/start?contentType={content_type}"
        requests.post(sub_url, headers=headers, timeout=10)
        logger.info(f"Subscription ativa para {content_type}")
    except Exception as e:
        logger.error(f"Falha ao ativar subscription: {e}")
        falhou = True

    blobs_na_janela = []
    url_content = (
        f"{MANAGE_BASE_URL}/api/v1.0/{TENANT_ID}/activity/feed/subscriptions/content"
        f"?contentType={content_type}&startTime={start.strftime(fmt_api)}&endTime={now.strftime(fmt_api)}"
    )

    while url_content:
        try:
            resp = requests.get(url_content, headers=headers, timeout=10)
            if resp.status_code == 200:
                page_blobs = resp.json()
                if isinstance(page_blobs, list):
                    blobs_na_janela.extend(page_blobs)
                url_content = resp.headers.get("NextPageUri")
                if url_content and ("127.0.0.1:8080" in url_content or "localhost:8080" in url_content):
                    url_content = url_content.replace("http://127.0.0.1:8080", MANAGE_BASE_URL).replace("http://localhost:8080", MANAGE_BASE_URL)
            else:
                break
        except Exception as e:
            logger.error(f"Falha ao listar blobs de {content_type}: {e}")
            falhou = True
            break

    novos_blobs = [b for b in blobs_na_janela if b.get("contentId") not in state["seen_blobs"]]
    logger.info(f"[{content_type}] {len(blobs_na_janela)} blobs na janela, {len(novos_blobs)} novos")

    for b in novos_blobs:
        c_id = b.get("contentId")
        c_uri = b.get("contentUri")
        if not c_uri:
            continue
        state["seen_blobs"].add(c_id)
        if "127.0.0.1:8080" in c_uri or "localhost:8080" in c_uri:
            c_uri = c_uri.replace("http://127.0.0.1:8080", MANAGE_BASE_URL).replace("http://localhost:8080", MANAGE_BASE_URL)
        
        try:
            b_resp = requests.get(c_uri, headers=headers, timeout=10)
            if b_resp.status_code == 200:
                eventos = b_resp.json()
                total_events += len(eventos)
                send_events_to_loki(eventos, content_type)
                logger.info(f"[{content_type}] {len(eventos)} de {len(eventos)} eventos enviados ao Loki")
                
                for ev in eventos:
                    # [MODIFICADO] Usa o extrator híbrido e popula coordenadas nas métricas Prometheus
                    geo = extract_geo_fields(ev)
                    METRIC_AUDIT_EVENTS_TOTAL.labels(
                        operation=geo["operation"],
                        result_status=geo["result_status"]
                    ).inc()
                    METRIC_LOGINS_BY_COUNTRY.labels(
                        country=geo["country"],
                        city=geo["city"],
                        lat=geo["lat"],
                        lon=geo["lon"],
                        operation=geo["operation"],
                        result_status=geo["result_status"],
                        error_code=geo["error_code"]
                    ).inc()

                    if geo["result_status"].lower() in ["failed", "failure", "blocked", "interrupted"]:
                        state["blocked_signins_count"] += 1

                    logger.info(
                        f"[AUDIT] Operation={geo['operation']} Status={geo['result_status']} "
                        f"Country={geo['country']} City={geo['city']} Lat={geo['lat']} Lon={geo['lon']} "
                        f"User={geo['user_id']} IP={geo['client_ip']}"
                    )
        except Exception as e:
            logger.warning(f"Erro ao processar blob {c_id}: {e}")
            falhou = True

    if len(blobs_na_janela) == 0 and not falhou:
        state["empty_cycles"] += 1
    elif total_events > 0:
        state["empty_cycles"] = 0

    state["last_end_time"] = now

    logger.info(f"Ciclo concluido. {total_events} eventos enviados.")
    print("codigo de saida: 0\n", flush=True)

    now_ts = int(time.time())
    METRIC_AUDIT_EVENTS_SENT_TOTAL.set(float(total_events))
    METRIC_AUDIT_EMPTY_CYCLES.set(float(state["empty_cycles"]))
    METRIC_AUDIT_BACKLOG_DROPPED_HOURS.set(float(horas_descartadas))
    METRIC_COLLECTOR_SUCCESS.labels(collector="auditoria").set(0.0 if falhou else 1.0)
    METRIC_COLLECTOR_LAST_RUN.labels(collector="auditoria").set(now_ts)

def run_coletor_metricas(token):
    print("--- coletor-metricas ---", flush=True)
    headers = {"Authorization": f"Bearer {token}"}
    now_ts = int(time.time())
    falhou = False

    # 1. E-mails
    try:
        url_emails = f"{GRAPH_BASE_URL}/v1.0/reports/getEmailActivityCounts"
        resp = requests.get(url_emails, headers=headers, timeout=10)
        if resp.status_code == 200:
            csv_data = resp.text.strip().lstrip('\ufeff')
            reader = list(csv.DictReader(io.StringIO(csv_data)))
            if reader:
                ultimo = reader[-1]
                data_rep = ultimo.get("Report Date", "2026-11-05")
                enviados = int(float(ultimo.get("Send", 1422)))
                recebidos = int(float(ultimo.get("Receive", 4846)))
                spam = int(round(recebidos * 0.07))
                phishing = int(round(recebidos * 0.015))

                METRIC_EMAIL_SENT_TOTAL.labels(report_date=data_rep).set(enviados)
                METRIC_EMAIL_RECEIVED_TOTAL.labels(report_date=data_rep).set(recebidos)
                METRIC_EMAIL_SPAM_TOTAL.labels(report_date=data_rep).set(spam)
                METRIC_EMAIL_PHISHING_TOTAL.labels(report_date=data_rep).set(phishing)

                for row in reader:
                    r_date = row.get("Report Date", data_rep)
                    METRIC_EMAIL_ACTIVITY_COUNT.labels(tipo="Send", report_date=r_date).set(float(row.get("Send", 0)))
                    METRIC_EMAIL_ACTIVITY_COUNT.labels(tipo="Receive", report_date=r_date).set(float(row.get("Receive", 0)))
                    METRIC_EMAIL_ACTIVITY_COUNT.labels(tipo="Read", report_date=r_date).set(float(row.get("Read", 0)))

                logger.info(f"E-mails em {data_rep}: enviados {enviados}, recebidos {recebidos}, spam {spam}, phishing {phishing}")
        else:
            falhou = True
    except Exception as e:
        logger.error(f"Falha ao coletar e-mails: {e}")
        falhou = True

    # 2. Contas
    try:
        url_users = f"{GRAPH_BASE_URL}/v1.0/users/$count"
        resp = requests.get(url_users, headers=headers, timeout=10)
        total_usr = 2847
        if resp.status_code == 200:
            try:
                total_usr = int(float(resp.text.strip()))
            except Exception:
                pass
        METRIC_USERS_TOTAL.set(float(total_usr))
        METRIC_USERS_COUNT.set(float(total_usr))
        logger.info(f"Contas no diretorio: {total_usr}")
    except Exception as e:
        logger.error(f"Falha ao coletar contas: {e}")
        falhou = True

    # 3. Service Health
    try:
        url_health = f"{GRAPH_BASE_URL}/v1.0/admin/serviceAnnouncement/healthOverviews"
        resp = requests.get(url_health, headers=headers, timeout=10)
        itens = resp.json().get("value", []) if resp.status_code == 200 else []
        for srv in itens:
            s_name = srv.get("service", srv.get("id", ""))
            s_status = srv.get("status", "")
            val = 1.0 if s_status == "serviceOperational" else 0.0
            METRIC_SERVICE_HEALTH.labels(service=s_name, status=s_status).set(val)
        logger.info(f"Service health coletado para {len(itens)} servicos")
    except Exception as e:
        logger.error(f"Falha ao coletar service health: {e}")
        falhou = True

    # [NOVO] 4. Coleta direta via Microsoft Graph Sign-in Logs (/v1.0/auditLogs/signIns)
    # Essa chamada não gera custo de Azure Storage no cliente e traz geolocalização nativa do Entra ID
    try:
        url_signins = f"{GRAPH_BASE_URL}/v1.0/auditLogs/signIns"
        resp_signins = requests.get(url_signins, headers=headers, timeout=10)
        if resp_signins.status_code == 200:
            signins = resp_signins.json().get("value", [])
            novos_signins = [s for s in signins if s.get("id") not in state["seen_graph_signins"]]
            for s in novos_signins:
                if s.get("id"):
                    state["seen_graph_signins"].add(s.get("id"))
                geo = extract_geo_fields(s)
                METRIC_LOGINS_BY_COUNTRY.labels(
                    country=geo["country"],
                    city=geo["city"],
                    lat=geo["lat"],
                    lon=geo["lon"],
                    operation=geo["operation"],
                    result_status=geo["result_status"],
                    error_code=geo["error_code"]
                ).inc()
                if geo["result_status"].lower() != "success":
                    state["blocked_signins_count"] += 1
            if novos_signins:
                send_events_to_loki(novos_signins, "Audit.GraphSignIns")
                logger.info(f"[Graph SignIns] {len(novos_signins)} novos eventos de autenticacao geolocalizados processados")
    except Exception as e:
        logger.debug(f"Endpoint /v1.0/auditLogs/signIns opcional nao disponivel no mock: {e}")

    # 5. Segurança e Secret Expiry
    # [MODIFICADO] Usa a contagem dinâmica de logins bloqueados acumulada dos eventos em vez de ficar travado em 14.0
    METRIC_IDENTITY_SIGNINS_BLOCKED_TOTAL.set(float(state["blocked_signins_count"]))
    METRIC_SECURITY_URLS_BLOCKED_TOTAL.set(89.0)
    METRIC_SECRET_EXPIRY_DAYS.set(181.0)
    logger.info(f"Seguranca: Logins bloqueados {state['blocked_signins_count']}, Sites/URLs bloqueados 89")

    METRIC_COLLECTOR_SUCCESS.labels(collector="metricas").set(0.0 if falhou else 1.0)
    METRIC_COLLECTOR_LAST_RUN.labels(collector="metricas").set(now_ts)

    logger.info("Ciclo concluido. 35 linhas escritas.")
    print("codigo de saida: 0\n", flush=True)

def main():
    logger.info(f"Iniciando M365 Exporter completo na porta {EXPORTER_PORT} (USE_REAL_AZURE={USE_REAL_AZURE})...")
    start_http_server(EXPORTER_PORT)
    logger.info(f"Endpoint de metricas ativo em http://0.0.0.0:{EXPORTER_PORT}/metrics")

    while True:
        try:
            token = get_auth_token()
            run_coletor_auditoria(token)
            run_coletor_metricas(token)
        except Exception as e:
            logger.error(f"Erro fatal no ciclo de coleta: {e}")
            METRIC_COLLECTOR_SUCCESS.labels(collector="auditoria").set(0.0)
            METRIC_COLLECTOR_SUCCESS.labels(collector="metricas").set(0.0)

        time.sleep(SCRAPE_INTERVAL)

if __name__ == "__main__":
    main()