---
title: Cheatsheet de Comandos & Operação
description: Comandos essenciais para gerenciamento diário do Lab Cloud
tags:
  - comandos
  - docker
  - operacao
  - cheatsheet
---

# Cheatsheet Operacional do Lab Cloud

## 1. Gestão do Ambiente Docker Compose

```bash
# Navegar até a raiz do projeto
cd ~/observability-lab

# Subir toda a infraestrutura em background
docker compose up -d

# Recompilar e subir apenas a API ou o Worker
docker compose up -d --build custom-api traffic-generator

# Verificar o estado dos 8 containers
docker compose ps

# Visualizar logs em tempo real do gerador de carga
docker logs -f lab-traffic-generator

# Visualizar logs da API
docker logs -f lab-api

# Parar todo o ambiente sem deletar os dados dos volumes
docker compose down
```

---

## 2. Testes de Conectividade e Endpoints

```bash
# Validar se a API responde e retorna o payload JSON
curl -i http://localhost:5000/api/pedidos

# Checar as métricas Prometheus exportadas pela API
curl -s http://localhost:5000/metrics | grep http_requests_total

# Checar se o Loki está pronto para receber logs
curl -s http://localhost:3100/ready

# Validar se a API do Zabbix está viva
curl -s http://localhost:8080/api_jsonrpc.php
```

---

## 3. Gestão e Manutenção do PostgreSQL via CLI

```bash
# Abrir console interativo psql como usuário zabbix
docker exec -it lab-postgres psql -U zabbix -d zabbix

# Listar tabelas criadas no banco
docker exec -it lab-postgres psql -U zabbix -d zabbix -c "\dt"

# Consultar registros da tabela de testes
docker exec -it lab-postgres psql -U zabbix -d zabbix -c "SELECT * FROM api_pedidos;"

# Resetar a senha do usuário Web do Zabbix (Admin) de volta para o padrão 'zabbix'
docker exec -it lab-postgres psql -U zabbix -d zabbix -c "UPDATE users SET passwd=md5('zabbix') WHERE username='Admin';"
```
