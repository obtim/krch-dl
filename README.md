# krch_free_dl

Скрипт для скачивания серий сериалов сервиса Koroche (`krch.tv`, Android-приложение `tv.koroche.app` v1.5.0) в максимальном качестве. Файлы получают имена по названию сериала и номеру серии.

> ⚠️ Только для личного просмотра. Массовое скачивание может нарушать ToS сервиса и закончиться блокировкой устройства или IP. Распространять файлы нельзя. Платные (`locked`) серии скрипт не скачивает.

---

## Функционал

- Регистрирует устройство анонимно: `POST /v1/auth/device` со случайным `deviceId` (UUID4). Токен кешируется в `~/.krch_token`, при `401` берётся новый.
- Собирает список сериалов из `GET /v1/home` (блоки `hero` и `sections`, без дублей).
- По каждому сериалу запрашивает `GET /v1/series/{series_id}/episodes` и оставляет только серии с `paid_access.type == "free"`.
- Скачивает HLS через `ffmpeg` без перекодирования (`-c copy`):
  - видео в максимальном разрешении: ffmpeg без `-map` сам выбирает 1080p;
  - аудио `ru`;
  - субтитры `ru` встраиваются как `mov_text`; если с ними сборка падает, повтор без субтитров (`-sn`);
  - `-movflags +faststart`.
- Имена файлов: `<out>/<Сериал>/<Сериал> - S01E01.mp4`. Символы `<>:"/\|?*` убираются, ширина номера не меньше 2 цифр.
- Возобновление: уже скачанные файлы пропускаются. Незаконченная загрузка лежит как `*.part.mp4` и удаляется при ошибке.
- Повторы HTTP-запросов (4 попытки с паузой) и пауза между запросами `--delay`.
- В конце итог: скачано / пропущено / ошибок.

## Требования

- Python 3.8+ (только stdlib)
- `ffmpeg`: ищется по порядку `--ffmpeg` → `$KRCH_FFMPEG` → `PATH` → `ffmpeg.exe` рядом со скриптом → `imageio-ffmpeg`

## Использование

```
python3 krch_free_dl.py                 # всё бесплатное -> ./Koroche
python3 krch_free_dl.py -n              # dry-run: только список файлов
python3 krch_free_dl.py -o D:/Video     # другая папка
python3 krch_free_dl.py -s XkwbZBQZ Fvppz6ZN   # только указанные сериалы
python3 krch_free_dl.py --delay 2       # пауза 2 с
```

| Флаг | По умолчанию | Описание |
|---|---|---|
| `-o, --out` | `Koroche` | Папка для файлов |
| `-s, --series` | все из `/v1/home` | Список `series_id` |
| `-n, --dry-run` | — | Не скачивать, только показать |
| `--delay` | `1.0` | Пауза между запросами, с |
| `--ffmpeg` | авто | Путь к `ffmpeg(.exe)` |

Установка ffmpeg на Windows (любой из вариантов):
```
conda install -c conda-forge ffmpeg
pip install imageio-ffmpeg
winget install Gyan.FFmpeg      # затем открыть новое окно консоли
```

## Ограничения

- Берутся только сериалы, которые есть на `/v1/home` (в HAR их 29). Эндпоинта каталога или поиска в HAR нет, поэтому остальные сериалы нужно указывать вручную через `-s`.
- Сезонов API не отдаёт, в именах всегда `S01`.
- Скрипт проверен только офлайн, на данных из HAR. На живом API не запускался.

---

## Что найдено в HAR

Источник: `HTTPToolkit_2026-11-04_11-05.har`. Устройство в дампе — эмулятор MEmu (`dl.memuplay.com`), который представляется как Android 9, `SM-N975F`.

### API: `https://api.krch.tv/v1`

Общие заголовки запросов:
```
accept: application/json, text/plain, */*
user-agent: Mozilla/5.0 (Linux; Android 9; SM-N975F Build/PI; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.72...
authorization: Bearer <JWT>
```

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/auth/device` | Тело `{"deviceId":"<uuid>"}`, ответ `{"token":"<JWT HS256>"}`. Логин и телефон не нужны. |
| `GET` | `/me` | Без токена: `401 Authorization header is required`. С токеном: `{"uid","store_uid","phone":null,"phone_verified":false,"s_m":false,"subscription":null}` |
| `GET` | `/home` | Витрина: `hero.items[]`, `sections[]` (`id`, `title`, `layout`, `items[].series`) |
| `GET` | `/history` | `{"items":[]}` |
| `GET` | `/watchlist` | `{"items":[]}` |
| `GET` | `/series/{series_id}/episodes` | Список серий и `meta.monetization` |
| `PUT` | `/episodes/{episode_id}/progress` | Прогресс просмотра (периодически во время воспроизведения) |

JWT payload: `did` (ID устройства), `uid`, `v:1`, `iat`, `exp`. Срок жизни около 1 года (`exp − iat ≈ 31 557 600 с`).

#### Объект `series` (из `/home`)
`series_id`, `title`, `description`, `synopsis`, `genre` (`Микродрама`, `Комедия`…), `age_rating` (`18+`), `badge` (`ORIGINAL`), `episodes_count`, `total_episodes`, `released_at`, `is_released`, `rating.value`, `share_url` (`https://krch.tv/k/<id>-<slug>`), картинки `title_img` / `hero_img` / `poster_2x3` / `poster_3x4` / `promo_1x1_img` (`2x`/`3x`), `hero_video.url` (mp4-трейлер), `is_in_watchlist`, `is_notify_enabled`.

