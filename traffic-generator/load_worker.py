import time
import random
import requests
import logging
import sys

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [traffic-worker] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("traffic-worker")

TARGET_URL = "http://custom-api:5000/api/pedidos"

def send_request():
    try:
        res = requests.get(TARGET_URL, timeout=2.0)
        return res.status_code
    except Exception as e:
        logger.warning(f"Falha de conexão com a API: {e}")
        return 0

def run():
    logger.info("Iniciando gerador contínuo de tráfego para a API...")
    cycle_counter = 0

    while True:
        cycle_counter += 1
        
        # Injeção de pico a cada 6 iterações
        if cycle_counter % 6 == 0:
            burst_size = random.randint(20, 35)
            logger.info(f">>> [SPIKE DETECTADO] Injetando rajada de {burst_size} requisições rápidas...")
            for _ in range(burst_size):
                send_request()
                time.sleep(random.uniform(0.01, 0.05))
            time.sleep(1.0)
            continue

        # Tráfego regular constante
        send_request()
        time.sleep(random.uniform(0.15, 0.45))

if __name__ == "__main__":
    time.sleep(5)
    run()
