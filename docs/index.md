---
title: Início
description: Visão geral da base de conhecimento do Lab Cloud
tags:
  - lab-cloud
  - observabilidade
  - sre
---

# Bem-vindo à Knowledge Base do Lab Cloud

Esta base de conhecimento documenta a concepção, implementação, operação e solução de incidentes da plataforma de observabilidade do **Lab Cloud**.

O ambiente foi desenvolvido com foco em resolver desafios de observabilidade corporativa em sistemas modernos e legados, unificando os pilares de **Métricas**, **Logs**, **Traces Distribuídos** e **Monitoramento de Infraestrutura**.

```mermaid
flowchart TD
    subgraph ClientLayer ["Geração de Tráfego & Clientes"]
        TG[Traffic Generator Worker] -->|HTTP GET /api/pedidos| API[Custom Flask API]
        DevUser[Engenheiro / Navegador] -->|HTTP| GrafanaUI[Grafana Dashboard :3000]
        DevUser -->|HTTP| PgAdminUI[pgAdmin 4 :5050]
        DevUser -->|HTTP| ZbxUI[Zabbix Web :8080]
    end

    subgraph ServiceLayer ["Aplicação & Coleta"]
        API -->|Scrape /metrics :5000| Prom[Prometheus TSDB :9090]
        API -->|Loki Docker Driver Push| Loki[Grafana Loki :3100]
        API -.->|Transações Futuras| PG[(PostgreSQL :5432)]
    end

    subgraph StorageInfra ["Armazenamento & Infraestrutura"]
        ZbxServer[Zabbix Server :10051] -->|Poll & Triggers| PG
        ZbxUI -->|Internal API| ZbxServer
    end

    subgraph VisualizationCore ["Central de Visualização"]
        GrafanaUI -->|PromQL| Prom
        GrafanaUI -->|LogQL| Loki
        GrafanaUI -->|JSON-RPC API| ZbxUI
        GrafanaUI -->|SQL Queries| PG
    end
```

## Objetivos Técnicos Alcançados

1. **Eficiência de Recursos:** Execução de 8 containers integrados em uma única máquina virtual com apenas **8 GB de RAM** (alocando cerca de 4 GB reais e reservando 4 GB de buffer).
2. **Independência de Cotas Cloud:** Superação das barreiras do plano gratuito do Grafana Cloud (14 dias de retenção e limite de 50 GB de logs/traces), mantendo dados históricos persistidos localmente.
3. **Análise de APM Real:** Diagnóstico de antipatterns como consultas sequenciais repetitivas (N+1) e tempos mortos (*gaps*) em requisições de sistemas de saúde legados.
4. **Visão Única (*Single Pane of Glass*):** Correlação direta entre picos de latência (Prometheus), falhas HTTP 500 estruturadas (Loki), saúde do sistema operacional (Zabbix) e tabelas transacionais (PostgreSQL).
