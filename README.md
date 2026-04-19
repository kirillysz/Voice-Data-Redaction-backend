# Voice Data Redaction — Backend Documentation

## Обзор

REST API для анонимизации голосовых данных. Принимает аудиофайл, транскрибирует его, детектирует персональные данные (ПДн) и возвращает редактированный транскрипт и аудио с заглушёнными фрагментами.

**Base URL:** `http://localhost:8000`

**Swagger UI:** `http://localhost:8000/docs`

---

## Стек

| Компонент | Технология |
|-----------|------------|
| Framework | FastAPI 0.136+ |
| Python | 3.14 |
| Очередь задач | RQ (Redis Queue) 2.8+ |
| Брокер | Redis 7.4+ |
| Валидация | Pydantic v2 |
| Rate limiting | SlowAPI |
| Менеджер зависимостей | uv |
| Запуск | Docker Compose |

---

## Быстрый старт

### Docker (рекомендуется)

```bash
git clone https://github.com/kirillysz/Voice-Data-Redaction-backend
cd Voice-Data-Redaction-backend
cp .env.example .env   # заполни переменные
docker compose up --build
```

Поднимает три контейнера: `redis`, `api`, `worker`.

### Локально

```bash
uv sync
redis-server &
uvicorn app.main:app --reload &
rq worker audio
```

---

## Конфигурация

Все переменные задаются в `.env` файле в корне проекта.

### Пример .env для Docker

```env
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

QWEN_API_URL=http://127.0.0.1:2222
```

### Пример .env для локальной разработки

```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

QWEN_API_URL=http://127.0.0.1:2222
```

### Все переменные

#### JWT

| Переменная | Тип | По умолчанию | Описание |
|------------|-----|--------------|----------|
| `JWT_SECRET_KEY` | string | случайный | Секрет для подписи токенов. **В продакшне задай вручную** — иначе токены инвалидируются при перезапуске |
| `JWT_ALGORITHM` | string | `HS256` | Алгоритм подписи |
| `JWT_ACCESS_TOKEN_EXPIRES` | bool | `True` | Включить истечение токена |
| `JWT_EXPIRES_MINUTES` | int | `30` | Время жизни токена (минуты) |

#### Файлы

| Переменная | Тип | По умолчанию | Описание |
|------------|-----|--------------|----------|
| `UPLOAD_DIR` | path | `app/static/uploads` | Директория входящих аудиофайлов |
| `OUTPUT_DIR` | path | `app/static/output` | Директория результатов обработки |
| `ALLOWED_EXTENSIONS` | list | `.mp3 .wav .ogg .m4a .flac .webm` | Разрешённые форматы |

Директории создаются автоматически при старте.

#### Redis

| Переменная | Тип | По умолчанию | Описание |
|------------|-----|--------------|----------|
| `REDIS_HOST` | string | `localhost` | Хост Redis. В Docker — `redis` |
| `REDIS_PORT` | int | `6379` | Порт |
| `REDIS_DB` | int | `0` | Номер базы данных |
| `REDIS_PASSWORD` | string \| null | `null` | Пароль. Если не задан — авторизация отключена |

#### Внешние сервисы

| Переменная | Тип | По умолчанию | Описание |
|------------|-----|--------------|----------|
| `QWEN_API_URL` | string | `http://127.0.0.1:2222` | URL AI-модели для обработки |

---

## Архитектура

```
Клиент
  │
  ▼
POST /transcriptions/redact
  │  сохранить файл в UPLOAD_DIR
  │  поставить job в RQ очередь "audio"
  └─► вернуть { job_id, status: "created" }

         RQ Worker (отдельный процесс/контейнер)
           │
           ▼
         process_job(input_path, output_path)
           │
           ▼
         process_audio_file(...)  ← основная логика здесь
           │  STT → NER → редакция аудио
           └─► сохранить результат в Redis

Клиент поллирует:
GET /transcriptions/redact/{job_id}
  └─► queued → started → done / failed
```

---

## API Endpoints

### POST /transcriptions/redact

Загрузить аудиофайл и запустить обработку.

