"""Download one reusable Wikimedia Commons photo for every seeded landmark."""

from __future__ import annotations

import csv
import html
import json
import re
import shutil
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = PROJECT_ROOT / "data" / "seed" / "landmarks_verified.csv"
ALBUM_ROOT = PROJECT_ROOT / "data" / "contributions" / "landmark_albums"
IMAGES_ROOT = ALBUM_ROOT / "images"
MANIFEST_PATH = ALBUM_ROOT / "manifest.json"
USER_AGENT = "IPLandmarkTravel/0.1 (community landmark album seed)"
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

QUERIES = [
    ("literature", "百草园与三味书屋", "luxun-former-residence", ("Lu Xun Native Place Shaoxing", "Sanwei Study Shaoxing")),
    ("literature", "外白渡桥", "waibaidu-bridge", ("Waibaidu Bridge Shanghai",)),
    ("literature", "边城茶峒古镇", "chadong-ancient-town", ("Chadong Town Hunan China", "Chadong Hunan")),
    ("literature", "地坛公园", "temple-of-earth", ("Temple of Earth Beijing",)),
    ("literature", "额尔古纳河右岸", "erguna-river", ("Ergune River China", "Argun River China")),
    ("literature", "巴黎圣母院", "notre-dame-literature", ("Notre-Dame de Paris",)),
    ("literature", "伊夫堡", "chateau-d-if", ("Chateau d'If Marseille",)),
    ("literature", "桑迪科夫马特洛塔", "james-joyce-tower", ("James Joyce Tower Sandycove",)),
    ("literature", "卢浮宫", "louvre-museum", ("Louvre Museum Paris",)),
    ("literature", "莫斯科大都会酒店", "hotel-metropol-moscow", ("Hotel Metropol Moscow",)),
    ("literature", "纯真博物馆", "museum-of-innocence", ("Museum of Innocence Istanbul",)),
    ("game", "小西天", "xiaoxitian-temple", ("File:隰县小西天 上院下院.JPG", "Xiaoxitian Temple Xi County Shanxi", "Xiaoxitian Shanxi")),
    ("game", "应县木塔", "yingxian-wooden-pagoda", ("Yingxian Wooden Pagoda",)),
    ("game", "佛光寺", "foguang-temple", ("Foguang Temple Shanxi",)),
    ("game", "开封府", "kaifengfu", ("Kaifeng Fu China", "Kaifeng Prefecture")),
    ("game", "佛罗伦萨圣母百花大教堂", "florence-duomo", ("Florence Cathedral Duomo",)),
    ("game", "威尼斯圣马可广场", "piazza-san-marco", ("Piazza San Marco Venice",)),
    ("game", "巴黎圣母院", "notre-dame-game", ("Notre-Dame de Paris",)),
    ("game", "金门大桥", "golden-gate-bridge", ("Golden Gate Bridge",)),
    ("game", "萨扎瓦修道院", "sazava-monastery", ("Sazava Monastery",)),
    ("screen", "重庆大厦", "chungking-mansions", ("Chungking Mansions Hong Kong",)),
    ("screen", "赤坎古镇", "chikan-ancient-town", ("Chikan Kaiping China", "Chikan Ancient Town Kaiping")),
    ("screen", "九份老街", "jiufen-old-street", ("Jiufen Taiwan",)),
    ("screen", "黄河路", "huanghe-road-shanghai", ("Huanghe Road Shanghai", "Huanghe Lu Shanghai")),
    ("screen", "北京大学红楼", "peking-university-red-building", ("Peking University Red Building",)),
    ("screen", "禾木村", "hemu-village", ("Hemu Village Xinjiang",)),
    ("screen", "真理之口", "mouth-of-truth", ("Mouth of Truth Rome",)),
    ("screen", "米拉贝尔花园", "mirabell-gardens", ("Mirabell Gardens Salzburg",)),
    ("screen", "莎士比亚书店", "shakespeare-and-company", ("Shakespeare and Company Paris",)),
    ("screen", "海克利尔城堡", "highclere-castle", ("Highclere Castle",)),
    ("screen", "圣多梅尼科宫四季酒店", "san-domenico-palace", ("San Domenico Palace Taormina",)),
    ("screen", "黑乡生活博物馆", "black-country-living-museum", ("Black Country Living Museum",)),
    ("screen", "皇家新月楼", "royal-crescent", ("Royal Crescent Bath",)),
]


def clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
    return text or None


def api_json(query: str) -> dict[str, object]:
    parameters: dict[str, str] = {
        "action": "query",
        "format": "json",
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": "1600",
    }
    if query.startswith("File:"):
        parameters["titles"] = query
    else:
        parameters.update({"generator": "search", "gsrnamespace": "6", "gsrlimit": "8", "gsrsearch": query})
    params = urlencode(parameters)
    request = Request(f"https://commons.wikimedia.org/w/api.php?{params}", headers={"User-Agent": USER_AGENT})
    with open_with_retry(request, timeout=45) as response:
        return json.load(response)


def open_with_retry(request: Request, timeout: int):
    for attempt in range(5):
        try:
            return urlopen(request, timeout=timeout)
        except HTTPError as error:
            if error.code != 429 or attempt == 4:
                raise
            retry_after = error.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else 3 * (attempt + 1)
        except URLError:
            if attempt == 4:
                raise
            delay = 3 * (attempt + 1)
        time.sleep(delay)
    raise RuntimeError("Image request retry loop terminated unexpectedly.")


def find_commons_image(query: str) -> dict[str, str] | None:
    pages = api_json(query).get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        return None
    ordered_pages = sorted(pages.values(), key=lambda page: page.get("index", 999999))
    for page in ordered_pages:
        if not isinstance(page, dict):
            continue
        image_info = page.get("imageinfo")
        if not isinstance(image_info, list) or not image_info or not isinstance(image_info[0], dict):
            continue
        info = image_info[0]
        if info.get("mime") not in ALLOWED_MIMES:
            continue
        metadata = info.get("extmetadata") if isinstance(info.get("extmetadata"), dict) else {}
        license_name = clean_text(metadata.get("LicenseShortName", {}).get("value"))
        if not license_name or not re.search(r"CC|Public domain|\bPD\b", license_name, flags=re.I):
            continue
        download_url = info.get("thumburl") or info.get("url")
        source_url = info.get("descriptionurl")
        if not isinstance(download_url, str) or not isinstance(source_url, str):
            continue
        return {
            "download_url": download_url,
            "source_url": source_url,
            "credit": clean_text(metadata.get("Artist", {}).get("value")) or "Wikimedia Commons contributor",
            "license": license_name,
        }
    return None


def download(url: str, target: Path) -> None:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    target.parent.mkdir(parents=True, exist_ok=True)
    with open_with_retry(request, timeout=90) as response, target.open("wb") as output:
        shutil.copyfileobj(response, output)
    if target.stat().st_size < 1024:
        target.unlink(missing_ok=True)
        raise RuntimeError(f"Downloaded file is unexpectedly small: {target}")


def main() -> None:
    seed_keys = {(row["ip_type"], row["landmark_name"]) for row in csv.DictReader(SEED_PATH.open(encoding="utf-8-sig", newline=""))}
    requested_keys = {(ip_type, name) for ip_type, name, _, _ in QUERIES}
    if seed_keys != requested_keys:
        raise RuntimeError("The image query list and current seed landmarks differ; update the query list before downloading.")

    albums: dict[str, list[dict[str, str]]] = {}
    unavailable: list[str] = []
    for ip_type, landmark_name, slug, queries in QUERIES:
        image = None
        for query in queries:
            image = find_commons_image(query)
            if image:
                break
        if image is None:
            unavailable.append(f"{ip_type}:{landmark_name}")
            continue
        extension = Path(urlparse(image["download_url"]).path).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            extension = ".jpg"
        relative_file = f"{ip_type}/{slug}/commons-01{extension}"
        download(image["download_url"], IMAGES_ROOT / relative_file)
        albums[f"{ip_type}:{landmark_name}"] = [
            {
                "file": relative_file,
                "alt": f"{landmark_name}实景",
                "caption": "Wikimedia Commons 实景图片",
                "credit": image["credit"],
                "license": image["license"],
                "source_url": image["source_url"],
            }
        ]
        print(f"Downloaded {relative_file}")
        time.sleep(1)

    MANIFEST_PATH.write_text(json.dumps({"schema_version": 1, "albums": albums}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Completed {len(albums)} albums; unavailable {len(unavailable)}.")
    if unavailable:
        print("Unavailable: " + " | ".join(unavailable))


if __name__ == "__main__":
    main()
