FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    TZ=Asia/Omsk

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY main.py ./
COPY config.yaml ./

# Данные (база вакансий, FSM) — на монтируемом томе, иначе теряются при пересборке.
RUN mkdir -p /data
ENV JOBHUNT_DB=/data/jobhunt.db \
    JOBHUNT_FSM_DB=/data/fsm.db \
    JOBHUNT_LOG_FILE=

CMD ["python", "main.py"]
