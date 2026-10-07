from __future__ import annotations
import re,sys
ZERO_WIDTH=re.compile('[\u200b\u200c\u200d\u2060\ufeff]')
MD_IMAGE=re.compile(r'!\[[^\]]*\]\([^)]*\)',re.I)
HTML_IMAGE=re.compile(r'<\s*(?:img|image)\b[^>]*>',re.I)
SCHEME_URL=re.compile(r'(?i)\b(?:https?|ftp)://[^\s<>()]+')
PROTO_URL=re.compile(r'(?i)(?<!:)//(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>()]*)?')
WWW_URL=re.compile(r'(?i)\bwww\.(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s<>()]*)?')
MD_DANGEROUS_LINK=re.compile(r'(?i)\[[^\]]*\]\(\s*(?:javascript|data|vbscript|file):[^)]*\)')
BARE_DOMAIN=re.compile(r'(?i)(?<![\w@])(?:[a-z0-9](?:[a-z0-9-]{0,62})\.)+(?:com|net|org|io|dev|app|ai|co|kr|jp|cn|ru|uk|de|fr|xyz|info|biz|gov|edu)(?:[/:?#][^\s<>()]*)?')
MENTION=re.compile(r'(?<![\w.])@[A-Za-z0-9_-]{1,64}')
SECRET_PATTERNS=[
 re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 re.compile(r'\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b'),
 re.compile(r'\bgithub_pat_[A-Za-z0-9_]{20,}\b'),
 re.compile(r'\bAKIA[0-9A-Z]{16}\b'),
 re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'),
 re.compile(r'(?i)\b(?:password|passwd|api[_-]?key|secret|token)\s*[:=]\s*["\']?[^\s"\']{8,}')]

def normalized(s:str)->str:return ZERO_WIDTH.sub('',s)

def scan_text(s:str):
    t=normalized(s)
    return {
      'external_urls_present':bool(SCHEME_URL.search(t) or PROTO_URL.search(t) or WWW_URL.search(t) or BARE_DOMAIN.search(t) or MD_DANGEROUS_LINK.search(t)),
      'markdown_images_present':bool(MD_IMAGE.search(t) or HTML_IMAGE.search(t)),
      'mentions_present':bool(MENTION.search(t)),
      'secret_scan_passed':not any(rx.search(t) for rx in SECRET_PATTERNS)}

def merge_flags(flags):
    return {'sanitized':True,
      'external_urls_present':any(f['external_urls_present'] for f in flags),
      'markdown_images_present':any(f['markdown_images_present'] for f in flags),
      'mentions_present':any(f['mentions_present'] for f in flags),
      'secret_scan_passed':all(f['secret_scan_passed'] for f in flags)}

def stage_strings(o):
    for f in o.get('findings',[]):
        for k in ('claim','evidence','impact','recommendation','source_ref','failure_family'):
            v=f.get(k)
            if isinstance(v,str):yield v
    for v in o.get('escalation',{}).get('reasons',[]):
        if isinstance(v,str):yield v

def scan_stage_result(o):
    vals=list(stage_strings(o));return merge_flags([scan_text(x) for x in vals] or [scan_text('')])

def sanitize(s):
    s=normalized(s);s=MD_IMAGE.sub('[image removed]',s);s=HTML_IMAGE.sub('[image removed]',s);s=MD_DANGEROUS_LINK.sub('[external link removed]',s)
    s=SCHEME_URL.sub('[external link removed]',s);s=PROTO_URL.sub('[external link removed]',s);s=WWW_URL.sub('[external link removed]',s);s=BARE_DOMAIN.sub('[external link removed]',s);s=MENTION.sub('[mention removed]',s)
    for rx in SECRET_PATTERNS:s=rx.sub('[secret removed]',s)
    return s

if __name__=='__main__': print(sanitize(sys.stdin.read()),end='')
