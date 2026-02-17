from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST
from .models import Notification


@login_required
def notification_list(request):
    """Список всех уведомлений"""
    notifications = Notification.objects.filter(user=request.user)

    # Отмечаем как прочитанные при просмотре
    if request.GET.get('mark_read') == 'true':
        notifications.filter(is_read=False).update(is_read=True)

    return render(request, 'notifications/list.html', {
        'notifications': notifications
    })


@login_required
def notification_dropdown(request):
    """Выпадающий список уведомлений для шапки"""
    notifications = Notification.objects.filter(
        user=request.user,
        is_read=False
    )[:10]

    count = notifications.count()
    html = render_to_string('notifications/dropdown.html', {
        'notifications': notifications
    })

    return JsonResponse({
        'html': html,
        'count': count
    })


@login_required
@require_POST
def mark_as_read(request, notification_id):
    """Отметить уведомление как прочитанное"""
    notification = get_object_or_404(
        Notification,
        id=notification_id,
        user=request.user
    )
    notification.mark_as_read()

    return JsonResponse({'success': True})


@login_required
@require_POST
def mark_all_read(request):
    """Отметить все как прочитанные"""
    Notification.objects.filter(
        user=request.user,
        is_read=False
    ).update(is_read=True)

    return JsonResponse({'success': True})


@login_required
def get_unread_count(request):
    """Получить количество непрочитанных"""
    count = Notification.objects.filter(
        user=request.user,
        is_read=False
    ).count()

    return JsonResponse({'count': count})