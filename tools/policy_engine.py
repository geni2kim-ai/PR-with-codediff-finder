from __future__ import annotations
import fnmatch, subprocess
from pathlib import Path, PurePosixPath
import yaml

LEVELS = ["L1", "L2", "ADVERSARIAL", "HUMAN"]


def normalize_repo_path(path: str) -> str:
    """Normalize a path only for policy matching.

    Git object lookup must use Git's exact path. This helper intentionally treats a
    backslash as a policy separator so Windows-style spellings cannot evade protected
    path rules, but the normalized value must never be fed back into Git.
    """
    p=str(path).replace('\\','/')
    while p.startswith('./'):
        p=p[2:]
    p=p.lstrip('/')
    parts=PurePosixPath(p).parts
    if any(x in {'','..'} for x in parts):
        raise ValueError(f'unsafe repository path: {path!r}')
    return '/'.join(parts)


def _match(path: str, pattern: str) -> bool:
    """Case-insensitive repository glob with segment-anywhere semantics."""
    p=normalize_repo_path(path).casefold()
    raw=str(pattern).replace('\\','/')
    anchored=raw.startswith('/')
    while raw.startswith('./'):
        raw=raw[2:]
    pat=raw.lstrip('/').casefold()
    candidates=[p]
    if not anchored:
        parts=p.split('/')
        candidates += ['/'.join(parts[i:]) for i in range(1,len(parts))]
    return any(fnmatch.fnmatchcase(c,pat) for c in candidates)


def load_yaml(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f)



