# Lab Cloud — Observability & Kubernetes (K3s) Knowledge Base

Repositório técnico oficial contendo a arquitetura, manifestos Kubernetes (K3s), configurações como código, microsserviços instrumentados, mocks de provedores e pipelines de observabilidade do ambiente **Lab Cloud**.

O ambiente opera sob uma **arquitetura híbrida moderna e otimizada**:
- **Zero consumo de cota de Remote Write**: As métricas são armazenadas localmente no **Prometheus (K3s)** e consultadas sob demanda pelo **Grafana Cloud** via **Grafana Private Data Source Connect (PDC)**.
- **Logs e Auditoria**: O **Grafana Alloy** unifica a coleta de logs dos pods e os eventos do Office 365 (com geolocalização `Country`, `Latitude`, `Longitude`), despachando para o **Loki Cloud**.
- **Traces Distribuídos**: Exportação OTLP para o **Tempo Cloud**.

---

## 🏛️ Arquitetura do Cluster K3s

```text
K3S CLUSTER
│
└── NODE-01 (Ubuntu Server - 192.168.0.208)
    │
    ├── NAMESPACE: default
    │   └── Pod: grafana-pdc-agent   (Túnel seguro PDC para consultas diretas do Grafana Cloud)
    │
    ├── NAMESPACE: monitoring
    │   ├── Pod: prometheus          (Armazenamento local de métricas | Porta 9090 - NodePort 30090)
    │   │                            └── Data Source no Grafana Cloud: http://prometheus.monitoring.svc.cluster.local:9090
    │   ├── Pod: grafana             (Dashboards locais OSS | Porta 3000 - NodePort 30300)
    │   ├── Pod: zabbix-server       (Servidor Zabbix | Porta 10051 - NodePort 30051)
    │   └── Pod: zabbix-web          (Frontend Zabbix | Porta 8080 - NodePort 30080)
    │
    ├── NAMESPACE: database
    │   ├── Pod: postgresql          (Porta 5432 - ClusterIP)
    │   └── Pod: pgadmin             (Porta 80 / NodePort 30550)
    │
    ├── NAMESPACE: logging
    │   └── Pod: loki                (Loki local | Porta 3100 / NodePort 30100)
    │
    ├── NAMESPACE: observability
    │   └── Pod: grafana-alloy       (Agente para Loki Cloud e Tempo Cloud | Portas 12345, 9999, 4317, 4318)
    │
    ├── NAMESPACE: applications
    │   ├── Pod: api-flask           (Microsserviço com rotas e métricas | Porta 5000 / NodePort 30500)
    │   ├── Pod: api-coleta          (Akamai Exporter | Porta 9110 / NodePort 30911)
    │   └── Pod: api-coleta-m365     (M365 Exporter & Auditoria | Porta 9115 / NodePort 30915)
    │
    └── NAMESPACE: simulations
        ├── Pod: mock-akamai         (Simulação CDN Akamai | Porta 8080)
        ├── Pod: mock-m365           (Simulação Microsoft 365 | Porta 8080)
        └── Pod: traffic-generator   (Worker contínuo de simulação de carga e spikes)
```

---

## 🚀 Componentes e Serviços

| Namespace | Pod / Serviço | Imagem | Papel no Ambiente | Acesso / NodePort |
| :--- | :--- | :--- | :--- | :--- |
| **default** | `grafana-pdc-agent` | `grafana/pdc-agent:latest` | Túnel seguro para queries do Grafana Cloud via PDC | Interno (Egress TLS) |
| **monitoring** | `prometheus` | `prom/prometheus:latest` | Data Source de métricas consultado pelo Grafana Cloud | `http://<IP_HOST>:30090` |
| **monitoring** | `grafana` | `grafana/grafana-oss:latest` | Dashboards centralizados OSS locais | `http://<IP_HOST>:30300` |
| **monitoring** | `zabbix-web` | `zabbix-web-nginx-pgsql:alpine-7.0` | Frontend web administrativo Zabbix | `http://<IP_HOST>:30080` |
| **monitoring** | `zabbix-server` | `zabbix-server-pgsql:alpine-7.0` | Servidor de monitoramento Zabbix | `NodePort 30051` |
| **database** | `postgresql` | `postgres:16-alpine` | DB transacional da API e do Zabbix | Interno (`5432`) |
| **database** | `pgadmin` | `dpage/pgadmin4:latest` | Interface gráfica para PostgreSQL | `http://<IP_HOST>:30550` |
| **logging** | `loki` | `grafana/loki:3.0.0` | Armazenamento local de logs | `http://<IP_HOST>:30100` |
| **observability**| `grafana-alloy`| `grafana/alloy:v1.3.0` | Envio de Logs (Loki Cloud) e Traces (Tempo Cloud) | `http://<IP_HOST>:31234` |
| **applications** | `api-flask` | `local/api-flask:latest` | Microsserviço com rotas e métricas | `http://<IP_HOST>:30500` |
| **applications** | `api-coleta` | `local/akamai-exporter:latest` | Coletor de telemetria Akamai | `http://<IP_HOST>:30911` |
| **applications** | `api-coleta-m365` | `local/m365-exporter:latest` | Coletor de telemetria e auditoria M365 | `http://<IP_HOST>:30915` |
| **simulations** | `mock-akamai` | `local/mock-akamai:latest` | Mock de CDN & Data Traffic Akamai | ClusterIP interno |
| **simulations** | `mock-m365` | `local/mock-m365:latest` | Mock de APIs Graph e O365 Audit | ClusterIP interno |
| **simulations** | `traffic-generator`| `local/traffic-generator:latest` | Gerador contínuo de carga e picos | Worker contínuo |

