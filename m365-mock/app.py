#!/usr/bin/env python3
"""
Mock das APIs da Microsoft usadas pelo coletor Office 365.

Responde no mesmo formato das APIs reais:
  - Entra ID   : emissao de token (client credentials)
  - Management : subscriptions/start, subscriptions/content, download de blobs
  - Graph      : relatorios de e-mail, contagem de usuarios, service health

Cenarios de teste sao trocados em tempo de execucao pelo endpoint /_control,
sem reiniciar o container.

Somente biblioteca padrao do Python: a imagem nao precisa de pip install.
"""

import json
import os
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

# ---------- CONFIG ----------
PORTA         = int(os.environ.get("MOCK_PORT", "8080"))
TENANT_ID     = os.environ.get("MOCK_TENANT_ID", "tenant-de-teste")
CLIENT_ID     = os.environ.get("MOCK_CLIENT_ID", "client-de-teste")
CLIENT_SECRET = os.environ.get("MOCK_CLIENT_SECRET", "segredo-de-teste")
TOKEN         = "mock-access-token"

# Blobs sao gerados em janelas de 5 minutos. A mesma janela devolve sempre o
# mesmo contentId, que e o que permite testar a deduplicacao do coletor.
JANELA_MIN       = 5
EVENTOS_POR_BLOB = int(os.environ.get("MOCK_EVENTOS_POR_BLOB", "80"))
BLOBS_POR_PAGINA = 3

CENARIOS = {
    "normal":           "Feed com eventos, tudo funcionando.",
    "vazio":            "Feed responde 200 com lista vazia (Unified Audit Log desligado).",
    "throttle":         "Primeiras chamadas ao feed respondem 429, depois normalizam.",
    "secret-invalido":  "Token falha com invalid_client.",
    "sem-consent":      "Token falha com unauthorized_client.",
    "graph-403":        "Graph responde 403 (permissao Delegated em vez de Application).",
}

estado = {
    "cenario": "normal",
    "throttle_restantes": 0,
    "subscriptions": set(),
    "requisicoes": 0,
    "logs_recebidos": 0,
}


