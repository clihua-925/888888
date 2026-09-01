# -*- coding: utf-8 -*-
"""TRADE_GRAPH_VISUALIZATION v41：贸易图谱——只负责商业关系可视化。

职责边界：
- 客户情报中心：研究企业（档案、补全、评分、扩张）
- 贸易图谱：展示关系（节点、边、路径、证据）

禁止：重复建设客户列表、客户档案编辑等功能。
"""
import json
from typing import List, Dict, Any
from core.memory.db import DB


class TradeGraphVisualization:
    """贸易图谱可视化引擎：只读展示，不写业务逻辑。"""

    def __init__(self):
        self.db = DB()

    # ---------- 核心对象查询 ----------

    def get_node(self, norm: str) -> Dict:
        """获取单个节点（点击后进入客户情报中心）。"""
        lead = self.db.get_lead(norm)
        if not lead:
            return {'error': '节点不存在'}

        # 只返回展示所需字段
        return {
            'norm': norm,
            'name': lead.get('name'),
            'type': lead.get('type', 'unknown'),
            'country': lead.get('country'),
            'category': lead.get('category'),
            'shipments': lead.get('shipments', 0),
            'website': lead.get('website'),
            'click_target': 'account_intelligence_center',  # 点击跳转目标
            'click_url': f'/account/{norm}'
        }

    def get_node_relationships(self, norm: str, limit: int = 100) -> List[Dict]:
        """获取节点的所有关系边（带证据）。"""
        rels = self.db.list_relationships(norm=norm, limit=limit)
        result = []
        for r in rels:
            result.append({
                'from_norm': r.get('from_norm'),
                'from_name': r.get('from_name'),
                'to_norm': r.get('to_norm'),
                'to_name': r.get('to_name'),
                'relation': r.get('relation'),
                'source': r.get('source'),
                'evidence': r.get('evidence'),
                'product': r.get('product'),
                'time_range': r.get('time_range'),
                'transaction_count': r.get('transaction_count'),
                'strength': self._calc_strength(r)
            })
        return result

    def _calc_strength(self, rel: Dict) -> str:
        """计算关系强度。"""
        evidence = rel.get('evidence') or {}
        tx = int(rel.get('transaction_count') or 0)
        if evidence.get('shipments') or evidence.get('bill_of_lading') or tx >= 10:
            return 'strong'
        if tx >= 3 or evidence.get('customs'):
            return 'medium'
        return 'weak'

    # ---------- 图谱子图查询 ----------

    def get_subgraph(self, center_norm: str, depth: int = 2, max_nodes: int = 50) -> Dict:
        """以某节点为中心，获取子图（用于可视化展示）。"""
        nodes = {}
        edges = []

        # BFS 遍历
        queue = [(center_norm, 0)]
        visited = {center_norm}

        while queue and len(nodes) < max_nodes:
            current_norm, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue

            # 获取节点信息
            node_info = self.get_node(current_norm)
            if 'error' not in node_info:
                nodes[current_norm] = node_info

            # 获取关系
            rels = self.get_node_relationships(current_norm, limit=30)
            for r in rels:
                other_norm = r['to_norm'] if r['from_norm'] == current_norm else r['from_norm']
                if other_norm not in nodes:
                    nodes[other_norm] = {
                        'norm': other_norm,
                        'name': r['to_name'] if r['from_norm'] == current_norm else r['from_name'],
                        'type': 'unknown',
                        'click_target': 'account_intelligence_center',
                        'click_url': f'/account/{other_norm}'
                    }

                edges.append({
                    'from': r['from_norm'],
                    'to': r['to_norm'],
                    'relation': r['relation'],
                    'strength': r['strength'],
                    'product': r['product'],
                    'evidence': r['evidence']
                })

                if other_norm not in visited and len(nodes) < max_nodes:
                    visited.add(other_norm)
                    queue.append((other_norm, current_depth + 1))

        return {
            'center': center_norm,
            'depth': depth,
            'node_count': len(nodes),
            'edge_count': len(edges),
            'nodes': list(nodes.values()),
            'edges': edges
        }

    # ---------- 路径分析 ----------

    def find_path(self, from_norm: str, to_norm: str, max_depth: int = 4) -> List[Dict]:
        """查找两个节点之间的贸易路径。"""
        # 简单的 BFS 路径查找
        queue = [(from_norm, [from_norm])]
        visited = {from_norm}

        while queue:
            current, path = queue.pop(0)
            if current == to_norm and len(path) > 1:
                return self._build_path_detail(path)

            if len(path) >= max_depth:
                continue

            rels = self.get_node_relationships(current, limit=20)
            for r in rels:
                next_norm = r['to_norm'] if r['from_norm'] == current else r['from_norm']
                if next_norm not in visited:
                    visited.add(next_norm)
                    queue.append((next_norm, path + [next_norm]))

        return []

    def _build_path_detail(self, path_norms: List[str]) -> List[Dict]:
        """将路径节点列表转换为详细路径信息。"""
        result = []
        for i, norm in enumerate(path_norms):
            node = self.get_node(norm)
            step = {
                'step': i + 1,
                'norm': norm,
                'name': node.get('name', norm),
                'type': node.get('type', 'unknown')
            }
            if i > 0:
                # 找与前一个节点的关系
                prev = path_norms[i - 1]
                rels = self.db.list_relationships(norm=prev, limit=100)
                for r in rels:
                    if r.get('to_norm') == norm or r.get('from_norm') == norm:
                        step['relation_from_prev'] = {
                            'type': r.get('relation'),
                            'evidence': r.get('evidence'),
                            'strength': self._calc_strength(r)
                        }
                        break
            result.append(step)
        return result

    # ---------- 全局图谱统计 ----------

    def get_graph_stats(self) -> Dict:
        """获取贸易图谱全局统计。"""
        try:
            with self.db.c() as c:
                node_count = c.execute('SELECT COUNT(DISTINCT norm) FROM leads').fetchone()[0]
                edge_count = c.execute('SELECT COUNT(*) FROM relationships').fetchone()[0]
                buyer_count = c.execute("SELECT COUNT(*) FROM leads WHERE type='buyer' OR category LIKE '%import%'").fetchone()[0]
                supplier_count = c.execute("SELECT COUNT(*) FROM leads WHERE type='supplier' OR category LIKE '%export%'").fetchone()[0]

                # 强证据边占比
                strong_edges = c.execute("""
                    SELECT COUNT(*) FROM relationships
                    WHERE evidence LIKE '%shipments%' OR evidence LIKE '%bill_of_lading%'
                """).fetchone()[0]

                return {
                    'total_nodes': node_count,
                    'total_edges': edge_count,
                    'buyers': buyer_count,
                    'suppliers': supplier_count,
                    'strong_edges': strong_edges,
                    'edge_strength_ratio': round(strong_edges / max(1, edge_count), 2)
                }
        except Exception as e:
            return {'error': str(e)}