**Rate limit:** 5 запросов в минуту с одного IP.

**Request:**

```
Content-Type: multipart/form-data
```

| Поле | Тип | Описание |
|------|-----|----------|
| file | File | Аудиофайл (.mp3, .wav, .ogg, .m4a, .flac, .webm) |

**Response `201 Created`:**

```json
{
  "job_id": "f00e2ac9-6228-427e-a5a8-077fe9952908",
  "status": "created"
}
```

**Errors:**

| Код | Причина |
|-----|---------|
| 400 | Неподдерживаемый формат файла |
| 429 | Превышен rate limit (5/мин) |

**Пример:**

```bash
curl -X POST http://localhost:8000/transcriptions/redact \
  -F "file=@audio.wav"
```

---

### GET /transcriptions/redact/{job_id}

Получить статус и результат обработки.

**Path параметры:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| job_id | string (UUID) | ID из POST /redact |

**Response — в процессе:**

```json
{ "status": "queued" }
```

```json
{ "status": "started" }
```

**Response `200` — завершён:**

```json
{
  "status": "done",
  "original_transcript": "Привет меня зовут Иван Иванов, мой телефон 89991234567",
  "redacted_transcript": "Привет меня зовут [ИМЯ] [ФАМИЛИЯ], мой телефон [ТЕЛЕФОН]",
  "entities": [
    {
      "type": "PERSON",
      "text": "Иван Иванов",
      "start_char": 20,
      "end_char": 31,
      "start_sec": 1.2,
      "end_sec": 2.4
    },
    {
      "type": "PHONE",
      "text": "89991234567",
      "start_char": 45,
      "end_char": 56,
      "start_sec": 3.1,
      "end_sec": 4.0
    }
  ],
  "redacted_audio_url": "app/static/output/<job_id>/redacted.mp3",
  "log": [
    {"type": "PERSON", "text": "Иван Иванов", "replaced_with": "[ИМЯ] [ФАМИЛИЯ]"},
    {"type": "PHONE", "text": "89991234567", "replaced_with": "[ТЕЛЕФОН]"}
  ]
}
```

**Response — ошибка:**

```json
{
  "status": "failed",
  "error": "Traceback (most recent call last): ..."
}
```

**Errors:**

| Код | Причина |
|-----|---------|
| 404 | Джоб не найден |
| 500 | Джоб завершён но результат пустой |

**Пример:**

```bash
curl http://localhost:8000/transcriptions/redact/f00e2ac9-6228-427e-a5a8-077fe9952908
```

---

### GET /transcriptions/redact/{job_id}/audio

Скачать редактированный аудиофайл.

**Path параметры:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| job_id | string (UUID) | ID завершённого джоба |

**Response `200`:**

```
Content-Type: audio/mpeg
Body: бинарный аудиофайл
```

**Errors:**

| Код | Причина |
|-----|---------|
| 400 | Джоб ещё не завершён |
| 404 | Аудиофайл не найден на диске |
| 500 | Результат джоба пустой |

**Пример:**

```bash
curl -O http://localhost:8000/transcriptions/redact/f00e2ac9-6228-427e-a5a8-077fe9952908/audio
```

---

### GET /transcriptions/redact/{job_id}/log

Получить отчёт по типам найденных ПДн.

**Path параметры:**

| Параметр | Тип | Описание |
|----------|-----|----------|
| job_id | string (UUID) | ID завершённого джоба |

**Response `200`:**

```json
{
  "job_id": "f00e2ac9-6228-427e-a5a8-077fe9952908",
  "total_redacted": 2,
  "by_type": {
    "PERSON": ["Иван Иванов"],
    "PHONE": ["89991234567"]
  }
}
```

**Errors:**

| Код | Причина |
|-----|---------|
| 400 | Джоб ещё не завершён |
| 500 | Результат джоба пустой |

---

## Схемы данных

### PDEntityResponse

