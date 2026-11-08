---
title: Métricas com Prometheus
description: Configuração do Prometheus TSDB, instrumentação e consultas PromQL
tags:
  - prometheus
  - métricas
  - promql
  - golden-signals
---

# Métricas com Prometheus (Golden Signals)

## 1. Configuração do Scraper (`prometheus/prometheus.yml`)

O Prometheus opera através do modelo **Pull** (*scraping*), consultando endpoints `/metrics` em intervalos pré-determinados.

```yaml
global:
  scrape_interval: 15s     # Frequência de coleta
  evaluation_interval: 15s # Frequência de avaliação de regras de alerta

scrape_configs:
  # Autocoleta do Prometheus
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  # Coleta da API do Lab Cloud via DNS da rede interna Docker
  - job_name: 'custom-api'
    static_configs:
      - targets: ['custom-api:5000']
```

---

## 2. Instrumentação no Código Python

No arquivo `app/main.py`, foram instanciados os dois tipos de métricas fundamentais:

```python
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Contador incremental: Total de requisições por método, rota e código de resposta
HTTP_REQUESTS_TOTAL = Counter(
    'http_requests_total',
    'Total de chamadas HTTP recebidas',
    ['method', 'endpoint', 'status']
)

# Histograma de latência: Mede a distribuição do tempo de processamento
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    'http_request_duration_seconds',
    'Duração das requisições HTTP em segundos',
    ['endpoint']
)
```

---

## 3. Consultas PromQL Utilizadas no Grafana

### Throughput / Requisições por Segundo (RPS)
Calcula a taxa instantânea de requisições por segundo recebidas pelo endpoint, agrupadas por código HTTP:
```promql
sum by (status) (rate(http_requests_total{job="custom-api"}[1m]))
```

### Taxa de Erro HTTP (%)
Calcula a proporção percentual de falhas HTTP 500 em relação ao tráfego total:
```promql
(sum(rate(http_requests_total{status="500"}[1m])) / sum(rate(http_requests_total[1m]))) * 100
```

### Latência Média do Endpoint (Segundos)
Mede o tempo médio despendido no processamento das rotas utilizando as somas e contagens do histograma:
```promql
sum(rate(http_request_duration_seconds_sum{endpoint="/api/pedidos"}[1m]))
/
sum(rate(http_request_duration_seconds_count{endpoint="/api/pedidos"}[1m]))
```
