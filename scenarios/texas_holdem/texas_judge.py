"""
Texas Hold'em Judge - Green Agent for AgentBeats Platform
按照 agentbeats/tutorial 的 debate_judge.py 模式实现
"""

import argparse
import contextlib
import uvicorn
import asyncio
import logging
import random
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Dict, List, Optional, Any

load_dotenv()

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    TaskState,
    Part,
    TextPart,
    AgentCard,
    AgentCapabilities,
    AgentSkill,
)
from a2a.utils import new_agent_text_message

# 从 agentbeats tutorial 导入基础类
import sys
sys.path.insert(0, "agentbeats-tutorial/src")
from agentbeats.green_executor import GreenAgent, GreenExecutor
from agentbeats.models import EvalRequest, EvalResult
from agentbeats.tool_provider import ToolProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("texas_judge")


# ==================== 牌局逻辑 ====================

SUITS = ['h', 'd', 'c', 's']  # hearts, diamonds, clubs, spades
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']

def new_deck() -> List[str]:
    """创建一副新牌"""
    return [f"{rank}{suit}" for suit in SUITS for rank in RANKS]

def shuffle_deck(deck: List[str], seed: int) -> List[str]:
    """根据种子洗牌"""
    rng = random.Random(seed)
    shuffled = deck.copy()
    rng.shuffle(shuffled)
    return shuffled


class HandResult(BaseModel):
    """单手牌结果"""
    hand_index: int
    winner: Optional[str]  # player_0 or player_1
    pot: int
    final_stacks: Dict[str, int]
    actions: List[Dict[str, Any]]


class PokerEvalResult(BaseModel):
    """扑克评估结果"""
    total_hands: int
    player_0_wins: int
    player_1_wins: int
    player_0_net: int  # net winnings
    player_1_net: int
    winner: str  # Overall winner based on net profit


# ==================== Green Agent ====================

