# Mock das APIs da Microsoft. Somente biblioteca padrao do Python:
# sem pip install, sem rede na build.
FROM python:3.12-slim

WORKDIR /app
COPY app.py .

ENV MOCK_PORT=8080
EXPOSE 8080

# O coletor roda fora do container e enxerga o mock em 127.0.0.1:8080.
# E esse endereco que precisa aparecer nos contentUri devolvidos.
ENV MOCK_HOST_PUBLICO=127.0.0.1:8080

CMD ["python", "-u", "app.py"]
