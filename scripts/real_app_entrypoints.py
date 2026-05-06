from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from executors.base_executor import BaseExecutor


TARGETS = [
    ("gmail", "https://mail.google.com"),
    ("whatsapp", "https://web.whatsapp.com"),
]


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        for name, url in TARGETS:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                dom = BaseExecutor.observe_page(page)
                structure = dom.get("appStructure", {})
                title = dom.get("title", "")
                elements = dom.get("elements", [])
                print(
                    f"ENTRY {name} title={title!r} "
                    f"elements={len(elements)} headings={len(structure.get('headings', []))} "
                    f"forms={len(structure.get('forms', []))}"
                )
            except Exception as exc:
                shot = BaseExecutor.capture_screenshot(page, f"entry_{name}")
                print(f"ENTRY_FAIL {name}: {exc} screenshot={shot}")
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
