from __future__ import annotations

def choose_queue(reasons,labels=None,rsi=None,failure_families=None):
    reasons=set(reasons or []);labels=set(labels or []);families=set(failure_families or [])
    if 'governance' in labels or any('GOVERNANCE' in x for x in reasons):return 'governance'
    if {'SECURITY-CRITICAL','DATA-CORRUPTION'} & families or any(x in reasons for x in {'CRITICAL','POST_MERGE_INCIDENT'}):return 'critical'
    if any('L1_L2_DISAGREEMENT' in x for x in reasons):return 'disagreement'
    if any('NOVEL' in x for x in reasons) or 'novel_failure_family' in labels:return 'novel-pattern'
    if any('LOW_CONFIDENCE' in x for x in reasons):return 'low-confidence'
    if rsi and rsi.get('promotion',{}).get('adversarial_required'):return 'rsi-followup'
    if any('RSI_ADVERSARIAL_REQUIRED' in x for x in reasons):return 'rsi-followup'
    return 'random-audit'
