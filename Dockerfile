FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROGRESS_DB=/data/progress.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 題庫（questions.json、圖片）已經預先從 PDF 轉好，直接放進 image
COPY app.py sampler.py store.py ./
COPY data/questions.json data/questions.json
COPY templates templates
COPY static static

RUN useradd --uid 1000 --create-home app && mkdir -p /data && chown app:app /data
USER app
VOLUME ["/data"]
EXPOSE 8000

# SQLite 單檔寫入：只開 1 個 worker，用 thread 處理併發
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "app:app"]
