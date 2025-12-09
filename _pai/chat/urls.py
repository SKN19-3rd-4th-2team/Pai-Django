# chat/urls.py
from django.urls import path
from . import views

app_name = "chat"

urlpatterns = [
    path("chat/", views.chat_interface, name="chat_interface"),
    path("api/stream/", views.chat_stream_api, name="chat_stream_api"),
    path("new/", views.new_chat, name="new_chat"),
    # [신규] 삭제 API
    path("api/delete/", views.delete_message_api, name="delete_message_api"),
]