| Поле | Тип | Описание |
|------|-----|----------|
| type | string | Тип ПДн: `PERSON`, `PHONE`, `EMAIL`, `PASSPORT`, `INN`, `SNILS`, `ADDRESS` |
| text | string | Оригинальный текст сущности |
| start_char | int | Позиция начала в транскрипте (символы) |
| end_char | int | Позиция конца в транскрипте (символы) |
| start_sec | float | Начало во времени аудио (секунды) |
| end_sec | float | Конец во времени аудио (секунды) |

### RedactionResponse

| Поле | Тип | Описание |
|------|-----|----------|
| status | string | `queued` / `started` / `done` / `failed` |
| original_transcript | string \| null | Оригинальный транскрипт |
| redacted_transcript | string \| null | Транскрипт с заменёнными ПДн |
| entities | PDEntityResponse[] | Список найденных сущностей |
| redacted_audio_url | string \| null | Путь к редактированному аудио |
| log | dict[] | Лог замен |

---

## Жизненный цикл джоба

```
created → queued → started → done
                           ↘ failed
```

| Статус | Описание |
|--------|----------|
| created | Файл принят, джоб поставлен в очередь |
| queued | Ожидает свободного воркера |
| started | Воркер обрабатывает |
| done | Успешно завершён, результат доступен |
| failed | Ошибка при обработке, текст ошибки в поле `error` |

---

## Что нужно реализовать

Функция `app/utils/processor.py::process_audio_file` сейчас заглушка. Нужно реализовать:

1. **STT** — транскрибировать аудио (Groq Whisper / QWEN через `QWEN_API_URL`)
2. **NER** — найти ПДн в тексте (Gemini / QWEN)
3. **Редакция аудио** — заглушить временные отрезки (`start_sec` → `end_sec`)

Функция принимает:

```python
def process_audio_file(input_path: str, output_path: str) -> dict:
```

И должна вернуть:

```python
{
    "original_transcript": str,
    "redacted_transcript": str,
    "entities": [
        {
            "type": str,        # PERSON / PHONE / EMAIL / PASSPORT / INN / SNILS / ADDRESS
            "text": str,
            "start_char": int,
            "end_char": int,
            "start_sec": float,
            "end_sec": float,
        }
    ],
    "redacted_audio_path": str,  # путь к выходному файлу
    "log": [
        {"type": str, "text": str, "replaced_with": str}
    ]
}
```

---
 
### GET /transcriptions/history
 
Получить пагинированную историю всех обработанных файлов, отсортированную от новых к старым.
 
**Query параметры:**
 
| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| page | int | `1` | Номер страницы (от 1) |
| page_size | int | `20` | Элементов на странице (макс. 100) |
| entity_type | string | — | Фильтр по типу ПДн: `PERSON`, `PHONE`, `EMAIL`, `ADDRESS`, `INN`, `SNILS`, `PASPORT` |
 
**Response `200`:**
 
```json
{
  "total": 42,
  "page": 1,
  "page_size": 20,
  "pages": 3,
  "items": [
    {
      "job_id": "f00e2ac9-6228-427e-a5a8-077fe9952908",
      "filename": "interview.wav",
      "created_at": "2025-04-19T14:32:01.123456+00:00",
      "duration_sec": 8.3,
      "total_redacted": 2,
      "entity_types": ["PERSON", "PHONE"],
      "status": "done"
    }
  ]
}
```
 
**Пример — все записи:**
 
```bash
curl http://localhost:8000/transcriptions/history
```
 
**Пример — только файлы с номерами телефонов, вторая страница:**
 
```bash
curl "http://localhost:8000/transcriptions/history?entity_type=PHONE&page=2&page_size=10"
```
 
---
 
### GET /transcriptions/history/{job_id}
 
Получить одну запись истории по ID джоба.
 
**Path параметры:**
 
| Параметр | Тип | Описание |
|----------|-----|----------|
| job_id | string (UUID) | ID джоба |
 
**Response `200`:**
 
```json
{
  "job_id": "f00e2ac9-6228-427e-a5a8-077fe9952908",
  "filename": "interview.wav",
  "created_at": "2025-04-19T14:32:01.123456+00:00",
  "duration_sec": 8.3,
  "total_redacted": 2,
  "entity_types": ["PERSON", "PHONE"],
  "status": "done"
}
```
 
