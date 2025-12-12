from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, logout, login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash

from .forms import SignupForm, LoginForm, ProfileUpdateForm

# from django.contrib.auth import logout as auth_logout

from django.http import HttpResponse

from .forms import SignupForm, LoginForm

# 수정 부분: signup(), login()


# 회원가입
def signup(request):
    if request.method == "POST":
        form = SignupForm(request.POST)

        if form.is_valid():
            user = form.save()  # User 모델에 저장됨 (비밀번호 자동 암호화. sha256)
            nickname = form.cleaned_data.get("nickname")

            return render(
                request, "account/signup_success.html", {"username": nickname}
            )  # 회원가입 성공 시 success 화면으로 이동

    else:
        form = SignupForm()

    return render(request, "account/signup.html", {"form": form})


# 로그인
def login(request):
    if request.method == "POST":
        form = LoginForm(
            request, data=request.POST
        )  # 비밀번호 일치 여부 등을 여기서 모두 django가 확인

        if form.is_valid():  # 유효성 검증 통과 시
            user = form.get_user()
            auth_login(request, user)  # 로그인 처리
            return redirect("chat:chat_interface")  # chat 페이지로 이동. 수정 부분

    else:
        form = LoginForm()

    return render(request, "account/login.html", {"form": form})


# 로그아웃 (버튼 추가 후)
# def logout(request):
#     auth_logout(request)
#     return redirect("")


def chat(request):
    return render(request, "account/chat.html")


def withdraw(request):
    return render(request, "account/withdraw.html")


@login_required
def myinfo(request):
    """
    마이페이지:
    - 현재 로그인한 사용자 정보 표시
    - 별명(닉네임) 변경
    - 비밀번호 변경
    """
    user = request.user
    success_message = ""

    # 기본 폼 생성 (GET일 때 사용)
    profile_form = ProfileUpdateForm(user=user)
    password_form = PasswordChangeForm(user)

    if request.method == "POST":
        if "update_info" in request.POST:
            # 통합 정보 수정 처리
            profile_form = ProfileUpdateForm(request.POST, user=user)
            password_form = PasswordChangeForm(user, request.POST)
            
            profile_changed = False
            password_changed = False
            
            # 별명 변경 처리 (별명이 입력된 경우에만)
            if profile_form.is_valid():
                new_nickname = profile_form.cleaned_data.get('nickname', '').strip()
                if new_nickname and new_nickname != user.first_name:
                    profile_form.save()
                    profile_changed = True
            
            # 비밀번호 변경 처리 (새 비밀번호가 입력된 경우에만)
            new_password1 = request.POST.get('new_password1', '').strip()
            if new_password1:  # 새 비밀번호가 입력된 경우에만 검증
                if password_form.is_valid():
                    changed_user = password_form.save()
                    # 비밀번호를 바꿔도 로그인 풀리지 않게 세션 유지
                    update_session_auth_hash(request, changed_user)
                    password_changed = True
            
            # 성공 메시지 설정
            if profile_changed and password_changed:
                success_message = "별명과 비밀번호가 성공적으로 변경되었습니다."
            elif profile_changed:
                success_message = "별명이 성공적으로 변경되었습니다."
            elif password_changed:
                success_message = "비밀번호가 성공적으로 변경되었습니다."
            elif not new_password1 and not profile_form.cleaned_data.get('nickname', '').strip():
                success_message = "변경할 정보를 입력해주세요."

    context = {
        "user_obj": user,
        "profile_form": profile_form,
        "password_form": password_form,
        "success_message": success_message,
    }
    return render(request, "account/myinfo.html", context)



def logout_view(request):
    """
    로그아웃 처리:
    1. 현재 사용자의 세션 데이터를 삭제합니다 (DB의 django_session 테이블에서 제거).
    2. 브라우저의 sessionid 쿠키도 무효화됩니다.
    3. 메인 페이지로 이동합니다.
    """
    logout(request)
    return redirect("main:index")  # 메인 페이지로 이동


def withdraw_final(request):
    pass