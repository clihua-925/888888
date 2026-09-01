# -*- coding: utf-8 -*-
"""Network Expansion Engine v45
核心职责：从客户情报中心触发，实现真正的双向网络扩张，结果自动进入对应池子。

扩张方向（13种）：
1.  customer → supplier              (客户→供应商)
2.  supplier → customer              (供应商→客户)
3.  same_supplier → new_customer     (同供应商→新客户)
4.  same_customer → new_supplier     (同客户→新供应商)
5.  same_product → related_customer  (同产品→相关客户)
6.  same_product → related_supplier  (同产品→相关供应商)
7.  trade_relation_reverse           (贸易关系反向扩张)
8.  associated_enterprise            (关联企业扩张)
9.  brand_association                (品牌关联)
10. address_identity                 (地址/企业身份关联)
11. public_web_association           (公开网页关联)
12. contact_organization             (联系人/组织关系扩张)
13. new_node_as_seed                 (新节点继续作为下一轮种子)

所有扩张出来的新节点：
- 根据角色自动进入客户资源池或供应商资源池
- 然后进入情报补全流程
- 最终形成闭环

实时显示：
- 已发现节点
- 新增客户
- 新增供应商
- 新增贸易边
- 新增证据
- 当前网络深度
- 当前扩张轮次
- 正在处理的节点
- 已经处理的节点
- 待处理节点

动态停止：
- 信息增益优先
- 策略切换机制
- 收敛判断
- 保留停止原因、最后一轮结果、信息增益曲线、未处理节点
"""

import json
import time
import uuid
from typing import List, Dict, Set, Any
from core.memory.db import DB
from core.intelligence.ai_router import ai_route
from core.intelligence.stop_condition import create_stop_condition


