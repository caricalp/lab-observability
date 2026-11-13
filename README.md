# Lab Cloud — Observability & Kubernetes (K3s) Knowledge Base

Repositório técnico oficial contendo a arquitetura, manifestos Kubernetes (K3s), configurações como código, microsserviços instrumentados, mocks de provedores e pipelines de observabilidade do ambiente **Lab Cloud**.

O ambiente foi unificado e migrado para uma infraestrutura moderna e profissional baseada em **Kubernetes leve (K3s)** rodando sobre uma única VM Linux (Ubuntu Server), integrando observability local (*self-hosted*) e exportação contínua de métricas, logs e traces para o perfil principal do **Grafana Cloud** via **Grafana Alloy**.

---

## 🏛️ Arquitetura do Cluster K3s

```text
K3S CLUSTER
│
└── NODE-01 (Ubuntu Server - 192.168.0.208)
    │
    ├── NAMESPACE: monitoring
    │   ├── Pod: zabbix-server      (Porta 10051 / NodePort 30051)
    │   ├── Pod: zabbix-web         (Porta 8080 / NodePort 30080)
    │   ├── Pod: prometheus         (Porta 9090 / NodePort 30090)
    │   └── Pod: grafana            (Porta 3000 / NodePort 30300)
    │
    ├── NAMESPACE: database
    │   ├── Pod: postgresql         (Porta 5432 - ClusterIP)
    │   └── Pod: pgadmin            (Porta 80 / NodePort 30550)
    │
    ├── NAMESPACE: logging
    │   └── Pod: loki               (Porta 3100 / NodePort 30100)
    │
    ├── NAMESPACE: observability
    │   └── Pod: grafana-alloy      (Porta 12345 / NodePort 31234 | OTLP 4317/4318)
    │
    ├── NAMESPACE: applications
    │   ├── Pod: api-flask          (Porta 5000 / NodePort 30500)
    │   ├── Pod: api-coleta         (Akamai Exporter - Porta 9110 / NodePort 30911)
    │   └── Pod: api-coleta-m365    (M365 Exporter - Porta 9115 / NodePort 30915)
    │
    └── NAMESPACE: simulations
        ├── Pod: mock-akamai        (Simulação Akamai - Porta 8080)
        ├── Pod: mock-m365          (Simulação Microsoft 365 - Porta 8080)
        └── Pod: traffic-generator  (Worker contínuo de simulação de carga e spikes)
```

---

## 🚀 Componentes e Serviços

| Namespace | Pod / Serviço | Imagem | Papel no Ambiente | Acesso / NodePort |
| :--- | :--- | :--- | :--- | :--- |
| **monitoring** | `grafana` | `grafana/grafana-oss:latest` | Dashboards centralizados OSS | `http://<IP_HOST>:30300` |
| **monitoring** | `prometheus` | `prom/prometheus:latest` | Scraping e consultas PromQL | `http://<IP_HOST>:30090` |
| **monitoring** | `zabbix-web` | `zabbix-web-nginx-pgsql:alpine-7.0` | Frontend web administrativo Zabbix | `http://<IP_HOST>:30080` |
| **monitoring** | `zabbix-server` | `zabbix-server-pgsql:alpine-7.0` | Servidor de monitoramento Zabbix | `NodePort 30051` |
| **database** | `postgresql` | `postgres:16-alpine` | DB transacional da API e do Zabbix | Interno (`5432`) |
| **database** | `pgadmin` | `dpage/pgadmin4:latest` | Interface gráfica para PostgreSQL | `http://<IP_HOST>:30550` |
| **logging** | `loki` | `grafana/loki:3.0.0` | Coleta e agregação de logs com LogQL | `http://<IP_HOST>:30100` |
| **observability**| `grafana-alloy`| `grafana/alloy:v1.3.0` | Pipeline de telemetria para Grafana Cloud | `http://<IP_HOST>:31234` |
| **applications** | `api-flask` | `local/api-flask:latest` | Microsserviço com rotas e métricas | `http://<IP_HOST>:30500` |
| **applications** | `api-coleta` | `local/akamai-exporter:latest` | Coletor de telemetria Akamai | `http://<IP_HOST>:30911` |
| **applications** | `api-coleta-m365` | `local/m365-exporter:latest` | Coletor de telemetria e logs M365 | `http://<IP_HOST>:30915` |
| **simulations** | `mock-akamai` | `local/mock-akamai:latest` | Mock de CDN & Data Traffic Akamai | ClusterIP interno |
| **simulations** | `mock-m365` | `local/mock-m365:latest` | Mock de APIs Graph e O365 Audit | ClusterIP interno |
| **simulations** | `traffic-generator`| `local/traffic-generator:latest` | Gerador contínuo de carga e picos | Worker contínuo |

