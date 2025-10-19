FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Опционально: системная таймзона (необязательно, мы и так используем pytz)
# RUN ln -snf /usr/share/zoneinfo/Asia/Ho_Chi_Minh /etc/localtime && echo "Asia/Ho_Chi_Minh" > /etc/timezone

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Render по умолчанию слушает порт из $PORT; используем uvicorn на нём
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}