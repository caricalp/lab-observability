import time
import random
import logging
import sys
from flask import Flask, jsonify, request
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [endpoint=%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("api-pedidos")

app = Flask(__name__)

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

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@app.route('/api/pedidos', methods=['GET'])
def get_pedidos():
    start_time = time.time()
    latency = random.uniform(0.05, 0.40)
    time.sleep(latency)
    
    if random.random() < 0.10:
        duration = time.time() - start_time
        HTTP_REQUESTS_TOTAL.labels(method='GET', endpoint='/api/pedidos', status='500').inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(endpoint='/api/pedidos').observe(duration)
        
        logger.error(f"Falha ao consultar base de dados para pedidos. Latência: {duration:.3f}s - Código: 500")
        return jsonify({"erro": "falha interna temporária"}), 500
        
    duration = time.time() - start_time
    total = random.randint(10, 100)
    HTTP_REQUESTS_TOTAL.labels(method='GET', endpoint='/api/pedidos', status='200').inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(endpoint='/api/pedidos').observe(duration)
    
    logger.info(f"Lista de pedidos recuperada com sucesso. Total retornado: {total} itens. Latência: {duration:.3f}s")
    return jsonify({"status": "sucesso", "total_pedidos": total}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
