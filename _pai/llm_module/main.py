# llm_module/main.py

import os
from typing import Literal
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, START, END, MessagesState
from langgraph.checkpoint.memory import MemorySaver

from .SYSTEM_PROMPT import SYSTEM_PROMPT

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

# 1. 모델 및 도구 설정
tools = [
    tool_search_patent_with_description,
    tool_search_ipc_code_with_description,
    tool_search_ipc_description_from_code,
    tool_search_detail_patent_by_id,
]

llm = ChatOpenAI(
    model="gpt-5.1",
    temperature=0,
    api_key=OPENAI_API_KEY,
)

llm_with_tools = llm.bind_tools(tools)


# 2. 노드 함수 정의
def call_model(state: MessagesState):
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}


def should_continue(state: MessagesState) -> Literal["tools"] | str:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return END


# 3. 그래프 생성 함수 (팩토리 패턴)
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

    # 메모리 체크포인터
    memory = MemorySaver()

    return workflow.compile(checkpointer=memory)


# ========================================================
# agent_executor 전역 변수 생성
# ========================================================
agent_executor = get_graph_agent()


# ==========================================
# 4. (테스트용) 대화 함수
# ==========================================
def chat_with_memory(user_input: str, thread_id: str = "default-thread") -> None:
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\n\n=== 사용자({thread_id}) 입력 ===")
    print(user_input)
    print("================================\n")

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_input),
    ]

    step_idx = 0

    # 전역 변수 agent_executor 사용
    for event in agent_executor.stream({"messages": messages}, config=config):
        for node_name, value in event.items():
            messages_in_node = value.get("messages", [])
            if not messages_in_node:
                continue

            last_message = messages_in_node[-1]

            if node_name == "agent":
                step_idx += 1
                tool_calls = getattr(last_message, "tool_calls", None) or []

                if tool_calls:
                    tool_names = [tc.get("name", "UNKNOWN_TOOL") for tc in tool_calls]
                    print(f"[Step {step_idx}][Agent] 다음 도구 호출 예정: {tool_names}")

                elif last_message.content:
                    print(
                        f"[Step {step_idx}][Agent 최종 답변]\n{last_message.content}\n"
                    )

            elif node_name == "tools":
                tool_name = getattr(last_message, "name", None) or getattr(
                    last_message, "tool", "unknown_tool"
                )
                content_str = str(last_message.content)
                preview = content_str[:120].replace("\n", " ")

                print(f"[Tool 결과 수신] tool='{tool_name}' (길이: {len(content_str)})")