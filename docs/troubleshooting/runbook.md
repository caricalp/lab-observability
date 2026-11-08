---
title: Guia de Resolução de Problemas (Runbook)
description: Diagnóstico e resolução detalhada de todos os erros encontrados no Lab Cloud
tags:
  - troubleshooting
  - runbook
  - fix
  - post-mortem
---

# Runbook de Troubleshooting — Lab Cloud

Este runbook compila todos os erros técnicos reais ocorridos durante a construção da infraestrutura, detalhando sintoma, causa-raiz, solução definitiva e prevenção futura.

---

## Incidente 1: `grafana-cli: executable file not found in $PATH`

### Sintoma
Ao tentar instalar o plugin do Zabbix manualmente dentro do container:
```text
OCI runtime exec failed: exec failed: unable to start container process: exec: "grafana-cli": executable file not found in $PATH
```

### Causa Raiz
Em versões modernas da imagem oficial do Grafana, o utilitário binário antigo `grafana-cli` foi unificado na CLI padrão (`grafana cli`) e reside no caminho `/usr/share/grafana/bin/`, que não é exportado por padrão no `$PATH` durante chamadas interativas via `docker exec`.

### Solução Aplicada
Em vez de scripts manuais dentro do container, declarou-se a variável de ambiente nativa no `docker-compose.yml`:
```yaml
environment:
  - GF_INSTALL_PLUGINS=alexanderzobnin-zabbix-app
```
*Prevenção:* O Grafana baixa, descompacta e registra o plugin automaticamente durante o ciclo de boot sem intervenção manual.

---

## Incidente 2: Falha de Sintaxe YAML (`did not find expected key`)

### Sintoma
```text
yaml: line 52: did not find expected key
```

### Causa Raiz
1. Duplicação da chave `grafana:` em duas posições do arquivo.
2. Uso de caracteres invisíveis Unicode (Non-Breaking Space `\u00a0` / NBSP) e tabs ao copiar blocos de código de navegadores web.
3. Desalinhamento da chave `POSTGRES_DB` no serviço `zabbix-web`.

### Solução Aplicada
1. Remoção do bloco duplicado.
2. Formatação estrita com indentação de 2 espaços em branco.
3. Validação do arquivo com `docker compose config` antes de iniciar os serviços.

---

## Incidente 3: Repositório do pgAdmin Incompatível com Ubuntu Plucky

### Sintoma
```text
Err:3 https://ftp.postgresql.org/pub/pgadmin/pgadmin4/apt/plucky pgadmin4 Release
  404 Not Found [IP: 2a04:4e42:f000::820 443]
E: The repository '... plucky Release' does not have a Release file.
```

### Causa Raiz
Tentativa de instalar o pacote `pgadmin4-web` via `apt` no sistema operacional hospedeiro rodando **Ubuntu Plucky**. O mantenedor oficial do pgAdmin não publicou compilações para essa release do Ubuntu.

### Solução Aplicada
1. Remoção do repositório quebrado do host:
   ```bash
   rm -f /etc/apt/sources.list.d/pgadmin4.list
   apt update
   ```
2. Conteinerização completa do pgAdmin no `docker-compose.yml` usando a imagem oficial `dpage/pgadmin4:latest` na porta `5050`.

---

## Incidente 4: `FATAL: password authentication failed for user "zabbix"`

### Sintoma
O container do Zabbix ou o pgAdmin não conseguem autenticar no PostgreSQL após alteração de senha no `docker-compose.yml`.

### Causa Raiz
A imagem oficial do PostgreSQL **ignora** alterações nas variáveis `POSTGRES_PASSWORD` após a inicialização da base, pois o volume de dados (`/var/lib/postgresql/data`) já está inicializado no disco.

### Solução Aplicada
Forçar a alteração de credencial diretamente no mecanismo relacional através do terminal:
```bash
docker exec -it lab-postgres psql -U zabbix -d zabbix -c "ALTER USER zabbix WITH PASSWORD 'SUA_NOVA_SENHA';"
docker compose restart zabbix-server zabbix-web
```

---

## Incidente 5: `Invalid character '<' looking for beginning of value` no Grafana

### Sintoma
O Grafana exibe o erro acima ao tentar testar o Data Source do Zabbix.

### Causa Raiz
O campo **URL** do Data Source foi preenchido com a rota web interativa do navegador (`http://...:8080/zabbix.php`). A página retornou HTML (`<!DOCTYPE...`), enquanto o plugin do Grafana esperava estritamente o formato JSON.

### Solução Aplicada
Corrigir a URL do Data Source para o endpoint oficial da API RPC:
```text
http://zabbix-web:8080/api_jsonrpc.php
```
