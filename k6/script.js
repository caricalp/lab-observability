import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '20s', target: 10 },  // Aquecimento gradual
    { duration: '40s', target: 35 },  // Carga alta para pressionar CPU/Memória do container Flask
    { duration: '20s', target: 50 },  // Pico de estresse (força throttling / travamento sob limite de recursos)
    { duration: '20s', target: 5 },   // Recuperação
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://custom-api:5000';

export default function () {
  const rand = Math.random();

  if (rand < 0.65) {
    // 65% das chamadas vão para a rota principal integrada ao Postgres
    const res = http.get(`${BASE_URL}/api/pedidos`, { timeout: '3s' });
    check(res, {
      'status 200 em /api/pedidos': (r) => r.status === 200,
    });
  } else if (rand < 0.85) {
    // 20% das chamadas vão para o endpoint 404
    const res = http.get(`${BASE_URL}/api/erro-404`, { timeout: '3s' });
    check(res, {
      'status 404 em /api/erro-404': (r) => r.status === 404,
    });
  } else {
    // 15% das chamadas vão para o endpoint 500
    const res = http.get(`${BASE_URL}/api/erro-500`, { timeout: '3s' });
    check(res, {
      'status 500 em /api/erro-500': (r) => r.status === 500,
    });
  }

  sleep(Math.random() * 0.3 + 0.05);
}
