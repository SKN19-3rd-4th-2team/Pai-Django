from django.db import models

# chat/models.py
from django.db import models
from django.contrib.auth.models import User  # 1. 사용자 테이블 (Django 기본 제공)


class ChatSession(models.Model):
    """
    2. 채팅 묶음 (Session)
    사용자가 '새 채팅'을 누를 때마다 하나씩 생성되는 대화방 개념
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="chat_sessions"
    )
    title = models.CharField(max_length=200, default="새로운 대화")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.title}"


class ChatMessage(models.Model):
    """
    3. 채팅 내역 (Message)
    개별 말풍선 하나하나를 저장
    """

    class MessageType(models.TextChoices):
        HUMAN = "human", "사용자"
        AI = "ai", "AI"
        TOOL = "tool", "시스템/도구"

    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="messages"
    )

    # 메시지 타입 (Human, AI, Tool 등)
    msg_type = models.CharField(max_length=10, choices=MessageType.choices)

    # 메시지 내용
    content = models.TextField()

    # 순서 (해당 세션 내에서 몇 번째 메시지인지)
    order = models.IntegerField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]  # 불러올 때 항상 순서대로

    def __str__(self):
        return f"[{self.session.id}] {self.msg_type}: {self.content[:20]}"
