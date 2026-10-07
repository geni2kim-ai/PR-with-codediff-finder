from __future__ import annotations
import argparse, json
from pathlib import Path as _P
from pathlib import Path
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
SCHEMA=json.loads((ROOT/'schemas/reviewer-task.schema.json').read_text(encoding='utf-8'))

def semantic_errors(o):
    e=[]; level=o.get('level')
    sec=o.get('security_boundary',{})
    if level in {'L1','L2'} and sec.get('prior_review_conclusions_visible'):
        e.append(f'{level} must not receive prior review conclusions')
    if level in {'L2','ADVERSARIAL'} and not sec.get('fresh_context_required'):
        e.append(f'{level} requires fresh context')
    if level in {'L1','L2'} and (o.get('lower_layer_result_refs') or o.get('lower_layer_result_digests')):
        e.append(f'{level} task must not include lower-layer results')
    if len(o.get('lower_layer_result_refs',[]))!=len(o.get('lower_layer_result_digests',[])):
        e.append('lower-layer refs/digests cardinality mismatch')
    if level=='ADVERSARIAL' and not sec.get('prior_review_conclusions_visible'):
        e.append('ADVERSARIAL task should receive bounded lower-layer refs for adjudication')
    if sec.get('external_network_allowed') or sec.get('secrets_allowed') or sec.get('delegation_allowed'):
        e.append('review task violates tool/security boundary')
    rt=o.get('runtime_enforcement',{})
    att=rt.get('runtime_attestation_digest')
    sandbox_claim=bool(rt.get('network_denied') or rt.get('filesystem_scoped_to_workspace'))
    if sandbox_claim and not (rt.get('network_denied') and rt.get('filesystem_scoped_to_workspace')):
        e.append('runtime sandbox claim must bind network and filesystem controls together')
    if sandbox_claim and not att:e.append('runtime sandbox claim requires attestation digest')
    if att and not sandbox_claim:e.append('runtime attestation digest present without sandbox enforcement claim')
    sensor=o.get('sensor',{})
    if sensor.get('evidence_ref'):
        ep=_P(sensor['evidence_ref'])
        if not ep.is_file():e.append('sensor evidence_ref is not accessible')
        else:
            try:
                ev=json.loads(ep.read_text(encoding='utf-8'))
                if ev.get('output_digest')!=sensor.get('evidence_digest'):e.append('sensor evidence_ref digest mismatch')
                if ev.get('semantic_digest')!=sensor.get('semantic_digest'):e.append('sensor evidence_ref semantic digest mismatch')
            except Exception as exc:e.append('sensor evidence_ref unreadable: '+type(exc).__name__)
    for ref,digest in zip(o.get('lower_layer_result_refs',[]),o.get('lower_layer_result_digests',[])):
        rp=_P(ref)
        if not rp.is_file():e.append(f'lower-layer result ref missing: {ref}')
        else:
            try:
                rr=json.loads(rp.read_text(encoding='utf-8'))
                if rr.get('result_digest')!=digest:e.append(f'lower-layer result digest mismatch: {ref}')
            except Exception as exc:e.append(f'lower-layer result unreadable: {ref}: {type(exc).__name__}')
    for group in ('policy','standards','tests'):
        for ref in o.get('trusted_refs',{}).get(group,[]):
            if not _P(ref).is_file():e.append(f'trusted ref missing: {ref}')
    spec=o.get('trusted_refs',{}).get('spec')
    if spec and not _P(spec).is_file():e.append(f'spec ref missing: {spec}')
    return e

def validate(o):
    return [x.message for x in Draft202012Validator(SCHEMA).iter_errors(o)] + semantic_errors(o)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('json');ns=ap.parse_args();o=json.loads(Path(ns.json).read_text(encoding='utf-8'));errs=validate(o)
    if errs:
        print('INVALID');[print('-',x) for x in errs];raise SystemExit(1)
    print('VALID')
if __name__=='__main__':main()
