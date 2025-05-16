# 📝 DocFlow Guardian

Система отслеживания и документооборота для управления служебными записками и документами организации. DocFlow Guardian облегчает процесс регистрации, отправки и получения документов внутри и извне организации.

## 🌟 Основные возможности

- 📄 Регистрация входящих и исходящих документов
- 🔄 Отслеживание статуса документов
- 👥 Управление пользователями с различными уровнями доступа
- 📊 Панель администратора для мониторинга
- 📝 Создание и использование шаблонов документов
- 🔍 Журнал документов с возможностью редактирования
- 🔄 Функции отмены и повтора действий
- 📤 Экспорт данных в Excel
- 🌐 Многоязычный интерфейс (Английский и Русский)
- 💬 Встроенная система чата и уведомлений в реальном времени
- 🔄 WebSocket-соединения для мгновенного обмена сообщениями

## 🔧 Технический стек

- **Бэкенд**: Django
- **Фронтенд**: HTML, CSS (Tailwind), JavaScript
- **База данных**: PostgreSQL
- **Контейнеризация**: Docker
- **Веб-сервер**: Nginx, Gunicorn

## 🚀 Установка и запуск

### Вариант 1: Через Docker (рекомендуется)

1. Убедитесь, что Docker и Docker Compose установлены на вашей системе.

2. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/yourusername/docflow-guardian.git
   cd docflow-guardian
   ```

3. Запустите контейнеры:
   ```bash
   docker-compose up -d
   ```

4. Приложение будет доступно по адресу http://localhost

5. Данные для входа по умолчанию:
   - Логин: `admin`
   - Пароль: `admin`

### Вариант 2: Быстрый запуск через скрипт

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/yourusername/docflow-guardian.git
   cd docflow-guardian
   ```

2. Запустите скрипт установки:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

3. Следуйте инструкциям на экране для завершения установки и создания администратора.

4. Приложение будет доступно по адресу http://127.0.0.1:8000

