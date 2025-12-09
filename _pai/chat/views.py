# chat/views.py

import json
import uuid
from django.shortcuts import render, redirect
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

# 모듈 가져오기
from llm_module.main import get_graph_agent
from llm_module.SYSTEM_PROMPT import SYSTEM_PROMPT
from llm_module.memory_utils import convert_session_to_langchain_messages

agent_executor = get_graph_agent()


# =========================================================
# 헬퍼 함수: 다음 order 번호 구하기
# =========================================================
def get_next_order(history):
    if not history:
        return 1
    # 현재 있는 메시지 중 가장 큰 order 값 + 1
    max_order = max(msg.get("order", 0) for msg in history)
    return max_order + 1


# =========================================================
# AI 메시지 저장 (DB 구조에 맞춰 id, order 추가)
# =========================================================
def save_ai_message_to_session(request, content):
    if "chat_history" not in request.session:
        request.session["chat_history"] = []

    history = request.session["chat_history"]

    new_msg = {
        "id": str(uuid.uuid4()),  # PK 역할
        "role": "assistant",
        "content": content,
        "order": get_next_order(history),  # 순서 보장
    }

    history.append(new_msg)
    request.session["chat_history"] = history
    request.session.save()


# =========================================================
# 뷰: 채팅 화면
# =========================================================
def chat_interface(request):
    if "chat_history" not in request.session:
        request.session["chat_history"] = []

    # 1. 가져오기
    raw_history = request.session["chat_history"]

    # 2. 정렬하기 (order 기준 오름차순)
    sorted_history = sorted(raw_history, key=lambda x: x.get("order", 0))

    context = {"chat_history": sorted_history}
    return render(request, "chat/chat_component.html", context)


# =========================================================
# API: 채팅 스트리밍
# =========================================================
@csrf_exempt
def chat_stream_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_input = data.get("message", "")
        except:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if not user_input:
            return JsonResponse({"error": "Empty message"}, status=400)

        # 세션 초기화
        if "chat_history" not in request.session:
            request.session["chat_history"] = []
        if "thread_id" not in request.session:
            request.session["thread_id"] = str(uuid.uuid4())

        # 1. [사용자 메시지 저장] (구조 업그레이드)
        history = request.session["chat_history"]
        user_msg = {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": user_input,
            "order": get_next_order(history),
        }
        history.append(user_msg)
        request.session["chat_history"] = history
        request.session.save()

        # 2. LangChain 메시지 변환 (Tool 메시지는 내부적으로 처리됨)
        # order 순으로 정렬해서 넣어줘야 정확한 맥락 유지
        sorted_history = sorted(history, key=lambda x: x.get("order", 0))
        langchain_messages = convert_session_to_langchain_messages(
            sorted_history, system_prompt=SYSTEM_PROMPT
        )

        # 3. 스트리밍
        thread_id = request.session["thread_id"]
        config = {"configurable": {"thread_id": thread_id}}

        def event_stream():
            full_ai_response = ""
            seen_tool_ids = set()

            try:
                for msg, metadata in agent_executor.stream(
                    {"messages": langchain_messages},
                    config=config,
                    stream_mode="messages",
                ):
                    curr_node = metadata.get("langgraph_node", "")

                    if curr_node == "agent" and msg.content:
                        if not msg.tool_calls:
                            full_ai_response += msg.content
                            yield json.dumps(
                                {"type": "token", "content": msg.content}
                            ) + "\n"

                    if curr_node == "agent" and msg.tool_calls:
                        for tool_call in msg.tool_calls:
                            t_id = tool_call.get("id")
                            t_name = tool_call.get("name")
                            if t_id not in seen_tool_ids:
                                seen_tool_ids.add(t_id)
                                yield json.dumps(
                                    {"type": "tool_call", "tool_name": t_name}
                                ) + "\n"

                    if curr_node == "tools":
                        content_str = str(msg.content)
                        yield json.dumps(
                            {"type": "tool_result", "length": len(content_str)}
                        ) + "\n"

                        # [중요] Tool 메시지도 세션에 저장해야 맥락이 유지됨 (화면엔 안 그려도 데이터는 필요)
                        # 여기서는 간단히 구현하기 위해 생략하거나, 필요하면 저장 로직 추가.
                        # (단, 사용자는 'tool 메시지를 안 보이게' 해달라고 했으므로 뷰에서 필터링하면 됨)

                if full_ai_response:
                    save_ai_message_to_session(request, full_ai_response)

            except Exception as e:
                yield json.dumps({"type": "error", "message": str(e)}) + "\n"

        return StreamingHttpResponse(
            event_stream(), content_type="application/x-ndjson"
        )

    return JsonResponse({"error": "Method not allowed"}, status=405)


# =========================================================
# [신규] API: 메시지 삭제 (Turn 단위 삭제)
# =========================================================
@csrf_exempt
def delete_message_api(request):
    """
    특정 ID의 사용자 메시지와, 그에 따른 AI 응답(다음 사용자 입력 전까지)을 모두 삭제
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            target_id = data.get("message_id")
        except:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        if not target_id or "chat_history" not in request.session:
            return JsonResponse({"status": "failed", "message": "No history or ID"})

        history = request.session["chat_history"]

        # 1. order 순으로 정렬 (삭제 범위를 정확히 찾기 위해)
        history.sort(key=lambda x: x.get("order", 0))

        start_index = -1

        # 2. 삭제할 사용자 메시지(target_id) 찾기
        for i, msg in enumerate(history):
            if msg["id"] == target_id:
                start_index = i
                break

        if start_index != -1:
            # 해당 메시지가 'user'인 경우에만 턴 삭제 로직 발동
            if history[start_index]["role"] == "user":
                end_index = start_index + 1

                # 3. 다음 'user' 메시지가 나올 때까지(또는 끝까지) 인덱스 전진
                while end_index < len(history):
                    if history[end_index]["role"] == "user":
                        break
                    end_index += 1

                # 4. 범위 삭제 (start_index 부터 end_index 직전까지)
                del history[start_index:end_index]

                # 5. 저장
                request.session["chat_history"] = history
                request.session.save()
                return JsonResponse({"status": "success"})

            else:
                # 사용자가 AI 메시지를 직접 지우려 할 때 (정책상 막거나, 단건 삭제만 허용)
                # 여기서는 '사용자 입력에 대한 묶음 삭제'가 목표이므로 에러 처리하거나 단건 삭제
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Only user messages can trigger turn deletion",
                    }
                )

        return JsonResponse({"status": "failed", "message": "Message not found"})

    return JsonResponse({"error": "Method not allowed"}, status=405)


def new_chat(request):
    if "chat_history" in request.session:
        del request.session["chat_history"]
    if "thread_id" in request.session:
        del request.session["thread_id"]
    return redirect("chat:chat_interface")
