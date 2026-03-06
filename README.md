## Прототип AI-агента для анализа кода

Минимальный каркас:
- **backend**: FastAPI, эндпоинт `/analyze`
- **frontend**: Svelte (Vite), форма отправки кода на анализ
- **запуск**: через Docker и `docker-compose`

### Структура

- `backend/app/main.py` — FastAPI-приложение
- `backend/requirements.txt` — зависимости backend
- `backend/Dockerfile` — образ API
- `frontend/` — Svelte-приложение (Vite)
- `frontend/Dockerfile` — образ frontend
- `docker-compose.yml` — запуск двух сервисов

### Как запустить

```bash
cd /ai-code-review
docker compose build
docker compose up
```

После запуска:

- Backend (Swagger UI): `http://localhost:8000/docs`
- Frontend UI: `http://localhost:4173`

### Настройка OpenAI

Backend использует OpenAI Chat Completions API.

Минимальная настройка через переменные окружения (на хосте, до `docker compose up`):

```bash
export OPENAI_API_KEY="ваш_ключ_OpenAI"
```

### Проверка API напрямую

```bash
curl -X POST "http://localhost:8000/analyze" \
  -H "Content-Type: application/json" \
  -d '{"code": "print(123)", "filename": "test.py", "language": "python"}'
```

