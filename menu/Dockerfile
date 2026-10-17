FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py menu_logic.py menu_db.py ./

CMD ["python", "app.py"]
