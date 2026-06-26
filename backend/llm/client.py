"""
LLM integration layer.
Supports any OpenAI-compatible API: LM Studio, Ollama, vLLM, text-generation-webui, etc.
User configures base_url and model name — that's it.
"""
import httpx
import json
import yaml
import os
from typing import Optional, Dict, List


class LLMClient:
    """Client for local LLM inference via OpenAI-compatible API."""

    def __init__(self, config_path: str = None):
        self.base_url = "http://localhost:1234/v1"
        self.model = "gemma-3-4b-it"
        self.temperature = 0.3
        self.max_tokens = 4096
        self.provider = "lmstudio"

        if config_path:
            self.load_config(config_path)

    def load_config(self, config_path: str):
        """Load LLM config from YAML."""
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        llm_config = config.get("llm", {})
        self.provider = llm_config.get("provider", "lmstudio")
        self.base_url = llm_config.get("base_url", self.base_url)
        self.model = llm_config.get("model", self.model)
        self.temperature = llm_config.get("temperature", 0.3)
        self.max_tokens = llm_config.get("max_tokens", 4096)

    def update_config(self, **kwargs):
        """Update LLM settings at runtime."""
        for key in ["base_url", "model", "temperature", "max_tokens", "provider"]:
            if key in kwargs:
                setattr(self, key, kwargs[key])

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
    ) -> Dict:
        """
        Send a chat completion request.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Override default temperature
            max_tokens: Override default max tokens
            response_format: Optional response format (e.g., {"type": "json_object"})
            
        Returns:
            Dict with 'content' (str), 'usage' (dict), 'raw' (dict)
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }

        if response_format:
            payload["response_format"] = response_format

        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                return {
                    "content": data["choices"][0]["message"]["content"],
                    "usage": data.get("usage", {}),
                    "raw": data,
                }
            except httpx.ConnectError:
                return {
                    "content": "",
                    "error": f"Cannot connect to LLM at {self.base_url}. Is your LLM server running?",
                    "usage": {},
                    "raw": {},
                }
            except httpx.HTTPStatusError as e:
                return {
                    "content": "",
                    "error": f"LLM returned HTTP {e.response.status_code}: {e.response.text}",
                    "usage": {},
                    "raw": {},
                }
            except Exception as e:
                return {
                    "content": "",
                    "error": f"LLM error: {str(e)}",
                    "usage": {},
                    "raw": {},
                }

    async def generate_json(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> Dict:
        """
        Request a JSON response from the LLM.
        Falls back to parsing JSON from text if the model doesn't support response_format.
        """
        # Try with response_format first
        result = await self.chat(
            messages=messages,
            temperature=temperature or 0.1,
            response_format={"type": "json_object"},
        )

        if result.get("error"):
            # Fallback: try without response_format
            result = await self.chat(
                messages=messages,
                temperature=temperature or 0.1,
            )

        content = result.get("content", "")
        if content:
            try:
                # Try to extract JSON from the response
                parsed = json.loads(content)
                result["parsed"] = parsed
            except json.JSONDecodeError:
                # Try to find JSON in the response
                import re
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                        result["parsed"] = parsed
                    except json.JSONDecodeError:
                        result["parsed"] = None
                        result["parse_error"] = "Could not parse JSON from LLM response"
                else:
                    result["parsed"] = None
                    result["parse_error"] = "No JSON found in LLM response"

        return result

    async def health_check(self) -> Dict:
        """Check if the LLM server is reachable and responsive."""
        url = f"{self.base_url}/models"
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                models = [m.get("id", "unknown") for m in data.get("data", [])]
                return {
                    "status": "connected",
                    "provider": self.provider,
                    "base_url": self.base_url,
                    "model": self.model,
                    "available_models": models,
                }
            except httpx.ConnectError:
                return {
                    "status": "disconnected",
                    "error": f"Cannot connect to {self.base_url}",
                    "provider": self.provider,
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "provider": self.provider,
                }

    def get_config(self) -> Dict:
        """Return current LLM configuration."""
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
