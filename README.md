# Lab — Observability & Infrastructure Knowledge Base

Repositório técnico oficial contendo a arquitetura, configurações como código, aplicações instrumentadas e runbooks de observabilidade do ambiente **Lab Cloud**.

Este ambiente foi projetado para operar uma stack completa de observabilidade local (*self-hosted*) em **Docker puro** dentro de uma VM Hyper-V Linux com restrição de memória (8 GB RAM), contornando limitações de retenção e cotas do Grafana Cloud Free Tier.

## 🚀 Tecnologias Integradas

| Componente | Versão / Imagem | Papel no Ambiente | Porta Exposta | 
| ----- | ----- | ----- | ----- | 
| **Grafana OSS** | `grafana/grafana-oss:latest` | Consolidação visual de Métricas, Logs, SQL e Zabbix | `3000` | 
| **Prometheus** | `prom/prometheus:latest` | Ingestão e consultas PromQL de Golden Signals | `9090` | 
| **Grafana Loki** | `grafana/loki:latest` | Armazenamento e agregação de logs com LogQL | `3100` | 
| **Zabbix Server** | `zabbix-server-pgsql:alpine-7.0` | Monitoramento de métricas do sistema operacional | `10051` | 
| **Zabbix Web** | `zabbix-web-nginx-pgsql:alpine-7.0` | Interface administrativa e API JSON-RPC | `8080` | 
| **PostgreSQL** | `postgres:16-alpine` | Banco de dados transacional do Zabbix e da API | `5432` | 
| **pgAdmin 4** | `dpage/pgadmin4:latest` | Gestão visual de schemas, tabelas e queries SQL | `5050` | 
| **Custom API** | Python 3.11 / Flask | API de microsserviço instrumentada com métricas | `5000` | 
| **Traffic Generator** | Python 3.11 / Requests | Worker contínuo de simulação de carga e spikes | Interna | 
| **k6** | scripts.js | Worker contínuo de simulação de carga e spikes | Interna |
## 📂 Estrutura Modular do Projeto

```
lab-observability/
├── docker-compose.yml              # Orquestração de todos os 8 containers
├── mkdocs.yml                      # Especificação do portal Material for MkDocs
├── README.md                       # Apresentação do projeto
├── prometheus/
│   └── prometheus.yml              # Configuração de scraping e targets
├── loki/
│   └── local-config.yaml           # Configuração de chunks e retenção do Loki
├── app/
│   ├── Dockerfile                  # Containerização da API
│   ├── requirements.txt            # Dependências Flask e prometheus_client
│   └── main.py                     # API REST com instrumentação e logging estruturado
├── traffic-generator/
│   ├── Dockerfile                  # Containerização do worker
│   ├── requirements.txt            # Dependência Requests
│   └── load_worker.py              # Loop de carga com injeção programada de spikes
└── docs/                           # Documentação completa em Markdown para MkDocs
│    ├── index.md
│    ├── architecture/
│    ├── observability/
│    ├── application/
│    ├── database/
│    ├── troubleshooting/
│    └── reference/
│
└── K6/                            # Script de carga com múltiplos estágios estressando /api/pedidos, /api/erro-404 e /api/erro-500.
     ├── scripts.js/
     ├── /api/pedidos/
     ├── /api/erro-404/
     ├── /api/erro-500/



```

## ⚡ Inicialização Rápida

1. **Pré-requisitos:** Docker Engine e Docker Compose instalados na VM Linux (`192.168.0.208`).

2. **Instalar o driver Loki do Docker:**

   ```
   docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions
   
   ```

3. **Subir toda a stack:**

   ```
   docker compose up -d --build
   
   ```

4. **Validar serviços:**

   * Grafana: `http://192.168.0.208:3000` (`admin` / `@Carica98`)

   * Zabbix Web: `http://192.168.0.208:8080` (`Admin` / `zabbix`)

   * pgAdmin: `http://192.168.0.208:5050` (`admin@admin.com` / `admin`)

   * Prometheus UI: `http://192.168.0.208:9090`