---

## 🌐 Estratégia de Otimização: Grafana Cloud via PDC

Para evitar custos e consumo da cota de **Remote Write** do Grafana Cloud:
1. **O Prometheus local** coleta e armazena todas as séries temporais dos containers, microsserviços e coletores dentro da VM Linux.
2. O **Grafana PDC Agent** estabelece um túnel reverso seguro (SSH/mTLS) para o endpoint `private-datasource-connect-prod-sa-east-1.grafana.net`.
3. No **Grafana Cloud**, o Data Source do Prometheus é configurado apontando diretamente para o DNS interno do cluster:
   ```text
   http://prometheus.monitoring.svc.cluster.local:9090
   ```
   marcado para utilizar a conexão privada do PDC.
4. **Resultado**: Os dashboards do Grafana Cloud consultam os dados diretamente no Prometheus local em tempo real, mantendo os dados protegidos e gastando **zero cota de Remote Write**.

---

## 📂 Estrutura de Diretórios do Projeto

```text
lab-cloud/
├── k8s/
│   ├── 00-namespaces.yaml           # Criação dos 6 namespaces isolados
│   ├── 01-database.yaml             # PostgreSQL com PVC dedicado e pgAdmin
│   ├── 02-logging.yaml              # Grafana Loki local com PVC e ConfigMap
│   ├── 03-simulations.yaml          # Mocks Akamai, M365 e Traffic Generator
│   ├── 04-applications.yaml         # API Flask, Akamai Exporter e M365 Exporter
│   ├── 05-monitoring.yaml           # Prometheus local (com PVC) e Zabbix
│   ├── 06-observability-alloy.yaml  # DaemonSet Grafana Alloy (Loki Cloud + Tempo Cloud)
│   └── 07-grafana-pdc.yaml          # Deployment do Grafana PDC Agent
├── app/                             # Código-fonte da Custom API Flask
├── m365-exporter/                   # Coletor nativo de métricas e auditoria do M365
├── traffic-generator/               # Código-fonte do gerador de carga e spikes
├── k6/                              # Scripts de teste de carga K6
└── README.md                        # Documentação da arquitetura e operação
```

---

## ⚡ Como Implantar e Operar o Cluster

### 1. Aplicação dos Manifestos
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

- **Prometheus Local:**
  ```bash
  curl http://<IP_HOST>:30090/api/v1/targets
  ```
- **Métricas do Akamai Exporter:**
  ```bash
  curl http://<IP_HOST>:30911/metrics
  ```
- **Métricas do Microsoft 365 Exporter:**
  ```bash
  curl http://<IP_HOST>:30915/metrics
  ```
- **API de Pedidos (Flask + PostgreSQL):**
  ```bash
  curl http://<IP_HOST>:30500/api/pedidos
  ```
- **Painel de Controle do Grafana Alloy:**
  Acesse `http://<IP_HOST>:31234` para visualizar os componentes ativos do Alloy.

---

## 🛡️ Boas Práticas e Segurança
- Nenhum segredo ou credencial sensível é armazenado em código versionado (uso de Secrets e placeholders `<GRAFANA_PDC_TOKEN>`, `<GRAFANA_CLOUD_API_TOKEN>`).
- Consultas externas da nuvem ocorrem exclusivamente através do canal criptografado do PDC, sem necessidade de expor o Prometheus na Internet pública.
