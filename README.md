# Lab Cloud — Observability & Infrastructure Knowledge Base

Repositório técnico oficial contendo a arquitetura, configurações como código, aplicações instrumentadas e runbooks de observabilidade do ambiente **Lab Cloud**.

Este ambiente foi projetado para operar uma stack híbrida e modular de observabilidade: local (*self-hosted*) em **Docker puro** dentro de uma VM Linux com restrição de memória (8 GB RAM), além de integração com **Grafana Cloud** (Métricas, Logs e Traces) via **Grafana Alloy**.

## 🚀 Tecnologias Integradas

| Componente | Versão / Imagem | Papel no Ambiente | Porta Exposta | 
| ----- | ----- | ----- | ----- | 
| **Grafana OSS** | `grafana/grafana-oss:latest` | Consolidação visual de Métricas, Logs, SQL e Zabbix | `3000` | 
| **Grafana Alloy** | `grafana/alloy:latest` | Agente unificado para coleta e envio ao Grafana Cloud (Métricas, Logs, Traces) | `12345`, `4317`, `4318` | 
| **Prometheus** | `prom/prometheus:latest` | Ingestão e consultas PromQL de Golden Signals | `9090` | 
| **Grafana Loki** | `grafana/loki:latest` | Armazenamento e agregação de logs com LogQL | `3100` | 
| **Zabbix Server** | `zabbix-server-pgsql:alpine-7.0` | Monitoramento de métricas do sistema operacional | `10051` | 
| **Zabbix Web** | `zabbix-web-nginx-pgsql:alpine-7.0` | Interface administrativa e API JSON-RPC | `8080` | 
| **PostgreSQL** | `postgres:16-alpine` | Banco de dados transacional do Zabbix e da API | `5432` | 
| **pgAdmin 4** | `dpage/pgadmin4:latest` | Gestão visual de schemas, tabelas e queries SQL | `5050` | 
| **Custom API** | Python 3.11 / Flask | API de microsserviço instrumentada com métricas e rotas de erro (404/500) | `5000` | 
| **K6** | `grafana/k6:latest` | Testes contínuos de carga e estresse nos endpoints | Interna | 
| **Traffic Generator** | Python 3.11 / Requests | Worker contínuo de simulação de carga e spikes | Interna | 

## 📂 Estrutura Modular do Projeto

```
lab-cloud/
├── docker-compose.yml              # Orquestração de todos os containers
├── mkdocs.yml                      # Especificação do portal Material for MkDocs
├── README.md                       # Apresentação do projeto
├── .env.example                    # Template de variáveis de ambiente seguras
├── alloy/
│   └── config.alloy                # Pipeline de coleta e exportação para o Grafana Cloud
├── prometheus/
│   └── prometheus.yml              # Configuração de scraping e targets
├── loki/
│   └── local-config.yaml           # Configuração de chunks e retenção do Loki
├── app/
│   ├── Dockerfile                  # Containerização da API
│   ├── requirements.txt            # Dependências Flask, prometheus_client e psycopg2
│   └── main.py                     # API REST com instrumentação, banco e rotas de erro
├── k6/
│   └── script.js                   # Cenários de teste de carga com múltiplos estágios
├── traffic-generator/
│   ├── Dockerfile                  # Containerização do worker
│   ├── requirements.txt            # Dependência Requests
│   └── load_worker.py              # Loop de carga com injeção programada de spikes
└── docs/                           # Documentação completa em Markdown para MkDocs
    ├── index.md
    ├── architecture/
    ├── observability/
    ├── application/
    ├── database/
    ├── troubleshooting/
    └── reference/
```

## ⚡ Inicialização Rápida

1. **Pré-requisitos:** Docker Engine e Docker Compose instalados na máquina/VM Linux.

2. **Configuração de Variáveis de Ambiente:**
   Copie o arquivo de exemplo e defina suas credenciais do Grafana Cloud (tokens e URLs):
   ```bash
   cp .env.example .env
   ```

3. **Instalar o driver Loki do Docker (opcional se usar Loki local):**
   ```bash
   docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions
   ```

4. **Subir toda a stack:**
   ```bash
   docker compose up -d --build
   ```

5. **Validar serviços:**
   * **Grafana Local:** `http://<IP-DO-HOST>:3000`
   * **Grafana Alloy UI:** `http://<IP-DO-HOST>:12345`
   * **Zabbix Web:** `http://<IP-DO-HOST>:8080`
   * **pgAdmin:** `http://<IP-DO-HOST>:5050`
   * **Prometheus UI:** `http://<IP-DO-HOST>:9090`
   * **Custom API:** `http://<IP-DO-HOST>:5000/api/pedidos`
