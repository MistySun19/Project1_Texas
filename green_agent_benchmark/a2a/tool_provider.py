# -*- coding: utf-8 -*-
"""
Tool provider for communicating with purple agents during evaluation.
"""

from .client import send_message


class ToolProvider:
    """
    Manages conversations with purple agents.
    
    Keeps track of context IDs for multi-turn conversations with each agent.
    """
    
    def __init__(self):
        self._context_ids = {}

    async def talk_to_agent(
        self, 
        message: str, 
        url: str, 
        new_conversation: bool = False
    ) -> str:
        """
        Communicate with another agent by sending a message and receiving their response.

        Args:
            message: The message to send to the agent
            url: The agent's URL endpoint
            new_conversation: If True, start fresh conversation; 
                            if False, continue existing conversation

        Returns:
            str: The agent's response message
        """
        outputs = await send_message(
            message=message, 
            base_url=url, 
            context_id=None if new_conversation else self._context_ids.get(url)
        )
        
        if outputs.get("status", "completed") != "completed":
            raise RuntimeError(f"{url} responded with: {outputs}")
        
        self._context_ids[url] = outputs.get("context_id")
        return outputs["response"]

    def reset(self):
        """Reset all conversation contexts."""
        self._context_ids = {}
