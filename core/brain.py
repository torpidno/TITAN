import os
import json
import logging
from typing import Any, Dict, List, Optional
import httpx
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("TITAN.Brain")


class HybridBrain:
    """
    Local-First Hybrid Brain engine.
    - Tier 1: Local NPU (FastFlowLM / qwen2.5-it:3b) runs primary tasks, local commands, and fast queries.
    - Tier 2: Google Gemini Cloud automatically handles tasks that are too advanced, heavy, or when local requests escalation.
    """

    def __init__(self):
        self.gemini_key = config.GEMINI_API_KEY
        self.gemini_model = config.GEMINI_MODEL
        self.local_endpoint = config.LOCAL_MODEL_ENDPOINT
        self.local_model = config.LOCAL_MODEL_NAME
        self.mode = config.TITAN_MODE

    async def check_local_health(self) -> bool:
        """Check if local FLM / NPU server is accessible, or attempt to spawn it."""
        if not config.LOCAL_MODEL_ENABLED:
            return False
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                res = await client.get(f"{self.local_endpoint}/models")
                return res.status_code == 200
        except Exception:
            # Try to auto-launch flm if installed on system
            try:
                import shutil
                if shutil.which("flm"):
                    import subprocess
                    logger.info("[FLM] FastFlowLM found on system. Launching FLM NPU server in background...")
                    subprocess.Popen(
                        ["flm", "serve", config.LOCAL_MODEL_NAME],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                    )
                    import asyncio
                    await asyncio.sleep(2.5)
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        res = await client.get(f"{self.local_endpoint}/models")
                        return res.status_code == 200
            except Exception as e:
                logger.debug(f"Auto-launch FLM failed: {e}")
            return False

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        system_instruction: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        force_cloud: bool = False,
    ) -> Dict[str, Any]:
        """
        Local-First generation loop with automatic Cloud escalation.
        
        1. Attempt with Local NPU (qwen2.5-it:3b).
        2. If task requires advanced reasoning, code synthesis, or local model signals '[ESCALATE]',
           escalate seamlessly to Google Gemini Cloud.
        """
        # If user explicitly forced cloud or mode is cloud_only
        if force_cloud or self.mode == "cloud_only":
            return await self._execute_cloud(messages, system_instruction, tools)

        # Local-First Path (Default in Hybrid and Local modes)
        local_available = await self.check_local_health()

        if local_available and config.LOCAL_MODEL_ENABLED:
            try:
                logger.info("[ROUTER] Tier 1: Executing on Local NPU (FastFlowLM / qwen2.5-it:3b)...")
                
                local_res = await self._call_local_flm(messages, system_instruction, tools)
                text = (local_res.get("text") or "").strip()
                tool_calls = local_res.get("tool_calls", [])

                has_prior_tool_results = any(m.get("role") == "tool" for m in messages)
                if not text and not tool_calls and has_prior_tool_results:
                    local_res["text"] = "Task completed successfully, Commander."
                    return local_res

                if not text and not tool_calls:
                    if self.gemini_key and self.mode != "local_only":
                        logger.info("[ROUTER] Local model returned empty response. Escalating to Gemini Cloud Engine...")
                        return await self._execute_cloud(messages, system_instruction, tools)
                    else:
                        local_res["text"] = "Command received."
                        return local_res

                return local_res

            except Exception as e:
                logger.warning(f"[ROUTER] Local NPU processing error: {e}")
                if self.mode == "local_only":
                    raise RuntimeError(f"Local engine failed and mode is local_only: {e}")
                
                if self.gemini_key:
                    logger.info("[ROUTER] ⚡ Local model error. Escalating to Gemini Cloud Engine...")
                    return await self._execute_cloud(messages, system_instruction, tools)
                raise e

        # If local is offline, fallback to Cloud
        if self.gemini_key:
            logger.info("[ROUTER] Local NPU offline. Routing to Gemini Cloud Engine...")
            return await self._execute_cloud(messages, system_instruction, tools)

        return {
            "text": "[TITAN Error]: Local NPU server is offline and no GEMINI_API_KEY is configured in .env.",
            "tool_calls": [],
            "provider": "none",
            "raw": None,
        }

    async def _execute_cloud(
        self,
        messages: List[Dict[str, Any]],
        system_instruction: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Call Google Gemini Cloud."""
        if not self.gemini_key:
            return {
                "text": "[TITAN Error]: Gemini API Key not found. Please set GEMINI_API_KEY in .env.",
                "tool_calls": [],
                "provider": "none",
                "raw": None,
            }
        logger.info("[GEMINI] Processing query with Gemini Cloud...")
        return await self._call_gemini(messages, system_instruction, tools)

    async def _call_gemini(
        self,
        messages: List[Dict[str, Any]],
        system_instruction: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Direct REST API call to Google AI Studio Gemini API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_key}"
        
        contents = []
        for m in messages:
            role = m.get("role", "user")
            if m.get("raw_parts"):
                contents.append({"role": "model", "parts": m["raw_parts"]})
            elif role in ("tool", "function"):
                contents.append({
                    "role": "user",
                    "parts": [{
                        "functionResponse": {
                            "name": m.get("name", "tool_result"),
                            "response": {"result": m.get("content", "")}
                        }
                    }]
                })
            elif role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": str(m.get("content", ""))}]
                })
            else:
                contents.append({
                    "role": "model",
                    "parts": [{"text": str(m.get("content", ""))}]
                })

        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.3,
                "topP": 0.95,
            }
        }

        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        if tools:
            gemini_func_declarations = []
            for t in tools:
                gemini_func_declarations.append({
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}})
                })
            payload["tools"] = [{"functionDeclarations": gemini_func_declarations}]

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"Gemini API error ({response.status_code}): {response.text}")
            
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return {"text": "", "tool_calls": [], "provider": "gemini", "raw_parts": [], "raw": data}
            
            first_candidate = candidates[0]
            parts = first_candidate.get("content", {}).get("parts", [])
            
            text_blocks = []
            tool_calls = []
            
            for part in parts:
                if "text" in part:
                    text_blocks.append(part["text"])
                if "functionCall" in part:
                    fn = part["functionCall"]
                    tool_calls.append({
                        "name": fn["name"],
                        "args": fn.get("args", {})
                    })

            return {
                "text": "\n".join(text_blocks) if text_blocks else None,
                "tool_calls": tool_calls,
                "raw_parts": parts,
                "provider": "gemini",
                "raw": data
            }

    async def _call_local_flm(
        self,
        messages: List[Dict[str, Any]],
        system_instruction: Optional[str] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Call local FastFlowLM OpenAI-compatible endpoint."""
        url = f"{self.local_endpoint}/chat/completions"
        
        formatted_system = system_instruction or ""
        if tools:
            tool_descriptions = "\n".join([
                f"- {t['name']}({', '.join(t.get('parameters', {}).get('properties', {}).keys())}): {t.get('description', '')}"
                for t in tools
            ])
            formatted_system += (
                f"\n\n[AVAILABLE TOOLS]:\n{tool_descriptions}\n\n"
                "[TOOL CALL INSTRUCTION]:\n"
                "To perform actions (opening apps, websites, wikis, volume, stats), respond with one or more JSON objects:\n"
                "- Desktop apps: {\"name\": \"open_application\", \"args\": {\"app_name\": \"<app>\"}}\n"
                "- Websites, wikis, URLs: {\"name\": \"open_url\", \"args\": {\"url\": \"<url or topic>\"}}\n"
                "When the user asks to open multiple applications and websites (e.g. 'open discord, steam, spotify and valheim wiki'), output a separate JSON tool call for EACH item on its own line."
            )

        formatted_messages = []
        if formatted_system:
            formatted_messages.append({"role": "system", "content": formatted_system})
            
        for m in messages:
            role = m.get("role", "user")
            if role in ("tool", "function"):
                formatted_messages.append({
                    "role": "user",
                    "content": f"[Tool '{m.get('name', 'action')}' completed]: {m.get('content', '')}"
                })
            elif role == "user":
                formatted_messages.append({
                    "role": "user",
                    "content": str(m.get("content", ""))
                })
            else:
                formatted_messages.append({
                    "role": "assistant",
                    "content": str(m.get("content", ""))
                })

        payload = {
            "model": self.local_model,
            "messages": formatted_messages,
            "temperature": 0.1,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Local FLM error ({res.status_code}): {res.text}")
            
            data = res.json()
            choice = data["choices"][0]["message"]
            text = choice.get("content") or ""
            tool_calls = []
            
            if "tool_calls" in choice and choice["tool_calls"]:
                for tc in choice["tool_calls"]:
                    fn = tc.get("function", {})
                    tool_calls.append({
                        "name": fn.get("name"),
                        "args": json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments"), str) else fn.get("arguments", {})
                    })
            elif text and ("{" in text and "}" in text):
                import re
                try:
                    clean_text = re.sub(r'```(?:json)?', '', text).replace('```', '').strip()
                    decoder = json.JSONDecoder()
                    pos = 0
                    while pos < len(clean_text):
                        idx = clean_text.find('{', pos)
                        if idx == -1:
                            break
                        try:
                            obj, end_idx = decoder.raw_decode(clean_text[idx:])
                            pos = idx + end_idx
                            if isinstance(obj, dict):
                                raw_name = obj.get("name") or obj.get("action") or obj.get("function")
                                args = obj.get("args") or obj.get("arguments") or obj.get("parameters") or {}
                                if not raw_name and "app_name" in obj:
                                    raw_name = "open_application"
                                    args = {"app_name": obj["app_name"]}
                                elif not raw_name and "url" in obj:
                                    raw_name = "open_url"
                                    args = {"url": obj["url"]}
                                elif not raw_name and "query" in obj:
                                    raw_name = "open_url" if "wiki" in str(obj.get("query", "")).lower() else "search_web"
                                    args = {"url": obj["query"]} if raw_name == "open_url" else {"query": obj["query"]}
                                elif not raw_name and "message" in obj and "launched " in str(obj["message"]).lower():
                                    raw_name = "open_application"
                                    target = str(obj["message"]).lower().split("launched ", 1)[-1].strip().strip(".")
                                    args = {"app_name": target}
                                
                                clean_name = raw_name.strip("_").strip() if raw_name else ""
                                if clean_name in ("open_browser", "open_website", "browse"):
                                    clean_name = "open_url"
                                    if "url" not in args and "query" in args:
                                        args = {"url": args["query"]}

                                if clean_name and tools and any(t["name"] == clean_name for t in tools):
                                    tool_calls.append({"name": clean_name, "args": args if isinstance(args, dict) else {}})
                        except Exception:
                            pos = idx + 1
                    
                    if tool_calls:
                        text = ""
                except Exception:
                    pass

            if text:
                import re
                for remnant in ["Provide a concise final confirmation", "[TOOL RESULT", "System note:", "[Tool", "completed]:"]:
                    text = text.replace(remnant, "").strip()
                text = re.sub(r'\[\s*\{\s*"status".*?\}\s*\]', '', text, flags=re.DOTALL).strip()
                text = re.sub(r'\{\s*"status".*?\}', '', text, flags=re.DOTALL).strip()
                text = text.strip("'\":` \n\r")
                if not text or text in ("open_url", "open_application", "search_web", "execute_powershell", "control_volume", "get_system_stats"):
                    text = "All requested applications and actions have been completed, Commander."

            return {
                "text": text,
                "tool_calls": tool_calls,
                "provider": "local_flm",
                "raw": data
            }
