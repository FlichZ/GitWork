#!/bin/bash

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}      DOCFLOW GUARDIAN SETUP     ${NC}"
echo -e "${BLUE}=====================================${NC}"

# Проверка наличия Python
echo -e "${YELLOW}Проверка наличия Python...${NC}"
if command -v python3 >/dev/null 2>&1; then
    python_cmd="python3"
    echo -e "${GREEN}Python найден!${NC}"
else
    if command -v python >/dev/null 2>&1; then
        python_cmd="python"
        echo -e "${GREEN}Python найден!${NC}"
    else
        echo -e "${RED}Python не найден. Пожалуйста, установите Python 3.8+ и попробуйте снова.${NC}"
        exit 1
    fi
fi

# Создание виртуального окружения
echo -e "${YELLOW}Создание виртуального окружения...${NC}"
$python_cmd -m venv .venv
if [ $? -ne 0 ]; then
    echo -e "${RED}Ошибка создания виртуального окружения. Убедитесь, что установлен пакет venv.${NC}"
    exit 1
fi
echo -e "${GREEN}Виртуальное окружение создано успешно!${NC}"

# Активация виртуального окружения
echo -e "${YELLOW}Активация виртуального окружения...${NC}"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    source .venv/Scripts/activate
else
    source .venv/bin/activate
fi
echo -e "${GREEN}Виртуальное окружение активировано!${NC}"

# Установка зависимостей
echo -e "${YELLOW}Установка зависимостей...${NC}"
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo -e "${RED}Ошибка установки зависимостей.${NC}"
    exit 1
fi
echo -e "${GREEN}Зависимости установлены успешно!${NC}"

# Проверка наличия файла .env
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Создание файла .env...${NC}"
    cat > .env << EOL
SECRET_KEY=$(openssl rand -hex 32)
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Настройки базы данных SQLite (для быстрой настройки)
DJANGO_USE_SQLITE=True

# Настройки базы данных PostgreSQL (если хотите использовать PostgreSQL)
# DB_NAME=docflow_guardian
# DB_USER=postgres
# DB_PASSWORD=postgres
# DB_HOST=localhost
# DB_PORT=5432

# Настройки Redis для Channels
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
EOL
    echo -e "${GREEN}Файл .env создан!${NC}"
fi

# Проверка Redis для WebSockets
echo -e "${YELLOW}Проверка наличия Redis (необходим для WebSockets)...${NC}"
if command -v redis-cli >/dev/null 2>&1; then
    echo -e "${GREEN}Redis найден!${NC}"
    redis-cli ping > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}Redis сервер не запущен.${NC}"
        echo -e "${YELLOW}Для работы чата и WebSockets убедитесь, что Redis запущен:${NC}"
        echo -e "${BLUE}sudo systemctl start redis${NC} (для Linux)"
        echo -e "${BLUE}brew services start redis${NC} (для macOS)"
    else
        echo -e "${GREEN}Redis сервер работает!${NC}"
    fi
else
    echo -e "${YELLOW}Redis не найден. Для работы чата и WebSockets необходимо установить Redis.${NC}"
    echo -e "${YELLOW}Инструкции по установке: https://redis.io/docs/getting-started/${NC}"
fi

# Миграции базы данных
echo -e "${YELLOW}Применение миграций...${NC}"
$python_cmd manage.py migrate
if [ $? -ne 0 ]; then
    echo -e "${RED}Ошибка применения миграций.${NC}"
    exit 1
fi
echo -e "${GREEN}Миграции применены успешно!${NC}"

# Сбор статических файлов
echo -e "${YELLOW}Сбор статических файлов...${NC}"
$python_cmd manage.py collectstatic --noinput
if [ $? -ne 0 ]; then
    echo -e "${RED}Ошибка сбора статических файлов.${NC}"
    exit 1
fi
echo -e "${GREEN}Статические файлы собраны успешно!${NC}"

# Создание суперпользователя
echo -e "${YELLOW}Хотите создать администратора с логином 'admin' и паролем 'admin'? (y/n)${NC}"
read create_default_admin
if [[ "$create_default_admin" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Создание стандартного суперпользователя...${NC}"
    $python_cmd manage.py shell -c "
from django.contrib.auth import get_user_model;
User = get_user_model();
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin');
    print('Суперпользователь успешно создан!');
else:
    print('Пользователь admin уже существует!');
"
    echo -e "${GREEN}Логин: admin, Пароль: admin${NC}"
else
    echo -e "${YELLOW}Создание собственного суперпользователя...${NC}"
    $python_cmd manage.py createsuperuser
    echo -e "${GREEN}Суперпользователь создан!${NC}"
fi

echo -e "${BLUE}=====================================${NC}"
echo -e "${GREEN}Установка DocFlow Guardian завершена успешно!${NC}"
echo -e "${BLUE}=====================================${NC}"
echo -e "${YELLOW}Для запуска Django сервера выполните:${NC}"
echo -e "${BLUE}$python_cmd manage.py runserver${NC}"
echo -e "${YELLOW}Для запуска WebSocket сервера в отдельном терминале выполните:${NC}"
echo -e "${BLUE}daphne -b 0.0.0.0 -p 8001 document_tracker.asgi:application${NC}"
echo -e "${YELLOW}Или используйте скрипт run_dev.sh для запуска обоих серверов.${NC}"
echo -e "${YELLOW}Перейдите по адресу: http://127.0.0.1:8000${NC}"
echo -e "${YELLOW}Логин: admin, Пароль: admin (если вы создали стандартного пользователя)${NC}" 
 