from django.db import models
from django.conf import settings
from django.utils import timezone


class Chat(models.Model):
    CHAT_TYPES = (
        ('private', 'Личный чат'),
        ('group', 'Групповой чат'),
    )

    chat_type = models.CharField(
        max_length=10,
        choices=CHAT_TYPES,
        default='private',
        verbose_name='Тип чата'
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Название'
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='chats',
        verbose_name='Участники'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлен')

    class Meta:
        verbose_name = 'Чат'
        verbose_name_plural = 'Чаты'
        ordering = ['-updated_at']

    def __str__(self):
        if self.chat_type == 'private':
            participants = self.participants.all()
            return f"Чат: {', '.join([p.username for p in participants])}"
        return self.name or f"Группа {self.id}"

    def get_other_participant(self, user):
        """Получить собеседника в личном чате"""
        if self.chat_type == 'private':
            return self.participants.exclude(id=user.id).first()
        return None


class Message(models.Model):
    chat = models.ForeignKey(
        Chat,
        related_name='messages',
        on_delete=models.CASCADE,
        verbose_name='Чат'
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='messages',
        on_delete=models.CASCADE,
        verbose_name='Отправитель'
    )
    content = models.TextField(verbose_name='Текст')
    attachment = models.FileField(
        upload_to='attachments/%Y/%m/',
        null=True,
        blank=True,
        verbose_name='Вложение'
    )
    is_read = models.BooleanField(default=False, verbose_name='Прочитано')
    is_edited = models.BooleanField(default=False, verbose_name='Изменено')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Отправлено')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Изменено')

    class Meta:
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.username}: {self.content[:50]}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])


class GroupChatMembership(models.Model):
    ROLES = (
        ('admin', 'Администратор'),
        ('member', 'Участник'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name='Пользователь'
    )
    chat = models.ForeignKey(
        Chat,
        on_delete=models.CASCADE,
        verbose_name='Чат'
    )
    role = models.CharField(
        max_length=10,
        choices=ROLES,
        default='member',
        verbose_name='Роль'
    )
    joined_at = models.DateTimeField(auto_now_add=True, verbose_name='Присоединился')

    class Meta:
        unique_together = ('user', 'chat')
        verbose_name = 'Участник группы'
        verbose_name_plural = 'Участники группы'

    def __str__(self):
        return f"{self.user.username} - {self.chat.name} ({self.role})"