from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, FriendRequest
from .forms import CustomUserCreationForm, CustomUserChangeForm


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = User

    list_display = ['username', 'email', 'is_online', 'in_call', 'is_staff', 'date_joined']
    list_filter = ['is_online', 'in_call', 'is_staff', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    fieldsets = UserAdmin.fieldsets + (
        ('Профиль', {
            'fields': ('avatar', 'bio', 'is_online', 'last_seen')
        }),
        ('Звонки', {
            'fields': ('in_call', 'current_call_chat_id')
        }),
        ('Настройки', {
            'fields': ('email_notifications', 'sound_notifications')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Личная информация', {
            'fields': ('email', 'first_name', 'last_name')
        }),
    )


@admin.register(FriendRequest)
class FriendRequestAdmin(admin.ModelAdmin):
    list_display = ['from_user', 'to_user', 'created_at', 'accepted', 'accepted_at']
    list_filter = ['accepted', 'created_at']
    search_fields = ['from_user__username', 'to_user__username']