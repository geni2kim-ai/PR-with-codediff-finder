from __future__ import annotations
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('tdc',ROOT/'vendor/TextDiffChecker_v1.4.6-harness.1/checker.py');tdc=importlib.util.module_from_spec(spec);spec.loader.exec_module(tdc)
def cost(ops):return sum((i2-i1)+(j2-j1) for tag,i1,i2,j1,j2 in ops if tag!='equal')
a=['A']*1000+['B']*1000+['A']*1000
rot=a[500:]+a[:500]
b=[('C' if i%2==0 and i<2600 else x) for i,x in enumerate(rot)]
_,s,ops,tr=tdc.diff_texts_with_trace(a,b,'a','b')
_,sx,opsx,trx=tdc.diff_texts_with_trace(a,b,'a','b',exact=True)
assert s['quality_class']=='HEURISTIC',s
assert sx['quality_class']=='PROVEN_EXACT',sx
assert cost(ops)>cost(opsx),(cost(ops),cost(opsx))
print({'default_cost':cost(ops),'exact_cost':cost(opsx),'default_quality':s['quality_class'],'exact_quality':sx['quality_class'],'default_path':tr['algorithm_path'],'exact_path':trx['algorithm_path']})
