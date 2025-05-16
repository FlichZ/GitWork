FROM python:3.9-slim

# Установка переменных окружения
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBUG 0

# Установка рабочей директории
WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование проекта
COPY . .

# Сборка статических файлов
RUN python manage.py collectstatic --noinput

# Установка прав на выполнение скрипта запуска
RUN chmod +x /app/entrypoint.sh

# Запуск приложения
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"] 
 