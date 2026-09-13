FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VERTICAL=cybersecurity \
    PRODUCT_NAME=SignalPath

WORKDIR /app

COPY pyproject.toml ./
COPY config ./config
COPY src ./src
COPY prompts ./prompts
COPY data/readable/shodan_100.jsonl ./data/readable/shodan_100.jsonl
COPY app.py ./

RUN pip install --no-cache-dir .

EXPOSE 8501

HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]
