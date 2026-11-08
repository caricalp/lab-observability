---
title: Topologia de Rede & Portas
description: Mapeamento de rede bridge Docker, portas expostas e DNS interno
tags:
  - rede
  - docker-bridge
  - portas
---

# Topologia de Rede e Portas

## 1. Rede Interna `lab-net` (Docker Bridge)

Todos os containers são conectados à rede Docker tipo bridge nomeada `lab-net`. O Docker possui um servidor DNS interno embutido (`127.0.0.11`) que resolve o **nome do serviço** diretamente para o IP interno do container (faixa `172.18.0.0/16`).

```mermaid
graph TD
    subgraph ExternalNetwork ["Rede Física / Hyper-V (192.168.0.0/24)"]
        Browser[Navegador do Host: 192.168.0.231]
    end

    subgraph HostVM ["VM Linux Server (192.168.0.208)"]
        direction TB
        subgraph PortsBridge ["Mapeamento de Portas do Host"]
            P3000[Porta 3000] -->|NAT| Grafana[lab-grafana]
            P8080[Porta 8080] -->|NAT| ZbxWeb[lab-zabbix-web]
            P5050[Porta 5050] -->|NAT| PgAdmin[lab-pgadmin]
            P9090[Porta 9090] -->|NAT| Prom[lab-prometheus]
            P3100[Porta 3100] -->|NAT| Loki[lab-loki]
            P5000[Porta 5000] -->|NAT| CustomAPI[lab-api]
            P5432[Porta 5432] -->|NAT| Postgres[lab-postgres]
            P10051[Porta 10051] -->|NAT| ZbxServer[lab-zabbix-server]
        end

        subgraph DockerNet ["Rede Interna: lab-net (DNS Interno)"]
            Grafana -.->|DNS: prometheus:9090| Prom
            Grafana -.->|DNS: loki:3100| Loki
            Grafana -.->|DNS: zabbix-web:8080| ZbxWeb
            Grafana -.->|DNS: postgres:5432| Postgres
            ZbxServer -.->|DNS: postgres:5432| Postgres
            ZbxWeb -.->|DNS: zabbix-server:10051| ZbxServer
            PgAdmin -.->|DNS: postgres:5432| Postgres
            TrafficGen[lab-traffic-generator] -.->|DNS: custom-api:5000| CustomAPI
        end
    end

    Browser --> P3000
    Browser --> P8080
    Browser --> P5050
    Browser --> P9090
    Browser --> P5000
```

---

## 2. Tabela de Portas e Protocolos

| Serviço | Nome do Container | Porta Externa (Host) | Porta Interna (Container) | Protocolo | Função |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Grafana** | `lab-grafana` | `3000` | `3000` | HTTP | UI Web e orquestração de painéis |
| **Zabbix Web** | `lab-zabbix-web` | `8080` | `8080` | HTTP | Interface administrativa e `/api_jsonrpc.php` |
| **Zabbix Server**| `lab-zabbix-server` | `10051` | `10051` | TCP | Porta de escuta de agentes e trappers |
| **Prometheus** | `lab-prometheus` | `9090` | `9090` | HTTP | Console Web e endpoint `/api/v1/query` |
| **Loki** | `lab-loki` | `3100` | `3100` | HTTP | Endpoint de push `/loki/api/v1/push` e queries |
| **PostgreSQL** | `lab-postgres` | `5432` | `5432` | TCP | Engine do PostgreSQL para clientes externos |
| **pgAdmin 4** | `lab-pgadmin` | `5050` | `80` | HTTP | Interface gráfica de gestão do banco de dados |
| **Custom API** | `lab-api` | `5000` | `5000` | HTTP | Endpoints `/api/pedidos` e `/metrics` |
| **Worker Carga**| `lab-traffic-generator`| *Nenhuma* | *Nenhuma* | — | Comunicação puramente de saída interna |
