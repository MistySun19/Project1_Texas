"""
Poker Player - Purple Agent for AgentBeats Platform
按照 agentbeats/tutorial 的 debater.py 模式实现
"""

import argparse
import uvicorn
import random
import json
import re
from dotenv import load_dotenv

load_dotenv()

from a2a.types import (
    AgentCapabilities,
    AgentCard,
)

# 始终导入这些类（不管是否使用 ADK）
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import Task, TaskState, Part, TextPart
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError

# 尝试使用 Google ADK
try:
    from google.adk.agents import Agent
    from google.adk.a2a.utils.agent_to_a2a import to_a2a
    USE_ADK = True
except ImportError:
    USE_ADK = False

try:
    import litellm
    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False


POKER_INSTRUCTION = """You are an expert Texas Hold'em poker player.

When you receive a game state, analyze it and decide your action.

Your response MUST be a valid JSON object with this format:
{"action": "fold" | "call" | "raise", "amount": <number if raising>}

Strategy tips:
- With strong hands (pairs, high cards), call or raise
- With weak hands, consider folding if the bet is high
- Position matters - being aggressive from late position is often good
- Consider pot odds when deciding to call

IMPORTANT: Only respond with the JSON action, no other text."""


class SimplePokerAgent:
    """简单的扑克代理，使用 LiteLLM 或随机策略"""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.history = []
    
    def decide(self, game_state_text: str) -> str:
        """做出决策"""
        if HAS_LITELLM:
            try:
                response = litellm.completion(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": POKER_INSTRUCTION},
                        {"role": "user", "content": game_state_text}
                    ],
                    max_tokens=100,
                    temperature=0.7,
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"LiteLLM error: {e}")
        
        # 降级到随机策略
        return self._random_strategy(game_state_text)
    
    def _random_strategy(self, game_state_text: str) -> str:
        """随机策略作为后备"""
        # 尝试解析 to_call
        to_call = 0
        try:
            if "to_call" in game_state_text:
                match = re.search(r"'to_call':\s*(\d+)", game_state_text)
                if match:
                    to_call = int(match.group(1))
        except:
            pass
        
        r = random.random()
        if to_call == 0:
            # 可以 check
            if r < 0.3:
                return '{"action": "call"}'  # check
            elif r < 0.7:
                return '{"action": "raise", "amount": 40}'
            else:
                return '{"action": "call"}'
        else:
            # 需要 call
            if r < 0.2:
                return '{"action": "fold"}'
            elif r < 0.7:
                return '{"action": "call"}'
            else:
                return '{"action": "raise", "amount": ' + str(to_call * 2 + 20) + '}'


class SimpleAgentExecutor(AgentExecutor):
    """简单的代理执行器"""
    
    def __init__(self, poker_agent: SimplePokerAgent):
        self.agent = poker_agent
    
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        request_text = context.get_user_input()
        
        # 创建任务
        msg = context.message
        if msg:
            task = new_task(msg)
            await event_queue.enqueue_event(task)
        else:
            raise ServerError(error={"message": "Missing message."})
        
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        
        try:
            # 获取决策
            response = self.agent.decide(request_text)
            
            await updater.add_artifact(
                parts=[Part(root=TextPart(text=response))],
                name="Decision",
            )
            await updater.complete()
        except Exception as e:
            await updater.failed(new_agent_text_message(f"Error: {e}"))
    
    async def cancel(self, request: RequestContext, event_queue: EventQueue) -> Task | None:
        return None


def create_agent_card(name: str, url: str) -> AgentCard:
    """创建 Agent Card"""
    from a2a.types import AgentSkill
    
    skill = AgentSkill(
        id='texas_holdem_player',
        name='Texas Hold\'em Player',
        description='Plays No-Limit Texas Hold\'em poker',
        tags=['poker', 'texas-holdem', 'player'],
        examples=['{"action": "fold"}', '{"action": "call"}', '{"action": "raise", "amount": 100}'],
    )
    
    return AgentCard(
        name=name,
        description='A Texas Hold\'em poker player agent',
        url=url,
        version='1.0.0',
        protocol_version='0.3.0',  # A2A 协议版本
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )


def main():
    import os
    
    parser = argparse.ArgumentParser(description="Run the poker player agent (Purple Agent)")
    parser.add_argument("--host", type=str, default=None, help="Host to bind the server")
    parser.add_argument("--port", type=int, default=None, help="Port to bind the server")
    parser.add_argument("--card-url", type=str, help="External URL to provide in the agent card")
    parser.add_argument("--model", type=str, default="gpt-4o-mini", help="LLM model to use")
    args = parser.parse_args()

    # 优先使用环境变量（AgentBeats Controller 设置的），然后使用命令行参数，最后使用默认值
    host = args.host or os.environ.get("HOST", "127.0.0.1")
    port = int(args.port or os.environ.get("AGENT_PORT", "9019"))
    agent_url = args.card_url or os.environ.get("AGENT_URL")
    
    # 修复 Controller 可能生成的双重协议问题 (http://https://...)
    if agent_url and agent_url.startswith("http://https://"):
        agent_url = agent_url.replace("http://https://", "https://")
    elif agent_url and agent_url.startswith("http://http://"):
        agent_url = agent_url.replace("http://http://", "http://")
    
    # 如果没有提供外部 URL，使用本地地址
    if not agent_url:
        agent_url = f"http://{host}:{port}/"

    if USE_ADK:
        # 使用 Google ADK
        root_agent = Agent(
            name="poker_player",
            model="gemini-2.0-flash",
            description="Plays Texas Hold'em poker.",
            instruction=POKER_INSTRUCTION,
        )

        agent_card = create_agent_card("PokerPlayer", agent_url)
        a2a_app = to_a2a(root_agent, agent_card=agent_card)
        
        # 添加 /status 健康检查端点（AgentBeats 平台需要）
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        
        async def status_endpoint(request):
            return JSONResponse({"status": "ok", "agent": "PokerPlayer"})
        
        a2a_app.routes.append(Route("/status", status_endpoint, methods=["GET"]))
        
        print(f"Starting Poker Player at {host}:{port}")
        print(f"Agent Card URL: {agent_url}")
        uvicorn.run(a2a_app, host=host, port=port)
    else:
        # 使用简单实现
        poker_agent = SimplePokerAgent(model=args.model)
        executor = SimpleAgentExecutor(poker_agent)
        agent_card = create_agent_card("PokerPlayer", agent_url)
        
        request_handler = DefaultRequestHandler(
            agent_executor=executor,
            task_store=InMemoryTaskStore(),
        )
        
        server = A2AStarletteApplication(
            agent_card=agent_card,
            http_handler=request_handler,
        )
        
        # 添加 /status 健康检查端点（AgentBeats 平台需要）
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        
        async def status_endpoint(request):
            return JSONResponse({"status": "ok", "agent": "PokerPlayer"})
        
        app = server.build()
        app.routes.append(Route("/status", status_endpoint, methods=["GET"]))
        
        print(f"Starting Poker Player at {host}:{port}")
        print(f"Agent Card URL: {agent_url}")
        uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
