from core.model.client import ModelClient
from core.utils.jsonutil import j,jl
from core.config import settings
class ReasoningEngine:
    def __init__(self,model=None): self.model=model or ModelClient()
    @property
    def available(self): return self.model.health()
    def json(self,prompt,system=None,as_list=False,temperature=0.3):
        if not self.model.health(): return [] if as_list else None
        t=self.model.chat(prompt,system=system,temperature=temperature)
        if not t: return [] if as_list else None
        return jl(t) if as_list else j(t)
    def text(self,prompt,system=None,temperature=0.3,max_tokens=None):
        """自由文本调用（专家推理/诊断用）"""
        if not self.model.health(): return ''
        return self.model.chat(prompt,system=system,temperature=temperature,
                               max_tokens=max_tokens or settings.LLM_REVIEW_MAX_TOKENS,
                               timeout=settings.LLM_REVIEW_TIMEOUT) or ''
    def review(self,prompt,system=None):
        """专家复核调用：小 tokens、低温度、强制 JSON 结论"""
        if not self.model.health(): return None
        t=self.model.chat(prompt,system=system,temperature=0.2,
                          max_tokens=settings.LLM_REVIEW_MAX_TOKENS,
                          timeout=settings.LLM_REVIEW_TIMEOUT)
        return j(t) if t else None
