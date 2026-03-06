from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
import os


class AnalyzeRequest(BaseModel):
    filename: str | None = None
    language: str | None = None
    code: str


class AnalyzeResponse(BaseModel):
    filename: str | None = None
    language: str | None = None
    lines: int
    characters: int
    message: str


_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        _openai_client = AsyncOpenAI(api_key=api_key)
    return _openai_client


def _local_code_analysis(code: str, language: str | None) -> str:
    """
    Простейший офлайн-анализ кода без LLM.
    Даёт базовые метрики и возможные подсказки.
    """
    if not code:
        return "Код отсутствует — ничего анализировать."

    lines = code.splitlines()
    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())

    lang = (language or "").lower()
    if lang in {"python", "py"}:
        comment_prefixes = ("#",)
    elif lang in {"js", "ts", "javascript", "typescript", "java", "c", "cpp", "c++", "c#", "go", "rust"}:
        comment_prefixes = ("//",)
    else:
        comment_prefixes = ("#", "//")

    comment_lines = sum(1 for l in lines if l.lstrip().startswith(comment_prefixes))
    long_lines = [i + 1 for i, l in enumerate(lines) if len(l) > 100]
    todo_markers = sum(1 for l in lines if "TODO" in l or "FIXME" in l)
    tab_indents = sum(1 for l in lines if "\t" in l)

    parts: list[str] = []
    parts.append(f"Строк всего: {total}, пустых строк: {blank}, строк с комментариями: {comment_lines}.")
    if long_lines:
        sample = ", ".join(map(str, long_lines[:10]))
        parts.append(
            f"Обнаружены очень длинные строки (>{100} символов) — например, строки: {sample}. "
            "Рекомендуется разбивать выражения на несколько строк."
        )
    if todo_markers:
        parts.append(
            f"Найдено пометок TODO/FIXME: {todo_markers}. "
            "Проверьте, не остались ли незавершённые места в коде."
        )
    if tab_indents:
        parts.append(
            "В коде встречаются табы для отступов. Лучше придерживаться единообразных пробелов "
            "(например, 4 пробела на уровень)."
        )
    if not long_lines and not todo_markers and not tab_indents:
        parts.append("Грубых стилистических проблем не обнаружено по простым эвристикам.")

    return "\n".join(parts)


app = FastAPI(title="AI Code Review Prototype", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_code(payload: AnalyzeRequest) -> AnalyzeResponse:
    code = payload.code or ""
    lines = len(code.splitlines()) if code else 0
    characters = len(code)

    # Вызов OpenAI для анализа кода
    model_message = ""
    try:
        client = _get_openai_client()
        system_prompt = (
            "Ты помощник для code review. "
            "Кратко оцени код, укажи потенциальные проблемы, читаемость и идеи улучшения. "
            "Пиши по-русски, 3–7 предложений."
        )

        user_prompt = (
            f"Файл: {payload.filename or 'N/A'}\n"
            f"Язык: {payload.language or 'не указан'}\n\n"
            f"Код:\n```{payload.language or ''}\n{code}\n```"
        )

        completion = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=400,
        )
        model_message = completion.choices[0].message.content or ""
    except Exception as exc:
        # Если модель недоступна, выполняем самописный локальный анализ
        local_report = _local_code_analysis(code, payload.language)
        model_message = (
            "Не удалось выполнить запрос к модели OpenAI ("
            f"{type(exc).__name__}: {exc}"
            "). Выполнен локальный анализ кода:\n\n"
            f"{local_report}"
        )

    return AnalyzeResponse(
        filename=payload.filename,
        language=payload.language,
        lines=lines,
        characters=characters,
        message=model_message,
    )


def create_app() -> FastAPI:
    return app
