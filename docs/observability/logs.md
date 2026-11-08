---
title: Logs Estruturados com Grafana Loki
description: Pipeline de logs com driver oficial Docker e consultas LogQL
tags:
  - loki
  - logs
  - logql
  - docker-driver
---

# Ingestão de Logs com Grafana Loki

## 1. Configuração do Servidor Loki (`loki/local-config.yaml`)

O Grafana Loki indexa apenas os metadados (labels), armazenando o conteúdo textual bruto em blocos comprimidos no sistema de arquivos local (`filesystem`), eliminando dependências externas como S3 ou MinIO.

```yaml
auth_enabled: false

server:
  http_listen_port: 3100

common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

schema_config:
  configs:
    - from: 2020-10-24
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  reject_old_samples: true
  reject_old_samples_max_age: 168h # Retenção máxima de 7 dias
```

---

## 2. Instalação e Uso do Loki Docker Driver

Em vez de instalar agentes adicionais como Promtail ou Grafana Alloy na VM, foi utilizado o plugin oficial do Docker, que intercepta o `stdout` e o `stderr` do container e os envia ao Loki via HTTP push.

### Instalação do Plugin no Host Linux:
```bash
docker plugin install grafana/loki-docker-driver:latest --alias loki --grant-all-permissions
```

### Declaração no `docker-compose.yml`:
```yaml
    logging:
      driver: loki
      options:
        loki-url: "http://127.0.0.1:3100/loki/api/v1/push"
        loki-retries: "2"
        loki-max-backoff: "800ms"
        loki-timeout: "1s"
        labels: "job"
        loki-external-labels: "job=custom-api,env=lab"
```

---

## 3. Consultas LogQL Aplicadas

### Visualização de Todo o Stream da Aplicação:
Recupera o fluxo contínuo de registros vinculados à label `custom-api`:
```logql
{job="custom-api"}
```

### Filtro Exclusivo de Incidentes e Falhas (HTTP 500):
Utiliza o operador de busca em texto (`|=`) para capturar linhas de erro geradas na simulação:
```logql
{job="custom-api"} |= "ERROR"
```
