from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from core.feedback_store import FeedbackStore
from executors.base_executor import BaseExecutor
from models.intent_schema import Context, IntentResult


def page_template(body: str) -> str:
    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <title>Stress Fixture</title>
        <style>
          body {{ font-family: Arial, sans-serif; margin: 0; }}
          header, main, section, form {{ padding: 16px; }}
          .hero {{ min-height: 220px; background: #f4f7fb; }}
          .row {{ display: flex; gap: 10px; align-items: center; margin: 8px 0; }}
          [contenteditable="true"], input, textarea {{
            min-width: 260px; min-height: 32px; border: 1px solid #999; padding: 6px;
          }}
          button, [role="button"] {{ padding: 8px 12px; margin: 4px; cursor: pointer; }}
          #status {{ margin-top: 12px; font-weight: bold; }}
        </style>
      </head>
      <body>{body}</body>
    </html>
    """


FIXTURES = [
    {
        "name": "gmail_role_text_changed_selectors",
        "html": page_template("""
          <header class="hero"><h1>Inbox</h1><p>Top app section changed.</p></header>
          <main role="main">
            <div role="button" aria-label="Compose">New mail</div>
            <form aria-label="message composer">
              <input aria-label="Recipients" />
              <input aria-label="Subject" />
              <div role="textbox" aria-label="Message Body" contenteditable="true"></div>
              <div role="button" aria-label="Send">Launch message</div>
            </form>
            <div id="status"></div>
          </main>
          <script>
            document.querySelector('[aria-label="Send"]').onclick = () => {
              document.querySelector('#status').textContent = 'sent';
            };
          </script>
        """),
        "steps": [
            ("click", {"labels": ["Compose"], "selectors": ["#missing-compose"]}),
            ("fill", {"labels": ["Recipients", "To"], "selectors": ["#missing-to"], "value": "a@example.com"}),
            ("fill", {"labels": ["Message Body", "Body"], "selectors": ["#missing-body"], "value": "hello"}),
            ("click", {"labels": ["Send"], "selectors": ["#missing-send"]}),
        ],
        "expect": "sent",
    },
    {
        "name": "whatsapp_dom_mouse_changed_labels",
        "html": page_template("""
          <main>
            <h1>Chats</h1>
            <section role="search" aria-label="Search chats">
              <div contenteditable="true" aria-label="Search or start new chat"></div>
            </section>
            <button title="Adrian Santhosh">Adrian Santhosh</button>
            <section aria-label="Conversation">
              <div contenteditable="true" aria-label="Type a message"></div>
              <button aria-label="Send message now">Paper plane</button>
            </section>
            <div id="status"></div>
          </main>
          <script>
            document.querySelector('[aria-label="Send message now"]').onclick = () => {
              document.querySelector('#status').textContent = 'message sent';
            };
          </script>
        """),
        "steps": [
            ("fill", {"labels": ["Search", "Search or start new chat"], "selectors": ["#old-search"], "value": "Adrian"}),
            ("click", {"labels": ["Adrian Santhosh"], "selectors": ["#old-contact"]}),
            ("fill", {"labels": ["Type a message", "Message"], "selectors": ["#old-message"], "value": "on my way"}),
            ("click", {"labels": ["Send", "Send message"], "selectors": ["#old-send"]}),
        ],
        "expect": "message sent",
    },
    {
        "name": "hero_app_structure_detection",
        "html": page_template("""
          <header class="hero">
            <h1>Jarvis Console</h1>
            <p>Adaptive hero section with changed layout.</p>
            <button data-testid="primary-action">Start</button>
          </header>
          <main><section><h2>Tasks</h2><button>Review queue</button></section></main>
          <div id="status"></div>
          <script>
            document.querySelector('[data-testid="primary-action"]').onclick = () => {
              document.querySelector('#status').textContent = 'started';
            };
          </script>
        """),
        "steps": [
            ("click", {"labels": ["Start"], "selectors": ["#gone"]}),
        ],
        "expect": "started",
        "require_structure": True,
    },
]


def run_step(page, action, payload):
    if action == "click":
        return BaseExecutor.click_resilient(
            page,
            selectors=payload.get("selectors", []),
            labels=payload.get("labels", []),
            timeout=1000,
        )
    if action == "fill":
        return BaseExecutor.fill_resilient(
            page,
            value=payload["value"],
            selectors=payload.get("selectors", []),
            labels=payload.get("labels", []),
            timeout=1000,
            press_ctrl_a=False,
        )
    raise ValueError(action)


def main():
    failures = []
    db = FeedbackStore(ROOT / "data" / "stress_feedback.db")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(record_video_dir=str(ROOT / "data" / "stress_videos"))
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()

        for fixture in FIXTURES:
            BaseExecutor.consume_action_events()
            page.set_content(fixture["html"])
            dom_before = BaseExecutor.observe_page(page)
            strategies = []
            try:
                for action, payload in fixture["steps"]:
                    strategies.append(run_step(page, action, payload))
                status = page.locator("#status").inner_text(timeout=1000)
                dom_after = BaseExecutor.observe_page(page)
                structure = dom_after.get("appStructure", {})
                if fixture.get("require_structure") and not structure.get("topSections"):
                    raise AssertionError("topSections missing from DOM structure")
                if status != fixture["expect"]:
                    raise AssertionError(f"expected {fixture['expect']}, got {status}")

                intent = IntentResult(
                    intent="browser_action",
                    app="browser",
                    raw_text=f"stress {fixture['name']}",
                )
                sid = db.log(
                    intent,
                    True,
                    "stress ok",
                    Context(dom=dom_before),
                    dom_before,
                    dom_after,
                )
                db.log_ui_action_events(sid, BaseExecutor.consume_action_events())
                db.log_page_snapshot(sid, dom_after)
                print(f"PASS {fixture['name']} -> {strategies}")
            except Exception as exc:
                shot = BaseExecutor.capture_screenshot(page, f"stress_{fixture['name']}")
                failures.append(f"{fixture['name']}: {exc} screenshot={shot}")
                print(f"FAIL {fixture['name']}: {exc}")

        trace_path = ROOT / "data" / "stress_trace.zip"
        context.tracing.stop(path=str(trace_path))
        context.close()
        browser.close()

    hints = db.get_learning_hints(10)
    db.close()
    print("HINTS")
    for hint in hints:
        print(f"- {hint}")

    if failures:
        print("FAILURES")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("ALL STRESS TESTS PASSED")


if __name__ == "__main__":
    main()
