# -*- coding: utf-8 -*-
"""STOP_CONDITION v45：动态信息增益停止机制。

核心原则：
1. 【信息增益优先于固定时间】
2. 禁止运行固定时间直接停止
3. 第一策略收益下降 → 切换第二策略
4. 第二策略收益下降 → 切换第三策略
5. 连续多个不同扩张策略均无法产生有价值的新信息 → 达到收敛条件 → 正常结束
6. 必须保留：停止原因、最后一轮结果、信息增益曲线、还有哪些未处理节点、为什么没有继续

停止条件层次：
- 最小执行时间：保证至少运行一段时间
- 建议执行时间：参考值
- 最大安全时间：防止死循环
- 信息增益收敛：主要停止条件
"""

import time
from typing import Dict, List, Any
from dataclasses import dataclass, field
from core.memory.db import DB


@dataclass
class StrategyResult:
    """单个策略的执行结果。"""
    strategy_name: str
    round_num: int
    new_customers: int = 0
    new_suppliers: int = 0
    new_edges: int = 0
    new_evidence: int = 0
    new_contacts: int = 0
    new_valid_emails: int = 0
    new_high_value_nodes: int = 0
    total_gain: int = 0
    execution_time: float = 0.0
    timestamp: float = 0.0


@dataclass
class RoundSummary:
    """单轮扩张的汇总结果。"""
    round_num: int
    strategy: str
    results: List[StrategyResult] = field(default_factory=list)
    total_new_customers: int = 0
    total_new_suppliers: int = 0
    total_new_edges: int = 0
    total_new_evidence: int = 0
    total_new_contacts: int = 0
    total_new_valid_emails: int = 0
    total_new_high_value_nodes: int = 0
    total_gain: int = 0
    timestamp: float = 0.0