def _git_tree_has(repo_path, ref, relpath):
    try:
        cp=subprocess.run(
            ['git','-C',str(Path(repo_path).resolve()),'cat-file','-e',f'{ref}:{relpath}'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5
        )
        return cp.returncode==0
    except Exception:
        return False


def is_self_protected_repository(repository: str | None = None, repo_path=None, protected_cfg=None, base_ref=None) -> bool:
    """Identify this harness from immutable/base evidence when available.

    The proposed HEAD may delete a sentinel.  A deletion must not be able to turn off
    self-protection, so callers reviewing a Git change should pass the trusted
    merge-base/base commit here.
    """
    cfg = protected_cfg or {}
    names = {str(x).casefold() for x in cfg.get('self_protection_repository_names', [])}
    if repository and str(repository).casefold() in names:
        return True
    if repo_path and base_ref:
        return (
            _git_tree_has(repo_path,base_ref,'tools/run_review_cycle.py') and
            _git_tree_has(repo_path,base_ref,'policy/protected-paths.yml')
        )
    if repo_path:
        root = Path(repo_path)
        return (root / 'tools/run_review_cycle.py').is_file() and (root / 'policy/protected-paths.yml').is_file()
    return False

def classify_paths(changed_paths, protected_cfg, *, include_self_protection=False):
    out = {"governance":[], "human_floor":[], "adversarial_floor":[], "supply_chain":[]}
    mappings = [("governance","governance_paths"),("human_floor","human_floor_paths"),("adversarial_floor","adversarial_floor_paths"),("supply_chain","supply_chain_files")]
    if include_self_protection:
        mappings += [("governance","self_protection_paths"),("human_floor","self_protection_paths"),("adversarial_floor","self_protection_adversarial_paths")]
    for original in changed_paths:
        path=normalize_repo_path(original)
        for dst, key in mappings:
            if any(_match(path, pat) for pat in protected_cfg.get(key, [])):
                out[dst].append(path)
    return {k:sorted(set(v)) for k,v in out.items()}


def matrix_human_required(reversibility, blast_radius):
    if reversibility == "HARD": return True
    if reversibility == "MODERATE" and blast_radius != "LOCAL": return True
    if reversibility == "EASY" and blast_radius in {"MULTI_SERVICE","EXTERNAL"}: return True
    return False


def derive_risk(model, path_hits):
    reasons=[]
    matrix = matrix_human_required(model["reversibility"], model["blast_radius"])
    if path_hits["human_floor"]: reasons.append("protected_path_human_floor")
    if model["data_sensitivity"] in {"PII","SECRET"}: reasons.append("data_sensitivity")
    if model["security_surface"] in {"HIGH","CRITICAL"}: reasons.append("security_surface")
    if model["availability_criticality"] == "CRITICAL": reasons.append("availability_criticality")
    governance = bool(path_hits["governance"])
    if governance: reasons.append("governance_change")
    floor = bool(reasons)
    return {
      "governance_path_hits":path_hits["governance"],
      "human_floor_path_hits":path_hits["human_floor"],
      "adversarial_floor_path_hits":path_hits["adversarial_floor"],
      "supply_chain_path_hits":path_hits["supply_chain"],
      "governance_change":governance,
      "matrix_human_review_required":matrix,
      "floor_human_review_required":floor,
      "human_review_required":matrix or floor,
      "floor_reasons":reasons
    }


def max_level(a,b): return LEVELS[max(LEVELS.index(a), LEVELS.index(b))]


def active_escalation_signals(model, path_hits, signals):
    active=set()
    if signals.get('reviewer_confidence') in {'low','medium'}: active.add('reviewer_confidence_low_or_medium')
    if signals.get('major_candidate'): active.add('major_candidate')
    if model['reversibility']=='MODERATE': active.add('moderate_reversibility')
    if model['blast_radius']!='LOCAL': active.add('service_or_larger_blast_radius')
    if signals.get('soft_large_diff'): active.add('soft_large_diff')
    if path_hits['human_floor']: active.add('protected_path_human_floor')
    if signals.get('test_integrity_finding'): active.add('test_integrity_finding')
    if path_hits['supply_chain']: active.add('supply_chain_change')
    if signals.get('l1_l2_disagreement'): active.add('l1_l2_disagreement')
    if signals.get('novel_failure_family'): active.add('novel_failure_family')
    if signals.get('deterministic_reviewer_conflict'): active.add('deterministic_reviewer_conflict')
    if signals.get('blocker_candidate'): active.add('blocker_candidate')
    if model['security_surface'] in {'HIGH','CRITICAL'}: active.add('security_surface_high_or_critical')
    if path_hits['adversarial_floor']: active.add('protected_path_adversarial_floor')
    if signals.get('spec_changed_after_open'): active.add('unexplained_spec_change_after_pr_open')
    if signals.get('reviewer_policy_tampering'): active.add('reviewer_policy_tampering')
    if path_hits['governance']: active.add('governance_change')
    if model['reversibility']=='HARD': active.add('hard_reversibility')
    if model['data_sensitivity'] in {'PII','SECRET'}: active.add('data_sensitivity_pii_or_secret')
    if model['availability_criticality']=='CRITICAL': active.add('availability_critical')
    if signals.get('destructive_migration'): active.add('destructive_migration')
    if signals.get('public_contract_break'): active.add('public_contract_break')
    if signals.get('payment_external_side_effect'): active.add('payment_or_irreversible_external_side_effect')
    if signals.get('ruleset_codeowners_change'): active.add('ruleset_or_codeowners_change')
    if signals.get('adversarial_unresolved'): active.add('adversarial_unresolved')
    if signals.get('sensor_runtime_untrusted'): active.add('runtime_untrusted')
    if signals.get('encoding_low_confidence'): active.add('encoding_low_confidence')
    if signals.get('sensor_approximate'): active.add('approximate_result')
    if signals.get('sensor_failed_invariant'): active.add('failed_invariant')
    if signals.get('diff_false_exact'): active.add('diff_false_exact')
    if signals.get('sensor_runtime_untrusted_on_protected'): active.add('runtime_untrusted_on_protected_path')
    if signals.get('sensor_nontext_sensitive'): active.add('nontext_sensitive_change')
    if signals.get('sensor_heuristic_high_risk'):
        if path_hits['adversarial_floor']:active.add('adversarial_protected_path')
        if path_hits['human_floor']:active.add('human_protected_path')
        if model['security_surface'] in {'HIGH','CRITICAL'}:active.add('security_high_or_critical')
        if signals.get('destructive_migration'):active.add('destructive_migration')
        if path_hits['governance']:active.add('governance_change')
        if signals.get('soft_large_diff') or signals.get('hard_large_diff'):active.add('large_diff')
    return active


def derive_required_level(model, path_hits, signals, escalation_cfg=None, sensor_cfg=None):
    if escalation_cfg is None:
        escalation_cfg={
          'L2_if_any':['reviewer_confidence_low_or_medium','major_candidate','moderate_reversibility','service_or_larger_blast_radius','soft_large_diff','protected_path_human_floor','test_integrity_finding','supply_chain_change'],
          'ADVERSARIAL_if_any':['l1_l2_disagreement','novel_failure_family','deterministic_reviewer_conflict','blocker_candidate','security_surface_high_or_critical','protected_path_adversarial_floor','unexplained_spec_change_after_pr_open','reviewer_policy_tampering'],
          'HUMAN_if_any':['governance_change','hard_reversibility','data_sensitivity_pii_or_secret','availability_critical','destructive_migration','public_contract_break','payment_or_irreversible_external_side_effect','ruleset_or_codeowners_change','adversarial_unresolved']
        }
    if sensor_cfg is None:
        sensor_cfg={'textdiff':{'l2_if_any':['runtime_untrusted','encoding_low_confidence','approximate_result'],'adversarial_if_any':['failed_invariant','diff_false_exact','runtime_untrusted_on_protected_path','nontext_sensitive_change']}}
    active=active_escalation_signals(model,path_hits,signals)
    level='L1';reasons=[]
    l2=set(escalation_cfg.get('L2_if_any',[]))|set(sensor_cfg.get('textdiff',{}).get('l2_if_any',[]))
    tdc=sensor_cfg.get('textdiff',{})
    adv=set(escalation_cfg.get('ADVERSARIAL_if_any',[]))|set(tdc.get('adversarial_if_any',[]))
    if signals.get('sensor_heuristic_high_risk'):
        adv |= set(tdc.get('adversarial_if_heuristic_and_any',[]))
    human=set(escalation_cfg.get('HUMAN_if_any',[]))
    if active & l2:
        level='L2';reasons.extend('L2:'+x for x in sorted(active & l2))
    if active & adv:
        level=max_level(level,'ADVERSARIAL');reasons.extend('ADVERSARIAL:'+x for x in sorted(active & adv))
    if active & human:
        level='HUMAN';reasons.extend('HUMAN:'+x for x in sorted(active & human))
    # Hard authority floor: configuration may add escalation but may not lower a HUMAN
    # requirement implied by protected paths or the deterministic risk matrix.
    risk=derive_risk(model,path_hits)
    if risk['human_review_required']:
        level='HUMAN'
        reasons.extend('HUMAN_FLOOR:'+x for x in risk['floor_reasons'])
        if risk['matrix_human_review_required']:reasons.append('HUMAN_FLOOR:risk_matrix')
    return level,sorted(set(reasons))


def gate_conclusion(result):
    if result["analysis_status"] in {"STALE","ABANDONED"}: return "cancelled"
    if result["analysis_status"] == "BLOCKED": return "action_required"
    sev={f["severity"] for f in result.get("findings",[])}
    if sev & {"blocker","major"}: return "failure"
    levels={"SENSOR":0,"L1":1,"L2":2,"ADVERSARIAL":3,"HUMAN":4}
    req=result["authority"]["required_level"]; got=result["authority"]["achieved_level"]
    if levels[got] < levels[req]: return "action_required"
    if result["risk"]["harness"]["human_review_required"] and got != "HUMAN": return "action_required"
    if sev & {"minor","nit"}: return "success"
    return "success"
