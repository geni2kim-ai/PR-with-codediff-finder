# Migration v2.3 → v2.4

1. 기존 v2.3 evidence를 그대로 재사용하지 말고 v2.4 adapter로 다시 생성한다. v2.4는 merge-base binding, tool pin, legacy encoding 정책 및 semantic recomputation을 요구한다.
2. orchestration 호출에 `--expected-base`를 반드시 전달한다.
3. custom standards/prompt/skill ref는 실제 파일이 존재해야 한다. 누락 ref는 fail-closed다.
4. 기존 case ledger는 v2.4 새 case부터 anchor/HMAC 체계를 사용한다. 기존 v2.3 case를 보존하려면 history로 읽기 전용 보관하고 새 event를 혼합하지 않는다.
5. ENFORCED를 사용하려면 routing policy 수정만으로 충분하지 않다. 외부 HMAC runtime attestation + ledger key + audit seed가 필요하다.
6. queue 디렉터리 표기는 `adversarial_queue/`로 통일한다.
7. active examples은 `examples/v24/`, v2.3 examples은 역사 자료로만 사용한다.
