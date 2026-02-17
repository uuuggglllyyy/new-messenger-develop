from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, OuterRef, Subquery, Count
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone
from django.core.files.images import get_image_dimensions
import os
import mimetypes
from PIL import Image

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
    chats = request.user.chats.annotate(
        last_message_time=Subquery(
            Message.objects.filter(chat=OuterRef('pk'))
            .order_by('-created_at')
            .values('created_at')[:1]
        )
    ).order_by('-last_message_time')

    unread_counts = {}
    for chat in chats:
        unread_counts[chat.id] = chat.messages.filter(
            ~Q(sender=request.user),
            is_read=False
        ).count()

    friends = get_friends(request.user)
    online_friends = friends.filter(is_online=True)

    context = {
        'chats': chats,
        'unread_counts': unread_counts,
        'online_friends': online_friends,
    }
    return render(request, 'chat/home.html', context)


@login_required
def chat_room(request, chat_id):
    """Комната чата"""
    chat = get_object_or_404(Chat, id=chat_id)

    if request.user not in chat.participants.all():
        messages.error(request, 'У вас нет доступа к этому чату.')
        return redirect('chat:home')

    messages_list = Message.objects.filter(chat=chat).select_related('sender')
    messages_list.filter(~Q(sender=request.user), is_read=False).update(is_read=True)

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

    chat = Chat.objects.filter(
        chat_type='private',
        participants=request.user
    ).filter(participants=other_user).first()

    if not chat:
        chat = Chat.objects.create(chat_type='private')
        chat.participants.add(request.user, other_user)

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

        chat = Chat.objects.create(
            chat_type='group',
            name=name
        )

        chat.participants.add(request.user, *participants_ids)

        GroupChatMembership.objects.create(
            user=request.user,
            chat=chat,
            role='admin'
        )

        return redirect('chat:chat_room', chat_id=chat.id)

    friends = get_friends(request.user)
    return render(request, 'chat/create_group.html', {'friends': friends})


@login_required
@require_POST
def upload_file(request, chat_id):
    """Загрузка одного файла в чат"""
    print(f"\n=== ЗАГРУЗКА ФАЙЛА ===")
    print(f"Chat ID: {chat_id}")
    print(f"User: {request.user}")

    chat = get_object_or_404(Chat, id=chat_id)

    if request.user not in chat.participants.all():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    if not request.FILES.get('file'):
        return JsonResponse({'error': 'Файл не выбран'}, status=400)

    file = request.FILES['file']

    print(f"✅ Файл: {file.name}")
    print(f"  - Размер: {file.size} байт ({file.size / 1024:.2f} KB)")
    print(f"  - Content-Type: {file.content_type}")

    # Проверка размера (100MB)
    max_size = 100 * 1024 * 1024
    if file.size > max_size:
        return JsonResponse({
            'error': f'Файл слишком большой. Максимальный размер: 100MB'
        }, status=400)

    # Черный список расширений
    dangerous_extensions = ['.exe', '.bat', '.sh', '.cmd', '.msi', '.dll', '.so', '.dylib', '.app', '.deb', '.rpm']
    ext = os.path.splitext(file.name)[1].lower()
    if ext in dangerous_extensions:
        return JsonResponse({
            'error': 'Этот тип файла не разрешен для загрузки'
        }, status=400)

    # Определяем MIME тип
    content_type = file.content_type
    if not content_type or content_type == 'application/octet-stream':
        content_type = mimetypes.guess_type(file.name)[0] or 'application/octet-stream'

    # Подготавливаем данные
    message_data = {
        'chat': chat,
        'sender': request.user,
        'content': '',
        'attachment': file,
        'attachment_name': file.name,
        'attachment_size': file.size,
        'attachment_type': content_type,
    }

    # Если это изображение
    if content_type.startswith('image/'):
        try:
            img = Image.open(file)
            message_data['image_width'] = img.width
            message_data['image_height'] = img.height
            file.seek(0)
        except Exception as e:
            print(f"⚠️ Ошибка обработки изображения: {e}")

    # Сохраняем сообщение
    try:
        message = Message.objects.create(**message_data)
        print(f"✅ Сообщение #{message.id} создано")

        response_data = {
            'success': True,
            'message_id': message.id,
            'file_url': message.attachment.url,
            'file_name': message.attachment_name,
            'file_size': message.format_size(),
            'file_icon': message.get_file_icon(),
            'file_type': message.get_file_type_display(),
            'timestamp': message.created_at.isoformat(),
        }

        if message.is_image():
            response_data.update({
                'is_image': True,
                'image_width': message.image_width,
                'image_height': message.image_height,
            })
        elif message.is_video():
            response_data['is_video'] = True

        return JsonResponse(response_data)

    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@require_POST
def upload_multiple_files(request, chat_id):
    """Загрузка нескольких файлов"""
    chat = get_object_or_404(Chat, id=chat_id)

    if request.user not in chat.participants.all():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    files = request.FILES.getlist('files')

    if not files:
        return JsonResponse({'error': 'Файлы не выбраны'}, status=400)

    results = []
    errors = []

    for file in files:
        if file.size > 100 * 1024 * 1024:
            errors.append(f'{file.name}: файл слишком большой')
            continue

        try:
            content_type = file.content_type or mimetypes.guess_type(file.name)[0] or 'application/octet-stream'

            message_data = {
                'chat': chat,
                'sender': request.user,
                'content': '',
                'attachment': file,
                'attachment_name': file.name,
                'attachment_size': file.size,
                'attachment_type': content_type,
            }

            if content_type.startswith('image/'):
                try:
                    img = Image.open(file)
                    message_data['image_width'] = img.width
                    message_data['image_height'] = img.height
                    file.seek(0)
                except:
                    pass

            message = Message.objects.create(**message_data)

            results.append({
                'success': True,
                'message_id': message.id,
                'file_url': message.attachment.url,
                'file_name': message.attachment_name,
                'file_size': message.format_size(),
                'file_icon': message.get_file_icon(),
            })

        except Exception as e:
            errors.append(f'{file.name}: {str(e)}')

    return JsonResponse({
        'success': True,
        'results': results,
        'errors': errors,
    })


@login_required
@require_POST
def upload_voice(request, chat_id):
    """Загрузка голосового сообщения"""
    chat = get_object_or_404(Chat, id=chat_id)

    if request.user not in chat.participants.all():
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    if not request.FILES.get('audio'):
        return JsonResponse({'error': 'Аудиофайл не найден'}, status=400)

    audio = request.FILES['audio']
    duration = request.POST.get('duration', 0)

    # Проверка размера (макс 5MB)
    if audio.size > 5 * 1024 * 1024:
        return JsonResponse({'error': 'Файл слишком большой (макс. 5MB)'}, status=400)

    try:
        message = Message.objects.create(
            chat=chat,
            sender=request.user,
            content='🎤 Голосовое сообщение',
            attachment=audio,
            attachment_name=audio.name,
            attachment_size=audio.size,
            attachment_type='audio/webm',
            is_voice=True,
            voice_duration=duration
        )

        return JsonResponse({
            'success': True,
            'message_id': message.id,
            'audio_url': message.attachment.url,
            'duration': duration,
            'timestamp': message.created_at.isoformat(),
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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


@login_required
def set_online_status(request):
    """Обновление статуса онлайн"""
    if request.method == 'POST':
        is_online = request.POST.get('is_online') == 'true'
        user = request.user
        user.is_online = is_online
        user.save()
        return JsonResponse({'success': True})
    return JsonResponse({'error': 'Method not allowed'}, status=405)