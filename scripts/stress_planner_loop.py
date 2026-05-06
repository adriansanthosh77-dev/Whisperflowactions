from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from executors.base_executor import BaseExecutor
from executors.browser_executor import BrowserExecutor
from models.intent_schema import Context, IntentResult


HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Planner Stress</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 24px; }
      header { padding: 24px; background: #f3f6fb; }
      main { margin-top: 18px; }
      [contenteditable="true"] { border: 1px solid #888; min-height: 34px; padding: 8px; width: 300px; }
      button { padding: 8px 12px; margin-top: 10px; }
    </style>
  </head>
  <body>
    <header>
      <h1>Changed Composer</h1>
      <p>This page intentionally avoids old selectors.</p>
    </header>
    <main role="main">
      <section aria-label="Composer surface">
        <div role="textbox" aria-label="Message Body" contenteditable="true"></div>
        <button aria-label="Send">Deliver</button>
      </section>
      <div id="status"></div>
    </main>
    <script>
      document.querySelector('[aria-label="Send"]').onclick = () => {
        const text = document.querySelector('[aria-label="Message Body"]').innerText;
        document.querySelector('#status').textContent = text.includes('hello planner') ? 'sent' : 'wrong text';
      };
    </script>
  </body>
</html>
"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_content(HTML)

        BaseExecutor._playwright = p
        BaseExecutor._browser = browser
        BaseExecutor._context = context

        executor = BrowserExecutor()
        intent = IntentResult(
            intent="browser_action",
            app="browser",
            raw_text='type "hello planner" in the message body and send',
            data={
                "goal": 'type "hello planner" in the message body and send',
                "action": "auto",
                "expected_text": "sent",
                "max_steps": 5,
            },
        )
        success, message = executor.adaptive_browser_task(intent, Context())
        print(success, message)
        print(page.locator("#status").inner_text())
        context.close()
        browser.close()
        if not success:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
