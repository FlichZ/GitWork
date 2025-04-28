from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json
from django.utils import timezone
from .models import Chat, ChatMessage, Organization, User

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope['user']
        self.session_key = self.scope['session'].session_key or self.scope['session'].get('_session_key')
        if not self.session_key:
            self.scope['session'].save()
            self.session_key = self.scope['session'].session_key
        self.chat_id = self.scope['url_route']['kwargs'].get('chat_id')
        print(f"WebSocket connect attempt: chat_id={self.chat_id}, user={self.user.username if self.user.is_authenticated else 'Guest'}, session_key={self.session_key}")

        if self.chat_id == 'support':
            self.chat = await self.get_support_chat()
            if not self.chat:
                await self.close()
                return
            self.room_group_name = 'support_chat'
        else:
            if not self.user.is_authenticated:
                await self.close()
                return
            self.chat = await self.get_chat(self.chat_id)
            if not self.chat:
                await self.close()
                return
            self.room_group_name = f'chat_{self.chat_id}'

        if self.chat_id != 'support' and self.user.is_authenticated:
            user_org = await self.get_user_organization(self.user)
            if not user_org:
                await self.close()
                return
            if user_org.is_prime_tech:
                # Асинхронно получаем prime_tech_organization
                prime_tech_org = await database_sync_to_async(lambda: self.chat.prime_tech_organization)()
                if prime_tech_org != user_org:
                    await self.close()
                    return
            else:
                # Асинхронно получаем secondary_organization
                secondary_org = await database_sync_to_async(lambda: self.chat.secondary_organization)()
                if secondary_org != user_org:
                    await self.close()
                    return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()
        print("WebSocket connection accepted")

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        saved_message = await self.save_message(self.chat, message)
        sender_name = self.user.username if self.user.is_authenticated else "Guest"
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender': sender_name,
                'session_key': self.session_key,
                'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
            }
        )

    async def chat_message(self, event):
        if self.chat_id == 'support':
            is_prime_tech = await self.is_prime_tech_user()
            is_sender = event['session_key'] == self.session_key
            if not (is_prime_tech or is_sender):
                return
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender': event['sender'],
            'timestamp': event['timestamp'],
        }))

    @database_sync_to_async
    def get_support_chat(self):
        try:
            return Chat.objects.select_related('prime_tech_organization').get(is_support=True)
        except Chat.DoesNotExist:
            prime_tech_org = Organization.objects.filter(is_prime_tech=True).first()
            if prime_tech_org:
                return Chat.objects.create(
                    prime_tech_organization=prime_tech_org,
                    is_support=True,
                    name="Support Chat"
                )
            return None

    @database_sync_to_async
    def get_chat(self, chat_id):
        try:
            return Chat.objects.select_related('prime_tech_organization', 'secondary_organization').get(id=chat_id)
        except Chat.DoesNotExist:
            return None

    @database_sync_to_async
    def get_user_organization(self, user):
        return user.organization if user.is_authenticated else None

    @database_sync_to_async
    def save_message(self, chat, message):
        return ChatMessage.objects.create(
            chat=chat,
            sender=self.user if self.user.is_authenticated else None,
            session_key=self.session_key if not self.user.is_authenticated else None,
            message=message,
            timestamp=timezone.now()
        )

    @database_sync_to_async
    def is_prime_tech_user(self):
        if not self.user.is_authenticated:
            return False
        return self.user.organization.is_prime_tech if self.user.organization else False