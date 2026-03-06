<script>
  let code = `def hello(name: str) -> None:
    print(f"Hello, {name}!")
`;

  let filename = "example.py";
  let language = "python";
  let loading = false;
  let error = "";
  let result = null;
  let displayMessage = "";

  const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

  async function analyze() {
    loading = true;
    error = "";
    result = null;

    try {
      const res = await fetch(`${API_URL}/analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ code, filename, language })
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      result = await res.json();

      const fullMessage = result?.message ?? "";
      const openAiErrorPrefix = "Не удалось выполнить запрос к модели OpenAI";
      const localMarker = "Выполнен локальный анализ кода:";

      if (fullMessage.startsWith(openAiErrorPrefix)) {
        console.warn(fullMessage);
        const idx = fullMessage.indexOf(localMarker);
        if (idx !== -1) {
          displayMessage = fullMessage.slice(idx + localMarker.length).trim();
        } else {
          displayMessage = fullMessage;
        }
      } else {
        displayMessage = fullMessage;
      }
    } catch (e) {
      error = e?.message ?? "Неизвестная ошибка";
    } finally {
      loading = false;
    }
  }
</script>

<main>
  <h1>AI Code Review — прототип</h1>

  <section class="form">
    <div class="field">
      <label>Имя файла (опционально)</label>
      <input bind:value={filename} placeholder="example.py" />
    </div>

    <div class="field">
      <label>Язык (опционально)</label>
      <input bind:value={language} placeholder="python / js / ts ..." />
    </div>

    <div class="field">
      <label>Код</label>
      <textarea bind:value={code} rows="10" spellcheck="false" />
    </div>

    <button on:click={analyze} disabled={loading}>
      {#if loading}
        Анализ...
      {:else}
        Запустить анализ
      {/if}
    </button>

    {#if error}
      <p class="error">Ошибка: {error}</p>
    {/if}
  </section>

  {#if result}
    <section class="result">
      <h2>Результат анализа</h2>
      <ul>
        {#if result.filename}
          <li><strong>Файл:</strong> {result.filename}</li>
        {/if}
        {#if result.language}
          <li><strong>Язык:</strong> {result.language}</li>
        {/if}
        <li><strong>Строк:</strong> {result.lines}</li>
        <li><strong>Символов:</strong> {result.characters}</li>
      </ul>
      <p>{displayMessage}</p>
    </section>
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #050816;
    color: #e5e7eb;
  }

  main {
    max-width: 960px;
    margin: 0 auto;
    padding: 2rem 1.25rem 3rem;
  }

  h1 {
    font-size: 1.8rem;
    margin-bottom: 1.5rem;
  }

  .form,
  .result {
    background: radial-gradient(circle at top left, #1f2937, #020617);
    border-radius: 1rem;
    padding: 1.5rem;
    box-shadow: 0 18px 40px rgba(0, 0, 0, 0.65);
    border: 1px solid rgba(148, 163, 184, 0.25);
    backdrop-filter: blur(18px);
  }

  .form {
    margin-bottom: 1.5rem;
  }

  .field {
    margin-bottom: 1rem;
  }

  label {
    display: block;
    margin-bottom: 0.3rem;
    font-size: 0.9rem;
    color: #9ca3af;
  }

  input,
  textarea {
    width: 100%;
    box-sizing: border-box;
    border-radius: 0.6rem;
    border: 1px solid #4b5563;
    padding: 0.55rem 0.75rem;
    font-size: 0.95rem;
    background: rgba(15, 23, 42, 0.95);
    color: #e5e7eb;
    outline: none;
  }

  input:focus,
  textarea:focus {
    border-color: #38bdf8;
    box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.6);
  }

  textarea {
    resize: vertical;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
      "Courier New", monospace;
    line-height: 1.4;
  }

  button {
    margin-top: 0.25rem;
    padding: 0.55rem 1.2rem;
    border-radius: 999px;
    border: none;
    background: linear-gradient(135deg, #22c55e, #3b82f6);
    color: white;
    font-weight: 600;
    cursor: pointer;
    font-size: 0.95rem;
    box-shadow: 0 14px 30px rgba(37, 99, 235, 0.55);
  }

  button:disabled {
    opacity: 0.6;
    cursor: default;
    box-shadow: none;
  }

  .error {
    margin-top: 0.5rem;
    color: #f97373;
    font-size: 0.9rem;
  }

  .result h2 {
    margin-top: 0;
    margin-bottom: 0.75rem;
    font-size: 1.2rem;
  }

  .result ul {
    list-style: none;
    padding: 0;
    margin: 0 0 0.75rem;
    font-size: 0.95rem;
  }

  .result li + li {
    margin-top: 0.25rem;
  }
</style>

