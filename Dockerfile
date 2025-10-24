FROM python:3.12

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app /app

ENV APP_CATEGORY="land"
ENV HOST="0.0.0.0"
ENV PORT="8000"

CMD ["python", "app.py"]
