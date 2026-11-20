# Языковые фиды galanshop.eu для Merchant Center
Раз в сутки GitHub Actions пересобирает файлы `docs/feed_<язык>.tsv` из английского фида Wix
и переводов со страниц `<язык>.galanshop.eu`. GitHub Pages раздаёт их по ссылке
`https://<имя>.github.io/<репозиторий>/feed_it.tsv` и т.д. Merchant Center скачивает их сам каждые 24 часа.
Секрет `WIX_FEED_URL` (ссылка на английский фид Wix с токеном) хранится в Settings → Secrets → Actions. В файлы не записывается.
