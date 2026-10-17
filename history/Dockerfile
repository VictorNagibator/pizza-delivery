FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py history_logic.py history_db.py ./

CMD ["python", "app.py"]