# ---------- 便捷函数 ----------
def get_subgraph(center_norm: str, depth: int = 2) -> Dict:
    return TradeGraphVisualization().get_subgraph(center_norm, depth)

def find_trade_path(from_norm: str, to_norm: str) -> List[Dict]:
    return TradeGraphVisualization().find_path(from_norm, to_norm)

def get_graph_statistics() -> Dict:
    return TradeGraphVisualization().get_graph_stats()

# ---------- 兼容 app.py / system.py 的导入别名 ----------
network = get_subgraph
path = find_trade_path
evidence = get_graph_statistics


# ---------- 前端API兼容函数 ----------

def network(center: str, depth: int = 2) -> dict:
    """前端API兼容：获取贸易网络子图。"""
    return get_subgraph(center, depth=depth)


def path(from_norm: str, to_norm: str) -> dict:
    """前端API兼容：查找贸易路径。"""
    result = find_trade_path(from_norm, to_norm)
    return {'ok': True, 'path': result}


def evidence(norm: str) -> dict:
    """前端API兼容：获取节点证据详情。"""
    viz = TradeGraphVisualization()
    node = viz.get_node(norm)
    rels = viz.get_node_relationships(norm)
    return {
        'ok': True,
        'norm': norm,
        'node': node,
        'relationships': rels,
        'evidence_count': len(rels),
    }
