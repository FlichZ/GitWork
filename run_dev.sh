#!/bin/bash

# Цвета для вывода
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=====================================${NC}"
echo -e "${BLUE}   DOCFLOW GUARDIAN DEVELOPMENT    ${NC}"
echo -e "${BLUE}=====================================${NC}"

# Определение команды Python
if command -v python3 >/dev/null 2>&1; then
    python_cmd="python3"
else
    python_cmd="python"
fi

# Активация виртуального окружения
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Активация виртуального окружения (.venv)...${NC}"
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        source .venv/Scripts/activate
    else
        source .venv/bin/activate
    fi
elif [ -d "env" ]; then
    echo -e "${YELLOW}Активация виртуального окружения (env)...${NC}"
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
        source env/Scripts/activate
    else
        source env/bin/activate
    fi
else
    echo -e "${RED}Виртуальное окружение не найдено. Запуск в основном окружении.${NC}"
fi

# Проверка Redis
echo -e "${YELLOW}Проверка подключения к Redis...${NC}"
redis-cli ping > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo -e "${RED}Redis недоступен. Для работы чата и WebSockets необходим Redis.${NC}"
    echo -e "${YELLOW}Пожалуйста, убедитесь, что Redis запущен:${NC}"
    echo -e "${BLUE}sudo systemctl start redis${NC} (для Linux)"
    echo -e "${BLUE}brew services start redis${NC} (для macOS)"
    echo -e "${RED}Запуск без Redis. Функции чата будут недоступны.${NC}"
else
    echo -e "${GREEN}Redis доступен. WebSockets будут работать.${NC}"
fi

# Запуск Daphne для WebSockets в фоновом режиме
echo -e "${YELLOW}Запуск Daphne ASGI сервера для WebSockets...${NC}"
daphne -b 0.0.0.0 -p 8001 document_tracker.asgi:application &
DAPHNE_PID=$!
echo -e "${GREEN}Daphne запущен (PID: $DAPHNE_PID)${NC}"

# Функция для корректного завершения процессов
cleanup() {
    echo -e "${YELLOW}Завершение процессов...${NC}"
    kill $DAPHNE_PID
    echo -e "${GREEN}Процессы остановлены.${NC}"
    exit 0
}

# Регистрация обработчика сигналов
trap cleanup SIGINT SIGTERM

# Запуск Django сервера
echo -e "${YELLOW}Запуск Django сервера...${NC}"
echo -e "${GREEN}DocFlow Guardian доступен по адресу: http://127.0.0.1:8000${NC}"
$python_cmd manage.py runserver

# Если Django сервер завершается, завершаем и Daphne
cleanup 
 