class DynamicStopCondition:
    """动态信息增益停止条件。

    配置参数：
    - min_execution_time: 最小执行时间（秒），默认60
    - suggested_time: 建议执行时间（秒），默认300
    - max_safety_time: 最大安全时间（秒），默认1800
    - strategy_switch_threshold: 策略切换阈值（连续几轮下降即切换），默认2
    - convergence_patience: 收敛耐心（连续几个不同策略无增益才停止），默认3
    - min_gain_per_round: 每轮最小有效增益，默认1
    """

    STRATEGIES = [
        'customer_to_supplier',      # 客户→供应商
        'supplier_to_customer',      # 供应商→客户
        'same_supplier_new_customer', # 同供应商→新客户
        'same_customer_new_supplier', # 同客户→新供应商
        'same_product_customer',      # 同产品→相关客户
        'same_product_supplier',      # 同产品→相关供应商
        'trade_relation_reverse',     # 贸易关系反向扩张
        'associated_enterprise',      # 关联企业扩张
        'brand_association',          # 品牌关联
        'address_identity',           # 地址/企业身份关联
        'public_web_association',     # 公开网页关联
        'contact_organization',       # 联系人/组织关系扩张
    ]

    def __init__(self, task_id: str = None, 
                 min_execution_time: int = 60,
                 suggested_time: int = 300,
                 max_safety_time: int = 1800,
                 strategy_switch_threshold: int = 2,
                 convergence_patience: int = 3,
                 min_gain_per_round: int = 1):
        self.task_id = task_id
        self.min_execution_time = min_execution_time
        self.suggested_time = suggested_time
        self.max_safety_time = max_safety_time
        self.strategy_switch_threshold = strategy_switch_threshold
        self.convergence_patience = convergence_patience
        self.min_gain_per_round = min_gain_per_round

        self.start_time = time.time()
        self.rounds: List[RoundSummary] = []
        self.current_strategy_index = 0
        self.strategy_history: List[str] = []
        self.consecutive_no_gain_strategies: set = set()
        self.stopped = False
        self.stop_reason = None
        self.remaining_nodes = 0
        self.db = DB()

    def evaluate(self, round_num: int, current_strategy: str,
                new_customers: int = 0, new_suppliers: int = 0,
                new_edges: int = 0, new_evidence: int = 0,
                new_contacts: int = 0, new_valid_emails: int = 0,
                new_high_value_nodes: int = 0,
                remaining_nodes: int = 0) -> Dict[str, Any]:
        """评估当前轮次是否应该停止。

        返回：{
            'should_stop': bool,
            'stop_reason': str,
            'action': 'continue' | 'switch_strategy' | 'stop',
            'next_strategy': str | None,
            'info_gain': dict,
            'stats': dict
        }
        """
        elapsed = time.time() - self.start_time
        self.remaining_nodes = remaining_nodes

        # 计算总增益
        total_gain = (new_customers + new_suppliers + new_edges + 
                     new_evidence + new_contacts + new_valid_emails + 
                     new_high_value_nodes)

        # 记录本轮结果
        round_summary = RoundSummary(
            round_num=round_num,
            strategy=current_strategy,
            total_new_customers=new_customers,
            total_new_suppliers=new_suppliers,
            total_new_edges=new_edges,
            total_new_evidence=new_evidence,
            total_new_contacts=new_contacts,
            total_new_valid_emails=new_valid_emails,
            total_new_high_value_nodes=new_high_value_nodes,
            total_gain=total_gain,
            timestamp=time.time()
        )
        self.rounds.append(round_summary)
        self.strategy_history.append(current_strategy)

        # 记录到数据库
        if self.task_id:
            self.db.record_info_gain(
                task_id=self.task_id,
                round_num=round_num,
                strategy=current_strategy,
                new_customers=new_customers,
                new_suppliers=new_suppliers,
                new_edges=new_edges,
                new_evidence=new_evidence,
                new_contacts=new_contacts,
                new_valid_emails=new_valid_emails,
                new_high_value_nodes=new_high_value_nodes,
                total_gain=total_gain,
                remaining_nodes=remaining_nodes
            )

        # ========== 第一层：最小执行时间保护 ==========
        if elapsed < self.min_execution_time:
            return {
                'should_stop': False,
                'stop_reason': f'Minimum execution time not reached ({elapsed:.0f}s < {self.min_execution_time}s)',
                'action': 'continue',
                'next_strategy': current_strategy,
                'info_gain': self._build_info_gain(round_summary),
                'stats': self._build_stats(elapsed)
            }

        # ========== 第二层：最大安全时间保护 ==========
        if elapsed >= self.max_safety_time:
            self.stopped = True
            self.stop_reason = f'Maximum safety time reached ({elapsed:.0f}s >= {self.max_safety_time}s)'
            return {
                'should_stop': True,
                'stop_reason': self.stop_reason,
                'action': 'stop',
                'next_strategy': None,
                'info_gain': self._build_info_gain(round_summary),
                'stats': self._build_stats(elapsed)
            }

        # ========== 第三层：信息增益判断 ==========

        # 3.1 当前策略是否有增益？
        has_gain = total_gain >= self.min_gain_per_round

        if has_gain:
            # 有增益，重置该策略的无增益计数
            self.consecutive_no_gain_strategies.discard(current_strategy)

            # 检查增益是否下降
            recent_same_strategy = [r for r in self.rounds[-5:] if r.strategy == current_strategy]
            if len(recent_same_strategy) >= self.strategy_switch_threshold:
                # 检查最近几轮同策略的增益趋势
                gains = [r.total_gain for r in recent_same_strategy[-self.strategy_switch_threshold:]]
                if len(gains) >= 2 and all(gains[i] >= gains[i+1] for i in range(len(gains)-1)) and gains[-1] < gains[0] * 0.5:
                    # 增益持续下降，建议切换策略
                    next_strategy = self._get_next_strategy()
                    return {
                        'should_stop': False,
                        'stop_reason': f'Gain decreasing under {current_strategy}: {gains}',
                        'action': 'switch_strategy',
                        'next_strategy': next_strategy,
                        'info_gain': self._build_info_gain(round_summary),
                        'stats': self._build_stats(elapsed)
                    }

            # 有增益且不下降，继续当前策略
            return {
                'should_stop': False,
                'stop_reason': None,
                'action': 'continue',
                'next_strategy': current_strategy,
                'info_gain': self._build_info_gain(round_summary),
                'stats': self._build_stats(elapsed)
            }

        # 3.2 无增益，标记该策略
        self.consecutive_no_gain_strategies.add(current_strategy)

        # 检查是否还有未尝试的策略
        available_strategies = [s for s in self.STRATEGIES if s not in self.consecutive_no_gain_strategies]

        if available_strategies:
            # 还有可用策略，切换
            next_strategy = available_strategies[0]
            return {
                'should_stop': False,
                'stop_reason': f'No gain from {current_strategy}, switching to {next_strategy}',
                'action': 'switch_strategy',
                'next_strategy': next_strategy,
                'info_gain': self._build_info_gain(round_summary),
                'stats': self._build_stats(elapsed)
            }

        # 3.3 所有策略都无增益 → 达到收敛条件
        self.stopped = True
        self.stop_reason = (
            f'Convergence reached: All {len(self.STRATEGIES)} strategies produced '
            f'no meaningful gain for consecutive rounds. '
            f'Total rounds: {len(self.rounds)}, '
            f'Elapsed: {elapsed:.0f}s, '
            f'Remaining nodes: {remaining_nodes}'
        )

        # 更新数据库中的停止原因
        if self.task_id and self.rounds:
            last_round = self.rounds[-1]
            self.db.record_info_gain(
                task_id=self.task_id,
                round_num=last_round.round_num,
                strategy=last_round.strategy,
                stop_reason=self.stop_reason,
                remaining_nodes=remaining_nodes
            )

        return {
            'should_stop': True,
            'stop_reason': self.stop_reason,
            'action': 'stop',
            'next_strategy': None,
            'info_gain': self._build_info_gain(round_summary),
            'stats': self._build_stats(elapsed)
        }

    def _get_next_strategy(self) -> str:
        """获取下一个策略。"""
        available = [s for s in self.STRATEGIES if s not in self.consecutive_no_gain_strategies]
        if available:
            return available[0]
        return self.STRATEGIES[0]  # 全部失败后回退到第一个

    def _build_info_gain(self, round_summary: RoundSummary) -> dict:
        """构建信息增益详情。"""
        return {
            'round': round_summary.round_num,
            'strategy': round_summary.strategy,
            'new_customers': round_summary.total_new_customers,
            'new_suppliers': round_summary.total_new_suppliers,
            'new_edges': round_summary.total_new_edges,
            'new_evidence': round_summary.total_new_evidence,
            'new_contacts': round_summary.total_new_contacts,
            'new_valid_emails': round_summary.total_new_valid_emails,
            'new_high_value_nodes': round_summary.total_new_high_value_nodes,
            'total_gain': round_summary.total_gain,
            'timestamp': round_summary.timestamp
        }

    def _build_stats(self, elapsed: float) -> dict:
        """构建统计信息。"""
        total_customers = sum(r.total_new_customers for r in self.rounds)
        total_suppliers = sum(r.total_new_suppliers for r in self.rounds)
        total_edges = sum(r.total_new_edges for r in self.rounds)
        total_evidence = sum(r.total_new_evidence for r in self.rounds)

        return {
            'elapsed_seconds': round(elapsed, 1),
            'total_rounds': len(self.rounds),
            'total_customers': total_customers,
            'total_suppliers': total_suppliers,
            'total_edges': total_edges,
            'total_evidence': total_evidence,
            'strategies_tried': list(set(self.strategy_history)),
            'strategies_exhausted': list(self.consecutive_no_gain_strategies),
            'remaining_nodes': self.remaining_nodes,
            'min_time': self.min_execution_time,
            'suggested_time': self.suggested_time,
            'max_time': self.max_safety_time,
        }

    def get_info_gain_curve(self) -> List[dict]:
        """获取完整的信息增益曲线。"""
        return [
            {
                'round': r.round_num,
                'strategy': r.strategy,
                'total_gain': r.total_gain,
                'new_customers': r.total_new_customers,
                'new_suppliers': r.total_new_suppliers,
                'new_edges': r.total_new_edges,
                'timestamp': r.timestamp
            }
            for r in self.rounds
        ]

    def get_final_report(self) -> dict:
        """获取最终停止报告。"""
        elapsed = time.time() - self.start_time
        return {
            'stopped': self.stopped,
            'stop_reason': self.stop_reason,
            'total_rounds': len(self.rounds),
            'total_elapsed': round(elapsed, 1),
            'info_gain_curve': self.get_info_gain_curve(),
            'last_round': self._build_info_gain(self.rounds[-1]) if self.rounds else None,
            'remaining_nodes': self.remaining_nodes,
            'strategies_tried': list(set(self.strategy_history)),
            'strategies_exhausted': list(self.consecutive_no_gain_strategies),
            'why_stopped': (
                'All expansion strategies converged with no meaningful information gain. '
                'The system tried multiple strategies and none produced new valuable nodes. '
                f'Remaining {self.remaining_nodes} nodes were queued but not processed '
                'due to convergence criteria.'
            )
        }


# ========== 便捷函数 ==========

def create_stop_condition(task_id: str = None, **kwargs) -> DynamicStopCondition:
    return DynamicStopCondition(task_id=task_id, **kwargs)
