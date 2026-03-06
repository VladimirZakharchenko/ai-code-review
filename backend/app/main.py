from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
from pyflakes.api import check as pyflakes_check
from pyflakes.reporter import Reporter
from mypy import api as mypy_api
import os
import ast
import io
import subprocess
import tempfile
from pathlib import Path


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
    """
    Клиент LLM с поддержкой двух провайдеров:
    - GenAPI (через GEN_API_KEY и GEN_API_BASE_URL, например GPT-4.1 от GenAPI);
    - прямой OpenAI (через OPENAI_API_KEY), если GenAPI не сконфигурирован.
    """
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    gen_api_key = os.getenv("GEN_API_KEY")
    gen_api_base_url = os.getenv("GEN_API_BASE_URL")

    if gen_api_key and gen_api_base_url:
        _openai_client = AsyncOpenAI(
            api_key=gen_api_key,
            base_url=gen_api_base_url,
        )
        return _openai_client

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set and GEN_API_KEY/GEN_API_BASE_URL are not configured"
        )
    _openai_client = AsyncOpenAI(api_key=api_key)
    return _openai_client


def _local_code_analysis(code: str, language: str | None, filename: str | None) -> str:
    """
    Простейший офлайн-анализ кода без LLM.
    Даёт базовые метрики и подсказки по стилю.
    """
    if not code:
        return "Код отсутствует — ничего анализировать."

    lines = code.splitlines()
    total = len(lines)
    blank = sum(1 for l in lines if not l.strip())

    lang = (language or "").lower()
    filename = filename or ""
    if lang in {"python", "py"}:
        comment_prefixes = ("#",)
    elif lang in {"js", "ts", "javascript", "typescript", "java", "c", "cpp", "c++", "c#", "go", "rust"}:
        comment_prefixes = ("//",)
    else:
        comment_prefixes = ("#", "//")

    comment_lines = sum(1 for l in lines if l.lstrip().startswith(comment_prefixes))
    long_lines = [i + 1 for i, l in enumerate(lines) if len(l) > 100]
    todo_markers = sum(1 for l in lines if "TODO" in l or "FIXME" in l)

    # Анализ отступов
    indent_widths: list[int] = []
    mixed_indent = False
    for l in lines:
        if not l.strip():
            continue
        leading = len(l) - len(l.lstrip("\t "))
        if leading:
            indent_widths.append(leading)
        if ("\t" in l[: leading]) and (" " in l[: leading]):
            mixed_indent = True
    max_indent = max(indent_widths) if indent_widths else 0

    tab_indents = sum(1 for l in lines if l.startswith("\t"))

    parts: list[str] = []
    parts.append(
        f"Строк всего: {total}, пустых строк: {blank}, строк с комментариями: {comment_lines}."
    )

    # Сопоставление языка и расширения файла
    if filename:
        ext = Path(filename).suffix.lower()
        ext_lang_map = {
            ".py": "python",
            ".pyw": "python",
            ".js": "javascript",
            ".mjs": "javascript",
            ".cjs": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cs": "c#",
            ".cpp": "c++",
            ".cc": "c++",
            ".cxx": "c++",
            ".h": "c",
            ".hpp": "c++",
            ".rb": "ruby",
            ".php": "php",
        }
        ext_lang = ext_lang_map.get(ext)
        if ext_lang and lang and lang != ext_lang:
            parts.append(
                "Несоответствие языка и расширения файла: "
                f"указан язык '{lang}', файл '{filename}' (расширение предполагает '{ext_lang}')."
            )

    if indent_widths:
        parts.append(f"Максимальная глубина отступа: {max_indent} символов.")
    if mixed_indent:
        parts.append(
            "Обнаружены смешанные отступы (табы и пробелы вместе). Лучше выбрать единый стиль."
        )
    if tab_indents:
        parts.append(
            "В коде встречаются табы для отступов. Лучше придерживаться единообразных пробелов "
            "(например, 4 пробела на уровень)."
        )

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

    # Дополнительный анализ для Python: неиспользуемые переменные и строки-«no-op»
    py_unused: list[str] = []
    py_noops: list[int] = []
    pyflakes_issues: list[str] = []
    mypy_issues: list[str] = []
    ruff_issues: list[str] = []
    if lang in {"python", "py"}:
        try:
            tree = ast.parse(code)
            assigned: set[str] = set()
            used: set[str] = set()

            class VarVisitor(ast.NodeVisitor):
                def visit_Name(self, node: ast.Name) -> None:
                    if isinstance(node.ctx, ast.Store):
                        if not node.id.startswith("_"):
                            assigned.add(node.id)
                    elif isinstance(node.ctx, ast.Load):
                        used.add(node.id)
                    self.generic_visit(node)

                def visit_Expr(self, node: ast.Expr) -> None:
                    # Строки, которые ничего не делают (не docstring)
                    if isinstance(node.value, ast.Constant) and isinstance(
                        node.value.value, str
                    ):
                        # docstring обычно первый Statement в модуле/функции/классе — пропускаем
                        py_noops.append(node.lineno)
                    self.generic_visit(node)

            VarVisitor().visit(tree)
            unused = sorted(assigned - used)
            if unused:
                py_unused = unused

            # Запуск pyflakes поверх кода
            buffer = io.StringIO()
            reporter = Reporter(buffer, buffer)
            # filename нужен только для сообщений, можно использовать фиктивное
            pyflakes_check(code, filename="<analyzed_code>", reporter=reporter)
            raw = buffer.getvalue().strip()
            if raw:
                pyflakes_issues = [line for line in raw.splitlines() if line.strip()]

            # Запуск mypy на временном файле
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir) / "snippet.py"
                tmp_path.write_text(code, encoding="utf-8")
                out, err, status = mypy_api.run(
                    [
                        str(tmp_path),
                        "--ignore-missing-imports",
                        "--follow-imports=skip",
                    ]
                )
                combined = (out or "") + (err or "")
                combined = combined.strip()
                if combined:
                    # Фильтруем только строки про snippet.py
                    mypy_issues = [
                        line for line in combined.splitlines() if "snippet.py" in line
                    ]

            # Запуск ruff на том же временном файле
            try:
                result = subprocess.run(
                    ["ruff", "check", str(tmp_path), "--quiet"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                ruff_out = (result.stdout or "").strip()
                if ruff_out:
                    ruff_issues = [
                        line for line in ruff_out.splitlines() if line.strip()
                    ]
            except Exception:
                # Если ruff недоступен или упал — игнорируем
                pass
        except SyntaxError as exc:
            # Код не парсится как Python — возможно, ошибка синтаксиса или неверно указан язык
            parts.append(
                "Код не удалось разобрать как Python (SyntaxError). "
                "Проверьте синтаксис или корректность выбранного языка. "
                f"Детали: {exc}."
            )

    if py_unused:
        parts.append(
            "Возможные неиспользуемые переменные: "
            + ", ".join(py_unused)
            + ". Рассмотрите возможность их удаления или использования."
        )
    if py_noops:
        sample = ", ".join(map(str, sorted(set(py_noops))[:10]))
        parts.append(
            "Обнаружены строковые литералы, которые ничего не делают (не docstring). "
            f"Проверьте строки: {sample}."
        )

    if pyflakes_issues:
        parts.append("Замечания pyflakes (анализ Python-кода):")
        parts.extend(f"- {issue}" for issue in pyflakes_issues)
    if mypy_issues:
        parts.append("Замечания mypy (проверка типов):")
        parts.extend(f"- {issue}" for issue in mypy_issues)
    if ruff_issues:
        parts.append("Замечания ruff (линтинг):")
        parts.extend(f"- {issue}" for issue in ruff_issues)

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

    # Вызов LLM-провайдера (OpenAI / GenAPI) для анализа кода
    model_message = ""
    try:
        client = _get_openai_client()
        # Модель можно переопределить через GEN_API_MODEL (для GenAPI)
        # или другую переменную окружения, иначе используется дефолт.
        model_name = os.getenv("GEN_API_MODEL") or "gpt-4.1-mini"
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
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=400,
        )
        model_message = completion.choices[0].message.content or ""
    except Exception as exc:
        # Если провайдер LLM недоступен, выполняем самописный локальный анализ
        local_report = _local_code_analysis(code, payload.language, payload.filename)
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
