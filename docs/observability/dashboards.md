---
title: Dashboards Unificados no Grafana
description: Estrutura do painel consolidando Golden Signals, Logs, Zabbix e SQL
tags:
  - grafana
  - dashboards
  - single-pane-of-glass
---

# Dashboards Unificados no Grafana

O dashboard principal **`API Observability - Labs`** foi desenhado seguindo a filosofia *Single Pane of Glass*, integrando quatro tecnologias distintas em uma única visão operacional correlacionada.

```text
+----------------------------------------------------------------------------------------------------+
|                                    API OBSERVABILITY - LABS                                        |
+----------------------------------+----------------------------------+------------------------------+
| 1. Throughput (RPS)              | 2. Taxa de Erro (%)              | 3. Latência Média            |
| Data Source: Prometheus          | Data Source: Prometheus          | Data Source: Prometheus      |
| Type: Time Series (rate)         | Type: Gauge (0-100%)             | Type: Time Series (s)        |
+----------------------------------+----------------------------------+------------------------------+
| 4. Zabbix Server CPU Load        | 5. Volume Financeiro Pedidos     |                              |
| Data Source: Zabbix API          | Data Source: PostgreSQL          |                              |
| Type: Time Series (Load 1m)      | Type: Stat Card (R$)             |                              |
+----------------------------------+----------------------------------+------------------------------+
| 6. Logs de Execução (Live Stream)                                   | 7. Avisos Críticos (HTTP 500)|
| Data Source: Loki                                                   | Data Source: Loki            |
| Type: Logs Panel ({job="custom-api"})                               | Type: Logs ({...} |= "ERROR")|
+---------------------------------------------------------------------+------------------------------+
```

---

## Detalhamento dos Painéis Implementados

### Painel 1: Taxa de Requisições por Segundo (Throughput / RPS)
* **Objetivo:** Medir a carga total da API discriminada por status HTTP (`200` vs `500`).
* **Visualização:** Time series com preenchimento de área suave.
* **Consulta:**
  ```promql
  sum by (status) (rate(http_requests_total{job="custom-api"}[1m]))
  ```

### Painel 2: Taxa de Erros HTTP (Error Rate)
* **Objetivo:** Exibir visualmente o percentual de falhas geradas pelo sistema.
* **Visualização:** Gauge circular com faixas de cor (0-5% verde, 5-10% amarelo, >10% vermelho).
* **Consulta:**
  ```promql
  (sum(rate(http_requests_total{status="500"}[1m])) / sum(rate(http_requests_total[1m]))) * 100
  ```

### Painel 3: Latência Média de Resposta
* **Objetivo:** Detectar picos de lentidão na rota `/api/pedidos`.
* **Visualização:** Time series configurada na unidade `Time -> seconds (s)`.
* **Consulta:**
  ```promql
  sum(rate(http_request_duration_seconds_sum{endpoint="/api/pedidos"}[1m])) 
  / 
  sum(rate(http_request_duration_seconds_count{endpoint="/api/pedidos"}[1m]))
  ```

### Painel 4 & 5: Logs Gerais e Falhas Críticas
* **Objetivo:** Permitir inspeção imediata do stack trace e mensagens de erro quando um pico aparece no gráfico superior.
* **Consultas:** `{job="custom-api"}` e `{job="custom-api"} |= "ERROR"`.
