# -*- coding: utf-8 -*-
"""v16.5: 网页AI兜底通道（DeepSeek/ChatGPT 网页版，走用户已登录的 CDP 浏览器会话）。
定位：疑难问题的少量对话式兜底，不是批量工具。
安全闸：每日上限 WEBAI_DAILY_MAX + 调用间隔 WEBAI_MIN_INTERVAL 秒 + 仅开发/维护区客户触发。
用法：
  from core.tools import web_ai
  txt=web_ai.ask('把 Signature Brands 的官网/邮箱/电话/地址给我，输出JSON')
  python -m core.tools.web_ai diag deepseek "hello"   # 诊断"""
import re,time,json,sqlite3,random
import os as _os,sys as _sys
_sys.path.insert(0,_os.path.abspath(_os.path.join(_os.path.dirname(__file__),'../..')))
from core.config import settings

ENGINES={
 'deepseek':{'url':'https://chat.deepseek.com/',
             'inputs':['textarea#chat-input','textarea[placeholder]','textarea'],
             'answers':['.ds-markdown','.markdown','.message','[class*=markdown]']},
 'chatgpt':{'url':'https://chatgpt.com/',
            'inputs':['#prompt-textarea','div[contenteditable="true"]','textarea'],
            'answers':['[data-message-author-role="assistant"]','.markdown','[class*=markdown]']},
 # v38 千问（通义）网页引擎：走用户在 CDP 浏览器里已登录的通义会话；
 # 未登录时 preflight 诚实失败并自动切换下一家——绝不假装成功。
 'qwen':{'url':'https://www.tongyi.com/',
         'inputs':['textarea[placeholder]','textarea','div[contenteditable="true"]'],
         'answers':['[class*=markdown]','.markdown','[class*=answer]','[class*=message]']},
}
_last_call=[0.0]

def _quota_ok(engine):
    day=time.strftime('%Y-%m-%d')
    try:
        conn=sqlite3.connect(settings.DATABASE_PATH)
        conn.execute('CREATE TABLE IF NOT EXISTS source_quota(source TEXT,day TEXT,count INT,UNIQUE(source,day))')
        r=conn.execute('SELECT count FROM source_quota WHERE source=? AND day=?',('webai_'+engine,day)).fetchone()
        used=r[0] if r else 0
        ok=used<int(settings.WEBAI_DAILY_MAX)
        conn.close(); return ok,used
    except Exception: return True,0

def _quota_inc(engine):
    day=time.strftime('%Y-%m-%d')
    try:
        conn=sqlite3.connect(settings.DATABASE_PATH)
        conn.execute('INSERT INTO source_quota(source,day,count) VALUES(?,?,1) ON CONFLICT(source,day) DO UPDATE SET count=count+1',('webai_'+engine,day))
        conn.commit(); conn.close()
    except Exception: pass

def _cdp_alive(url):
    import urllib.request
    try:
        op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(url+'/json/version',timeout=4) as r: return r.status==200
    except Exception: return False

