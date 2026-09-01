import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from core.tools.data_sources.manager import identity_valid,hard_evidence,norm
from core.runtime import graph

def test_identity_only_is_kept():
    assert identity_valid({'name':'ABC Importer LLC','type':'importer','evidence':{}})
    assert not identity_valid({'name':'ABC Logistics','type':'lead','evidence':{}})

def test_graph_contains_clean_gates_and_harvest():
    # v31.0：旧 Lead Generation 节点已重组为 Trade Graph Pipeline；
    # 渗透/清洗/收割能力分别并入 CUSTOMS_NODE_COLLECTION / ENTITY_RESOLUTION /
    # GRAPH_EXPANSION / RESOURCE_CLASSIFICATION，职责不丢、节点更少。
    expected=['PRODUCT_DEFINITION','TRADE_STRATEGY','CUSTOMS_NODE_COLLECTION','TRADE_EDGE_BUILD',
              'EVIDENCE_VERIFY','ENTITY_RESOLUTION','GRAPH_EXPANSION','RESOURCE_CLASSIFICATION','DATABASE_COMMIT']
    for x in expected: assert x in graph.ORDER

def test_hard_evidence():
    assert hard_evidence({'evidence':{'shipments':3}})
    assert not hard_evidence({'evidence':{}})

def test_norm():
    assert norm('ABC, Inc.')=='abc'
