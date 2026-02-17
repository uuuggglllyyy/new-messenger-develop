from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .forms import CustomUserCreationForm, UserProfileForm
from .models import FriendRequest

User = get_user_model()


def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, '🎉 Регистрация прошла успешно! Добро пожаловать!')
            return redirect('chat:home')
        else:
            messages.error(request, '❌ Пожалуйста, исправьте ошибки в форме.')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
def profile(request, username=None):
    """Просмотр профиля пользователя"""
    if username:
        user = get_object_or_404(User, username=username)
    else:
        user = request.user

    # Проверка дружбы
    are_friends = False
    friend_request_sent = None

    if request.user != user:
        are_friends = FriendRequest.objects.filter(
            Q(from_user=request.user, to_user=user, accepted=True) |
            Q(from_user=user, to_user=request.user, accepted=True)
        ).exists()

        if not are_friends:
            friend_request_sent = FriendRequest.objects.filter(
                from_user=request.user,
                to_user=user,
                accepted=False
            ).first()

    # Статистика
    friends_count = FriendRequest.objects.filter(
        Q(from_user=user) | Q(to_user=user), accepted=True
    ).count()

    chats_count = user.chats.count()

    context = {
        'profile_user': user,
        'are_friends': are_friends,
        'friend_request_sent': friend_request_sent,
        'friends_count': friends_count,
        'chats_count': chats_count,
    }
    return render(request, 'accounts/profile.html', context)


@login_required
def edit_profile(request):
    """Редактирование профиля"""
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Профиль успешно обновлен!')
            return redirect('accounts:profile')
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, 'accounts/edit_profile.html', {'form': form})


@login_required
@require_POST
def send_friend_request(request, user_id):
    """Отправка запроса в друзья"""
    to_user = get_object_or_404(User, id=user_id)

    if request.user == to_user:
        return JsonResponse({'error': 'Нельзя отправить запрос самому себе'}, status=400)

    # Проверяем существующий запрос
    existing_request = FriendRequest.objects.filter(
        from_user=request.user,
        to_user=to_user
    ).first()

    if existing_request:
        return JsonResponse({'error': 'Запрос уже отправлен'}, status=400)

    friend_request = FriendRequest.objects.create(
        from_user=request.user,
        to_user=to_user
    )

    return JsonResponse({
        'success': True,
        'message': f'Запрос отправлен пользователю {to_user.username}',
        'request_id': friend_request.id
    })


@login_required
@require_POST
def accept_friend_request(request, request_id):
    """Принять запрос в друзья"""
    friend_request = get_object_or_404(FriendRequest, id=request_id, to_user=request.user)
    friend_request.accept()

    return JsonResponse({
        'success': True,
        'message': f'Вы приняли запрос в друзья от {friend_request.from_user.username}'
    })


@login_required
@require_POST
def reject_friend_request(request, request_id):
    """Отклонить запрос в друзья"""
    friend_request = get_object_or_404(FriendRequest, id=request_id, to_user=request.user)
    friend_request.reject()

    return JsonResponse({'success': True, 'message': 'Запрос отклонен'})


@login_required
def friend_list(request):
    """Список друзей"""
    # Принятые запросы
    sent_requests = FriendRequest.objects.filter(from_user=request.user, accepted=True)
    received_requests = FriendRequest.objects.filter(to_user=request.user, accepted=True)

    friends = []
    for req in sent_requests:
        friends.append(req.to_user)
    for req in received_requests:
        friends.append(req.from_user)

    # Входящие запросы
    pending_requests = FriendRequest.objects.filter(to_user=request.user, accepted=False)

    # Онлайн друзья
    online_friends = [f for f in friends if f.is_online]

    context = {
        'friends': friends,
        'online_friends': online_friends,
        'pending_requests': pending_requests,
        'friends_count': len(friends),
        'online_count': len(online_friends),
    }
    return render(request, 'accounts/friend_list.html', context)


@login_required
def search_users(request):
    """Поиск пользователей"""
    query = request.GET.get('q', '').strip()
    users = []

    if query:
        users = User.objects.filter(
            Q(username__icontains=query) |
            Q(email__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        ).exclude(id=request.user.id)[:20]

    return render(request, 'accounts/search_users.html', {
        'users': users,
        'query': query,
        'count': len(users)
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