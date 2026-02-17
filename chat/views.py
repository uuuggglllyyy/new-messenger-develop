from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, OuterRef, Subquery, Count
from django.views.decorators.http import require_POST
from django.utils import timezone
from .models import Chat, Message, GroupChatMembership
from accounts.models import User, FriendRequest


def get_friends(user):
    """Получает список друзей пользователя"""
    accepted_requests = FriendRequest.objects.filter(
        Q(from_user=user) | Q(to_user=user),
        accepted=True
    )

    friends = User.objects.none()
    for request in accepted_requests:
        if request.from_user == user:
            friends |= User.objects.filter(id=request.to_user.id)
        else:
            friends |= User.objects.filter(id=request.from_user.id)

    return friends.distinct()


@login_required
def chat_home(request):
    """Главная страница чата"""
    # Получаем чаты пользователя с последним сообщением
    chats = request.user.chats.annotate(
        last_message_time=Subquery(
            Message.objects.filter(chat=OuterRef('pk'))
            .order_by('-created_at')
            .values('created_at')[:1]
        )
    ).order_by('-last_message_time')

    # Получаем непрочитанные сообщения
    unread_counts = {}
    for chat in chats:
        unread_counts[chat.id] = chat.messages.filter(
            ~Q(sender=request.user),
            is_read=False
        ).count()

    # Получаем друзей онлайн
    friends = get_friends(request.user)
    online_friends = friends.filter(is_online=True)

    # Статистика
    total_friends = friends.count()
    total_unread = sum(unread_counts.values())

    context = {
        'chats': chats,
        'unread_counts': unread_counts,
        'online_friends': online_friends,
        'total_friends': total_friends,
        'total_unread': total_unread,
    }
    return render(request, 'chat/home.html', context)


@login_required
def chat_room(request, chat_id):
    """Комната чата"""
    chat = get_object_or_404(Chat, id=chat_id)

    if request.user not in chat.participants.all():
        messages.error(request, 'У вас нет доступа к этому чату.')
        return redirect('chat:home')

    # Получаем сообщения
    messages_list = Message.objects.filter(chat=chat).select_related('sender')

    # Отмечаем как прочитанные
    messages_list.filter(~Q(sender=request.user), is_read=False).update(is_read=True)

    # Получаем собеседника для личного чата
    other_participant = None
    if chat.chat_type == 'private':
        other_participant = chat.participants.exclude(id=request.user.id).first()

    context = {
        'chat': chat,
        'messages': messages_list,
        'other_participant': other_participant,
    }
    return render(request, 'chat/chat_room.html', context)


@login_required
def create_private_chat(request, user_id):
    """Создание личного чата"""
    other_user = get_object_or_404(User, id=user_id)

    # Проверяем существующий чат
    chat = Chat.objects.filter(
        chat_type='private',
        participants=request.user
    ).filter(participants=other_user).first()

    if not chat:
        chat = Chat.objects.create(chat_type='private')
        chat.participants.add(request.user, other_user)
        messages.success(request, f'Чат с {other_user.username} создан!')

    return redirect('chat:chat_room', chat_id=chat.id)


@login_required
def create_group_chat(request):
    """Создание группового чата"""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        participants_ids = request.POST.getlist('participants')

        if not name:
            messages.error(request, 'Введите название группы')
            return redirect('chat:create_group')

        if not participants_ids:
            messages.error(request, 'Выберите хотя бы одного участника')
            return redirect('chat:create_group')

        # Создаем чат
        chat = Chat.objects.create(
            chat_type='group',
            name=name
        )

        # Добавляем участников
        chat.participants.add(request.user, *participants_ids)

        # Создаем членство с ролью админа
        GroupChatMembership.objects.create(
            user=request.user,
            chat=chat,
            role='admin'
        )

        messages.success(request, f'Группа "{name}" создана!')
        return redirect('chat:chat_room', chat_id=chat.id)

    friends = get_friends(request.user)
    return render(request, 'chat/create_group.html', {'friends': friends})


@login_required
@require_POST
def upload_file(request, chat_id):
    """Загрузка файла"""
    if not request.FILES.get('file'):
        return JsonResponse({'error': 'Файл не выбран'}, status=400)

    chat = get_object_or_404(Chat, id=chat_id)

    if request.user not in chat.participants.all():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    file = request.FILES['file']

    # Проверка размера
    if file.size > 10 * 1024 * 1024:  # 10MB
        return JsonResponse({'error': 'Файл слишком большой (макс. 10MB)'}, status=400)

    # Проверка на дубликат
    recent_message = Message.objects.filter(
        chat=chat,
        sender=request.user,
        attachment__icontains=file.name,
        created_at__gte=timezone.now() - timezone.timedelta(seconds=5)
    ).first()

    if recent_message:
        return JsonResponse({
            'message_id': recent_message.id,
            'file_url': recent_message.attachment.url,
            'file_name': file.name,
            'duplicate': True
        })

    # Создаем сообщение
    message = Message.objects.create(
        chat=chat,
        sender=request.user,
        content='📎 Отправлен файл',
        attachment=file
    )

    return JsonResponse({
        'success': True,
        'message_id': message.id,
        'file_url': message.attachment.url,
        'file_name': file.name,
        'timestamp': message.created_at.isoformat(),
    })


@login_required
@require_POST
def delete_message(request, message_id):
    """Удаление сообщения"""
    try:
        message = Message.objects.get(id=message_id)

        if message.sender != request.user:
            return JsonResponse({'error': 'Нельзя удалить чужое сообщение'}, status=403)

        chat_id = message.chat.id
        message.delete()

        return JsonResponse({'success': True, 'chat_id': chat_id})
    except Message.DoesNotExist:
        return JsonResponse({'error': 'Сообщение не найдено'}, status=404)


@login_required
@require_POST
def edit_message(request, message_id):
    """Редактирование сообщения"""
    try:
        message = Message.objects.get(id=message_id)

        if message.sender != request.user:
            return JsonResponse({'error': 'Нельзя редактировать чужое сообщение'}, status=403)

        new_content = request.POST.get('content', '').strip()

        if not new_content:
            return JsonResponse({'error': 'Сообщение не может быть пустым'}, status=400)

        message.content = new_content
        message.is_edited = True
        message.save()

        return JsonResponse({
            'success': True,
            'message_id': message.id,
            'content': new_content,
            'edited': True
        })
    except Message.DoesNotExist:
        return JsonResponse({'error': 'Сообщение не найдено'}, status=404)


@login_required
@require_POST
def clear_chat(request, chat_id):
    """Очистить все свои сообщения в чате"""
    chat = get_object_or_404(Chat, id=chat_id)

    if request.user not in chat.participants.all():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    deleted = Message.objects.filter(
        chat=chat,
        sender=request.user
    ).delete()[0]

    return JsonResponse({
        'success': True,
        'deleted_count': deleted,
        'message': f'Удалено {deleted} сообщений'
    })