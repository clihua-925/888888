# -*- coding: utf-8 -*-
"""联系方式提取 provider（v38 精简版）。

v37 起字段级补全由 core.intelligence.waterfall 统一编排（成功即停/便宜优先/最后验证），
本模块只保留两个被 waterfall 复用的免费 provider：
- _extract_from_html：官网 HTML 正则提取（website/emails/phones/address）
- _search_website_by_company：bing 搜索公司官网
旧的整记录 enrich/enrich_one/run 流程已删除（被 waterfall 取代，禁止新旧两套并存）。
"""
import re, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from core.config import settings
from core.memory.db import DB


class ContactFinder:
    def __init__(self):
        self.db = DB()

    def _extract_from_html(self, html):
        if not html:
            return {}
        emails = re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', html)
        phones = re.findall(r'(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}', html)
        websites = re.findall(r'https?://[A-Za-z0-9./_-]+', html)
        addresses = re.findall(r'\d{1,6}\s+[A-Za-z0-9][\w .#-]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Parkway|Pkwy)[\w .,#-]*', html)
        out = {}
        if websites:
            out['website'] = websites[0].strip('.,;')
        if emails:
            out['emails'] = list(dict.fromkeys(emails[:5]))
        if phones:
            out['phones'] = list(dict.fromkeys(phones[:2]))
        if addresses:
            out['address'] = addresses[0].strip()
        return out

    def _search_website_by_company(self, name, country='USA'):
        try:
            import requests
            from bs4 import BeautifulSoup
            query = f"{name} official website"
            headers = {'User-Agent': 'Mozilla/5.0'}
            url = f"https://www.bing.com/search?q={requests.utils.quote(query)}"
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            first = soup.select_one('li.b_algo h2 a')
            if first:
                link = first.get('href')
                if link and 'http' in link:
                    return link
        except Exception:
            pass
        return None
