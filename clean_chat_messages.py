import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'messenger_project.settings')
django.setup()

from chat.models import Message, Chat
from django.db import connection


def clean_all_messages():
    """ПОЛНАЯ очистка всех дублирующихся сообщений"""

    print("🧹 НАЧАЛО ОЧИСТКИ СООБЩЕНИЙ")
    print("=" * 50)

    total_before = Message.objects.count()
    print(f"📊 Сообщений до очистки: {total_before}")

    # Получаем все чаты
    chats = Chat.objects.all()

    total_deleted = 0

    for chat in chats:
        print(f"\n📋 Чат #{chat.id}:")

        # Получаем все сообщения чата, группируем по содержимому и отправителю
        messages = Message.objects.filter(chat=chat).order_by('created_at')

        # Словарь для отслеживания уникальных сообщений
        unique_messages = {}
        to_delete = []

        for msg in messages:
            # Создаем ключ: отправитель + содержимое + дата (с точностью до минуты)
            key = f"{msg.sender_id}_{msg.content}_{msg.created_at.strftime('%Y%m%d%H%M')}"

            if key in unique_messages:
                to_delete.append(msg.id)
                print(f"  🗑️ Дубль: '{msg.content[:30]}...' от {msg.sender}")
            else:
                unique_messages[key] = msg.id

        # Удаляем дубликаты
        if to_delete:
            deleted = Message.objects.filter(id__in=to_delete).delete()[0]
            total_deleted += deleted
            print(f"  ✅ Удалено дублей: {deleted}")

    print("\n" + "=" * 50)
    print(f"✅ Всего удалено дублей: {total_deleted}")

    total_after = Message.objects.count()
    print(f"📊 Сообщений после очистки: {total_after}")

    # Сбрасываем автоинкремент
    with connection.cursor() as cursor:
        if connection.vendor == 'sqlite':
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='chat_message';")
            print("🔄 Сброс автоинкремента для SQLite")

    return total_deleted


def show_messages_by_chat():
    """Показать все сообщения по чатам"""

    chats = Chat.objects.all()

    print("\n📋 ТЕКУЩИЕ СООБЩЕНИЯ:")
    print("=" * 50)

    for chat in chats:
        print(f"\nЧат #{chat.id}:")
        messages = Message.objects.filter(chat=chat).order_by('created_at')

        if messages:
            for msg in messages:
                print(f"  [{msg.id}] {msg.sender}: {msg.content[:50]}")
        else:
            print("  Нет сообщений")


if __name__ == '__main__':
    # Показываем текущие сообщения
    show_messages_by_chat()

    # Спрашиваем подтверждение
    response = input("\n🗑️ Удалить ВСЕ дублирующиеся сообщения? (y/n): ")

    if response.lower() == 'y':
        clean_all_messages()
        show_messages_by_chat()
        print("\n✨ Очистка завершена! Теперь запустите сервер заново.")
    else:
        print("❌ Операция отменена")