class TexasJudge(GreenAgent):
    """
    Texas Hold'em Green Agent
    负责协调扑克游戏，向玩家发送状态，收集决策，评判结果
    """

    def __init__(self):
        self._required_roles = ["player_0", "player_1"]
        self._required_config_keys = ["num_hands", "starting_stack", "small_blind", "big_blind"]
        self._tool_provider = ToolProvider()

    def validate_request(self, request: EvalRequest) -> tuple[bool, str]:
        """验证评估请求"""
        missing_roles = set(self._required_roles) - set(request.participants.keys())
        if missing_roles:
            return False, f"Missing roles: {missing_roles}"

        missing_config_keys = set(self._required_config_keys) - set(request.config.keys())
        if missing_config_keys:
            return False, f"Missing config keys: {missing_config_keys}"

        try:
            int(request.config["num_hands"])
            int(request.config["starting_stack"])
            int(request.config["small_blind"])
            int(request.config["big_blind"])
        except Exception as e:
            return False, f"Invalid config values: {e}"

        return True, "ok"

    async def run_eval(self, req: EvalRequest, updater: TaskUpdater) -> None:
        """运行扑克评估"""
        logger.info(f"Starting Texas Hold'em evaluation: {req}")

        try:
            num_hands = int(req.config["num_hands"])
            starting_stack = int(req.config["starting_stack"])
            small_blind = int(req.config["small_blind"])
            big_blind = int(req.config["big_blind"])

            await updater.update_status(
                TaskState.working,
                new_agent_text_message(f"Starting {num_hands} hands of Texas Hold'em")
            )

            # 运行所有手牌
            hand_results = await self.play_match(
                participants=req.participants,
                num_hands=num_hands,
                starting_stack=starting_stack,
                small_blind=small_blind,
                big_blind=big_blind,
                updater=updater,
            )

            # 计算最终结果
            eval_result = self.calculate_results(hand_results, starting_stack)

            logger.info(f"Evaluation complete: {eval_result.model_dump_json()}")

            # 创建最终结果
            result = EvalResult(
                winner=eval_result.winner,
                detail=eval_result.model_dump()
            )

            # 构建详细的 metrics 输出
            metrics_text = f"""
📊 **Texas Hold'em Match Results**
=====================================

🏆 **Winner: {eval_result.winner.upper()}**

📈 **Statistics:**
- Total Hands Played: {eval_result.total_hands}
- Player 0 Hands Won: {eval_result.player_0_wins}
- Player 1 Hands Won: {eval_result.player_1_wins}

💰 **Final Profit/Loss:**
- Player 0 Net: {'+' if eval_result.player_0_net >= 0 else ''}{eval_result.player_0_net} chips
- Player 1 Net: {'+' if eval_result.player_1_net >= 0 else ''}{eval_result.player_1_net} chips

📋 **Config:**
- Starting Stack: {starting_stack}
- Small Blind: {small_blind}
- Big Blind: {big_blind}
"""

            await updater.add_artifact(
                parts=[
                    Part(root=TextPart(text=metrics_text)),
                    Part(root=TextPart(text=f"\n📦 Raw JSON:\n{result.model_dump_json(indent=2)}")),
                ],
                name="Match Results",
            )

        finally:
            self._tool_provider.reset()

    async def play_match(
        self,
        participants: Dict[str, str],
        num_hands: int,
        starting_stack: int,
        small_blind: int,
        big_blind: int,
        updater: TaskUpdater,
    ) -> List[HandResult]:
        """打完所有手牌"""
        results = []
        stacks = {"player_0": starting_stack, "player_1": starting_stack}
        button = 0  # player_0 starts on button

        for hand_idx in range(num_hands):
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(f"Playing hand {hand_idx + 1}/{num_hands}")
            )

            result = await self.play_single_hand(
                participants=participants,
                hand_index=hand_idx,
                stacks=stacks.copy(),
                button=button,
                small_blind=small_blind,
                big_blind=big_blind,
            )

            results.append(result)

            # 更新筹码
            stacks = result.final_stacks.copy()

            # 轮换按钮位置
            button = 1 - button

            logger.info(f"Hand {hand_idx + 1} complete: winner={result.winner}, pot={result.pot}")

        return results

    async def play_single_hand(
        self,
        participants: Dict[str, str],
        hand_index: int,
        stacks: Dict[str, int],
        button: int,
        small_blind: int,
        big_blind: int,
    ) -> HandResult:
        """打一手牌（简化版本）"""
        actions = []
        deck = shuffle_deck(new_deck(), seed=hand_index * 1000)

        # 发牌
        hole_cards = {
            "player_0": [deck[0], deck[2]],
            "player_1": [deck[1], deck[3]],
        }

        # 盲注
        sb_player = f"player_{button}"
        bb_player = f"player_{1 - button}"

        pot = 0
        bets = {"player_0": 0, "player_1": 0}

        # 小盲
        sb_amount = min(small_blind, stacks[sb_player])
        stacks[sb_player] -= sb_amount
        bets[sb_player] = sb_amount
        pot += sb_amount

        # 大盲
        bb_amount = min(big_blind, stacks[bb_player])
        stacks[bb_player] -= bb_amount
        bets[bb_player] = bb_amount
        pot += bb_amount

        actions.append({"player": sb_player, "action": "post_sb", "amount": sb_amount})
        actions.append({"player": bb_player, "action": "post_bb", "amount": bb_amount})

        # 翻前行动（从小盲后的玩家开始）
        current_bet = big_blind
        current_player = sb_player  # 翻前小盲先行动
        folded = None

        # 简化的下注轮
        for round_num in range(4):  # 最多4轮行动
            if folded:
                break

            to_call = current_bet - bets[current_player]

            # 构建请求消息
            game_state = {
                "hand_index": hand_index,
                "your_role": current_player,
                "hole_cards": hole_cards[current_player],
                "pot": pot,
                "your_stack": stacks[current_player],
                "opponent_stack": stacks["player_1" if current_player == "player_0" else "player_0"],
                "to_call": to_call,
                "current_bet": current_bet,
                "actions_this_hand": actions,
                "legal_actions": self._get_legal_actions(stacks[current_player], to_call, current_bet),
            }

            prompt = f"""You are playing Texas Hold'em poker.
Game State:
{game_state}

Please respond with your action in JSON format:
{{"action": "fold|call|raise", "amount": <number if raising>}}
"""

            try:
                response = await self._tool_provider.talk_to_agent(
                    prompt,
                    str(participants[current_player]),
                    new_conversation=True
                )
                logger.info(f"{current_player} response: {response}")

                # 解析响应
                action_data = self._parse_action(response, stacks[current_player], to_call, current_bet)

                if action_data["action"] == "fold":
                    folded = current_player
                    actions.append({"player": current_player, "action": "fold"})
                elif action_data["action"] == "call":
                    call_amount = min(to_call, stacks[current_player])
                    stacks[current_player] -= call_amount
                    bets[current_player] += call_amount
                    pot += call_amount
                    actions.append({"player": current_player, "action": "call", "amount": call_amount})
                elif action_data["action"] == "raise":
                    raise_amount = action_data.get("amount", current_bet * 2)
                    total_bet = min(raise_amount, stacks[current_player] + bets[current_player])
                    add_amount = total_bet - bets[current_player]
                    stacks[current_player] -= add_amount
                    bets[current_player] = total_bet
                    pot += add_amount
                    current_bet = total_bet
                    actions.append({"player": current_player, "action": "raise", "amount": total_bet})

                # 检查是否下注相等（下注轮结束）
                if bets["player_0"] == bets["player_1"]:
                    break

            except Exception as e:
                logger.error(f"Error getting action from {current_player}: {e}")
                # 默认弃牌
                folded = current_player
                actions.append({"player": current_player, "action": "fold", "error": str(e)})
                break

            # 切换玩家
            current_player = "player_1" if current_player == "player_0" else "player_0"

        # 确定赢家
        if folded:
            winner = "player_1" if folded == "player_0" else "player_0"
        else:
            # 简化: 随机决定（真实实现需要比较牌力）
            winner = "player_0" if random.random() > 0.5 else "player_1"

        # 分配底池
        stacks[winner] += pot

        return HandResult(
            hand_index=hand_index,
            winner=winner,
            pot=pot,
            final_stacks=stacks,
            actions=actions,
        )

    def _get_legal_actions(self, stack: int, to_call: int, current_bet: int) -> List[str]:
        """获取合法行动"""
        actions = ["fold"]
        if to_call == 0:
            actions.append("check")
        if to_call > 0 and stack >= to_call:
            actions.append("call")
        if stack > to_call:
            actions.append("raise")
        return actions

    def _parse_action(self, response: str, stack: int, to_call: int, current_bet: int) -> Dict[str, Any]:
        """解析玩家响应"""
        import json
        import re

        # 尝试解析 JSON
        try:
            # 查找 JSON
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                data = json.loads(json_match.group())
                action = data.get("action", "fold").lower()
                if action in ["fold", "call", "check", "raise"]:
                    return {"action": action, "amount": data.get("amount", current_bet * 2)}
        except:
            pass

        # 关键词匹配
        response_lower = response.lower()
        if "fold" in response_lower:
            return {"action": "fold"}
        elif "call" in response_lower:
            return {"action": "call"}
        elif "check" in response_lower:
            return {"action": "call" if to_call > 0 else "check"}
        elif "raise" in response_lower or "bet" in response_lower:
            return {"action": "raise", "amount": current_bet * 2}

        # 默认弃牌
        return {"action": "fold"}

    def calculate_results(self, hand_results: List[HandResult], starting_stack: int) -> PokerEvalResult:
        """计算最终评估结果"""
        player_0_wins = sum(1 for r in hand_results if r.winner == "player_0")
        player_1_wins = sum(1 for r in hand_results if r.winner == "player_1")

        # 从最后一手牌获取最终筹码
        final_stacks = hand_results[-1].final_stacks if hand_results else {"player_0": starting_stack, "player_1": starting_stack}

        player_0_net = final_stacks.get("player_0", starting_stack) - starting_stack
        player_1_net = final_stacks.get("player_1", starting_stack) - starting_stack

        if player_0_net > player_1_net:
            winner = "player_0"
        elif player_1_net > player_0_net:
            winner = "player_1"
        else:
            winner = "tie"

        return PokerEvalResult(
            total_hands=len(hand_results),
            player_0_wins=player_0_wins,
            player_1_wins=player_1_wins,
            player_0_net=player_0_net,
            player_1_net=player_1_net,
            winner=winner,
        )