class WebAI:
    """挂 CDP 桌面浏览器（用户已登录 DeepSeek/GPT 的那个 Chrome）。"""
    def __init__(self):
        self._pw=None; self._br=None; self._pg=None
    def _launch(self):
        from playwright.sync_api import sync_playwright
        if not (settings.IY_WEB_CDP_ENABLED and _cdp_alive(settings.IY_WEB_CDP_URL)):
            raise RuntimeError('CDP 浏览器未就绪（先跑 start_chrome_debug.bat 并登录 AI 网站）')
        self._pw=sync_playwright().start()
        self._br=self._pw.chromium.connect_over_cdp(settings.IY_WEB_CDP_URL)
        ctx=self._br.contexts[0]
        self._pg=ctx.new_page()
    def close(self):
        try:
            if self._pg: self._pg.close()
            if self._pw: self._pw.stop()
        except Exception: pass
    def _first_visible(self,selectors):
        for sel in selectors:
            try:
                els=self._pg.query_selector_all(sel)
                for el in els:
                    if el.is_visible(): return el
            except Exception: continue
        return None
    def ask(self,question,engine=None,timeout=None):
        """开新会话问一个问题，等流式输出稳定后取回最后一条回答。失败返回 None。"""
        engine=engine or settings.WEBAI_ENGINE
        cfg=ENGINES.get(engine)
        if not cfg: print('[webai] 未知引擎:',engine); return None
        ok,used=_quota_ok(engine)
        if not ok:
            print('[webai] %s 已达今日上限(%d轮)，跳过'%(engine,settings.WEBAI_DAILY_MAX)); return None
        # 拟人节奏: 随机间隔
        import random as _rnd
        need=float(settings.WEBAI_MIN_INTERVAL)*_rnd.uniform(1.0,2.5)
        gap=time.time()-_last_call[0]
        if gap<need: time.sleep(need-gap)
        if not self._pg: self._launch()
        try:
            self._pg.goto(cfg['url'],timeout=60000,wait_until='domcontentloaded')
            self._pg.wait_for_timeout(5000)
            box=self._first_visible(cfg['inputs'])
            if not box:
                print('[webai] %s 未找到输入框（未登录或页面改版）'%engine); return None
            # 点击输入框并清空可能存在的旧内容
            box.click()
            self._pg.wait_for_timeout(500)
            try:
                box.fill('')
            except Exception:
                pass
            self._pg.wait_for_timeout(300)
            # 使用 insert_text 一次性输入完整问题，速度更快且不易中断
            # 限制 4000 字符，基本覆盖审核 prompt 长度
            text = question[:4000]
            self._pg.keyboard.insert_text(text)
            self._pg.wait_for_timeout(1200)  # 确保文本完全写入
            self._pg.keyboard.press('Enter')
            _last_call[0]=time.time()
            # 等回答出现并稳定（流式结束=连续2轮文本不变）
            deadline=time.time()+int(timeout or settings.WEBAI_TIMEOUT)
            last=''; stable=0; seen=False
            while time.time()<deadline:
                self._pg.wait_for_timeout(3000)
                el=self._first_visible(cfg['answers'])
                txt=''
                if el:
                    try:
                        els=self._pg.query_selector_all(cfg['answers'][0])
                        els=[e for e in els if e.is_visible()]
                        if els: txt=els[-1].inner_text().strip()
                    except Exception: pass
                if txt:
                    seen=True
                    if txt==last: stable+=1
                    else: stable=0
                    last=txt
                    if stable>=2 and len(txt)>10: break
            if not seen:
                print('[webai] %s 无回答（可能触发验证或限流）'%engine); return None
            _quota_inc(engine)
            print('[webai] %s 回答 %d 字（今日第%d/%d轮）'%(engine,len(last),used+1,settings.WEBAI_DAILY_MAX))
            return last
        except Exception as e:
            print('[webai] %s 异常: %s'%(engine,str(e)[:100]))
            return None

def solve(problem,context='',engines=None,timeout=None):
    """难题终结者：本地解决不了的核心问题，按引擎链逐个问，拿到第一个有效回答。"""
    engines=engines or [settings.WEBAI_ENGINE]+[e for e in ('deepseek','chatgpt') if e!=settings.WEBAI_ENGINE]
    prompt=(problem+'\n\n背景上下文：\n'+str(context)[:3000]) if context else problem
    w=WebAI()
    try:
        w._launch()
        for eng in engines:
            r=w.ask(prompt,engine=eng,timeout=timeout)
            if r and len(r.strip())>10:
                print('[webai] 难题已由 %s 解决(%d字)'%(eng,len(r)))
                return r
            print('[webai] %s 无有效回答, 换下一引擎'%eng)
        return None
    except Exception as e:
        print('[webai] solve failed:',str(e)[:100]); return None
    finally: w.close()

def ask(question,engine=None,timeout=None):
    """一次性入口：自动开/关浏览器页。"""
    w=WebAI()
    try:
        w._launch()
        return w.ask(question,engine=engine,timeout=timeout)
    except Exception as e:
        print('[webai] failed:',str(e)[:100]); return None
    finally: w.close()

if __name__=='__main__':
    import sys
    if len(sys.argv)>2 and sys.argv[1]=='diag':
        eng=sys.argv[2]
        q=sys.argv[3] if len(sys.argv)>3 else '请只回答两个字：收到'
        print('== 网页AI诊断:',eng,'==')
        print('引擎URL:',ENGINES.get(eng,{}).get('url'))
        print('每日上限:',settings.WEBAI_DAILY_MAX,'| 间隔:',settings.WEBAI_MIN_INTERVAL,'s')
        r=ask(q,engine=eng,timeout=90)
        print('回答:',(r or '(无)')[:200])
    else:
        print('用法: python -m core.tools.web_ai diag deepseek "问题"')