**Errors:**
 
| Код | Причина |
|-----|---------|
| 404 | Запись не найдена |
 
**Пример:**
 
```bash
curl http://localhost:8000/transcriptions/history/f00e2ac9-6228-427e-a5a8-077fe9952908
```
 
---
 
### DELETE /transcriptions/history/{job_id}
 
Удалить запись из истории. Не затрагивает RQ-джоб и файлы на диске.
 
**Path параметры:**
 
| Параметр | Тип | Описание |
|----------|-----|----------|
| job_id | string (UUID) | ID джоба |
 
**Response `204 No Content`**
 
**Errors:**
 
| Код | Причина |
|-----|---------|
| 404 | Запись не найдена |
 
**Пример:**
 
```bash
curl -X DELETE http://localhost:8000/transcriptions/history/f00e2ac9-6228-427e-a5a8-077fe9952908
```
 
---
 
## Схемы данных
 
### PDEntityResponse
 
| Поле | Тип | Описание |
|------|-----|----------|
| type | string | Тип ПДн: `PERSON`, `PHONE`, `EMAIL`, `PASSPORT`, `INN`, `SNILS`, `ADDRESS` |
| text | string | Оригинальный текст сущности |
| start_char | int | Позиция начала в транскрипте (символы) |
| end_char | int | Позиция конца в транскрипте (символы) |
| start_sec | float | Начало во времени аудио (секунды) |
| end_sec | float | Конец во времени аудио (секунды) |
 
### RedactionResponse
 
| Поле | Тип | Описание |
|------|-----|----------|
| status | string | `queued` / `started` / `done` / `failed` |
| original_transcript | string \| null | Оригинальный транскрипт |
| redacted_transcript | string \| null | Транскрипт с заменёнными ПДн |
| entities | PDEntityResponse[] | Список найденных сущностей |
| duration_sec | float \| null | Длительность аудио в секундах |
| redacted_audio_url | string \| null | Путь к редактированному аудио |
| log | dict[] | Лог замен |
 
### HistoryEntry
 
| Поле | Тип | Описание |
|------|-----|----------|
| job_id | string | Уникальный идентификатор джоба |
| filename | string | Оригинальное имя загруженного файла |
| created_at | string | Дата и время завершения в формате ISO-8601 UTC |
| duration_sec | float | Длительность аудио в секундах |
| total_redacted | int | Суммарное количество найденных ПДн |
| entity_types | string[] | Уникальные типы ПДн, обнаруженные в файле |
| status | string | `done` / `failed` |
 
---
 
## Жизненный цикл джоба
 
```
created → queued → started → done ──► history entry saved
                           ↘ failed
```
 
| Статус | Описание |
|--------|----------|
| created | Файл принят, джоб поставлен в очередь |
| queued | Ожидает свободного воркера |
| started | Воркер обрабатывает |
| done | Успешно завершён, результат доступен, запись добавлена в историю |
| failed | Ошибка при обработке, текст ошибки в поле `error` |
 
> **Хранение истории:** записи хранятся в Redis 90 дней и автоматически удаляются. Для ручного удаления использовать
`DELETE /transcriptions/history/{job_id}`.
 
---

---

## Структура проекта

```
tulahack2026/
├── .env                                # переменные окружения
├── .dockerignore
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── uv.lock
└── app/
    ├── main.py                         # FastAPI app, middleware, роутеры
    ├── api/
    │   └── v1/
    │       └── endpoints/
    │           └── transcriptions.py   # все эндпоинты
    ├── core/
    │   └── config.py                   # Settings (pydantic-settings)
    ├── schemas/
    │   └── transcriptions.py           # PDEntityResponse, RedactionResponse
    ├── utils/
    │   ├── processor.py                # ← СЮДА писать логику STT + NER + редакция
    │   ├── tasks.py                    # process_job — RQ задача
    │   ├── queue.py                    # get_queue()
    │   ├── redis_client.py             # get_redis()
    │   └── limiter.py                  # slowapi limiter
    └── static/
        ├── uploads/                    # входящие файлы
        └── output/                     # результаты обработки
```

---