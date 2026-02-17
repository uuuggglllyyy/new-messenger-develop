import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Chat, Message
from notifications.models import Notification

User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.chat_id = self.scope['url_route']['kwargs']['chat_id']
        self.chat_group_name = f'chat_{self.chat_id}'

        if self.scope['user'].is_anonymous:
            await self.close()
        else:
            if not await self.is_participant():
                await self.close()
            else:
                await self.channel_layer.group_add(
                    self.chat_group_name,
                    self.channel_name
                )
                await self.accept()

                # Обновляем статус онлайн
                await self.set_user_online(True)

                # Сообщаем о подключении
                await self.channel_layer.group_send(
                    self.chat_group_name,
                    {
                        'type': 'user_online',
                        'user_id': self.scope['user'].id,
                        'username': self.scope['user'].username
                    }
                )

    async def disconnect(self, close_code):
        if hasattr(self, 'chat_group_name'):
            # Сообщаем об отключении
            await self.channel_layer.group_send(
                self.chat_group_name,
                {
                    'type': 'user_offline',
                    'user_id': self.scope['user'].id,
                    'username': self.scope['user'].username
                }
            )

            await self.channel_layer.group_discard(
                self.chat_group_name,
                self.channel_name
            )

            # Обновляем статус онлайн
            await self.set_user_online(False)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            # Текстовое сообщение
            if message_type == 'message':
                await self.handle_message(data)

            # Файловое сообщение (НОВОЕ)
            elif message_type == 'file_message':
                await self.handle_file_message(data)

            # Индикатор печатания
            elif message_type == 'typing':
                await self.handle_typing(data)

            # Прочтение сообщений
            elif message_type == 'read':
                await self.handle_read()

            # === ЗВОНКИ ===
            elif message_type == 'call_offer':
                await self.handle_call_offer(data)
            elif message_type == 'call_answer':
                await self.handle_call_answer(data)
            elif message_type == 'ice_candidate':
                await self.handle_ice_candidate(data)
            elif message_type == 'call_end':
                await self.handle_call_end()
            elif message_type == 'call_reject':
                await self.handle_call_reject(data)

            # Редактирование сообщения
            elif message_type == 'edit':
                await self.handle_edit(data)

            # Удаление сообщения
            elif message_type == 'delete':
                await self.handle_delete(data)

        except Exception as e:
            print(f"❌ Error in receive: {e}")

    async def handle_message(self, data):
        """Обработка текстового сообщения"""
        content = data['message'].strip()

        if not content:
            return

        message = await self.save_message(content)

        if message:
            await self.channel_layer.group_send(
                self.chat_group_name,
                {
                    'type': 'chat_message',
                    'message_id': message.id,
                    'message': content,
                    'sender': self.scope['user'].username,
                    'sender_id': self.scope['user'].id,
                    'timestamp': message.created_at.isoformat(),
                    'is_edited': False
                }
            )

            await self.create_notifications(message)

    # НОВЫЙ МЕТОД: Обработка файлового сообщения
    async def handle_file_message(self, data):
        """Обработка сообщения с файлом"""
        file_data = {
            'message_id': data['message_id'],
            'file_url': data['file_url'],
            'file_name': data['file_name'],
            'file_size': data['file_size'],
            'file_icon': data['file_icon'],
            'is_image': data.get('is_image', False),
            'is_video': data.get('is_video', False),
            'image_width': data.get('image_width'),
            'image_height': data.get('image_height'),
        }

        await self.channel_layer.group_send(
            self.chat_group_name,
            {
                'type': 'file_message',
                'sender': self.scope['user'].username,
                'sender_id': self.scope['user'].id,
                'timestamp': data['timestamp'],
                **file_data
            }
        )

    async def handle_typing(self, data):
        """Обработка индикатора печатания"""
        await self.channel_layer.group_send(
            self.chat_group_name,
            {
                'type': 'typing_indicator',
                'user': self.scope['user'].username,
                'is_typing': data['is_typing'],
            }
        )

    async def handle_read(self):
        """Обработка прочтения сообщений"""
        count = await self.mark_messages_as_read()

        if count > 0:
            await self.channel_layer.group_send(
                self.chat_group_name,
                {
                    'type': 'read_receipt',
                    'user_id': self.scope['user'].id,
                    'username': self.scope['user'].username,
                }
            )

    async def handle_call_offer(self, data):
        """Обработка предложения звонка"""
        await self.channel_layer.group_send(
            self.chat_group_name,
            {
                'type': 'call_offer',
                'offer': data['offer'],
                'from_user_id': self.scope['user'].id,
                'from_username': self.scope['user'].username,
                'call_type': data.get('call_type', 'video'),
            }
        )

    async def handle_call_answer(self, data):
        """Обработка ответа на звонок"""
        await self.channel_layer.group_send(
            self.chat_group_name,
            {
                'type': 'call_answer',
                'answer': data['answer'],
                'from_user_id': self.scope['user'].id,
            }
        )

    async def handle_ice_candidate(self, data):
        """Обработка ICE кандидата"""
        await self.channel_layer.group_send(
            self.chat_group_name,
            {
                'type': 'ice_candidate',
                'candidate': data['candidate'],
                'from_user_id': self.scope['user'].id,
            }
        )

    async def handle_call_end(self):
        """Обработка завершения звонка"""
        await self.channel_layer.group_send(
            self.chat_group_name,
            {
                'type': 'call_end',
                'from_user_id': self.scope['user'].id,
            }
        )

    async def handle_call_reject(self, data):
        """Обработка отклонения звонка"""
        await self.channel_layer.group_send(
            self.chat_group_name,
            {
                'type': 'call_reject',
                'from_user_id': self.scope['user'].id,
                'reason': data.get('reason', 'rejected'),
            }
        )

    async def handle_edit(self, data):
        """Обработка редактирования сообщения"""
        message_id = data['message_id']
        new_content = data['content'].strip()

        if not new_content:
            return

        success = await self.edit_message(message_id, new_content)

        if success:
            await self.channel_layer.group_send(
                self.chat_group_name,
                {
                    'type': 'message_edited',
                    'message_id': message_id,
                    'content': new_content,
                    'edited_by': self.scope['user'].id,
                    'edited_at': timezone.now().isoformat(),
                }
            )

    async def handle_delete(self, data):
        """Обработка удаления сообщения"""
        message_id = data['message_id']
        success = await self.delete_message(message_id)

        if success:
            await self.channel_layer.group_send(
                self.chat_group_name,
                {
                    'type': 'message_deleted',
                    'message_id': message_id,
                    'deleted_by': self.scope['user'].id,
                }
            )

    # Отправка событий в WebSocket
    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'message_id': event['message_id'],
            'message': event['message'],
            'sender': event['sender'],
            'sender_id': event['sender_id'],
            'timestamp': event['timestamp'],
            'is_edited': event.get('is_edited', False),
        }))

    # НОВЫЙ МЕТОД: Отправка файлового сообщения
    async def file_message(self, event):
        """Отправка файлового сообщения"""
        await self.send(text_data=json.dumps({
            'type': 'file',
            'message_id': event['message_id'],
            'file_url': event['file_url'],
            'file_name': event['file_name'],
            'file_size': event['file_size'],
            'file_icon': event['file_icon'],
            'is_image': event.get('is_image', False),
            'is_video': event.get('is_video', False),
            'image_width': event.get('image_width'),
            'image_height': event.get('image_height'),
            'sender': event['sender'],
            'sender_id': event['sender_id'],
            'timestamp': event['timestamp'],
        }))

    async def typing_indicator(self, event):
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'user': event['user'],
            'is_typing': event['is_typing'],
        }))

    async def read_receipt(self, event):
        await self.send(text_data=json.dumps({
            'type': 'read',
            'user_id': event['user_id'],
            'username': event['username'],
        }))

    async def user_online(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_online',
            'user_id': event['user_id'],
            'username': event['username'],
        }))

    async def user_offline(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_offline',
            'user_id': event['user_id'],
            'username': event['username'],
        }))

    async def call_offer(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_offer',
            'offer': event['offer'],
            'from_user_id': event['from_user_id'],
            'from_username': event['from_username'],
            'call_type': event.get('call_type', 'video'),
        }))

    async def call_answer(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_answer',
            'answer': event['answer'],
            'from_user_id': event['from_user_id'],
        }))

    async def ice_candidate(self, event):
        await self.send(text_data=json.dumps({
            'type': 'ice_candidate',
            'candidate': event['candidate'],
            'from_user_id': event['from_user_id'],
        }))

    async def call_end(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_end',
            'from_user_id': event['from_user_id'],
        }))

    async def call_reject(self, event):
        await self.send(text_data=json.dumps({
            'type': 'call_reject',
            'from_user_id': event['from_user_id'],
            'reason': event.get('reason', 'rejected'),
        }))

    async def message_edited(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_edited',
            'message_id': event['message_id'],
            'content': event['content'],
            'edited_by': event['edited_by'],
            'edited_at': event['edited_at'],
        }))

    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id'],
            'deleted_by': event['deleted_by'],
        }))

    # Database методы
    @database_sync_to_async
    def is_participant(self):
        try:
            chat = Chat.objects.get(id=self.chat_id)
            return chat.participants.filter(id=self.scope['user'].id).exists()
        except Chat.DoesNotExist:
            return False

    @database_sync_to_async
    def set_user_online(self, is_online):
        user = self.scope['user']
        user.is_online = is_online
        user.save(update_fields=['is_online'])

    @database_sync_to_async
    def save_message(self, content):
        # Проверка на дубликат
        recent = Message.objects.filter(
            chat_id=self.chat_id,
            sender=self.scope['user'],
            content=content,
            created_at__gte=timezone.now() - timezone.timedelta(seconds=2)
        ).exists()

        if recent:
            return None

        chat = Chat.objects.get(id=self.chat_id)
        return Message.objects.create(
            chat=chat,
            sender=self.scope['user'],
            content=content
        )

    @database_sync_to_async
    def edit_message(self, message_id, new_content):
        try:
            message = Message.objects.get(
                id=message_id,
                sender=self.scope['user'],
                chat_id=self.chat_id
            )
            message.content = new_content
            message.is_edited = True
            message.save(update_fields=['content', 'is_edited', 'updated_at'])
            return True
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def delete_message(self, message_id):
        try:
            message = Message.objects.get(
                id=message_id,
                sender=self.scope['user'],
                chat_id=self.chat_id
            )
            message.delete()
            return True
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def mark_messages_as_read(self):
        return Message.objects.filter(
            chat_id=self.chat_id,
            is_read=False
        ).exclude(sender=self.scope['user']).update(is_read=True)

    @database_sync_to_async
    def create_notifications(self, message):
        if not message:
            return

        chat = Chat.objects.get(id=self.chat_id)
        recipients = chat.participants.exclude(id=self.scope['user'].id)

        for recipient in recipients:
            if recipient.email_notifications:
                # Здесь можно добавить отправку email
                pass

            Notification.objects.create(
                user=recipient,
                notification_type='message',
                title=f'Новое сообщение от {self.scope["user"].username}',
                message=message.content[:50] + ('...' if len(message.content) > 50 else ''),
                link=f'/chat/room/{self.chat_id}/'
            )


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope['user'].is_anonymous:
            await self.close()
        else:
            self.notification_group = f'notifications_{self.scope["user"].id}'
            await self.channel_layer.group_add(
                self.notification_group,
                self.channel_name
            )
            await self.accept()

            # Отправляем количество непрочитанных
            await self.send_unread_count()

    async def disconnect(self, close_code):
        if hasattr(self, 'notification_group'):
            await self.channel_layer.group_discard(
                self.notification_group,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get('type') == 'mark_read':
                await self.mark_notification_read(data.get('notification_id'))
            elif data.get('type') == 'mark_all_read':
                await self.mark_all_read()
        except:
            pass

    async def send_notification(self, event):
        await self.send(text_data=json.dumps({
            'type': 'notification',
            'notification_id': event['notification_id'],
            'title': event['title'],
            'message': event['message'],
            'link': event['link'],
            'created_at': event['created_at'],
        }))

        # Обновляем счетчик
        await self.send_unread_count()

    async def send_unread_count(self):
        count = await self.get_unread_count()
        await self.send(text_data=json.dumps({
            'type': 'unread_count',
            'count': count
        }))

    @database_sync_to_async
    def get_unread_count(self):
        from notifications.models import Notification
        return Notification.objects.filter(
            user=self.scope['user'],
            is_read=False
        ).count()

    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        from notifications.models import Notification
        try:
            notification = Notification.objects.get(
                id=notification_id,
                user=self.scope['user']
            )
            notification.is_read = True
            notification.save()
            return True
        except:
            return False

    @database_sync_to_async
    def mark_all_read(self):
        from notifications.models import Notification
        return Notification.objects.filter(
            user=self.scope['user'],
            is_read=False
        ).update(is_read=True)