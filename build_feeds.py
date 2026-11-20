"""Строит фиды для Merchant Center по одному на каждый язык сайта galanshop.eu.

Источник цен/наличия/картинок/gtin: английский фид Wix (ссылка в переменной окружения WIX_FEED_URL).
Название и описание берутся с языковой страницы (JSON-LD Product), ссылка ведёт на поддомен языка.

Запуск:  WIX_FEED_URL='https://...' python build_feeds.py [код_языка ...]
Результат: папка feeds/feed_<язык>.tsv  + отчёт feeds/report.csv
"""
import csv, io, json, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

LANGS = "cs da de el es fi fr hu it nl pl pt ro sk sv".split()  # только языки, которые поддерживает Merchant Center; en = www (оригинальный фид Wix)
OUT = os.environ.get("FEEDS_OUT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs")
UA = {"User-Agent": "Mozilla/5.0"}


def get(url, tries=8):
    for i in range(tries):
        try:
            time.sleep(0.4)
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read().decode("utf-8")
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(min(60, 5 * 2 ** i) if "429" in str(e) else 2)


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
    rows = list(csv.DictReader(io.StringIO(get(os.environ["WIX_FEED_URL"])), delimiter="\t"))
    cols = list(rows[0].keys())
    os.makedirs(OUT, exist_ok=True)
    report = []
    for lang in langs:
        def one(r):
            slug = slug_of(r["link"])
            try:
                name, desc = page_data(lang, slug)
            except Exception as e:
                return r, None, None, f"error {e}"
            return r, name, desc, "ok" if name else "no-product-data"
        with ThreadPoolExecutor(2) as ex:
            res = list(ex.map(one, rows))
        path = os.path.join(OUT, f"feed_{lang}.tsv")
        n_ok = n_same = 0
        if sum(1 for x in res if x[3] == "ok") < len(res) * 0.9:
            print(f"{lang}: ПРОПУЩЕН (много ошибок), старый файл не тронут", flush=True)
            report += [(lang, x[0]["id"], slug_of(x[0]["link"]), x[3]) for x in res if x[3] != "ok"]
            continue
        with open(path + ".tmp", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
            w.writeheader()
            for r, name, desc, st in res:
                if st != "ok":
                    report.append((lang, r["id"], slug_of(r["link"]), st))
                    continue  # товар без перевода не публикуем в языковом фиде
                o = dict(r)
                o["title"] = name
                if desc:
                    o["description"] = desc
                o["link"] = f"https://{lang}.galanshop.eu/product-page/{slug_of(r['link'])}"
                if name == r["title"]:
                    n_same += 1
                    report.append((lang, r["id"], slug_of(r["link"]), "title-same-as-english"))
                w.writerow(o)
                n_ok += 1
        os.replace(path + ".tmp", path)
        print(f"{lang}: {n_ok} товаров, из них название совпадает с английским: {n_same}", flush=True)
    with open(os.path.join(OUT, "report.csv"), "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows([("lang", "id", "slug", "status")] + report)


if __name__ == "__main__":
    main()
