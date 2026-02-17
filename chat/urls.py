from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_home, name='home'),
    path('room/<int:chat_id>/', views.chat_room, name='chat_room'),
    path('create/<int:user_id>/', views.create_private_chat, name='create_private'),
    path('create-group/', views.create_group_chat, name='create_group'),
    path('upload/<int:chat_id>/', views.upload_file, name='upload_file'),
    path('message/<int:message_id>/delete/', views.delete_message, name='delete_message'),
    path('message/<int:message_id>/edit/', views.edit_message, name='edit_message'),
    path('clear/<int:chat_id>/', views.clear_chat, name='clear_chat'),
]