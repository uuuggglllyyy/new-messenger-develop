from django.db import models
from django.conf import settings
from django.utils import timezone
import os
import mimetypes


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

    # Текстовое сообщение (может быть пустым, если есть вложение)
    content = models.TextField(verbose_name='Текст', blank=True)

    # Вложения
    attachment = models.FileField(
        upload_to='attachments/%Y/%m/',
        null=True,
        blank=True,
        verbose_name='Файл'
    )
    attachment_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='Имя файла'
    )
    attachment_size = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Размер файла (байт)'
    )
    attachment_type = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='MIME тип'
    )

    # Для изображений
    image_width = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Ширина изображения'
    )
    image_height = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Высота изображения'
    )

    # Для видео
    video_thumbnail = models.ImageField(
        upload_to='thumbnails/%Y/%m/',
        null=True,
        blank=True,
        verbose_name='Превью видео'
    )
    video_duration = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Длительность видео (сек)'
    )

    # Для голосовых сообщений
    is_voice = models.BooleanField(
        default=False,
        verbose_name='Голосовое сообщение'
    )
    voice_duration = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Длительность голоса (сек)'
    )

    # Статус
    is_read = models.BooleanField(default=False, verbose_name='Прочитано')
    is_edited = models.BooleanField(default=False, verbose_name='Изменено')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Отправлено')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Изменено')

    class Meta:
        verbose_name = 'Сообщение'
        verbose_name_plural = 'Сообщения'
        ordering = ['created_at']

    def __str__(self):
        if self.attachment:
            return f"{self.sender.username}: [{self.get_file_type_display()}] {self.attachment_name or 'файл'}"
        return f"{self.sender.username}: {self.content[:50]}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])

    def save(self, *args, **kwargs):
        """Автоматически заполняем информацию о файле при сохранении"""
        if self.attachment and not self.attachment_name:
            self.attachment_name = self.attachment.name.split('/')[-1]

            # Получаем размер файла
            if self.attachment.size:
                self.attachment_size = self.attachment.size

            # Определяем MIME тип
            if not self.attachment_type:
                import mimetypes
                mime_type, _ = mimetypes.guess_type(self.attachment_name)
                self.attachment_type = mime_type or 'application/octet-stream'

        super().save(*args, **kwargs)

    def get_file_icon(self):
        """Возвращает иконку Bootstrap Icons для типа файла"""
        if not self.attachment:
            return 'bi-file-earmark'

        ext = os.path.splitext(self.attachment_name)[1].lower() if self.attachment_name else ''

        icons = {
            # Изображения
            '.jpg': 'bi-file-image', '.jpeg': 'bi-file-image', '.png': 'bi-file-image',
            '.gif': 'bi-file-image', '.webp': 'bi-file-image', '.svg': 'bi-file-image',
            '.bmp': 'bi-file-image', '.ico': 'bi-file-image',

            # Видео
            '.mp4': 'bi-file-play', '.webm': 'bi-file-play', '.mov': 'bi-file-play',
            '.avi': 'bi-file-play', '.mkv': 'bi-file-play', '.flv': 'bi-file-play',
            '.wmv': 'bi-file-play', '.m4v': 'bi-file-play',

            # Аудио
            '.mp3': 'bi-file-music', '.wav': 'bi-file-music', '.ogg': 'bi-file-music',
            '.flac': 'bi-file-music', '.aac': 'bi-file-music', '.m4a': 'bi-file-music',

            # Документы
            '.pdf': 'bi-file-pdf',
            '.doc': 'bi-file-word', '.docx': 'bi-file-word',
            '.xls': 'bi-file-excel', '.xlsx': 'bi-file-excel',
            '.ppt': 'bi-file-ppt', '.pptx': 'bi-file-ppt',
            '.txt': 'bi-file-text', '.rtf': 'bi-file-text',
            '.odt': 'bi-file-text', '.ods': 'bi-file-spreadsheet',

            # Архивы
            '.zip': 'bi-file-zip', '.rar': 'bi-file-zip', '.7z': 'bi-file-zip',
            '.tar': 'bi-file-zip', '.gz': 'bi-file-zip',

            # Код
            '.py': 'bi-file-code', '.js': 'bi-file-code', '.html': 'bi-file-code',
            '.css': 'bi-file-code', '.json': 'bi-file-code', '.xml': 'bi-file-code',
            '.php': 'bi-file-code', '.java': 'bi-file-code', '.cpp': 'bi-file-code',
            '.c': 'bi-file-code', '.h': 'bi-file-code', '.sql': 'bi-file-code',
        }

        return icons.get(ext, 'bi-file-earmark')

    def get_file_type_display(self):
        """Возвращает читаемое название типа файла"""
        if self.is_voice:
            return 'Голосовое сообщение'

        if not self.attachment_type:
            return 'Файл'

        if self.attachment_type.startswith('image/'):
            return 'Изображение'
        elif self.attachment_type.startswith('video/'):
            return 'Видео'
        elif self.attachment_type.startswith('audio/'):
            return 'Аудио'
        elif 'pdf' in self.attachment_type:
            return 'PDF'
        elif 'word' in self.attachment_type or 'document' in self.attachment_type:
            return 'Документ'
        elif 'excel' in self.attachment_type or 'spreadsheet' in self.attachment_type:
            return 'Таблица'
        elif 'zip' in self.attachment_type or 'rar' in self.attachment_type or 'compressed' in self.attachment_type:
            return 'Архив'
        else:
            return 'Файл'

    def is_image(self):
        """Проверяет, является ли вложение изображением"""
        return bool(self.attachment and self.attachment_type and self.attachment_type.startswith('image/'))

    def is_video(self):
        """Проверяет, является ли вложение видео"""
        return bool(self.attachment and self.attachment_type and self.attachment_type.startswith('video/'))

    def is_audio(self):
        """Проверяет, является ли вложение аудио"""
        return bool(self.attachment and self.attachment_type and self.attachment_type.startswith('audio/'))

    def is_document(self):
        """Проверяет, является ли вложение документом"""
        if not self.attachment or self.is_image() or self.is_video() or self.is_audio() or self.is_voice:
            return False

        doc_types = ['pdf', 'word', 'document', 'text', 'excel', 'spreadsheet', 'presentation']
        return any(dt in (self.attachment_type or '').lower() for dt in doc_types)

    def format_size(self):
        """Форматирует размер файла в читаемый вид"""
        if not self.attachment_size:
            return ''

        size = self.attachment_size
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} ТБ"

    def get_thumbnail_url(self):
        """Возвращает URL превью для видео или изображения"""
        if self.video_thumbnail:
            return self.video_thumbnail.url
        return None


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