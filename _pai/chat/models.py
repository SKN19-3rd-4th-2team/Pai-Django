# chat/models.py

from django.db import models
from django.contrib.auth.models import User


class ChatHistory(models.Model):
    history_id = models.AutoField(primary_key=True)

    # [수정] 비회원은 user가 없으므로 null=True 허용
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="histories",
        null=True,  # DB에 NULL 저장 허용
        blank=True,  # 폼 검증 시 빈값 허용
    )

    # [추가] 비회원 식별용 세션 ID
    session_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    order_num = models.IntegerField(db_column="order", default=0)
    description = models.CharField(max_length=255, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_history"

    def __str__(self):
        # 유저가 있으면 유저명, 없으면(비회원) 세션ID 표시
        identifier = (
            self.user.username if self.user else f"Guest-{str(self.session_id)[:8]}"
        )
        return f"{identifier} - {self.description}"


class Chat(models.Model):
    MESSAGE_TYPES = (("HUMAN", "Human"), ("AI", "AI"), ("TOOLS", "Tools"))
    chat_id = models.AutoField(primary_key=True)
    history = models.ForeignKey(
        ChatHistory,
        on_delete=models.CASCADE,
        db_column="history_id",
        related_name="chats",
    )
    type = models.CharField(max_length=10, choices=MESSAGE_TYPES)
    order_num = models.IntegerField(db_column="order")
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat"
        ordering = ["order_num"]