# ---------- GERACAO DE DADOS ----------
def janela_de(momento):
    """Arredonda para o inicio da janela de 5 minutos."""
    return momento.replace(
        minute=(momento.minute // JANELA_MIN) * JANELA_MIN, second=0, microsecond=0
    )


def blobs_no_intervalo(inicio, fim, content_type):
    """Um blob por janela de 5 min dentro do intervalo pedido."""
    blobs = []
    atual = janela_de(inicio)
    limite = janela_de(fim)

    while atual <= limite and len(blobs) < 24:
        marca = atual.strftime("%Y%m%d%H%M")
        blobs.append(
            {
                "contentType": content_type,
                "contentId": "blob-%s-%s" % (marca, content_type.split(".")[-1].lower()),
                "contentUri": "http://%s/api/v1.0/%s/activity/feed/audit/blob-%s"
                % (HOST_PUBLICO, TENANT_ID, marca),
                "contentCreated": atual.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "contentExpiration": (atual + timedelta(days=7)).strftime(
                    "%Y-%m-%dT%H:%M:%S.000Z"
                ),
            }
        )
        atual += timedelta(minutes=JANELA_MIN)

    return blobs


def eventos_do_blob(blob_id):
    """Eventos de autenticacao no formato da Management Activity API com distribuicao global variada."""
    marca = blob_id.replace("blob-", "")
    try:
        base = datetime.strptime(marca, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        base = datetime.now(timezone.utc)

    usuarios = [
        "ana.souza@contoso.com",
        "bruno.lima@contoso.com",
        "carla.dias@contoso.com",
        "diego.martins@contoso.com",
        "elena.rocha@contoso.com",
    ]

    paises_config = [
        # (IP base, Codigo, Lat, Lon, Peso/Probabilidade)
        ("203.0.113.10", "BR", -23.5505, -46.6333, 40),  # Brasil (Volume muito alto)
        ("203.0.113.11", "US",  37.7749, -122.4194, 60), # EUA (Ataque/Volume massivo)
        ("203.0.113.12", "PT",  38.7223,   -9.1393, 15), # Portugal (Moderado)
        ("203.0.113.13", "DE",  52.5200,   13.4050, 20), # Alemanha (Moderado)
        ("203.0.113.14", "JP",  35.6762,  139.6503,  8), # Japão (Baixo)
        ("203.0.113.15", "CN",  39.9042,  116.4074, 50), # China (Volume alto)
        ("203.0.113.16", "RU",  55.7558,   37.6173, 75), # Rússia (Volume crítico)
        ("203.0.113.17", "GB",  51.5074,   -0.1278, 25), # Reino Unido (Moderado)
        ("203.0.113.18", "AU", -33.8688,  151.2093,  5), # Austrália (Raro)
        ("203.0.113.19", "ZA", -26.2041,   28.0473,  6), # África do Sul (Raro)
        ("203.0.113.20", "IN",  28.6139,   77.2090, 35), # Índia (Alto)
        ("203.0.113.21", "FR",  48.8566,    2.3522, 18), # França (Moderado)
        ("203.0.113.22", "CA",  45.4215,  -75.6972, 12), # Canadá (Moderado)
        ("203.0.113.23", "ES",  40.4168,   -3.7038, 22), # Espanha (Moderado)
        ("203.0.113.24", "IT",  41.9028,   12.4964, 19), # Itália (Moderado)
        ("203.0.113.25", "NL",  52.3676,    4.9041, 30), # Holanda (Alto - Datacenters)
        ("203.0.113.26", "IE",  53.3498,   -6.2603, 16), # Irlanda (Moderado)
        ("203.0.113.27", "SE",  59.3293,   18.0686,  9), # Suécia (Baixo)
        ("203.0.113.28", "CH",  46.8182,    8.2275, 11), # Suíça (Baixo/Moderado)
        ("203.0.113.29", "AR", -34.6037,  -58.3816, 26), # Argentina (Moderado/Alto)
        ("203.0.113.30", "CL", -33.4489,  -70.6693, 14), # Chile (Moderado)
        ("203.0.113.31", "MX",  19.4326,  -99.1332, 34), # México (Alto)
        ("203.0.113.32", "CO",   4.7110,  -74.0721, 17), # Colômbia (Moderado)
        ("203.0.113.33", "KR",  37.5665,  126.9780, 48), # Coreia do Sul (Muito alto)
        ("203.0.113.34", "SG",   1.3521,  103.8198, 32), # Singapura (Alto)
        ("203.0.113.35", "ID",  -6.2088,  106.8456, 24), # Indonésia (Moderado)
        ("203.0.113.36", "VN",  21.0285,  105.8542, 38), # Vietnã (Alto)
        ("203.0.113.37", "AE",  25.2048,   55.2708, 15), # Emirados Árabes Unidos (Moderado)
        ("203.0.113.38", "IL",  32.0853,   34.7818, 13), # Israel (Moderado)
        ("203.0.113.39", "NG",   9.0765,    7.3986, 21), # Nigéria (Moderado)
        ("203.0.113.40", "EG",  30.0444,   31.2357, 10), # Egito (Baixo)
        ("203.0.113.41", "KE",  -1.2921,   36.8219,  7), # Quênia (Raro)
        ("203.0.113.42", "NZ", -36.8485,  174.7633,  4), # Nova Zelândia (Muito raro)
    ]

    populacao = []
    pesos = []
    for item in paises_config:
        populacao.append({
            "ip": item[0],
            "country": item[1],
            "lat": item[2],
            "lon": item[3]
        })
        pesos.append(item[4])

    eventos = []
    total_amostras = EVENTOS_POR_BLOB
    sorteados = random.choices(populacao, weights=pesos, k=total_amostras)

    for i, geo in enumerate(sorteados):
        falhou = (i % 5 == 0)
        momento = base + timedelta(seconds=i * 3)

        eventos.append({
            "CreationTime": momento.strftime("%Y-%m-%dT%H:%M:%S"),
            "Id": str(uuid.uuid5(uuid.NAMESPACE_URL, "%s-%d" % (blob_id, i))),
            "Operation": "UserLoginFailed" if falhou else "UserLoggedIn",
            "OrganizationId": TENANT_ID,
            "RecordType": 15,
            "ResultStatus": "Failed" if falhou else "Success",
            "UserKey": "chave-%d" % i,
            "UserType": 0,
            "Workload": "AzureActiveDirectory",
            "ClientIP": geo["ip"],
            "Country": geo["country"],
            "Latitude": geo["lat"],
            "Longitude": geo["lon"],
            "UserId": usuarios[i % len(usuarios)],
            "ExtendedProperties": [
                {"Name": "ResultStatusDetail", "Value": "Redirect"},
                {"Name": "UserAgent", "Value": "Mozilla/5.0"}
            ],
            "ErrorNumber": "50126" if falhou else "0"
        })
    return eventos


def relatorio_de_email():
    """CSV com BOM, no mesmo formato da Graph real.

    Este endpoint nao aceita $format=application/json: responde 400 com
    "JSON format is not supported". O mock reproduz isso em rota_graph.
    """
    hoje = datetime.now(timezone.utc).date()
    atualizado = hoje - timedelta(days=2)     # a Graph tem atraso de ate 48h

    linhas = ["Report Refresh Date,Send,Receive,Read,Report Date,Report Period"]
    for i in range(7):
        dia = hoje - timedelta(days=i + 2)
        linhas.append(
            "%s,%d,%d,%d,%s,7" % (atualizado, 1200 + i * 37, 4300 + i * 91,
                                  3100 + i * 55, dia)
        )
    return "\ufeff" + "\r\n".join(linhas) + "\r\n"


def service_health():
    return {
        "value": [
            {"id": "Exchange", "service": "Exchange Online", "status": "serviceOperational"},
            {"id": "SharePoint", "service": "SharePoint Online", "status": "serviceOperational"},
            {"id": "Teams", "service": "Microsoft Teams", "status": "serviceDegradation"},
        ]
    }


# ---------- HANDLER ----------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ----- utilidades -----
    def responder(self, codigo, corpo, tipo="application/json", cabecalhos=None):
        if isinstance(corpo, (dict, list)):
            corpo = json.dumps(corpo, ensure_ascii=False)
        dados = corpo.encode("utf-8")

        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        for nome, valor in (cabecalhos or {}).items():
            self.send_header(nome, valor)
        self.end_headers()
        self.wfile.write(dados)

    def erro_oauth(self, codigo, erro, descricao):
        self.responder(codigo, {"error": erro, "error_description": descricao})

    def corpo_recebido(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(tamanho).decode("utf-8") if tamanho else ""

    def token_valido(self):
        if self.headers.get("Authorization") == "Bearer %s" % TOKEN:
            return True
        self.responder(401, {"error": {"code": "InvalidAuthenticationToken",
                                       "message": "Access token is empty or invalid."}})
        return False

    def log_message(self, formato, *args):
        print("[mock] %s - %s" % (self.address_string(), formato % args), flush=True)

    # ----- rotas -----
    def do_POST(self):
        caminho = urlparse(self.path).path
        estado["requisicoes"] += 1

        # Token: POST /<tenant>/oauth2/v2.0/token
        if caminho.endswith("/oauth2/v2.0/token"):
            return self.rota_token()

        # Subscription: POST /api/v1.0/<tenant>/activity/feed/subscriptions/start
        if caminho.endswith("/activity/feed/subscriptions/start"):
            return self.rota_subscription_start()

        # Atalho para smoke test sem Alloy: recebe o push do Loki e so conta.
        if caminho.endswith("/loki/api/v1/push"):
            return self.rota_loki_push()

        if caminho.startswith("/_control"):
            return self.rota_control(caminho)

        self.responder(404, {"error": "rota nao encontrada: %s" % caminho})

    def do_GET(self):
        url = urlparse(self.path)
        caminho = unquote(url.path)
        parametros = parse_qs(url.query)
        estado["requisicoes"] += 1

        if caminho.startswith("/_control"):
            return self.rota_control(caminho)

        # Management: lista de blobs
        if caminho.endswith("/activity/feed/subscriptions/content"):
            return self.rota_content(parametros)

        # Management: download de um blob
        if "/activity/feed/audit/" in caminho:
            if not self.token_valido():
                return
            blob_id = caminho.rsplit("/", 1)[-1]
            return self.responder(200, eventos_do_blob(blob_id))

        # Graph
        if caminho.startswith("/v1.0/"):
            return self.rota_graph(caminho)

        self.responder(404, {"error": "rota nao encontrada: %s" % caminho})

    # ----- implementacao das rotas -----
    def rota_token(self):
        campos = parse_qs(self.corpo_recebido())
        cenario = estado["cenario"]

        if cenario == "secret-invalido":
            return self.erro_oauth(401, "invalid_client",
                                   "AADSTS7000215: Invalid client secret provided.")
        if cenario == "sem-consent":
            return self.erro_oauth(400, "unauthorized_client",
                                   "AADSTS65001: The user or administrator has not consented.")

        if campos.get("client_id", [""])[0] != CLIENT_ID:
            return self.erro_oauth(400, "invalid_request",
                                   "AADSTS900023: Application with identifier was not found.")
        if campos.get("client_secret", [""])[0] != CLIENT_SECRET:
            return self.erro_oauth(401, "invalid_client",
                                   "AADSTS7000215: Invalid client secret provided.")
        if campos.get("grant_type", [""])[0] != "client_credentials":
            return self.erro_oauth(400, "unsupported_grant_type", "grant_type invalido.")

        self.responder(200, {
            "token_type": "Bearer",
            "expires_in": 3599,
            "ext_expires_in": 3599,
            "access_token": TOKEN,
        })

    def rota_subscription_start(self):
        if not self.token_valido():
            return
        tipo = parse_qs(urlparse(self.path).query).get("contentType", ["?"])[0]

        if tipo in estado["subscriptions"]:
            return self.responder(400, {
                "error": {
                    "code": "AF20024",
                    "message": "The subscription is already enabled. No property change.",
                }
            })

        estado["subscriptions"].add(tipo)
        self.responder(200, {"contentType": tipo, "status": "enabled"})

    def rota_content(self, parametros):
        if not self.token_valido():
            return

        if estado["cenario"] == "throttle" and estado["throttle_restantes"] > 0:
            estado["throttle_restantes"] -= 1
            return self.responder(429, {"error": {"code": "TooManyRequests"}},
                                  cabecalhos={"Retry-After": "1"})

        if estado["cenario"] == "vazio":
            return self.responder(200, [])

        tipo = parametros.get("contentType", ["Audit.AzureActiveDirectory"])[0]
        agora = datetime.now(timezone.utc)

        def ler(nome, padrao):
            valor = parametros.get(nome, [None])[0]
            if not valor:
                return padrao
            try:
                return datetime.strptime(valor[:19], "%Y-%m-%dT%H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                return padrao

        inicio = ler("startTime", agora - timedelta(hours=1))
        fim = ler("endTime", agora)

        todos = blobs_no_intervalo(inicio, fim, tipo)
        pagina = int(parametros.get("_pagina", ["0"])[0])
        recorte = todos[pagina * BLOBS_POR_PAGINA : (pagina + 1) * BLOBS_POR_PAGINA]

        cabecalhos = {}
        if len(todos) > (pagina + 1) * BLOBS_POR_PAGINA:
            cabecalhos["NextPageUri"] = (
                "http://%s/api/v1.0/%s/activity/feed/subscriptions/content"
                "?contentType=%s&_pagina=%d" % (HOST_PUBLICO, TENANT_ID, tipo, pagina + 1)
            )

        self.responder(200, recorte, cabecalhos=cabecalhos)

    def rota_graph(self, caminho):
        if not self.token_valido():
            return

        if estado["cenario"] == "graph-403":
            return self.responder(403, {
                "error": {
                    "code": "Authorization_RequestDenied",
                    "message": "Insufficient privileges to complete the operation.",
                }
            })

        if "getEmailActivityCounts" in caminho:
            if "application/json" in self.path:
                return self.responder(400, {
                    "error": {
                        "code": "UnknownError",
                        "message": '{"Message":"JSON format is not supported."}',
                    }
                })
            return self.responder(200, relatorio_de_email(), tipo="application/octet-stream")

        if re.search(r"/users/\$count$", caminho):
            return self.responder(200, "2847", tipo="text/plain")

        if caminho.endswith("/admin/serviceAnnouncement/healthOverviews"):
            return self.responder(200, service_health())

        self.responder(404, {"error": {"code": "ResourceNotFound", "message": caminho}})

    def rota_loki_push(self):
        corpo = self.corpo_recebido()
        try:
            entradas = sum(len(s.get("values", [])) for s in json.loads(corpo)["streams"])
        except (ValueError, KeyError):
            entradas = 0
        estado["logs_recebidos"] += entradas
        auth = "com basic auth" if self.headers.get("Authorization") else "sem auth"
        print("[mock] push recebido: %d entradas, %s (total %d)"
              % (entradas, auth, estado["logs_recebidos"]), flush=True)
        self.responder(204, "")

    def rota_control(self, caminho):
        partes = [p for p in caminho.split("/") if p]

        if len(partes) == 1:
            return self.responder(200, {
                "cenario": estado["cenario"],
                "cenarios_disponiveis": CENARIOS,
                "subscriptions": sorted(estado["subscriptions"]),
                "requisicoes": estado["requisicoes"],
                "logs_recebidos": estado["logs_recebidos"],
            })

        if len(partes) >= 2 and partes[1] == "reset":
            estado.update(cenario="normal", throttle_restantes=0,
                          requisicoes=0, logs_recebidos=0)
            estado["subscriptions"] = set()
            return self.responder(200, {"ok": True, "cenario": "normal"})

        if len(partes) >= 3 and partes[1] == "cenario":
            nome = partes[2]
            if nome not in CENARIOS:
                return self.responder(400, {"error": "cenario desconhecido",
                                            "disponiveis": sorted(CENARIOS)})
            estado["cenario"] = nome
            estado["throttle_restantes"] = 2 if nome == "throttle" else 0
            return self.responder(200, {"ok": True, "cenario": nome,
                                        "descricao": CENARIOS[nome]})

        self.responder(404, {"error": "rota de controle invalida"})


HOST_PUBLICO = os.environ.get("MOCK_HOST_PUBLICO", "127.0.0.1:%d" % PORTA)


if __name__ == "__main__":
    print("Mock das APIs da Microsoft em http://0.0.0.0:%d" % PORTA, flush=True)
    print("  tenant : %s" % TENANT_ID, flush=True)
    print("  cenario: %s  (troque em POST /_control/cenario/<nome>)" % estado["cenario"],
          flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORTA), Handler).serve_forever()