# ==================== Agent Card ====================

def texas_judge_agent_card(agent_name: str, card_url: str) -> AgentCard:
    """创建 Agent Card"""
    skill = AgentSkill(
        id='evaluate_texas_holdem',
        name='Evaluates Texas Hold\'em poker matches',
        description='Orchestrate and judge Texas Hold\'em poker matches between two AI agents.',
        tags=['poker', 'texas-holdem', 'evaluation'],
        examples=["""
{
  "participants": {
    "player_0": "https://player0.example.com:443",
    "player_1": "https://player1.example.com:8443"
  },
  "config": {
    "num_hands": 10,
    "starting_stack": 1000,
    "small_blind": 10,
    "big_blind": 20
  }
}
"""]
    )

    return AgentCard(
        name=agent_name,
        description='Texas Hold\'em Poker Judge - Evaluates poker matches between two AI agents',
        url=card_url,
        version='1.0.0',
        protocol_version='0.3.0',  # A2A 协议版本
        default_input_modes=['text'],
        default_output_modes=['text'],
        capabilities=AgentCapabilities(streaming=True),
        skills=[skill],
    )


# ==================== Main ====================

async def main():
    import os
    
    parser = argparse.ArgumentParser(description="Run the Texas Hold'em Judge (Green Agent)")
    parser.add_argument("--host", type=str, default=None, help="Host to bind the server")
    parser.add_argument("--port", type=int, default=None, help="Port to bind the server")
    parser.add_argument("--card-url", type=str, help="External URL to provide in the agent card")
    parser.add_argument("--cloudflare-quick-tunnel", action="store_true",
                        help="Use a Cloudflare quick tunnel. Requires cloudflared.")
    args = parser.parse_args()

    # 优先使用环境变量（AgentBeats Controller 设置的），然后使用命令行参数，最后使用默认值
    host = args.host or os.environ.get("HOST", "127.0.0.1")
    port = int(args.port or os.environ.get("AGENT_PORT", "9009"))
    agent_url = args.card_url or os.environ.get("AGENT_URL")
    
    # 修复 Controller 可能生成的双重协议问题 (http://https://...)
    if agent_url and agent_url.startswith("http://https://"):
        agent_url = agent_url.replace("http://https://", "https://")
    elif agent_url and agent_url.startswith("http://http://"):
        agent_url = agent_url.replace("http://http://", "http://")

    if args.cloudflare_quick_tunnel:
        from agentbeats.cloudflare import quick_tunnel
        agent_url_cm = quick_tunnel(f"http://{host}:{port}")
    elif agent_url:
        agent_url_cm = contextlib.nullcontext(agent_url)
    else:
        agent_url_cm = contextlib.nullcontext(f"http://{host}:{port}/")

    async with agent_url_cm as final_agent_url:
        agent = TexasJudge()
        executor = GreenExecutor(agent)
        agent_card = texas_judge_agent_card("TexasHoldemJudge", final_agent_url)

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
            return JSONResponse({"status": "ok", "agent": "TexasHoldemJudge"})
        
        app = server.build()
        app.routes.append(Route("/status", status_endpoint, methods=["GET"]))

        logger.info(f"Starting Texas Hold'em Judge at {host}:{port}")
        logger.info(f"Agent Card URL: {final_agent_url}")

        uvicorn_config = uvicorn.Config(app, host=host, port=port)
        uvicorn_server = uvicorn.Server(uvicorn_config)
        await uvicorn_server.serve()


if __name__ == '__main__':
    asyncio.run(main())
