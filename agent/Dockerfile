FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent.py .

# Anthropic key and project key come in at runtime via env vars — never bake them in
ENV PORT=8002

EXPOSE 8002

CMD ["python", "agent.py"]
