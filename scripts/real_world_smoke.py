from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from executors.base_executor import BaseExecutor


TARGETS = [
    {
        "name": "example",
        "url": "https://example.com",
        "expect_heading": True,
    },
    {
        "name": "wikipedia",
        "url": "https://www.wikipedia.org",
        "search_labels": ["Search Wikipedia", "Search"],
        "search_text": "OpenAI",
        "click_labels": ["Search"],
    },
    {
        "name": "hacker_news",
        "url": "https://news.ycombinator.com",
        "click_labels": ["new"],
    },
]


def main():
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        for target in TARGETS:
            try:
                page.goto(target["url"], wait_until="domcontentloaded", timeout=20000)
                dom = BaseExecutor.observe_page(page)
                structure = dom.get("appStructure", {})
                element_count = len(dom.get("elements", []))
                if element_count == 0:
                    raise AssertionError("no visible actionable elements found")
                if target.get("expect_heading") and not structure.get("headings"):
                    raise AssertionError("expected headings in app structure")

                strategies = []
                if target.get("search_labels"):
                    strategies.append(BaseExecutor.fill_resilient(
                        page,
                        target["search_text"],
                        labels=target["search_labels"],
                        timeout=2500,
                    ))
                if target.get("click_labels"):
                    strategies.append(BaseExecutor.click_resilient(
                        page,
                        labels=target["click_labels"],
                        timeout=2500,
                    ))

                print(
                    f"PASS {target['name']} elements={element_count} "
                    f"headings={len(structure.get('headings', []))} strategies={strategies}"
                )
            except Exception as exc:
                shot = BaseExecutor.capture_screenshot(page, f"real_world_{target['name']}")
                failures.append(f"{target['name']}: {exc} screenshot={shot}")
                print(f"FAIL {target['name']}: {exc}")

        context.close()
        browser.close()

    if failures:
        print("FAILURES")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print("REAL WORLD SMOKE PASSED")


if __name__ == "__main__":
    main()
