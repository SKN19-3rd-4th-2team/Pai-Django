from django.db import models
from django.contrib.auth.models import User

# User 모델 확장
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    nickname = models.CharField(max_length=50, blank=True, null=True)
    
    def __str__(self):
        return f"{self.user.username}의 프로필"