---

## 📂 Estrutura de Diretórios do Projeto

```text
lab-cloud/
├── k8s/
│   ├── 00-namespaces.yaml           # Criação dos 6 namespaces isolados
│   ├── 01-database.yaml             # PostgreSQL com PVC dedicado e pgAdmin
│   ├── 02-logging.yaml              # Grafana Loki com PVC e ConfigMap
│   ├── 03-simulations.yaml          # Mocks Akamai, M365 e Traffic Generator
│   ├── 04-applications.yaml         # API Flask, Akamai Exporter e M365 Exporter
│   ├── 05-monitoring.yaml           # Prometheus, Grafana e Zabbix (Server + Web)
│   └── 06-observability-alloy.yaml  # DaemonSet Grafana Alloy com RBAC para k8s
├── app/                             # Código-fonte da Custom API Flask
├── m365-exporter/                   # Coletor nativo de métricas e auditoria do M365
├── traffic-generator/               # Código-fonte do gerador de carga e spikes
├── k6/                              # Scripts de teste de carga K6
└── README.md                        # Documentação da arquitetura e operação
```

---

## ⚡ Como Implantar e Operar o Cluster

### 1. Pré-requisitos
- Ubuntu Server 22.04 / 24.04 LTS
- K3s instalado (`curl -sfL https://get.k3s.io | sh -s - --disable traefik`)
- Containerd e utilitário `kubectl` prontos no host

### 2. Configuração de Credenciais do Grafana Cloud
Configure o ConfigMap do Grafana Alloy com suas credenciais seguras do Grafana Cloud (Prometheus, Loki e OTLP):
- Crie ou edite o arquivo `k8s/06-observability-alloy.yaml` preenchendo os campos `<GRAFANA_CLOUD_USER_ID>` e `<GRAFANA_CLOUD_API_TOKEN>`.

### 3. Aplicação dos Manifestos
Para subir todo o ecossistema com um único comando:

```bash
kubectl apply -f k8s/
```

Verifique se todos os pods estão saudáveis:

```bash
kubectl get pods -A
```

---

## 🔍 Endpoints de Teste e Validação

- **API de Pedidos (Flask + PostgreSQL):**
  ```bash
  curl http://<IP_HOST>:30500/api/pedidos
  ```
- **Métricas Prometheus da Aplicação:**
  ```bash
  curl http://<IP_HOST>:30500/metrics
  ```
- **Métricas do Akamai Exporter:**
  ```bash
  curl http://<IP_HOST>:30911/metrics
  ```
- **Métricas do Microsoft 365 Exporter:**
  ```bash
  curl http://<IP_HOST>:30915/metrics
  ```
- **Painel de Controle do Grafana Alloy:**
  Acesse `http://<IP_HOST>:31234` para visualizar o grafo de componentes vivos do Alloy.

---

## 🛡️ Boas Práticas e Segurança
- Nenhum segredo ou credencial sensível é armazenado diretamente em código versionado.
- Os pods de banco de dados e simulações operam exclusivamente via ClusterIP interno dentro da malha de rede do K3s, expondo apenas as portas estritamente necessárias via NodePort.
