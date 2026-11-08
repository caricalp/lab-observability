---
title: PostgreSQL 16 & pgAdmin 4
description: Modelagem relacional, gerenciamento via pgAdmin e comandos DDL/DML
tags:
  - postgresql
  - pgadmin
  - sql
  - ddl
---

# Banco de Dados PostgreSQL & pgAdmin 4

## 1. Arquitetura da Camada Relacional

O serviço `lab-postgres` atua simultaneamente como:
1. **Backend de Persistência do Zabbix:** Armazena configurações, hosts, templates, histórico de telemetria e triggers.
2. **Base de Dados Transacional da Aplicação:** Contém as tabelas de negócio do laboratório (ex.: pedidos processados).

O gerenciamento é realizado via **pgAdmin 4** rodando no container `lab-pgadmin` acessível na porta `5050`.

---

## 2. Parâmetros de Conexão no pgAdmin

* **Host name/address:** `postgres` *(resolvido pelo DNS interno do Docker)*
* **Porta:** `5432`
* **Maintenance database:** `zabbix`
* **Username:** `zabbix`
* **Password:** `zabbix_password` (ou a credencial personalizada atualizada)

---

## 3. Script SQL de Negócio Criado no pgAdmin

Para conectar o mundo relacional aos painéis do Grafana, a seguinte tabela foi modelada e populada:

```sql
CREATE TABLE IF NOT EXISTS api_pedidos (
    id SERIAL PRIMARY KEY,
    cliente VARCHAR(100) NOT NULL,
    valor NUMERIC(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'CONCLUIDO',
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Registros de teste para alimentar o dashboard
INSERT INTO api_pedidos (cliente, valor, status) VALUES
('Cliente Alfa', 150.50, 'CONCLUIDO'),
('Cliente Beta', 299.90, 'CONCLUIDO'),
('Cliente Gama', 89.00, 'PENDENTE'),
('Cliente Delta', 1200.00, 'CONCLUIDO');
```

---

## 4. Consulta SQL Integrada ao Grafana

No Data Source do PostgreSQL do Grafana, a consulta abaixo consolida o total financeiro aprovado:

```sql
SELECT SUM(valor) AS total_faturado 
FROM api_pedidos 
WHERE status = 'CONCLUIDO';
```
