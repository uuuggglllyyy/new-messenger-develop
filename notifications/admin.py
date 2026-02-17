from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'title', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['user__username', 'title', 'message']
    readonly_fields = ['created_at']

    fieldsets = (
        ('Пользователь', {
            'fields': ('user',)
        }),
        ('Уведомление', {
            'fields': ('notification_type', 'title', 'message', 'link')
        }),
        ('Статус', {
            'fields': ('is_read', 'created_at')
        }),
    )