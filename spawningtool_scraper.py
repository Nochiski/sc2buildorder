"""
Spawning Tool 프로 리플레이 빌드오더 스크래퍼 (비동기 버전)
- 5.0.15 패치 이후 (2025년 10월~) 프로토스 빌드오더만 수집
- 프로 리플레이에서 파싱된 빌드오더 데이터를 가져옴
사용법:
  uv add aiohttp beautifulsoup4 pandas
  uv run python spawningtool_scraper.py
"""
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import json
import re
from typing import Optional

BASE_URL = "https://lotv.spawningtool.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# 태그 ID (spawningtool 필터용)
RACE_TAGS = {"Protoss": 17, "Terran": 1, "Zerg": 2}
PLAYER_TAGS = {"herO": 728, "ShoWTimE": 159, "Zoun": 2426}

# 동시 요청 제한 (서버 부하 방지)
MAX_CONCURRENT = 5
SEMAPHORE: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENT)


async def fetch(session: aiohttp.ClientSession, url: str, params: Optional[list[tuple[str, str]]] = None) -> str:
    """세마포어로 동시 요청 수를 제한하면서 페이지를 가져옴"""
    async with SEMAPHORE:
        async with session.get(url, params=params, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            resp.raise_for_status()
            return await resp.text()


async def get_replay_list(
    session: aiohttp.ClientSession,
    page: int = 1,
    pro_only: bool = True,
    patch: Optional[str] = None,
    tags: Optional[list[int]] = None,
    after_played_on: Optional[str] = None,
) -> list[dict]:
    """리플레이 목록 페이지에서 리플레이 ID와 기본 정보를 가져옴"""

    params: list[tuple[str, str]] = [
        ("p", str(page)),
        ("order_by", "date"),
    ]

    if pro_only:
        params.append(("pro_only", "on"))
    if patch:
        params.append(("patch", patch))
    if after_played_on:
        params.append(("after_played_on", after_played_on))
    if tags:
        for t in tags:
            params.append(("tag", str(t)))

    url = f"{BASE_URL}/replays/"
    print(f"  [요청] {url} | params={params}")

    html = await fetch(session, url, params)
    soup = BeautifulSoup(html, "html.parser")
    replays = []

    table = soup.find("table", class_="table-striped")
    if not table:
        print("  [경고] 리플레이 테이블을 찾을 수 없음")
        return replays

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        link = row.find("a", href=re.compile(r"^/\d+/$"))
        if not link:
            continue

        replay_id_match = re.search(r"/(\d+)/", link["href"])
        if not replay_id_match:
            continue

        rid = int(replay_id_match.group(1))
        replay_info = {
            "id": rid,
            "title": link.get_text(strip=True),
            "url": f"{BASE_URL}/{rid}/",
        }

        if len(cells) >= 3:
            replay_info["date_played"] = cells[2].get_text(strip=True)
        if len(cells) >= 4:
            replay_info["game_length"] = cells[3].get_text(strip=True)

        replays.append(replay_info)

    print(f"  [결과] {len(replays)}개 리플레이 발견")
    return replays


def parse_build_order(html: str, replay_id: int) -> dict:
    """HTML에서 빌드오더를 파싱 (CPU 작업이므로 동기 함수)"""

    soup = BeautifulSoup(html, "html.parser")

    result = {
        "replay_id": replay_id,
        "url": f"{BASE_URL}/{replay_id}/",
        "players": [],
        "matchup": "",
        "map": "",
        "date_played": "",
        "game_length": "",
    }

    overview = soup.find("div", id="replay-overview")
    if overview:
        map_h3 = overview.find("h3", string=re.compile(r"Map:"))
        if map_h3:
            result["map"] = map_h3.get_text(strip=True).replace("Map:", "").strip()

        time_section = overview.find("h3", string=re.compile(r"Time"))
        if time_section:
            ul = time_section.find_next_sibling("ul")
            if ul:
                for li in ul.find_all("li"):
                    text = li.get_text(strip=True)
                    if "Played on:" in text:
                        result["date_played"] = text.replace("Played on:", "").strip()
                    elif "Length:" in text:
                        result["game_length"] = text.replace("Length:", "").strip()

        player_infos = []
        for h4 in overview.find_all("h4"):
            name = h4.get_text(strip=True)
            name = re.sub(r"\s*-\s*Winner!?\s*$", "", name)

            race = ""
            ul = h4.find_next_sibling("ul")
            if ul:
                race_li = ul.find("li")
                if race_li:
                    img = race_li.find("img")
                    if img and img.get("alt"):
                        race = img["alt"]

            player_infos.append({"name": name, "race": race})

        if len(player_infos) == 2:
            r1 = player_infos[0]["race"][0] if player_infos[0]["race"] else "?"
            r2 = player_infos[1]["race"][0] if player_infos[1]["race"] else "?"
            result["matchup"] = f"{r1}v{r2}"

        for i, pinfo in enumerate(player_infos):
            player_pane = soup.find("div", id=f"player-{i+1}")

            player_data = {
                "name": pinfo["name"],
                "race": pinfo["race"],
                "build_order": [],
            }

            if player_pane:
                table = player_pane.find("table")
                if table:
                    for row in table.find_all("tr"):
                        cells = row.find_all("td")
                        if len(cells) >= 3:
                            player_data["build_order"].append({
                                "supply": cells[0].get_text(strip=True),
                                "time": cells[1].get_text(strip=True),
                                "action": cells[2].get_text(strip=True),
                            })

            result["players"].append(player_data)

    bo_counts = [len(p["build_order"]) for p in result["players"]]
    print(f"  [#{replay_id}] {result['matchup']} | "
          f"{' vs '.join(p['name'] for p in result['players'])} | "
          f"빌드 {bo_counts}")

    return result


async def get_build_order(session: aiohttp.ClientSession, replay_id: int) -> dict:
    """개별 리플레이 페이지에서 양쪽 플레이어의 빌드오더를 추출 (비동기)"""
    url = f"{BASE_URL}/{replay_id}/"
    html = await fetch(session, url)
    return parse_build_order(html, replay_id)


async def scrape_protoss_builds(
    player_names: Optional[list[str]] = None,
    max_pages: int = 5,
    after_played_on: str = "2025-10-01",
) -> list[dict]:
    """프로토스 프로 리플레이에서 빌드오더를 비동기로 수집"""

    all_builds = []
    seen_ids: set[int] = set()

    players = player_names or list(PLAYER_TAGS.keys())
    player_tag_ids = {name: PLAYER_TAGS[name] for name in players if name in PLAYER_TAGS}

    if not player_tag_ids:
        print("[에러] 유효한 선수 태그를 찾을 수 없습니다.")
        return all_builds

    async with aiohttp.ClientSession() as session:
        # 1단계: 모든 선수의 리플레이 목록을 동시에 수집
        list_tasks = []
        for player_name, tag_id in player_tag_ids.items():
            for page in range(1, max_pages + 1):
                list_tasks.append((player_name, tag_id, page))

        print(f"\n[수집] {len(list_tasks)}개 목록 페이지를 동시 요청합니다...")

        async def fetch_list(player_name, tag_id, page):
            try:
                replays = await get_replay_list(
                    session, page=page, pro_only=True,
                    tags=[tag_id], after_played_on=after_played_on,
                )
                return [(player_name, r) for r in replays]
            except Exception as e:
                print(f"  [에러] {player_name} 페이지 {page} 실패: {e}")
                return []

        list_results = await asyncio.gather(
            *[fetch_list(pn, tid, pg) for pn, tid, pg in list_tasks]
        )

        # 중복 제거
        unique_replays = []
        for result_group in list_results:
            for player_name, replay in result_group:
                if replay["id"] not in seen_ids:
                    seen_ids.add(replay["id"])
                    unique_replays.append((player_name, replay))

        print(f"\n[수집] 중복 제거 후 {len(unique_replays)}개 리플레이 빌드오더를 동시 요청합니다...")

        # 2단계: 모든 빌드오더를 동시에 수집
        async def fetch_build(player_name, replay):
            try:
                build_data = await get_build_order(session, replay["id"])
                build_data["title"] = replay.get("title", "")
                build_data["searched_player"] = player_name
                if not build_data["date_played"]:
                    build_data["date_played"] = replay.get("date_played", "")
                return build_data
            except Exception as e:
                print(f"  [에러] 리플레이 #{replay['id']} 빌드오더 로딩 실패: {e}")
                return None

        build_results = await asyncio.gather(
            *[fetch_build(pn, r) for pn, r in unique_replays]
        )

        all_builds = [b for b in build_results if b is not None]

    return all_builds


def export_builds(builds: list[dict], filename: str = "protoss_builds_post_patch.json"):
    """수집된 데이터를 JSON으로 저장"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(builds, f, ensure_ascii=False, indent=2)
    print(f"\n[저장] {filename}에 {len(builds)}개 빌드 저장 완료")


async def async_main():
    print("=" * 60)
    print("Spawning Tool 프로토스 빌드오더 스크래퍼 (비동기)")
    print("2025년 10월~ 프로 리플레이 기준")
    print(f"동시 요청 제한: {MAX_CONCURRENT}개")
    print("=" * 60)

    TARGET_PLAYERS = ["herO", "ShoWTimE", "Zoun"]
    MAX_PAGES = 5
    AFTER_PLAYED_ON = "2025-10-01"

    builds = await scrape_protoss_builds(
        player_names=TARGET_PLAYERS,
        max_pages=MAX_PAGES,
        after_played_on=AFTER_PLAYED_ON,
    )

    if not builds:
        print("\n수집된 빌드가 없습니다.")
        return

    export_builds(builds)
    print(f"\n총 {len(builds)}개 경기 수집 완료")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