### Вариант 3: Ручная установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/yourusername/docflow-guardian.git
   cd docflow-guardian
   ```

2. Создайте и активируйте виртуальное окружение:
   ```bash
   python -m venv env
   source env/bin/activate  # для Linux/macOS
   # или
   env\Scripts\activate  # для Windows
   ```

3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

4. Создайте файл .env с следующим содержимым:
   ```
   SECRET_KEY=your_secret_key_here
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1

   # Настройки базы данных PostgreSQL
   DB_NAME=docflow_guardian
   DB_USER=postgres
   DB_PASSWORD=postgres
   DB_HOST=localhost
   DB_PORT=5432

   # Настройки Redis для Channels
   REDIS_HOST=127.0.0.1
   REDIS_PORT=6379
   ```

5. Для локальной разработки можно использовать SQLite вместо PostgreSQL:
   ```bash
   export DJANGO_USE_SQLITE=True
   ```

6. Выполните миграции:
   ```bash
   python manage.py migrate
   ```

7. Создайте суперпользователя:
   ```bash
   python manage.py createsuperuser
   ```

8. Соберите статические файлы:
   ```bash
   python manage.py collectstatic
   ```

9. Запустите сервер разработки:
   ```bash
   python manage.py runserver
   ```

10. Приложение будет доступно по адресу http://127.0.0.1:8000

### Вариант 4: Ручной запуск с поддержкой WebSocket и PostgreSQL

Для полноценной работы с поддержкой чата в реальном времени и базой данных PostgreSQL необходимо:

1. **Подготовка базы данных PostgreSQL:**
   ```bash
   # Создание базы данных
   sudo -u postgres psql -c "CREATE DATABASE docflow_guardian;"
   sudo -u postgres psql -c "CREATE USER postgres WITH PASSWORD 'postgres';"
   sudo -u postgres psql -c "ALTER ROLE postgres SET client_encoding TO 'utf8';"
   sudo -u postgres psql -c "ALTER ROLE postgres SET default_transaction_isolation TO 'read committed';"
   sudo -u postgres psql -c "ALTER ROLE postgres SET timezone TO 'UTC';"
   sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE docflow_guardian TO postgres;"
   ```

2. **Настройка Redis для WebSockets:**
   ```bash
   # Установка Redis (Ubuntu/Debian)
   sudo apt update
   sudo apt install redis-server
   
   # Установка Redis (macOS)
   brew install redis
   
   # Запуск Redis
   sudo systemctl start redis-server  # Linux
   # или
   brew services start redis          # macOS
   ```

3. **Создайте файл .env в корне проекта:**
   ```
   SECRET_KEY=your_secret_key_here
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   
   # Настройки базы данных PostgreSQL
   DB_NAME=docflow_guardian
   DB_USER=postgres
   DB_PASSWORD=postgres
   DB_HOST=localhost
   DB_PORT=5432
   
   # Настройки Redis для Channels
   REDIS_HOST=127.0.0.1
   REDIS_PORT=6379
   ```

4. **Установка зависимостей:**
   ```bash
   # Активация виртуального окружения
   source .venv/bin/activate  # для Linux/macOS
   # или
   .venv\Scripts\activate     # для Windows
   
   # Установка зависимостей
   pip install -r requirements.txt
   ```

5. **Применение миграций:**
   ```bash
   python manage.py migrate
   ```

6. **Создание суперпользователя:**
   ```bash
   python manage.py createsuperuser
   ```

7. **Сбор статических файлов:**
   ```bash
   python manage.py collectstatic --noinput
   ```

8. **Запуск серверов в разных терминалах:**

   Терминал 1 - Запуск Daphne для WebSockets:
   ```bash
   daphne -b 0.0.0.0 -p 8001 document_tracker.asgi:application
   ```

   Терминал 2 - Запуск Django:
   ```bash
   python manage.py runserver
   ```

9. **Или запуск обоих серверов через скрипт:**
   ```bash
   chmod +x run_dev.sh
   ./run_dev.sh
   ```

10. **Приложение будет доступно по адресу:**
    - Django: http://127.0.0.1:8000
    - WebSockets (для чата): ws://127.0.0.1:8001/ws/

### Проверка работы WebSockets

Чтобы убедиться, что WebSockets работают:
1. Откройте приложение в браузере
2. Войдите в систему
3. Перейдите в раздел чата
4. Отправьте сообщение — оно должно появиться без перезагрузки страницы

## ��‍💻 Использование

### Первый вход

После установки вы можете войти в систему используя учетные данные:

- **Для Docker**: 
  - Логин: `admin`
  - Пароль: `admin`

- **Для ручной установки**: 
  - Используйте учетные данные, указанные при выполнении `createsuperuser`

### Пользовательские роли

В системе предусмотрены следующие роли пользователей:
- **Администратор (admin)**: Полный доступ ко всем функциям
- **Менеджер (manager)**: Управление документами и базовый доступ к пользователям
- **Сотрудник (staff)**: Работа с документами
- **Внешний пользователь (external)**: Ограниченный доступ

### Основной функционал

1. **Отправка документов**: Регистрация и отправка документов другим пользователям или внешним получателям
2. **Получение документов**: Регистрация входящих документов
3. **Панель мониторинга**: Просмотр статистики и состояния документов
4. **Шаблоны**: Создание и использование шаблонов для повторяющихся документов
5. **Журналы**: Ведение подробных журналов всех действий с документами
6. **Уведомления**: Получение уведомлений о новых документах

### Система чатов в реальном времени

DocFlow Guardian поддерживает чаты в реальном времени с помощью технологии WebSockets:

1. **Внутренние чаты**: Общение между пользователями системы для обсуждения документов
2. **Чат поддержки**: Возможность обратиться к администраторам для получения помощи
3. **Мгновенные уведомления**: Получение уведомлений о документах и событиях в реальном времени

## 🔄 Резервное копирование

Для регулярного резервного копирования базы данных можно использовать встроенную функцию резервного копирования в интерфейсе администратора. Также для автоматического резервного копирования можно настроить cron-задачу.

### Резервное копирование в Docker:

```bash
docker-compose exec db pg_dump -U postgres -d docflow_guardian > backup_$(date +%Y-%m-%d).sql
```

### Восстановление в Docker:

```bash
cat your_backup_file.sql | docker-compose exec -T db psql -U postgres -d docflow_guardian
```

## 🌐 Многоязычность

DocFlow Guardian поддерживает несколько языков интерфейса:
- English (по умолчанию)
- Русский

Язык можно переключить через выпадающее меню в правом верхнем углу интерфейса.

## 🛠️ Настройка

Дополнительные настройки доступны через файл settings.py или через переменные окружения. Основные параметры:

- `DEBUG`: Включение/выключение режима отладки
- `ALLOWED_HOSTS`: Список разрешенных хостов
- `LANGUAGE_CODE`: Код языка по умолчанию
- `TIME_ZONE`: Временная зона
- `REDIS_HOST`, `REDIS_PORT`: Настройки подключения к Redis для WebSocket-коммуникации

## 📝 Лицензия

[MIT License](LICENSE)

## 📧 Контакты

Если у вас возникли вопросы или предложения по улучшению DocFlow Guardian, пожалуйста, создайте issue в репозитории или свяжитесь с нами по электронной почте: zubastik_bro@mail.ru 
 