class NetworkExpansionEngine:
    """网络扩张引擎。"""

    EXPANSION_STRATEGIES = {
        'customer_to_supplier': {
            'name': '客户→供应商',
            'description': '从客户出发，寻找其供应商',
            'direction': 'forward',
            'role_filter': 'supplier'
        },
        'supplier_to_customer': {
            'name': '供应商→客户',
            'description': '从供应商出发，寻找其客户',
            'direction': 'forward',
            'role_filter': 'customer'
        },
        'same_supplier_new_customer': {
            'name': '同供应商→新客户',
            'description': '找到与种子共享供应商的其他客户',
            'direction': 'lateral',
            'role_filter': 'customer'
        },
        'same_customer_new_supplier': {
            'name': '同客户→新供应商',
            'description': '找到与种子共享客户的其他供应商',
            'direction': 'lateral',
            'role_filter': 'supplier'
        },
        'same_product_customer': {
            'name': '同产品→相关客户',
            'description': '找到采购同类产品的其他客户',
            'direction': 'lateral',
            'role_filter': 'customer'
        },
        'same_product_supplier': {
            'name': '同产品→相关供应商',
            'description': '找到供应同类产品的其他供应商',
            'direction': 'lateral',
            'role_filter': 'supplier'
        },
        'trade_relation_reverse': {
            'name': '贸易关系反向扩张',
            'description': '反向追踪贸易关系链',
            'direction': 'reverse',
            'role_filter': 'both'
        },
        'associated_enterprise': {
            'name': '关联企业扩张',
            'description': '通过集团、母公司、子公司关系扩张',
            'direction': 'lateral',
            'role_filter': 'both'
        },
        'brand_association': {
            'name': '品牌关联',
            'description': '通过品牌关联找到相关企业',
            'direction': 'lateral',
            'role_filter': 'both'
        },
        'address_identity': {
            'name': '地址/企业身份关联',
            'description': '通过相同地址或企业注册信息关联',
            'direction': 'lateral',
            'role_filter': 'both'
        },
        'public_web_association': {
            'name': '公开网页关联',
            'description': '通过公开网页信息找到关联企业',
            'direction': 'lateral',
            'role_filter': 'both'
        },
        'contact_organization': {
            'name': '联系人/组织关系扩张',
            'description': '通过联系人跳槽、组织关系找到新企业',
            'direction': 'lateral',
            'role_filter': 'both'
        },
    }

    def __init__(self):
        self.db = DB()

    def expand(self, seed_norm: str, category_id: str = None,
               expansion_types: List[str] = None,
               max_depth: int = 5, max_new: int = 50,
               task_id: str = None) -> dict:
        """网络扩张主入口。

        Args:
            seed_norm: 种子节点norm
            category_id: 品类ID（严格隔离）
            expansion_types: 指定扩张类型列表，None则使用全部
            max_depth: 最大扩张深度（安全保护）
            max_new: 每轮最大新节点数
            task_id: 任务ID
        """
        task_id = task_id or f"exp-{uuid.uuid4().hex[:8]}"

        # 创建任务面板记录
        self.db.create_task(
            task_id=task_id,
            task_name=f"Network Expansion: {seed_norm}",
            task_type='network_expansion',
            category_id=category_id,
            parent_task_id=None
        )
        self.db.update_task(task_id, run_status='running', current_stage='expansion')

        # 获取种子实体
        seed_entity = self.db.get_entity(seed_norm)
        if not seed_entity:
            # 尝试从第一采集链获取并创建统一实体
            lead = self.db.get_lead(seed_norm)
            if lead:
                seed_entity = self.db.get_or_create_entity(
                    norm=seed_norm,
                    name=lead.get('name'),
                    country=lead.get('country'),
                    category_id=category_id
                )
            else:
                self.db.update_task(task_id, run_status='failed', failure_reason='Seed not found')
                return {'ok': False, 'error': 'seed not found', 'seed_norm': seed_norm}

        seed_entity_id = seed_entity['entity_id']

        # 初始化动态停止条件
        stop_condition = create_stop_condition(
            task_id=task_id,
            min_execution_time=60,
            suggested_time=300,
            max_safety_time=1800,
            strategy_switch_threshold=2,
            convergence_patience=3,
            min_gain_per_round=1
        )

        # 确定扩张策略
        strategies = expansion_types or list(self.EXPANSION_STRATEGIES.keys())

        # 扩张状态跟踪
        all_discovered = {}  # norm -> entity_info
        processed_nodes = set()
        pending_nodes = [(seed_norm, 0, None)]  # (norm, depth, parent_norm)
        round_num = 0
        current_strategy_index = 0

        # 实时统计
        stats = {
            'total_discovered': 0,
            'total_new_customers': 0,
            'total_new_suppliers': 0,
            'total_new_edges': 0,
            'total_new_evidence': 0,
            'current_depth': 0,
            'current_round': 0,
            'current_strategy': strategies[0] if strategies else None,
            'processing_node': seed_norm,
            'processed_count': 0,
            'pending_count': 1,
        }

        try:
            while pending_nodes and round_num < max_depth * len(strategies):
                round_num += 1
                stats['current_round'] = round_num

                # 获取当前策略
                current_strategy = strategies[current_strategy_index % len(strategies)]
                stats['current_strategy'] = current_strategy

                # 获取待处理节点
                if not pending_nodes:
                    break

                current_norm, current_depth, parent_norm = pending_nodes.pop(0)
                stats['processing_node'] = current_norm
                stats['pending_count'] = len(pending_nodes)

                if current_norm in processed_nodes:
                    continue

                processed_nodes.add(current_norm)
                stats['processed_count'] = len(processed_nodes)
                stats['current_depth'] = current_depth

                # 执行扩张
                discovered = self._execute_strategy(
                    task_id=task_id,
                    strategy=current_strategy,
                    seed_norm=current_norm,
                    seed_entity_id=seed_entity_id,
                    parent_norm=parent_norm,
                    category_id=category_id,
                    max_new_per_type=max(5, max_new // len(strategies))
                )

                # 处理发现的新节点
                round_new_customers = 0
                round_new_suppliers = 0
                round_new_edges = 0
                round_new_evidence = 0

                for node in discovered:
                    node_norm = node['norm']
                    node_role = node.get('role', 'unknown')

                    if node_norm not in all_discovered:
                        all_discovered[node_norm] = node
                        stats['total_discovered'] += 1

                        # 自动按角色分类入库
                        if node_role in ('customer', 'buyer', 'importer'):
                            self._add_to_pool(node, 'customer', category_id, task_id)
                            round_new_customers += 1
                            stats['total_new_customers'] += 1
                        elif node_role in ('supplier', 'shipper', 'exporter'):
                            self._add_to_pool(node, 'supplier', category_id, task_id)
                            round_new_suppliers += 1
                            stats['total_new_suppliers'] += 1

                        # 保存贸易边
                        edge_id = self.db.save_trade_edge(
                            from_entity_id=seed_entity_id,
                            to_entity_id=node.get('entity_id'),
                            from_norm=current_norm,
                            to_norm=node_norm,
                            relation=current_strategy,
                            product=node.get('product'),
                            hs_code=node.get('hs_code'),
                            evidence_level='MEDIUM',
                            discovered_via='network_expansion',
                            parent_node=parent_norm or seed_norm,
                            expansion_path=f"{seed_norm}->{current_norm}->{node_norm}",
                            category_id=category_id,
                            confidence=node.get('confidence', 0.5)
                        )
                        round_new_edges += 1
                        stats['total_new_edges'] += 1

                        # 保存证据
                        self.db.save_evidence(
                            entity_id=node.get('entity_id'),
                            trade_edge_id=edge_id,
                            source_type='trade_evidence' if node.get('has_trade_record') else 'web_scrape',
                            source=f"network_expansion:{current_strategy}",
                            evidence=node.get('evidence', ''),
                            confidence=node.get('confidence', 0.5),
                            metadata={'task_id': task_id, 'round': round_num}
                        )
                        round_new_evidence += 1
                        stats['total_new_evidence'] += 1

                        # 记录扩张日志
                        self.db.log_expansion(
                            task_id=task_id,
                            round_num=round_num,
                            strategy=current_strategy,
                            discovered_entity_id=node.get('entity_id'),
                            discovered_norm=node_norm,
                            discovered_name=node.get('name', node_norm),
                            discovered_role=node_role,
                            relation_type=current_strategy,
                            from_entity_id=seed_entity_id,
                            evidence=node.get('evidence', ''),
                            confidence=node.get('confidence', 0.5),
                            category_id=category_id
                        )

                        # 新节点作为下一轮种子（深度控制）
                        if current_depth < max_depth:
                            pending_nodes.append((node_norm, current_depth + 1, current_norm))

                # 更新任务面板
                self.db.update_task(
                    task_id=task_id,
                    discovered_customers=stats['total_new_customers'],
                    discovered_suppliers=stats['total_new_suppliers'],
                    new_trade_edges=stats['total_new_edges'],
                    new_evidence=stats['total_new_evidence'],
                    current_node=current_norm,
                    progress_pct=min(100, round(len(processed_nodes) / max(1, len(processed_nodes) + len(pending_nodes)) * 100, 1))
                )

                # ===== v45 修复：实时广播可视化进度 =====
                try:
                    from core.webui.broadcaster import get_broadcaster
                    broadcaster = get_broadcaster()
                    broadcaster.emit('network_expansion_progress', {
                        'task_id': task_id,
                        'seed_norm': seed_norm,
                        'current_node': current_norm,
                        'current_round': round_num,
                        'current_depth': current_depth,
                        'current_strategy': current_strategy,
                        'strategy_name': self.EXPANSION_STRATEGIES.get(current_strategy, {}).get('name', current_strategy),
                        'processed_count': len(processed_nodes),
                        'pending_count': len(pending_nodes),
                        'new_this_round': {
                            'customers': round_new_customers,
                            'suppliers': round_new_suppliers,
                            'edges': round_new_edges,
                            'evidence': round_new_evidence
                        },
                        'totals': {
                            'customers': stats['total_new_customers'],
                            'suppliers': stats['total_new_suppliers'],
                            'edges': stats['total_new_edges'],
                            'evidence': stats['total_new_evidence']
                        },
                        'timestamp': time.time()
                    })
                    for node in discovered:
                        broadcaster.emit('network_expansion_node', {
                            'task_id': task_id,
                            'node_norm': node['norm'],
                            'node_name': node.get('name', node['norm']),
                            'node_role': node.get('role', 'unknown'),
                            'parent_norm': current_norm,
                            'strategy': current_strategy,
                            'evidence': node.get('evidence', ''),
                            'confidence': node.get('confidence', 0),
                            'depth': current_depth + 1,
                            'entered_pool': node.get('role') in ('customer', 'buyer', 'importer', 'supplier', 'shipper', 'exporter')
                        })
                except Exception:
                    pass

                # 评估停止条件
                remaining = len(pending_nodes)
                stop_eval = stop_condition.evaluate(
                    round_num=round_num,
                    current_strategy=current_strategy,
                    new_customers=round_new_customers,
                    new_suppliers=round_new_suppliers,
                    new_edges=round_new_edges,
                    new_evidence=round_new_evidence,
                    remaining_nodes=remaining
                )

                if stop_eval['action'] == 'switch_strategy':
                    current_strategy_index += 1
                elif stop_eval['should_stop']:
                    break

            # 扩张结束，生成最终报告
            final_report = stop_condition.get_final_report()

            self.db.update_task(
                task_id=task_id,
                run_status='completed',
                current_stage='completed',
                progress_pct=100,
                completed_at=time.time()
            )

            return {
                'ok': True,
                'task_id': task_id,
                'seed_norm': seed_norm,
                'seed_entity_id': seed_entity_id,
                'total_discovered': len(all_discovered),
                'total_new_customers': stats['total_new_customers'],
                'total_new_suppliers': stats['total_new_suppliers'],
                'total_new_edges': stats['total_new_edges'],
                'total_new_evidence': stats['total_new_evidence'],
                'total_rounds': round_num,
                'max_depth_reached': stats['current_depth'],
                'processed_nodes': list(processed_nodes),
                'pending_nodes': [n[0] for n in pending_nodes],
                'stop_reason': final_report.get('stop_reason'),
                'info_gain_curve': stop_condition.get_info_gain_curve(),
                'strategies_tried': final_report.get('strategies_tried', []),
                'strategies_exhausted': final_report.get('strategies_exhausted', []),
                'remaining_nodes': len(pending_nodes),
                'why_stopped': final_report.get('why_stopped'),
                'discovered': list(all_discovered.values())
            }

        except Exception as e:
            self.db.update_task(task_id, run_status='failed', failure_reason=str(e)[:500])
            return {'ok': False, 'error': str(e), 'task_id': task_id}

    def _execute_strategy(self, task_id: str, strategy: str, seed_norm: str,
                         seed_entity_id: str, parent_norm: str = None,
                         category_id: str = None, max_new_per_type: int = 5) -> List[dict]:
        """执行单个扩张策略。"""
        strategy_config = self.EXPANSION_STRATEGIES.get(strategy, {})
        discovered = []

        try:
            if strategy == 'customer_to_supplier':
                discovered = self._expand_customer_to_supplier(seed_norm, max_new_per_type, category_id)
            elif strategy == 'supplier_to_customer':
                discovered = self._expand_supplier_to_customer(seed_norm, max_new_per_type, category_id)
            elif strategy == 'same_supplier_new_customer':
                discovered = self._expand_same_supplier_new_customer(seed_norm, max_new_per_type, category_id)
            elif strategy == 'same_customer_new_supplier':
                discovered = self._expand_same_customer_new_supplier(seed_norm, max_new_per_type, category_id)
            elif strategy == 'same_product_customer':
                discovered = self._expand_same_product_customer(seed_norm, max_new_per_type, category_id)
            elif strategy == 'same_product_supplier':
                discovered = self._expand_same_product_supplier(seed_norm, max_new_per_type, category_id)
            elif strategy == 'trade_relation_reverse':
                discovered = self._expand_trade_relation_reverse(seed_norm, max_new_per_type, category_id)
            elif strategy == 'associated_enterprise':
                discovered = self._expand_associated_enterprise(seed_norm, max_new_per_type, category_id)
            elif strategy == 'brand_association':
                discovered = self._expand_brand_association(seed_norm, max_new_per_type, category_id)
            elif strategy == 'address_identity':
                discovered = self._expand_address_identity(seed_norm, max_new_per_type, category_id)
            elif strategy == 'public_web_association':
                discovered = self._expand_public_web_association(seed_norm, max_new_per_type, category_id)
            elif strategy == 'contact_organization':
                discovered = self._expand_contact_organization(seed_norm, max_new_per_type, category_id)
            else:
                discovered = []
        except Exception as e:
            # 策略失败不阻塞整体流程
            discovered = []

        return discovered[:max_new_per_type]

    def _expand_customer_to_supplier(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """客户→供应商：从海关数据找该客户的供应商。"""
        with self.db.c() as x:
            rows = x.execute(
                """SELECT DISTINCT shipper as name, shipper as norm, 
                   descr as product, hs, COUNT(*) as shipment_count
                   FROM customs_raw 
                   WHERE importer_norm=? 
                   GROUP BY shipper
                   ORDER BY shipment_count DESC
                   LIMIT ?""",
                (seed_norm, max_new)
            ).fetchall()

        return [self._node_from_trade_row(r, 'supplier', seed_norm) for r in rows]

    def _expand_supplier_to_customer(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """供应商→客户：从海关数据找该供应商的客户。"""
        with self.db.c() as x:
            rows = x.execute(
                """SELECT DISTINCT importer as name, importer_norm as norm,
                   descr as product, hs, COUNT(*) as shipment_count
                   FROM customs_raw 
                   WHERE shipper=? 
                   GROUP BY importer_norm
                   ORDER BY shipment_count DESC
                   LIMIT ?""",
                (seed_norm, max_new)
            ).fetchall()

        return [self._node_from_trade_row(r, 'customer', seed_norm) for r in rows]

    def _expand_same_supplier_new_customer(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """同供应商→新客户：找到与种子共享供应商的其他客户。"""
        with self.db.c() as x:
            # 先找种子的供应商
            suppliers = x.execute(
                "SELECT DISTINCT shipper FROM customs_raw WHERE importer_norm=?",
                (seed_norm,)
            ).fetchall()

            if not suppliers:
                return []

            supplier_list = [s[0] for s in suppliers[:10]]
            placeholders = ','.join(['?' for _ in supplier_list])
            rows = x.execute(
                f"""SELECT DISTINCT importer as name, importer_norm as norm,
                    descr as product, hs, COUNT(*) as shipment_count
                    FROM customs_raw 
                    WHERE shipper IN ({placeholders}) AND importer_norm != ?
                    GROUP BY importer_norm
                    ORDER BY shipment_count DESC
                    LIMIT ?""",
                supplier_list + [seed_norm, max_new]
            ).fetchall()

        return [self._node_from_trade_row(r, 'customer', seed_norm) for r in rows]

    def _expand_same_customer_new_supplier(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """同客户→新供应商：找到与种子共享客户的其他供应商。"""
        with self.db.c() as x:
            # 先找种子的客户
            customers = x.execute(
                "SELECT DISTINCT importer_norm FROM customs_raw WHERE shipper=?",
                (seed_norm,)
            ).fetchall()

            if not customers:
                return []

            customer_list = [c[0] for c in customers[:10]]
            placeholders = ','.join(['?' for _ in customer_list])
            rows = x.execute(
                f"""SELECT DISTINCT shipper as name, shipper as norm,
                    descr as product, hs, COUNT(*) as shipment_count
                    FROM customs_raw 
                    WHERE importer_norm IN ({placeholders}) AND shipper != ?
                    GROUP BY shipper
                    ORDER BY shipment_count DESC
                    LIMIT ?""",
                customer_list + [seed_norm, max_new]
            ).fetchall()

        return [self._node_from_trade_row(r, 'supplier', seed_norm) for r in rows]

    def _expand_same_product_customer(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """同产品→相关客户：找到采购同类产品的其他客户。"""
        with self.db.c() as x:
            # 找种子采购的产品HS
            hs_codes = x.execute(
                "SELECT DISTINCT hs FROM customs_raw WHERE importer_norm=? AND hs IS NOT NULL",
                (seed_norm,)
            ).fetchall()

            if not hs_codes:
                return []

            hs_list = [h[0] for h in hs_codes[:5]]
            placeholders = ','.join(['?' for _ in hs_list])
            rows = x.execute(
                f"""SELECT DISTINCT importer as name, importer_norm as norm,
                    descr as product, hs, COUNT(*) as shipment_count
                    FROM customs_raw 
                    WHERE hs IN ({placeholders}) AND importer_norm != ?
                    GROUP BY importer_norm
                    ORDER BY shipment_count DESC
                    LIMIT ?""",
                hs_list + [seed_norm, max_new]
            ).fetchall()

        return [self._node_from_trade_row(r, 'customer', seed_norm) for r in rows]

    def _expand_same_product_supplier(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """同产品→相关供应商：找到供应同类产品的其他供应商。"""
        with self.db.c() as x:
            hs_codes = x.execute(
                "SELECT DISTINCT hs FROM customs_raw WHERE shipper=? AND hs IS NOT NULL",
                (seed_norm,)
            ).fetchall()

            if not hs_codes:
                return []

            hs_list = [h[0] for h in hs_codes[:5]]
            placeholders = ','.join(['?' for _ in hs_list])
            rows = x.execute(
                f"""SELECT DISTINCT shipper as name, shipper as norm,
                    descr as product, hs, COUNT(*) as shipment_count
                    FROM customs_raw 
                    WHERE hs IN ({placeholders}) AND shipper != ?
                    GROUP BY shipper
                    ORDER BY shipment_count DESC
                    LIMIT ?""",
                hs_list + [seed_norm, max_new]
            ).fetchall()

        return [self._node_from_trade_row(r, 'supplier', seed_norm) for r in rows]

    def _expand_trade_relation_reverse(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """贸易关系反向扩张：反向追踪贸易链。"""
        with self.db.c() as x:
            # 如果种子是客户，找其供应商的供应商
            # 如果种子是供应商，找其客户的客户
            rows1 = x.execute(
                """SELECT shipper as name, shipper as norm, descr as product, hs, 
                   COUNT(*) as shipment_count FROM customs_raw 
                   WHERE importer_norm IN (
                       SELECT DISTINCT shipper FROM customs_raw WHERE importer_norm=?
                   ) AND shipper != ?
                   GROUP BY shipper ORDER BY shipment_count DESC LIMIT ?""",
                (seed_norm, seed_norm, max_new // 2)
            ).fetchall()

            rows2 = x.execute(
                """SELECT importer as name, importer_norm as norm, descr as product, hs,
                   COUNT(*) as shipment_count FROM customs_raw 
                   WHERE shipper IN (
                       SELECT DISTINCT importer_norm FROM customs_raw WHERE shipper=?
                   ) AND importer_norm != ?
                   GROUP BY importer_norm ORDER BY shipment_count DESC LIMIT ?""",
                (seed_norm, seed_norm, max_new // 2)
            ).fetchall()

        results = ([self._node_from_trade_row(r, 'supplier', seed_norm) for r in rows1] +
                   [self._node_from_trade_row(r, 'customer', seed_norm) for r in rows2])
        return results[:max_new]

    def _expand_associated_enterprise(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """关联企业扩张：通过集团、母公司、子公司关系。"""
        entity = self.db.get_entity(seed_norm)
        if not entity:
            return []

        # 使用AI推断关联企业
        prompt = f"""基于企业 "{entity.get('name', seed_norm)}" 的公开信息，
推断可能与其有关联关系的企业（母公司、子公司、兄弟公司、同一集团）。

已知信息：{json.dumps({k: entity.get(k) for k in ['name', 'country', 'website', 'address'] if entity.get(k)}, ensure_ascii=False)}

请输出JSON数组：
[{{"name": "公司名", "relation": "母公司/子公司/兄弟公司/同一集团", "confidence": "high/medium/low", "reasoning": "推断依据"}}]

最多返回{max_new}个。如果无法推断，返回空数组。"""

        result = ai_route(prompt=prompt, system="你是企业关联关系分析专家。")
        if result.get('ok') and result.get('structured'):
            nodes = result['structured'] if isinstance(result['structured'], list) else []
            return [self._node_from_ai_node(n, 'associated', seed_norm) for n in nodes[:max_new]]

        return []

    def _expand_brand_association(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """品牌关联：通过品牌找到相关企业。"""
        entity = self.db.get_entity(seed_norm)
        brand = entity.get('brand', '') if entity else ''

        if not brand:
            return []

        # 从数据库找同品牌企业
        with self.db.c() as x:
            rows = x.execute(
                """SELECT norm, name, role, products, source 
                   FROM trade_nodes 
                   WHERE norm != ? AND (products LIKE ? OR raw LIKE ?)
                   LIMIT ?""",
                (seed_norm, f'%${brand}%', f'%${brand}%', max_new)
            ).fetchall()

        return [self._node_from_db_row(r, 'brand', seed_norm) for r in rows]

    def _expand_address_identity(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """地址/企业身份关联：通过相同地址或注册信息关联。"""
        entity = self.db.get_entity(seed_norm)
        address = entity.get('address', '') if entity else ''
        country = entity.get('country', '') if entity else ''

        if not address:
            return []

        # 简化地址匹配（实际应使用更复杂的地址标准化）
        with self.db.c() as x:
            rows = x.execute(
                """SELECT norm, name, role, products, source 
                   FROM trade_nodes 
                   WHERE norm != ? AND country = ?
                   LIMIT ?""",
                (seed_norm, country, max_new)
            ).fetchall()

        return [self._node_from_db_row(r, 'address', seed_norm) for r in rows]

    def _expand_public_web_association(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """公开网页关联：通过公开网页信息找到关联企业。"""
        entity = self.db.get_entity(seed_norm)
        name = entity.get('name', seed_norm) if entity else seed_norm

        prompt = f"""基于公开网页信息，找到与 "{name}" 有业务往来或关联关系的企业。

请输出JSON数组：
[{{"name": "公司名", "relation": "客户/供应商/合作伙伴/竞争对手", "confidence": "high/medium/low", "source": "信息来源描述"}}]

最多返回{max_new}个。如果信息不足，返回空数组。"""

        result = ai_route(prompt=prompt, system="你是企业公开信息分析专家。")
        if result.get('ok') and result.get('structured'):
            nodes = result['structured'] if isinstance(result['structured'], list) else []
            return [self._node_from_ai_node(n, 'web', seed_norm) for n in nodes[:max_new]]

        return []

    def _expand_contact_organization(self, seed_norm: str, max_new: int, category_id: str = None) -> List[dict]:
        """联系人/组织关系扩张：通过联系人跳槽、组织关系找到新企业。"""
        entity = self.db.get_entity(seed_norm)
        entity_id = entity.get('entity_id') if entity else None

        if not entity_id:
            return []

        contacts = self.db.list_entity_contacts(entity_id)
        if not contacts:
            return []

        # 基于联系人信息推断关联企业
        contact_names = [c.get('name', '') for c in contacts[:3] if c.get('name')]
        if not contact_names:
            return []

        prompt = f"""基于以下联系人在 "{entity.get('name', seed_norm)}" 任职的信息，
推断他们可能还关联的其他企业（如前雇主、兼职公司、关联组织）。

联系人：{', '.join(contact_names)}

请输出JSON数组：
[{{"name": "公司名", "relation": "前雇主/兼职/关联组织", "contact": "关联联系人", "confidence": "high/medium/low"}}]

最多返回{max_new}个。如果无法推断，返回空数组。"""

        result = ai_route(prompt=prompt, system="你是企业组织关系分析专家。")
        if result.get('ok') and result.get('structured'):
            nodes = result['structured'] if isinstance(result['structured'], list) else []
            return [self._node_from_ai_node(n, 'contact', seed_norm) for n in nodes[:max_new]]

        return []

    # ========== 节点转换辅助方法 ==========

    def _node_from_trade_row(self, row, role: str, parent_norm: str) -> dict:
        """从海关数据行转换为统一节点格式。"""
        if isinstance(row, sqlite3.Row):
            row = dict(row)
        else:
            row = {
                'name': row[0], 'norm': row[1], 'product': row[2],
                'hs': row[3], 'shipment_count': row[4]
            }

        norm = row.get('norm', row.get('name', ''))
        # 创建或获取统一实体
        entity = self.db.get_or_create_entity(norm=norm, name=row.get('name'))

        return {
            'norm': norm,
            'name': row.get('name', norm),
            'role': role,
            'entity_id': entity.get('entity_id'),
            'product': row.get('product', ''),
            'hs_code': row.get('hs', ''),
            'shipment_count': row.get('shipment_count', 0),
            'has_trade_record': True,
            'confidence': 0.8,
            'evidence': f"Trade record: {row.get('shipment_count', 0)} shipments",
            'parent_norm': parent_norm,
            'source': 'customs_data'
        }

    def _node_from_ai_node(self, node: dict, relation_type: str, parent_norm: str) -> dict:
        """从AI推断结果转换为统一节点格式。"""
        name = node.get('name', '')
        norm = name.lower().replace(' ', '_')[:50] if name else f"unk-{uuid.uuid4().hex[:8]}"
        entity = self.db.get_or_create_entity(norm=norm, name=name)

        return {
            'norm': norm,
            'name': name,
            'role': node.get('relation', 'unknown').lower().replace('客户', 'customer').replace('供应商', 'supplier'),
            'entity_id': entity.get('entity_id'),
            'product': '',
            'hs_code': '',
            'shipment_count': 0,
            'has_trade_record': False,
            'confidence': 0.5 if node.get('confidence') == 'medium' else (0.8 if node.get('confidence') == 'high' else 0.3),
            'evidence': node.get('reasoning', '') or node.get('source', ''),
            'parent_norm': parent_norm,
            'source': 'ai_inference'
        }

    def _node_from_db_row(self, row, relation_type: str, parent_norm: str) -> dict:
        """从数据库行转换为统一节点格式。"""
        if isinstance(row, sqlite3.Row):
            row = dict(row)
        else:
            row = {
                'norm': row[0], 'name': row[1], 'role': row[2],
                'products': row[3], 'source': row[4]
            }

        norm = row.get('norm', '')
        name = row.get('name', norm)
        entity = self.db.get_or_create_entity(norm=norm, name=name)

        return {
            'norm': norm,
            'name': name,
            'role': row.get('role', 'unknown'),
            'entity_id': entity.get('entity_id'),
            'product': row.get('products', ''),
            'hs_code': '',
            'shipment_count': 0,
            'has_trade_record': True,
            'confidence': 0.6,
            'evidence': f"Found in database: {row.get('source', '')}",
            'parent_norm': parent_norm,
            'source': 'database'
        }

    def _add_to_pool(self, node: dict, pool_type: str, category_id: str = None, task_id: str = None):
        """将新节点添加到对应资源池。"""
        entity_id = node.get('entity_id')
        norm = node.get('norm')

        if not entity_id:
            return

        # 设置角色
        self.db.set_entity_role(
            entity_id=entity_id,
            role=pool_type,
            trade_count=node.get('shipment_count', 0)
        )

        # 设置品类
        if category_id:
            self.db.set_entity_category(
                entity_id=entity_id,
                category_id=category_id
            )

        # 记录生命周期转换
        current_state = self.db.get_current_lifecycle_state(entity_id)
        if current_state == 'DISCOVERED':
            self.db.transition_lifecycle(
                entity_id=entity_id,
                from_state='DISCOVERED',
                to_state='TRADE_CONFIRMED',
                reason=f'Network expansion discovered via {node.get("source", "unknown")}',
                actor='network_expansion_engine',
                metadata={'task_id': task_id, 'parent_norm': node.get('parent_norm')}
            )

        # 标记为待补全
        self.db.transition_lifecycle(
            entity_id=entity_id,
            from_state=self.db.get_current_lifecycle_state(entity_id),
            to_state='ENRICHING',
            reason='Auto-enqueued for waterfall enrichment',
            actor='network_expansion_engine',
            metadata={'task_id': task_id}
        )

        # ===== v45 修复：自动触发情报补全闭环 =====
        try:
            from core.intelligence.waterfall import enrich_entity
            entity_id_val = node.get('entity_id')
            if entity_id_val:
                import threading
                def _auto_enrich():
                    try:
                        result = enrich_entity(
                            entity_id=entity_id_val,
                            norm=norm,
                            category_id=category_id,
                            task_id=task_id
                        )
                        from core.webui.broadcaster import get_broadcaster
                        get_broadcaster().emit('auto_enrich_complete', {
                            'task_id': task_id,
                            'norm': norm,
                            'entity_id': entity_id_val,
                            'filled_count': len(result.get('filled', {})),
                            'completeness_after': result.get('completeness_after', 0)
                        })
                    except Exception as e:
                        self.db.save_task_log(task_id, 'auto_enrich_failed', str(e)[:200])
                threading.Thread(target=_auto_enrich, daemon=True).start()
        except Exception:
            pass

    def get_expansion_visualization(self, task_id: str) -> dict:
        """获取网络扩张的可视化数据。"""
        logs = self.db.get_expansion_log(task_id)
        gain_curve = self.db.get_info_gain_curve(task_id)
        task = self.db.get_task(task_id)

        # 构建节点和边
        nodes = {}
        edges = []

        for log in logs:
            discovered_norm = log.get('discovered_norm')
            discovered_name = log.get('discovered_name')
            from_entity = log.get('from_entity_id')

            if discovered_norm and discovered_norm not in nodes:
                nodes[discovered_norm] = {
                    'id': discovered_norm,
                    'name': discovered_name or discovered_norm,
                    'role': log.get('discovered_role', 'unknown'),
                    'round': log.get('round_num'),
                    'is_enriched': bool(log.get('is_enriched')),
                    'confidence': log.get('confidence', 0)
                }

            if from_entity and discovered_norm:
                edges.append({
                    'from': from_entity,
                    'to': discovered_norm,
                    'relation': log.get('relation_type'),
                    'round': log.get('round_num')
                })

        return {
            'task_id': task_id,
            'status': task.get('run_status') if task else 'unknown',
            'nodes': list(nodes.values()),
            'edges': edges,
            'gain_curve': gain_curve,
            'total_discovered': len(nodes),
            'total_edges': len(edges)
        }


# ========== 便捷函数 ==========
_engine = None

def get_engine() -> NetworkExpansionEngine:
    global _engine
    if _engine is None:
        _engine = NetworkExpansionEngine()
    return _engine

def expand_network(seed_norm: str, category_id: str = None,
                  expansion_types: List[str] = None,
                  max_depth: int = 5, max_new: int = 50,
                  task_id: str = None) -> dict:
    return get_engine().expand(seed_norm, category_id, expansion_types, max_depth, max_new, task_id)

def get_expansion_visualization(task_id: str) -> dict:
    return get_engine().get_expansion_visualization(task_id)
