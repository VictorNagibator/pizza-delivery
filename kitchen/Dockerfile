FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py kitchen_logic.py kitchen_db.py ./

CMD ["python", "app.py"]