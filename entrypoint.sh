#!/bin/bash

# Ожидание доступности базы данных
echo "Waiting for PostgreSQL..."
python -c "
import sys
import time
import psycopg2
from os import environ

# Получаем переменные окружения
DB_HOST = environ.get('DB_HOST', 'localhost')
DB_PORT = environ.get('DB_PORT', '5432')
DB_NAME = environ.get('DB_NAME', 'docflow_guardian')
DB_USER = environ.get('DB_USER', 'postgres')
DB_PASSWORD = environ.get('DB_PASSWORD', 'postgres')

# Максимальное количество попыток
max_attempts = 30
for i in range(max_attempts):
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
        )
        conn.close()
        print('PostgreSQL is available!')
        break
    except psycopg2.OperationalError:
        print(f'PostgreSQL not available yet (attempt {i+1}/{max_attempts})...')
        time.sleep(3)
        if i == max_attempts - 1:
            print('Maximum attempts reached. PostgreSQL connection failed.')
            sys.exit(1)
"

# Ожидание доступности Redis
echo "Waiting for Redis..."
python -c "
import sys
import time
import redis
from os import environ

# Получаем переменные окружения для Redis
REDIS_HOST = environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(environ.get('REDIS_PORT', 6379))

# Максимальное количество попыток
max_attempts = 30
for i in range(max_attempts):
    try:
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)
        r.ping()
        print('Redis is available!')
        break
    except (redis.exceptions.ConnectionError, ConnectionRefusedError):
        print(f'Redis not available yet (attempt {i+1}/{max_attempts})...')
        time.sleep(3)
        if i == max_attempts - 1:
            print('Maximum attempts reached. Redis connection failed.')
            sys.exit(1)
"

# Выполнение миграций
echo "Applying migrations..."
python manage.py migrate --noinput

# Проверка наличия суперпользователя и создание, если не существует
echo "Checking for superuser..."
python manage.py shell -c "
from django.contrib.auth import get_user_model;
User = get_user_model();
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin');
    print('Superuser created with username: admin, password: admin');
else:
    print('Superuser already exists.');
"

# Сбор статических файлов
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Запуск Daphne для WebSockets в фоновом режиме
echo "Starting Daphne for WebSockets..."
daphne -b 0.0.0.0 -p 8001 document_tracker.asgi:application &

# Запуск сервера через Gunicorn
echo "Starting Gunicorn server..."
gunicorn document_tracker.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 120 
 