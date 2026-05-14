import os
import sys
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

SYSTEM_PROMPT = """당신은 20년 경력의 IT·AI 강사이자 교육 스타트업 대표입니다.

강의 철학:
- 1시간이든 6개월이든, 투자한 시간만큼 수강생에게 실질적 가치(취업, 업무 능력 향상)를 제공
- 이론보다 실습 중심, 현업 적용 가능성 최우선
- 교육 대상자의 수준과 목적에 맞는 맞춤형 커리큘럼 설계

역할:
기업 AX(AI Transformation) 교육 커리큘럼 설계 전문 챗봇

대화 방식:
1. 사용자가 커리큘럼 요청 시, 아직 파악되지 않은 정보를 자연스럽게 질문하여 수집합니다.
   필요 정보: 회사명/부서, 교육 대상자(직급·직무·AI 경험 수준), 주요 주제/기능, 교육 시간/기간, 목표(취업·업무효율·DX 추진 등)
2. 정보가 충분히 모이면 아래 형식으로 커리큘럼을 생성합니다.
3. 수정 요청 시 해당 부분만 정밀하게 조정합니다.

커리큘럼 출력 형식:
---
## [회사명] AX 교육 커리큘럼

### 교육 개요
- 교육 대상: ...
- 교육 목표: ...
- 총 교육 시간: ...
- 난이도: ...

### 커리큘럼 구성
#### Day 1 (또는 모듈 1): [제목]
- 주제: ...
- 핵심 내용: ...
- 실습: ...
- 소요 시간: ...

(각 Day/모듈 반복)

### 교육 후 기대 효과
- ...

### 추천 사전 학습
- ...
---

주의:
- 교육 대상자 수준에 맞는 용어와 예시 사용
- 실습 비중은 전체의 40% 이상 권장
- 현업 적용 사례를 각 모듈에 포함
- 비전공자 대상이면 전문 용어 최소화, 쉬운 비유 활용
"""

GREETING = """
╔══════════════════════════════════════════════════════╗
║       AX 교육 커리큘럼 설계 챗봇                     ║
║       기업 맞춤형 AI 전환 교육 커리큘럼 설계         ║
╚══════════════════════════════════════════════════════╝

안녕하세요! AX(AI 전환) 교육 커리큘럼 설계 전문 챗봇입니다.

맞춤형 커리큘럼을 설계하기 위해 몇 가지 여쭤볼게요.
어떤 교육을 원하시나요?

예시: "마케팅팀 직원 20명 대상으로 AI 활용 업무 자동화 교육, 하루 8시간"

명령어: 'new' = 새 대화 시작 | 'quit' 또는 'exit' = 종료
"""


def get_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if key:
        return key
    print("OPENAI_API_KEY가 설정되지 않았습니다.")
    key = input("OpenAI API Key를 입력하세요: ").strip()
    if not key:
        print("API Key가 없으면 실행할 수 없습니다.")
        sys.exit(1)
    return key


def stream_response(client: OpenAI, messages: list) -> str:
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
    print("\n[챗봇] ", end="", flush=True)

    full_response = ""
    stream = client.chat.completions.create(
        model="gpt-4o",
        messages=api_messages,
        stream=True,
        temperature=0.7,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        print(delta, end="", flush=True)
        full_response += delta

    print("\n")
    return full_response


def main():
    api_key = get_api_key()
    client = OpenAI(api_key=api_key)
    messages: list = []

    print(GREETING)

    while True:
        try:
            user_input = input("[나] ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n종료합니다.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("종료합니다.")
            break

        if user_input.lower() == "new":
            messages = []
            print("\n새 대화를 시작합니다.\n")
            print(GREETING)
            continue

        messages.append({"role": "user", "content": user_input})

        try:
            response = stream_response(client, messages)
            messages.append({"role": "assistant", "content": response})
        except Exception as e:
            print(f"\n오류 발생: {e}\n")


if __name__ == "__main__":
    main()
