# Планировщик проектов — образ для Docker
FROM python:3.12-slim

# Рабочая директория внутри контейнера
WORKDIR /app

# Сначала зависимости — слой кэшируется отдельно от кода
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY app/ ./app/

# Папки для БД и загруженных файлов (вынесем в volume, чтобы данные не терялись)
RUN mkdir -p /app/app/data/uploads

# Порт веб-приложения
EXPOSE 5000

# Простой healthcheck для docker-compose / оркестраторов
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/', timeout=3)" || exit 1

# Запуск приложения (без перезагрузки, слушает 0.0.0.0:5000)
CMD ["python", "app/main.py"]
