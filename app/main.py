import os
import time
import random
import logging
import sys
import psycopg2
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Configuração de logging estruturado para o stdout do container (coletado pelo Loki)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [endpoint=%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("api-pedidos")

app = Flask(__name__)

# Configuração de conexão com o serviço PostgreSQL
DB_HOST = os.getenv("DB_HOST", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "zabbix")
DB_USER = os.getenv("DB_USER", "zabbix")
DB_PASSWORD = os.getenv("DB_PASSWORD", "@Carica98")

HTTP_REQUESTS_TOTAL = Counter(
    'http_requests_total',
    'Total de chamadas HTTP recebidas',
    ['method', 'endpoint', 'status']
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    'http_request_duration_seconds',
    'Duração das requisições HTTP em segundos',
    ['endpoint']
)

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=2
    )

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_pedidos (
                id SERIAL PRIMARY KEY,
                cliente VARCHAR(100) NOT NULL,
                valor NUMERIC(10, 2) NOT NULL,
                status VARCHAR(20) DEFAULT 'CONCLUIDO',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("SELECT COUNT(*) FROM api_pedidos;")
        if cur.fetchone()[0] == 0:
            cur.execute("""
                INSERT INTO api_pedidos (cliente, valor, status) VALUES
                ('Cliente Alfa', 150.50, 'CONCLUIDO'),
                ('Cliente Beta', 299.90, 'CONCLUIDO'),
                ('Cliente Gama', 89.00, 'PENDENTE'),
                ('Cliente Delta', 1200.00, 'CONCLUIDO');
            """)
        conn.commit()
        cur.close()
        conn.close()
        logger.info("Conexão com PostgreSQL validada e tabela api_pedidos pronta.")
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados PostgreSQL: {e}")

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@app.route('/api/pedidos', methods=['GET'])
def get_pedidos():
    start_time = time.time()
    # Simula carga de CPU/memória e latência sob estresse
    _buffer = [x ** 2 for x in range(15000)]
    latency = random.uniform(0.05, 0.30)
    time.sleep(latency)

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), COALESCE(SUM(valor), 0) FROM api_pedidos;")
        total_itens, valor_total = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        duration = time.time() - start_time
        HTTP_REQUESTS_TOTAL.labels(method='GET', endpoint='/api/pedidos', status='500').inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(endpoint='/api/pedidos').observe(duration)
        logger.error(f"Falha de conexão com PostgreSQL em /api/pedidos: {e} - Latência: {duration:.3f}s - Código: 500")
        return jsonify({"erro": "falha ao consultar banco de dados", "detalhe": str(e)}), 500

    # 10% de chance de falha interna simulada
    if random.random() < 0.10:
        duration = time.time() - start_time
        HTTP_REQUESTS_TOTAL.labels(method='GET', endpoint='/api/pedidos', status='500').inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(endpoint='/api/pedidos').observe(duration)
        logger.error(f"Falha ao consultar base de dados para pedidos. Latência: {duration:.3f}s - Código: 500")
        return jsonify({"erro": "falha interna temporária"}), 500

    duration = time.time() - start_time
    HTTP_REQUESTS_TOTAL.labels(method='GET', endpoint='/api/pedidos', status='200').inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(endpoint='/api/pedidos').observe(duration)

    logger.info(
        f"Lista de pedidos recuperada do Postgres com sucesso. "
        f"Total: {total_itens} itens (R$ {float(valor_total):.2f}). Latência: {duration:.3f}s - Código: 200"
    )
    return jsonify({
        "status": "sucesso",
        "total_pedidos": total_itens,
        "valor_total": float(valor_total)
    }), 200

# Rota explícita para simular erro 404 (Not Found) com log na própria app Flask
@app.route('/api/erro-404', methods=['GET'])
@app.route('/404', methods=['GET'])
def endpoint_404():
    start_time = time.time()
    time.sleep(random.uniform(0.01, 0.08))
    duration = time.time() - start_time

    HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint='/api/erro-404', status='404').inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(endpoint='/api/erro-404').observe(duration)

    logger.warning(
        f"WARN/ERROR 404 em {request.path}: Recurso ou pedido não encontrado. "
        f"IP={request.remote_addr} Latência: {duration:.3f}s - Código: 404"
    )
    return jsonify({
        "status": "erro",
        "codigo": 404,
        "mensagem": "Recurso não encontrado na API"
    }), 404

# Rota explícita para simular erro 500 (Internal Server Error) com log na própria app Flask
@app.route('/api/erro-500', methods=['GET'])
@app.route('/500', methods=['GET'])
def endpoint_500():
    start_time = time.time()
    # Aloca memória/CPU extra para ajudar a estressar os limites do container sob rajada do K6
    _heavy_alloc = bytearray(2 * 1024 * 1024)  # 2 MB por requisição concorrente
    time.sleep(random.uniform(0.05, 0.25))
    duration = time.time() - start_time

    HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint='/api/erro-500', status='500').inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(endpoint='/api/erro-500').observe(duration)

    logger.error(
        f"ERROR 500 em {request.path}: Exceção crítica não tratada / Timeout no pool do banco. "
        f"IP={request.remote_addr} Latência: {duration:.3f}s - Código: 500"
    )
    return jsonify({
        "status": "erro",
        "codigo": 500,
        "mensagem": "Erro interno crítico simulado no servidor"
    }), 500

# Handler global para qualquer outra rota inexistente também gerar log 404 e métrica
@app.errorhandler(404)
def handle_404(e):
    HTTP_REQUESTS_TOTAL.labels(method=request.method, endpoint=request.path, status='404').inc()
    logger.warning(f"Rota inexistente acessada: {request.path} - Código: 404")
    return jsonify({"status": "erro", "codigo": 404, "mensagem": "Endpoint não encontrado"}), 404

if __name__ == '__main__':
    init_db()
    # threaded=True permite concorrência para que a carga do K6 estresse CPU e RAM
    app.run(host='0.0.0.0', port=5000, threaded=True)
