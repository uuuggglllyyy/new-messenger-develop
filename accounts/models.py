from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from PIL import Image


class User(AbstractUser):
    # Разрешаем конфликты с auth.User
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='custom_user_set',
        related_query_name='custom_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='custom_user_set',
        related_query_name='custom_user',
    )

    # Профиль
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name='Аватар')
    bio = models.TextField(max_length=500, blank=True, verbose_name='О себе')

    # Статус
    is_online = models.BooleanField(default=False, verbose_name='Онлайн')
    last_seen = models.DateTimeField(null=True, blank=True, verbose_name='Последний визит')

    # Статус звонка
    in_call = models.BooleanField(default=False, verbose_name='В звонке')
    current_call_chat_id = models.IntegerField(null=True, blank=True, verbose_name='ID чата звонка')

    # Настройки
    email_notifications = models.BooleanField(default=True, verbose_name='Email уведомления')
    sound_notifications = models.BooleanField(default=True, verbose_name='Звуковые уведомления')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата регистрации')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

    def __str__(self):
        return self.username

    def get_full_name_or_username(self):
        """Возвращает полное имя или username"""
        full_name = self.get_full_name()
        return full_name if full_name else self.username

    def save(self, *args, **kwargs):
        # Обновляем last_seen при выходе
        if not self.is_online:
            self.last_seen = timezone.now()

        super().save(*args, **kwargs)

        # Обработка аватара
        if self.avatar:
            try:
                img = Image.open(self.avatar.path)
                if img.height > 300 or img.width > 300:
                    output_size = (300, 300)
                    img.thumbnail(output_size)
                    img.save(self.avatar.path)
            except:
                pass


class FriendRequest(models.Model):
    from_user = models.ForeignKey(
        User,
        related_name='friend_requests_sent',
        on_delete=models.CASCADE,
        verbose_name='Отправитель'
    )
    to_user = models.ForeignKey(
        User,
        related_name='friend_requests_received',
        on_delete=models.CASCADE,
        verbose_name='Получатель'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата запроса')
    accepted = models.BooleanField(default=False, verbose_name='Принят')
    accepted_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата принятия')

    class Meta:
        unique_together = ('from_user', 'to_user')
        verbose_name = 'Запрос в друзья'
        verbose_name_plural = 'Запросы в друзья'

    def __str__(self):
        return f"{self.from_user} -> {self.to_user}"

    def accept(self):
        self.accepted = True
        self.accepted_at = timezone.now()
        self.save()

    def reject(self):
        self.delete()