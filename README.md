# Lab Cloud — Observability & Kubernetes (K3s) Knowledge Base

Repositório técnico oficial contendo a arquitetura, manifestos Kubernetes (K3s), configurações como código, microsserviços instrumentados, mocks de provedores e pipelines de observabilidade do ambiente **Lab Cloud**.

O ambiente opera sob uma **arquitetura híbrida moderna, resiliente e otimizada**:
- **Zero consumo de cota de Remote Write**: As métricas são armazenadas localmente no **Prometheus (K3s)** e consultadas sob demanda pelo **Grafana Cloud** via **Grafana Private Data Source Connect (PDC)**.
- **Telemetria de IA & Antigravity (OTLP)**: Coleta automática de consumo de tokens (input, output, thoughts, total), modelo utilizado e erros de quota, enviando diretamente para o **Grafana Cloud OTLP Gateway** via **Grafana Alloy** e armazenando no **Prometheus**.
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
    │   └── Pod: grafana-pdc-agent          (Túnel seguro PDC para queries do Grafana Cloud)
    │
    ├── NAMESPACE: monitoring
    │   ├── Pod: prometheus                 (Armazenamento local de métricas | Porta 9090 - NodePort 30090)
    │   │                                   └── Data Source no Grafana Cloud: http://prometheus.monitoring.svc.cluster.local:9090
    │   ├── Pod: grafana                    (Dashboards locais OSS | Porta 3000 - NodePort 30300)
    │   ├── Pod: zabbix-server              (Servidor Zabbix | Porta 10051 - NodePort 30051)
    │   └── Pod: zabbix-web                 (Frontend Zabbix | Porta 8080 - NodePort 30080)
    │
    ├── NAMESPACE: database
    │   ├── Pod: postgresql                 (Porta 5432 - ClusterIP)
    │   └── Pod: pgadmin                    (Porta 80 / NodePort 30550)
    │
    ├── NAMESPACE: logging
    │   └── Pod: loki                       (Loki local | Porta 3100 / NodePort 30100)
    │
    ├── NAMESPACE: observability
    │   ├── Pod: grafana-alloy              (Agente OTLP, Loki Cloud e Tempo Cloud | Portas 12345, 9999, 4317, 4318)
    │   └── Pod: antigravity-exporter       (Telemetria de Tokens & Modelos Antigravity | Porta 9125 - NodePort 30925)
    │
    ├── NAMESPACE: applications
    │   ├── Pod: api-flask                  (Microsserviço com rotas e métricas | Porta 5000 / NodePort 30500)
    │   ├── Pod: api-coleta                 (Akamai Exporter | Porta 9110 / NodePort 30911)
    │   └── Pod: api-coleta-m365            (M365 Exporter & Auditoria | Porta 9115 / NodePort 30915)
    │
    └── NAMESPACE: simulations
        ├── Pod: mock-akamai                (Simulação CDN Akamai | Porta 8080)
        ├── Pod: mock-m365                  (Simulação Microsoft 365 | Porta 8080)
        └── Pod: traffic-generator          (Worker contínuo de simulação de carga e spikes)
```

---

## 🤖 Telemetria Antigravity & LLM (OTLP Gateway)

O ambiente monitora ativamente as interações e execuções da inteligência artificial **Antigravity**:

### 1. Métricas Coletadas
* **`antigravity_token_usage_total{model, token_type}`**: Total de tokens consumidos categorizados por modelo (ex.: `gemini-3.8-flash`, `gemini-2.5-pro`) e tipo (`input`, `output`, `thoughts`, `cached`, `tool`, `total`).
* **`antigravity_requests_total{model, status}`**: Total de chamadas executadas com sucesso ou falha.
* **`antigravity_errors_total{error_type}`**: Monitoramento de esgotamento de quota (`quota_exhausted`) e erros de API (`api_error`).
* **`antigravity_sessions_total`**: Contagem de sessões ativas do agente.

### 2. Fluxo de Exportação Duplo
1. **OTLP Gateway (Grafana Cloud)**:
   * O pod `antigravity-exporter` e qualquer script local envia telemetria via OTLP HTTP para `http://127.0.0.1:30318/v1/metrics`.
   * O **Grafana Alloy** autentica e despacha os dados para `https://otlp-gateway-prod-sa-east-1.grafana.net/otlp`.
2. **Prometheus Local (Grafana PDC)**:
   * O endpoint `http://127.0.0.1:30925/metrics` é raspado pelo Prometheus local a cada 15s e consultado diretamente pelo Grafana Cloud via túnel seguro **PDC**.

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
│   ├── 06-observability-alloy.yaml  # Grafana Alloy (Loki Cloud + OTLP Gateway)
│   ├── 07-grafana-pdc.yaml          # Deployment do Grafana PDC Agent
│   └── 08-antigravity-exporter.yaml # Exporter OTLP & Prometheus para Antigravity
├── app/                             # Código-fonte da Custom API Flask
├── antigravity-exporter/            # Coletor de telemetria e tokens da Antigravity
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

- **Telemetria Antigravity:**
  ```bash
  curl http://<IP_HOST>:30925/metrics | grep antigravity
  ```
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
