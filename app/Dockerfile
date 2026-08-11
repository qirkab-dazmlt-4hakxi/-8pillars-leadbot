FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY leadbot ./leadbot
RUN mkdir -p /app/data/inbox
CMD ["python","-m","leadbot.main","watch"]
