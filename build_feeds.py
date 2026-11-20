"""Строит фиды для Merchant Center по одному на каждый язык сайта galanshop.eu.

Цены/наличие/картинки/gtin берутся каждый день из английского фида Wix (WIX_FEED_URL, секрет).
Названия и описания (переводы) берутся со страниц <язык>.galanshop.eu, но Wix сильно тормозит
запросы с серверов GitHub, поэтому переводы кэшируются в cache.json:
  - товары, которых нет в кэше, догружаются в первую очередь;
  - каждый день обновляется ещё REFRESH самых старых записей (весь кэш обходится за пару недель);
  - если страница не открылась, остаётся прежний перевод из кэша.
Результат: docs/feed_<язык>.tsv  (раздаётся GitHub Pages)  и cache.json
"""
import csv, io, json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

LANGS = "cs da de el es fi fr hu it nl pl pt ro sk sv".split()  # языки, которые поддерживает Merchant Center
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("FEEDS_OUT") or os.path.join(HERE, "docs")
CACHE = os.environ.get("CACHE_FILE") or os.path.join(HERE, "cache.json")
UA = {"User-Agent": "Mozilla/5.0"}
MAX_NEW = int(os.environ.get("MAX_NEW", "400"))     # сколько новых страниц за запуск
REFRESH = int(os.environ.get("REFRESH", "60"))      # сколько старых записей обновить за запуск
RETRY_MISS_DAYS = 7
DEADLINE = time.time() + int(os.environ.get("MAX_SECONDS", str(100 * 60)))


def get(url, tries=3):
    for i in range(tries):
        try:
            time.sleep(0.4)
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read().decode("utf-8")
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(min(30, 5 * 2 ** i) if "429" in str(e) else 2)


def slug_of(link):
    return re.search(r"/product-page/([^?#]+)", link).group(1)


def page_data(lang, slug):
    h = get(f"https://{lang}.galanshop.eu/product-page/{slug}")
    for m in re.finditer(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', h, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        if isinstance(d, dict) and d.get("@type") == "Product":
            return d.get("name", "").strip(), re.sub(r"\s+", " ", d.get("description", "") or "").strip()
    return None, None


def main():
    langs = sys.argv[1:] or LANGS
    rows = list(csv.DictReader(io.StringIO(get(os.environ["WIX_FEED_URL"], tries=4)), delimiter="\t"))
    if len(rows) < 20:
        raise SystemExit(f"Wix feed too small ({len(rows)}), abort")
    cols = list(rows[0].keys())
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    now = int(time.time())

    # 1) что нужно догрузить: нет в кэше (или промах старше недели)
    need = []
    for lang in langs:
        for r in rows:
            k = f"{lang}|{slug_of(r['link'])}"
            e = cache.get(k)
            if e is None or (e.get("miss") and now - e["miss"] > RETRY_MISS_DAYS * 86400):
                need.append(k)
    # 2) плюс самые старые записи для обновления
    old = sorted((k for k, e in cache.items() if not e.get("miss") and k.split("|")[0] in langs and k not in need),
                 key=lambda k: cache[k].get("t", 0))[:REFRESH]
    todo = need[:MAX_NEW] + old
    print(f"в кэше {len(cache)}, нужно догрузить {len(need)}, обновить {len(old)}, всего запросов {len(todo)}", flush=True)

    def fetch(k):
        if time.time() > DEADLINE:
            return k, "skip", None
        lang, slug = k.split("|", 1)
        try:
            name, desc = page_data(lang, slug)
            return k, "ok" if name else "nodata", (name, desc)
        except Exception as e:
            return k, "err", str(e)

    stats = {"ok": 0, "nodata": 0, "err": 0, "skip": 0}
    with ThreadPoolExecutor(2) as ex:
        for k, st, val in ex.map(fetch, todo):
            stats[st] += 1
            if st == "ok":
                cache[k] = {"n": val[0], "d": val[1], "t": now}
            elif st == "nodata" and k not in cache:
                cache[k] = {"miss": now}
    print("результат запросов:", stats, flush=True)

    # 3) собираем фиды из кэша
    os.makedirs(OUT, exist_ok=True)
    for lang in langs:
        path = os.path.join(OUT, f"feed_{lang}.tsv")
        n = 0
        with open(path + ".tmp", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
            w.writeheader()
            for r in rows:
                slug = slug_of(r["link"])
                e = cache.get(f"{lang}|{slug}")
                if not e or e.get("miss") or not e.get("n"):
                    continue  # нет перевода — товар в этом языке не публикуем
                o = dict(r)
                o["title"] = e["n"]
                if e.get("d"):
                    o["description"] = e["d"]
                o["link"] = f"https://{lang}.galanshop.eu/product-page/{slug}"
                w.writerow(o)
                n += 1
        if n < len(rows) * 0.8:
            os.remove(path + ".tmp")
            print(f"{lang}: только {n} из {len(rows)} — файл не обновлён", flush=True)
            continue
        os.replace(path + ".tmp", path)
        print(f"{lang}: {n} товаров", flush=True)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main()
