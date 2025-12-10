# app/main.py
from langchain_core.messages import HumanMessage, SystemMessage
import os
from typing import Literal
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.memory import MemorySaver

# 상대 경로 import 유지
from .total_tools import (
    tool_search_ipc_code_with_description,
    tool_search_ipc_description_from_code,
    tool_search_patent_with_description,
    tool_search_detail_patent_by_id,
)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY 가 설정되지 않았습니다.")

# 1. 모델 및 도구 설정 (이건 전역으로 둬도 무방, 재사용을 위해)
tools = [
    tool_search_patent_with_description,
    tool_search_ipc_code_with_description,
    tool_search_ipc_description_from_code,
    tool_search_detail_patent_by_id,
]

llm = ChatOpenAI(
    model="gpt-5.1",  # 혹은 gpt-4-turbo, gpt-3.5-turbo 등
    temperature=0,
    api_key=OPENAI_API_KEY,
)

llm_with_tools = llm.bind_tools(tools)


# 2. 노드 함수 정의
def call_model(state: MessagesState):
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def should_continue(state: MessagesState) -> Literal["tools", END]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


# 3. [핵심] 그래프 생성 함수 (팩토리 패턴)
def get_graph_agent():
    """
    호출 시점에 워크플로우를 컴파일하여 agent_executor를 반환합니다.
    """
    workflow = StateGraph(MessagesState)

    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(tools))

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges("agent", should_continue, ["tools", END])
    workflow.add_edge("tools", "agent")

    # 메모리 체크포인터 (LangGraph 내부 상태 관리용)
    memory = MemorySaver()

    return workflow.compile(checkpointer=memory)


# ==========================================
# 3. 대화 함수 (스트리밍 + 툴 호출 로그)
# ==========================================


def chat_with_memory(user_input: str, thread_id: str = "default-thread") -> None:
    """
    한 턴의 사용자 입력에 대해 ReAct 에이전트를 실행하고,
    에이전트의 '생각 / 도구 호출 / 최종 답변'을 단계별로 콘솔에 출력합니다.
    """
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\n\n=== 사용자({thread_id}) 입력 ===")
    print(user_input)
    print("================================\n")

    # 매 턴마다 system + user 메시지를 넣어줌
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_input),
    ]

    step_idx = 0

    for event in agent_executor.stream({"messages": messages}, config=config):
        # event 예시: {"agent": {"messages": [...]}} 또는 {"tools": {"messages": [...]}}
        for node_name, value in event.items():
            messages_in_node = value.get("messages", [])
            if not messages_in_node:
                continue

            last_message = messages_in_node[-1]

            # 1) 에이전트 노드 (LLM)
            if node_name == "agent":
                step_idx += 1
                tool_calls = getattr(last_message, "tool_calls", None) or []

                # (A) 이번 step에서 도구를 호출하려는 경우
                if tool_calls:
                    tool_names = [tc.get("name", "UNKNOWN_TOOL") for tc in tool_calls]
                    print(f"[Step {step_idx}][Agent] 다음 도구 호출 예정: {tool_names}")

                # (B) 최종 자연어 답변 (tool_calls 없이 content만 있는 경우)
                elif last_message.content:
                    print(
                        f"[Step {step_idx}][Agent 최종 답변]\n{last_message.content}\n"
                    )

            # 2) 툴 노드
            elif node_name == "tools":
                # 툴 메시지는 ToolMessage 형태로 들어옴
                tool_name = getattr(last_message, "name", None) or getattr(
                    last_message, "tool", "unknown_tool"
                )
                content_str = str(last_message.content)
                preview = content_str[:120].replace("\n", " ")

                print(
                    f"[Tool 결과 수신] tool='{tool_name}' "
                    f"(내용 길이: {len(content_str)}자, 미리보기: {preview}...)"
                )