#### Ответ `/series/{id}/episodes`
```json
{
  "episodes": [{
    "episode_id": "n4x78vc3KA",
    "series_id": "XkwbZBQZ",
    "episode_number": 1,
    "is_watched": false, "is_liked": false, "likes_count": 149,
    "video": {
      "url": "https://cdn.krch.tv/live/assets/vods/<vod_id>/master.m3u8",
      "first_frame_url": "https://cdn.krch.tv/live/assets/images/<id>.2x.jpg"
    },
    "paid_access": {"type": "free" | "locked"}
  }],
  "meta": {
    "monetization": {"free_episodes_count": 6, "episodes_per_ad": 1,
                     "episodes_per_task": 1, "show_paywall_after": 6},
    "ad_limits": {"ads_watched_today": 0, "limit_reached": false}
  }
}
```
Модель монетизации: первые 6 серий бесплатно, дальше одна серия за рекламу или задание, либо подписка.

### CDN: `https://cdn.krch.tv/live/assets/`

- `images/<id>.2x.jpg|png` — постеры, кадры
- `videos/<id>.mp4` — трейлеры (`hero_video`), поддерживаются Range-запросы (`206`)
- `vods/<vod_id>/` — серии в HLS, сделаны `shaka-packager v3.4.2`, CMAF/fMP4, **без шифрования и DRM**, CDN не требует авторизации

Структура `vods/<vod_id>/`:
```
master.m3u8
360p.m3u8   540p.m3u8   720p.m3u8   1080p.m3u8
audio.m3u8        (ru, 2ch)
subs_ru.m3u8      (WebVTT)
<variant>/init.mp4, <variant>/segment_N.m4s
audio/init.mp4,    audio/segment_N.m4s
subs_ru/segment_N.vtt
```

| Вариант | Разрешение | BANDWIDTH | Кодек |
|---|---|---|---|
| 360p | 360x640 | 1 578 373 | avc1.4d401e |
| 540p | 540x960 | 3 102 231 | avc1.4d401f |
| 720p | 720x1280 | 4 604 295 | avc1.640028 |
| 1080p | 1080x1920 | 8 905 110 | avc1.640029 |

Аудио `mp4a.40.2`, 25 fps, SDR, вертикальное видео.

### ⚠️ Уязвимость: утечка URL платных серий

`/series/{id}/episodes` возвращает `video.url` для **всех** серий, включая `paid_access.type == "locked"`. При этом CDN отдаёт HLS без токена и шифрования. Получается, что пейвол работает только на стороне клиента. Пример: у «Зад Славы» (`XkwbZBQZ`) серии 7–20 помечены `locked`, но ссылки на них есть в ответе.

Рекомендация сервису: не отдавать `video.url` для `locked` серий, а на CDN выдавать подписанные URL или токены с коротким сроком жизни (или включить шифрование HLS / DRM).

Скрипт этой уязвимостью **не пользуется**.

> Перед публичной выкладкой репозитория стоит сообщить об этой уязвимости в Koroche (responsible disclosure) и дать время на исправление.

### Сторонние SDK и трекеры в трафике

- Firebase: `koroche-7bda6` (installations, Crashlytics `1:901023312036:android:96797dd009f2c8854c1e31`)
- AppMetrica / Yandex Mobile Ads (`report.appmetrica.yandex.net`, `startup.mobile.yandex.net`, `yandex.com/ads/v1/startup`)
- myTarget / VK Ads (`ad.mail.ru/sdk/log/`)
- AppsFlyer 6.17.5 (`hoj8it.*.appsflyersdk.com`, `app_id=tv.koroche.app`)
- OneSignal (`app 56c1da30-75e4-45b0-a4c5-672bb8d2558e`)
- Фоновый трафик Google Play и GMS, а также другое приложение на том же устройстве (`olimpbet-android`) к Koroche не относятся.

### Сериалы на `/home` (в дампе 29)

Например: «Дорога в пустоту» (`Fvppz6ZN`), «Силуэты», «Запрещай меня полностью», «Полуподкаст», «Я — уверена», «Когда убьют, тогда и приходите», «ВЭБМАМ» (`EBK3W6j1`), «Зад Славы» (`XkwbZBQZ`) и другие.
