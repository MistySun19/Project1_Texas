# -*- coding: utf-8 -*-
"""
A2A client utilities for communicating with purple agents.
"""

import httpx
from typing import Any, Dict, Optional
import json


async def send_message(
    message: str,
    base_url: str,
    *,
    context_id: Optional[str] = None,
    streaming: bool = False,
    consumer: Optional[Any] = None,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """
    Send a message to an A2A agent and get the response.
    
    Args:
        message: The message content to send
        base_url: The agent's base URL
        context_id: Optional context ID for multi-turn conversations
        streaming: Whether to use streaming mode
        consumer: Optional callback for streaming events
        timeout: Request timeout in seconds
        
    Returns:
        Dict containing response, status, and context_id
    """
    # Prepare the request
    url = f"{base_url.rstrip('/')}/tasks/send"
    
    payload = {
        "message": {
            "role": "user",
            "parts": [{"text": message}]
        }
    }
    
    if context_id:
        payload["contextId"] = context_id
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        if streaming:
            # Use SSE streaming
            url = f"{base_url.rstrip('/')}/tasks/sendSubscribe"
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                full_response = ""
                new_context_id = context_id
                
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data = json.loads(line[5:].strip())
                        if consumer:
                            await consumer(data, None)
                        # Extract response text and context_id from events
                        if "result" in data:
                            result = data["result"]
                            if "contextId" in result:
                                new_context_id = result["contextId"]
                            if "status" in result:
                                status = result["status"].get("state", "")
                                if status == "completed":
                                    # Get final response
                                    if "artifacts" in result:
                                        for artifact in result["artifacts"]:
                                            for part in artifact.get("parts", []):
                                                if "text" in part:
                                                    full_response += part["text"]
                                                    
                return {
                    "response": full_response,
                    "status": "completed",
                    "context_id": new_context_id
                }
        else:
            # Simple request-response
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Extract response from result
            result = data.get("result", {})
            response_text = ""
            
            if "artifacts" in result:
                for artifact in result["artifacts"]:
                    for part in artifact.get("parts", []):
                        if "text" in part:
                            response_text += part["text"]
            
            return {
                "response": response_text,
                "status": result.get("status", {}).get("state", "completed"),
                "context_id": result.get("contextId", context_id)
            }
