from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login

from django.http import HttpResponse


# Create your views here.
def login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        if username == "test" and password == "1234":
            return redirect("account:chat")  # 성공 시 이동

        else:  # 실패 시
            return render(
                request, "account/login.html", {"error": "ID 또는 PW가 틀렸습니다."}
            )

    return render(request, "account/login.html")
    # 실제 인증 받을 때
    # user = authenticate(request, username=username, password=password)
    # if user:
    #     login(request, user)
    #     return redirect('chat')  # 로그인 후 이동할 페이지 (사용자 고유 아이디... 별명? 넘겨서?)

    # else:
    #     return render(request, "accounts/login.html", {"error": "ID 또는 PW가 틀렸습니다."})


def signup(request):
    if request.method == "POST":
        userid = request.POST.get("userid")
        password = request.POST.get("password")
        username = request.POST.get("username")

        return render(request, "account/signup_success.html", {"username": username})

    return render(request, "account/signup.html")


def chat(request):
    return render(request, "account/chat.html")


def withdraw(request):
    return render(request, "account/withdraw.html")


def myinfo(request):
    context = {
        "user_id": "FantAstIc5",
        "password": "@@FantAstIc5",
        "nickname": "판타스틱오",
        "message": "변경이 완료되었습니다.",
    }
    return render(request, "account/myinfo.html", context)
