# SC2 Build Order Analyzer

StarCraft 2 프로 빌드오더 수집 및 분석 도구.

[Spawning Tool](https://lotv.spawningtool.com)에서 프로 리플레이 빌드오더를 비동기 스크래핑하고,
매치업별 테크 분기 경로를 분류/분석합니다.

## 프로젝트 구조

```
spawningtool_scraper.py           # 비동기 스크래퍼 (aiohttp)
protoss_builds_post_patch.json    # 전체 수집 데이터 (패치 이후)

pvz_build_order_analysis.md       # PvZ 분석 결과
pvz_ground.json                   # PvZ 지상형 경기
pvz_air.json                      # PvZ 빠른 공중형 경기
pvz_mixed.json                    # PvZ 혼합형 경기
```

## 사용법

```bash
uv add aiohttp beautifulsoup4
uv run python spawningtool_scraper.py
```

## 데이터 출처

- [Spawning Tool](https://lotv.spawningtool.com)
- 2025년 10월 밸런스 패치 이후 프로 리플레이 기준
