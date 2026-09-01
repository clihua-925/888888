# -*- coding: utf-8 -*-
"""AI Router v40：统一管理 GPT / DeepSeek / Qwen 调用。
规则：
1. 所有业务模块不直接调用任何模型，只调用 ai_router.route()
2. 模型优先级：GPT → DeepSeek → Qwen，自动降级
3. 所有AI判断必须先输出自然语言推理，再转换结构化字段
4. 输出格式统一：{natural_language, structured, confidence, model_used}
"""

import json, os, time, re
from typing import Dict, Any, Optional
from core.config import settings

MODEL_CONFIG = {
    'gpt': {
        'api_key': os.getenv('OPENAI_API_KEY') or getattr(settings, 'OPENAI_API_KEY', ''),
        'base_url': os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1'),
        'model': os.getenv('OPENAI_MODEL', 'gpt-4o'),
        'timeout': 60,
    },
    'deepseek': {
        'api_key': os.getenv('DEEPSEEK_API_KEY') or getattr(settings, 'DEEPSEEK_API_KEY', ''),
        'base_url': os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1'),
        'model': os.getenv('DEEPSEEK_MODEL', 'deepseek-chat'),
        'timeout': 60,
    },
    'qwen': {
        'api_key': os.getenv('QWEN_API_KEY') or getattr(settings, 'QWEN_API_KEY', ''),
        'base_url': os.getenv('QWEN_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1'),
        'model': os.getenv('QWEN_MODEL', 'qwen-max'),
        'timeout': 60,
    }
}

MODEL_PRIORITY = ['gpt', 'deepseek', 'qwen']

class AIRouter:
    """统一AI网关：所有业务AI调用必须经过此处。"""

    def __init__(self):
        self._clients = {}
        self._last_error = {}
        self._fallback_chain = MODEL_PRIORITY.copy()

    def _get_client(self, model_name: str):
        if model_name in self._clients:
            return self._clients[model_name]
        cfg = MODEL_CONFIG.get(model_name)
        if not cfg or not cfg.get('api_key'):
            return None
        try:
            import openai
            client = openai.OpenAI(
                api_key=cfg['api_key'],
                base_url=cfg['base_url'],
                timeout=cfg['timeout']
            )
            self._clients[model_name] = client
            return client
        except Exception as e:
            self._last_error[model_name] = str(e)
            return None

    def _call_model(self, model_name: str, messages: list, temperature: float = 0.3, 
                    max_tokens: int = 2000, json_mode: bool = False) -> Optional[dict]:
        client = self._get_client(model_name)
        if not client:
            return None
        cfg = MODEL_CONFIG[model_name]
        try:
            kwargs = {
                'model': cfg['model'],
                'messages': messages,
                'temperature': temperature,
                'max_tokens': max_tokens,
            }
            if json_mode:
                kwargs['response_format'] = {"type": "json_object"}

            resp = client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content
            return {
                'content': content,
                'model': model_name,
                'usage': {
                    'prompt_tokens': resp.usage.prompt_tokens,
                    'completion_tokens': resp.usage.completion_tokens
                }
            }
        except Exception as e:
            self._last_error[model_name] = str(e)
            return None

    def route(self, prompt: str, system: str = "", 
              require_natural_language: bool = True,
              structured_schema: Optional[dict] = None,
              temperature: float = 0.3, max_tokens: int = 2000) -> dict:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})

        if require_natural_language and structured_schema:
            nl_instruction = f"""
【强制输出格式】
你必须先以自然语言进行完整推理，然后给出结构化判断。

自然语言部分要求：
1. 先说明判断结果（例如：该企业高度可能是真实采购客户 / 信息不完整无法判断）
2. 列出原因（至少3条）
3. 给出置信度（Strong / Moderate / Weak）

结构化部分要求（JSON）：
{json.dumps(structured_schema, ensure_ascii=False, indent=2)}

请严格按以下格式输出：
===自然语言===
[你的推理]
===结构化===
```json
[JSON对象]
```
"""
            prompt = nl_instruction + "\n\n【任务】\n" + prompt

        messages.append({"role": "user", "content": prompt})

        last_error = ""
        for model_name in self._fallback_chain:
            result = self._call_model(
                model_name, messages, 
                temperature=temperature, 
                max_tokens=max_tokens,
                json_mode=False
            )
            if result:
                return self._parse_response(
                    result['content'], 
                    model_name, 
                    require_natural_language,
                    structured_schema
                )
            last_error = self._last_error.get(model_name, f"{model_name} unavailable")

        return {
            'ok': False,
            'natural_language': '',
            'structured': {},
            'confidence': 'Weak',
            'model_used': 'none',
            'error': f"All models failed. Last: {last_error}",
            'raw': ''
        }

    def _parse_response(self, content: str, model_used: str, 
                        require_nl: bool, schema: Optional[dict]) -> dict:
        content = content or ""

        nl_match = re.search(r'===自然语言===\s*(.*?)\s*(?:===结构化===|```json)', content, re.DOTALL)
        natural_language = nl_match.group(1).strip() if nl_match else content[:500]

        structured = {}
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if not json_match:
            json_match = re.search(r'===结构化===\s*(.*?)\s*(?:```|$)', content, re.DOTALL)

        if json_match:
            try:
                structured = json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                try:
                    start = content.find('{')
                    end = content.rfind('}')
                    if start >= 0 and end > start:
                        structured = json.loads(content[start:end+1])
                except:
                    pass

        if schema and structured:
            for key in schema.get('required', []):
                if key not in structured:
                    structured[key] = None

        confidence = 'Weak'
        if 'strong' in natural_language.lower() or '高度' in natural_language:
            confidence = 'Strong'
        elif 'moderate' in natural_language.lower() or '中等' in natural_language or '可能' in natural_language:
            confidence = 'Moderate'
        elif structured and structured.get('confidence'):
            confidence = structured['confidence']

        return {
            'ok': True,
            'natural_language': natural_language,
            'structured': structured,
            'confidence': confidence,
            'model_used': model_used,
            'error': '',
            'raw': content
        }

    def quick_judge(self, prompt: str, system: str = "") -> dict:
        return self.route(prompt, system, require_natural_language=False, max_tokens=500)

_router = None

def get_router() -> AIRouter:
    global _router
    if _router is None:
        _router = AIRouter()
    return _router

def ai_route(prompt: str, system: str = "", schema: Optional[dict] = None, 
             require_nl: bool = True) -> dict:
    return get_router().route(prompt, system, require_nl, schema)

def ai_quick(prompt: str, system: str = "") -> dict:
    return get_router().quick_judge(prompt, system)
