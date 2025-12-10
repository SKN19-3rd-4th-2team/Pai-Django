from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User

# 수정 부분
# 회원가입 Form
class SignupForm(UserCreationForm):
    username = forms.CharField(
        label='아이디',
        widget=forms.TextInput(attrs={'class': 'input-box'})
    )
    password1 = forms.CharField(
        label='비밀번호',
        widget=forms.PasswordInput(attrs={'class': 'input-box'})
    )
    nickname = forms.CharField(
        label='별명',
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'class': 'input-box', 'placeholder': '챗봇에게 불리고 싶은 이름'})
    )
    password2 = forms.CharField(
        label='비밀번호 확인',
        widget=forms.PasswordInput(attrs={'class': 'input-box'})
    )

    class Meta:
        model = User
        fields = ['username', 'password1', 'password2', 'nickname']
        # django에서 제공하는 User 모델에서 비밀번호는 반드시 비밀번호 확인 필요.
        
    def save(self, commit=True):
        # nickname(별명)을 User.first_name에 저장
        
        user = super().save(commit=False)
        nickname = self.cleaned_data.get('nickname', '').strip()
        if nickname:
            user.first_name = nickname
        if commit:
            user.save()
        return user


# 로그인 Form
class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label='아이디',
        widget=forms.TextInput(attrs={'class': 'input-box'})
    )
    password = forms.CharField(
        label='비밀번호',
        widget=forms.PasswordInput(attrs={'class': 'input-box'})
    )
