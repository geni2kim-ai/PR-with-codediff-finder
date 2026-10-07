from __future__ import annotations
import re,sys
ZERO_WIDTH=re.compile('[\u200b\u200c\u200d\u2060\ufeff]')
MD_IMAGE=re.compile(r'!\[[^\]]*\]\([^)]*\)',re.I)
HTML_IMAGE=re.compile(r'<\s*(?:img|image)\b[^>]*>',re.I)
SCHEME_URL=re.compile(r'(?i)(?:https?|ftp)://[^\s<>()]+')
PROTO_URL=re.compile(r'(?i)(?<!:)//(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>()]*)?')
WWW_URL=re.compile(r'(?i)\bwww\.(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>()]*)?')
MD_DANGEROUS_LINK=re.compile(r'(?i)\[[^\]]*\]\(\s*(?:javascript|data|vbscript|file):[^)]*\)')
BARE_HOST=re.compile(r'(?i)(?<![\w@])(?:[a-z0-9](?:[a-z0-9-]{0,62})\.)+[a-z]{2,63}(?=$|[\s/?:#])')
MENTION=re.compile(r'(?<![\w.])@[A-Za-z0-9_-]{1,64}')
SECRET_PATTERNS=[
 re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
 re.compile(r'(?i)(?:^|[^A-Za-z0-9_])(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}(?:$|[^A-Za-z0-9_])'),
 re.compile(r'(?i)(?:^|[^A-Za-z0-9_])github_pat_[A-Za-z0-9_]{20,}(?:$|[^A-Za-z0-9_])'),
 re.compile(r'(?:^|[^A-Z0-9])AKIA[0-9A-Z]{16}(?:$|[^A-Z0-9])'),
 re.compile(r'(?:^|[^A-Za-z0-9_-])sk_(?:live|test)_[A-Za-z0-9]{12,}(?:$|[^A-Za-z0-9_-])'),
 re.compile(r'(?i)(?:^|[^A-Za-z0-9_-])sk-(?:proj-)?[A-Za-z0-9_-]{16,}(?:$|[^A-Za-z0-9_-])'),
 re.compile(r'(?:^|[^A-Za-z0-9_-])xox[baprs]-[A-Za-z0-9-]{10,}(?:$|[^A-Za-z0-9_-])'),
 re.compile(r'(?:^|[^A-Za-z0-9_-])AIza[0-9A-Za-z_-]{30,}(?:$|[^A-Za-z0-9_-])'),
 re.compile(r'(?i)Bearer\s+[A-Za-z0-9._~+/-]{12,}={0,2}'),
 re.compile(r'(?i)(?:^|[^A-Za-z0-9_])eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?:$|[^A-Za-z0-9_])'),
 re.compile(r'(?i)(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s:@/]+:[^\s@/]+@[^\s]+'),
 re.compile(r'(?i)(?:[A-Za-z0-9_]*(?:password|passwd|api[_-]?key|secret|token)[A-Za-z0-9_]*)\s*["\']?\s*[:=]\s*["\']?[^\s"\']{8,}')]

def normalized(s:str)->str:return ZERO_WIDTH.sub('',s)
def scan_text(s:str,*,bare_host=False):
    t=normalized(s);url=bool(SCHEME_URL.search(t) or PROTO_URL.search(t) or WWW_URL.search(t) or MD_DANGEROUS_LINK.search(t))
    if bare_host:url=url or bool(BARE_HOST.search(t))
    return {'external_urls_present':url,'markdown_images_present':bool(MD_IMAGE.search(t) or HTML_IMAGE.search(t)),'mentions_present':bool(MENTION.search(t)),'secret_scan_passed':not any(rx.search(t) for rx in SECRET_PATTERNS)}
def merge_flags(flags):
    return {'sanitized':True,'external_urls_present':any(f['external_urls_present'] for f in flags),'markdown_images_present':any(f['markdown_images_present'] for f in flags),'mentions_present':any(f['mentions_present'] for f in flags),'secret_scan_passed':all(f['secret_scan_passed'] for f in flags)}
def stage_strings(o):
    for f in o.get('findings',[]):
        for k in ('claim','evidence','impact','recommendation','source_ref','failure_family'):
            v=f.get(k)
            if isinstance(v,str):yield k,v
    for v in o.get('escalation',{}).get('reasons',[]):
        if isinstance(v,str):yield 'escalation_reason',v
def scan_stage_result(o):
    vals=list(stage_strings(o));flags=[scan_text(v,bare_host=(k in {'source_ref','failure_family'})) for k,v in vals]
    return merge_flags(flags or [scan_text('')])
def sanitize(s):
    s=normalized(s);s=MD_IMAGE.sub('[image removed]',s);s=HTML_IMAGE.sub('[image removed]',s);s=MD_DANGEROUS_LINK.sub('[external link removed]',s);s=SCHEME_URL.sub('[external link removed]',s);s=PROTO_URL.sub('[external link removed]',s);s=WWW_URL.sub('[external link removed]',s);s=MENTION.sub('[mention removed]',s)
    for rx in SECRET_PATTERNS:s=rx.sub('[secret removed]',s)
    return s
if __name__=='__main__': print(sanitize(sys.stdin.read()),end='')
