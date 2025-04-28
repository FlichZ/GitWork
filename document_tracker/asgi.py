import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Устанавливаем DJANGO_SETTINGS_MODULE перед любыми импортами Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'document_tracker.settings')

# Инициализируем Django ASGI приложение
django_asgi_app = get_asgi_application()

# Теперь безопасно импортировать маршруты WebSocket
from staffs.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})