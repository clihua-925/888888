import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from core.runtime import nodes

def test_identity_only_policy():
    c={'name':'Buyer Only Name','type':'importer','evidence':{}}
    assert nodes.identity_valid(c)

def test_non_customer_is_not_identity_valid():
    c={'name':'Buyer Logistics','type':'lead','evidence':{}}
    assert not nodes.identity_valid(c)
