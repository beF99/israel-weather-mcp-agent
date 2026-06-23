import re
from typing import Optional

from mcp.server.fastmcp import FastMCP
from playwright.async_api import Browser, BrowserContext, Page
from playwright.async_api import ElementHandle
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright


mcp = FastMCP("weather-Israel")

FORECAST_URL = "https://www.weather2day.co.il/forecast"

# מצב גלובלי של סשן הדפדפן בין קריאות הכלים.
_playwright = None
_browser: Optional[Browser] = None
_context: Optional[BrowserContext] = None
_page: Optional[Page] = None
_last_city: Optional[str] = None


def _debug(message: str) -> None:
    print(f"[weather-israel] {message}")


async def _ensure_browser_session() -> Page:
    """יוצר סשן דפדפן פעם אחת ומחזיר עמוד פעיל."""
    global _playwright, _browser, _context, _page

    if _page is not None:
        _debug("Reusing existing browser page session.")
        return _page

    _debug("Starting Playwright browser session.")
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(headless=False)
    _context = await _browser.new_context(locale="he-IL")
    _page = await _context.new_page()
    _debug("Browser session started.")
    return _page


def _clean_text(text: str) -> str:
    """ניקוי טקסט בסיסי כדי להחזיר למודל פלט קריא ושימושי."""
    cleaned = text.replace("\u200f", " ").replace("\u200e", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


async def _find_first_visible_input(page: Page):
    """מנסה לאתר שדה חיפוש עיר דרך רשימת סלקטורים עם fallback."""
    selectors = [
        'input[placeholder*="עיר"]:visible',
        'input[placeholder*="יישוב"]:visible',
        'input[placeholder*="חיפוש"]:visible',
        'input[aria-label*="עיר"]:visible',
        'input[aria-label*="חיפוש"]:visible',
        'input[id*="city"]:visible',
        'input[name*="city"]:visible',
        ".tt-input",
        'input[type="search"]:visible',
    ]

    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count() > 0:
                await locator.wait_for(state="visible", timeout=2500)
                return locator
        except Exception:
            continue

    # fallback בטוח: רק שדות גלויים בפועל
    fallback_visible = page.locator("input:visible").first
    if await fallback_visible.count() > 0:
        return fallback_visible

    return None


async def _dismiss_blocking_ui(page: Page) -> None:
    """מנסה לסגור שכבות שחוסמות אינטראקציה (כמו קוקיז/מודאלים)."""
    candidate_selectors = [
        'button:has-text("אישור")',
        'button:has-text("מסכים")',
        'button:has-text("הבנתי")',
        'button:has-text("סגור")',
        'button:has-text("Accept")',
        '[aria-label*="close"]',
        '[aria-label*="Close"]',
        ".close",
        ".modal-close",
        ".cookie-accept",
    ]

    for selector in candidate_selectors:
        try:
            btn = page.locator(selector).first
            if await btn.count() == 0:
                continue
            await btn.click(timeout=800, force=True)
            await page.wait_for_timeout(150)
        except Exception:
            continue


async def _select_best_input_handle(page: Page) -> Optional[ElementHandle]:
    """בחירה חכמה של שדה החיפוש המתאים ביותר להזנת עיר."""
    inputs = await page.query_selector_all("input")
    best_handle: Optional[ElementHandle] = None
    best_score = -1

    for handle in inputs:
        try:
            is_visible = await handle.is_visible()
            if not is_visible:
                continue

            disabled = await handle.get_attribute("disabled")
            readonly = await handle.get_attribute("readonly")
            if disabled is not None or readonly is not None:
                continue

            input_type = (await handle.get_attribute("type") or "text").lower()
            if input_type not in ("text", "search", ""):
                continue

            placeholder = (await handle.get_attribute("placeholder") or "").lower()
            aria_label = (await handle.get_attribute("aria-label") or "").lower()
            name = (await handle.get_attribute("name") or "").lower()
            input_id = (await handle.get_attribute("id") or "").lower()
            classes = (await handle.get_attribute("class") or "").lower()

            score = 0
            for token in ("עיר", "יישוב", "חיפוש", "city", "search"):
                if token in placeholder:
                    score += 6
                if token in aria_label:
                    score += 5
                if token in name:
                    score += 3
                if token in input_id:
                    score += 3

            for token in ("tt-input", "autocomplete", "autosuggest", "search"):
                if token in classes:
                    score += 2

            box = await handle.bounding_box()
            if box and box.get("width", 0) > 120 and box.get("height", 0) > 20:
                score += 2

            if score > best_score:
                best_score = score
                best_handle = handle
        except Exception:
            continue

    return best_handle


async def _click_first_city_option(page: Page):
    """בוחר פריט ראשון מרשימת ההצעות עם כמה אפשרויות fallback."""
    option_selectors = [
        '[role="option"]',
        ".tt-menu .tt-suggestion",
        ".tt-suggestion",
        "#city_list li",
        "#city_list a",
        ".autocomplete li",
        ".ui-autocomplete li",
        ".react-autosuggest__suggestions-list li",
        ".search-results li",
        "ul li",
    ]

    for selector in option_selectors:
        options = page.locator(selector)
        try:
            count = await options.count()
            if count == 0:
                continue

            first = options.first
            await first.wait_for(state="visible", timeout=2500)
            await first.click(timeout=5000)
            return True
        except Exception:
            continue

    return False


async def _click_city_option_by_text(page: Page, city: str) -> bool:
    """מנסה לבחור הצעה שמתאימה לשם העיר המבוקש."""
    city = (city or "").strip()
    if not city:
        return False

    option_selectors = [
        '[role="option"]',
        ".tt-menu .tt-suggestion",
        ".tt-suggestion",
        "#city_list li",
        "#city_list a",
        ".autocomplete li",
        ".ui-autocomplete li",
        ".react-autosuggest__suggestions-list li",
        ".search-results li",
        "ul li",
    ]

    for selector in option_selectors:
        options = page.locator(selector)
        try:
            count = await options.count()
            if count == 0:
                continue

            for i in range(min(count, 10)):
                candidate = options.nth(i)
                if not await candidate.is_visible():
                    continue
                text = (await candidate.inner_text(timeout=1000)).strip()
                if city in text or text in city:
                    await candidate.click(timeout=4000)
                    return True
        except Exception:
            continue

    return False


async def _has_visible_city_options(page: Page) -> bool:
    option_selectors = [
        '[role="option"]',
        ".tt-menu .tt-suggestion",
        ".tt-suggestion",
        "#city_list li",
        "#city_list a",
        ".autocomplete li",
        ".ui-autocomplete li",
        ".react-autosuggest__suggestions-list li",
        ".search-results li",
    ]

    for selector in option_selectors:
        try:
            options = page.locator(selector)
            count = await options.count()
            if count == 0:
                continue
            for i in range(min(count, 5)):
                if await options.nth(i).is_visible():
                    return True
        except Exception:
            continue
    return False


async def _wait_for_city_context(page: Page, city: Optional[str], timeout_ms: int = 7000) -> bool:
    """
    ממתין שהעמוד יעבור לקונטקסט עיר:
    או URL שונה מעמוד התחזית הראשי, או הופעת שם העיר בתוכן הדף.
    """
    city = (city or "").strip()
    deadline = timeout_ms / 1000
    start = 0.0

    # בדיקות מחזוריות במקום timeout קשיח על פעולה אחת.
    while start <= deadline:
        try:
            if page.url != FORECAST_URL:
                return True

            if city:
                body_text = await page.locator("body").inner_text(timeout=1200)
                if city in body_text:
                    return True
        except Exception:
            pass

        await page.wait_for_timeout(350)
        start += 0.35

    return False


@mcp.tool()
async def open_weather_forecast_israel() -> str:
    """פותח דפדפן ומנווט לעמוד התחזית בישראל. זה כלי פתיחה מומלץ לפני שאר הכלים."""
    try:
        page = await _ensure_browser_session()
        _debug("Opening forecast URL.")
        await page.goto(FORECAST_URL, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(1200)
        _debug(f"Page opened. Current URL: {page.url}")
        return "Weather Israel forecast page opened successfully."
    except PlaywrightTimeout:
        return "Timeout while opening weather site. Please try again."
    except Exception as e:
        return f"Failed to open weather site: {e}"


@mcp.tool()
async def enter_weather_forecast_city_israel(city: str) -> str:
    """מזין עיר לשדה החיפוש באתר התחזית הישראלי. מומלץ להפעיל אחרי open_weather_forecast_israel."""
    global _last_city

    if not city or not city.strip():
        return "City is required."

    page = await _ensure_browser_session()
    if not page.url.startswith(FORECAST_URL):
        _debug("Page not on forecast URL. Navigating automatically.")
        await page.goto(FORECAST_URL, wait_until="domcontentloaded", timeout=45000)

    try:
        await _dismiss_blocking_ui(page)
        await page.wait_for_timeout(400)

        input_handle = await _select_best_input_handle(page)
        if input_handle is None:
            input_box = await _find_first_visible_input(page)
            if input_box is not None:
                try:
                    await input_box.scroll_into_view_if_needed(timeout=1500)
                    await input_box.wait_for(state="visible", timeout=2500)
                except Exception:
                    pass
            else:
                return "Could not find city input field on weather page."
        else:
            await input_handle.scroll_into_view_if_needed()

        if input_handle is None and input_box is None:
            return "Could not find city input field on weather page."

        city = city.strip()
        _debug(f"Typing city into input: {city}")

        # אם המודל מנסה שוב אותה עיר וההצעות כבר פתוחות, לא מקלידים מחדש.
        if _last_city == city and await _has_visible_city_options(page):
            return f"City already typed and suggestions visible: {city}"

        typed_ok = False
        last_error = ""

        for attempt in range(1, 3):
            # ניסיון 1: דרך Locator רגיל (אם נמצא)
            if input_handle is None and input_box is not None:
                try:
                    await input_box.click(timeout=4500, force=True)
                    await input_box.fill("", timeout=3000)
                    await input_box.type(city, delay=85, timeout=6000)
                    typed_ok = True
                except Exception as e:
                    last_error = str(e)

            # ניסיון 2: דרך ElementHandle
            if not typed_ok and input_handle is not None:
                try:
                    await input_handle.click(timeout=4500)
                    await input_handle.fill("")
                    await input_handle.type(city, delay=85)
                    typed_ok = True
                except Exception as e:
                    last_error = str(e)

            # ניסיון 3: הזרקת value + dispatch events (fallback קשיח)
            if not typed_ok:
                target = input_handle
                if target is None and input_box is not None:
                    target = await input_box.element_handle()
                if target is not None:
                    try:
                        await target.evaluate(
                            """(el, value) => {
                                el.focus();
                                el.value = "";
                                el.dispatchEvent(new Event("input", { bubbles: true }));
                                el.value = value;
                                el.dispatchEvent(new Event("input", { bubbles: true }));
                                el.dispatchEvent(new Event("change", { bubbles: true }));
                                el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
                            }""",
                            city,
                        )
                        typed_ok = True
                    except Exception as e:
                        last_error = str(e)

            if typed_ok:
                break

            # ניסיון חוזר פנימי לפני שמחזירים כשל למודל.
            _debug(f"Typing attempt {attempt} failed, retrying once internally.")
            await _dismiss_blocking_ui(page)
            await page.wait_for_timeout(500)
            input_handle = await _select_best_input_handle(page)
            if input_handle is None:
                input_box = await _find_first_visible_input(page)

        if not typed_ok:
            return f"Timeout while typing city into weather search. Last error: {last_error}"

        _last_city = city

        await page.wait_for_timeout(1200)
        return f"City typed successfully: {city}"
    except PlaywrightTimeout:
        return "Timeout while typing city into weather search."
    except Exception as e:
        return f"Failed to type city: {e}"


@mcp.tool()
async def select_weather_forecast_city_israel() -> str:
    """בוחר את העיר הראשונה מרשימת ההצעות. אם צריך משתמש גם במקלדת (חץ למטה + Enter)."""
    page = await _ensure_browser_session()
    if not page.url.startswith(FORECAST_URL):
        _debug("Page not on forecast URL before select. Navigating automatically.")
        await page.goto(FORECAST_URL, wait_until="domcontentloaded", timeout=45000)

    try:
        await _dismiss_blocking_ui(page)
        await page.wait_for_timeout(500)

        selected = False

        # אסטרטגיה 1: לבחור לפי טקסט עיר מדויק.
        if _last_city:
            selected = await _click_city_option_by_text(page, _last_city)

        # אסטרטגיה 2: אם לא נמצא מדויק, לבחור פריט ראשון מהרשימה.
        if not selected:
            selected = await _click_first_city_option(page)

        # אסטרטגיה 3: fallback מקלדת מתוך שדה החיפוש.
        if not selected:
            input_box = await _find_first_visible_input(page)
            if input_box is not None:
                _debug("Click selection fallback failed, trying keyboard selection.")
                await input_box.click(timeout=2500, force=True)
                await page.keyboard.press("ArrowDown")
                await page.wait_for_timeout(250)
                await page.keyboard.press("Enter")
                selected = True
            else:
                # fallback אחרון: ניסיון בחירה גלובלי גם בלי locator לשדה.
                _debug("No visible input found. Trying global keyboard fallback.")
                await page.keyboard.press("ArrowDown")
                await page.wait_for_timeout(250)
                await page.keyboard.press("Enter")
                selected = True

        if not selected:
            return "Could not select city option. Try entering city again."

        # אימות שהבחירה באמת הובילה לקונטקסט של עיר.
        city_context_ok = await _wait_for_city_context(page, _last_city, timeout_ms=8000)
        if not city_context_ok:
            return "City option selection did not open city forecast context yet."

        await page.wait_for_timeout(1500)
        city_name = _last_city or "selected city"
        _debug(f"City selection completed for: {city_name}")
        return f"Selected first city option for: {city_name}"
    except PlaywrightTimeout as e:
        return f"Timeout while selecting city option: {e}"
    except Exception as e:
        return f"Failed to select city option: {e}"


@mcp.tool()
async def extract_weather_forecast_content_israel() -> str:
    """מחלץ תוכן תחזית מהעמוד ומחזיר טקסט נקי ל-LLM. להפעיל אחרי בחירת עיר."""
    page = await _ensure_browser_session()
    if not page.url.startswith("https://www.weather2day.co.il"):
        _debug("Page not on weather2day before extract. Navigating automatically.")
        await page.goto(FORECAST_URL, wait_until="domcontentloaded", timeout=45000)

    try:
        if _last_city:
            city_ready = await _wait_for_city_context(page, _last_city, timeout_ms=2500)
            if not city_ready:
                return "City forecast is not open yet. Call select_weather_forecast_city_israel first."

        candidates = [
            "main",
            "#main",
            ".forecast",
            ".weather",
            ".content",
            "body",
        ]

        best_text = ""
        for selector in candidates:
            locator = page.locator(selector).first
            try:
                if await locator.count() == 0:
                    continue
                text = await locator.inner_text(timeout=3500)
                cleaned = _clean_text(text)
                if len(cleaned) > len(best_text):
                    best_text = cleaned
            except Exception:
                continue

        if not best_text:
            # fallback אחרון: חילוץ מכל גוף הדף.
            body_text = await page.locator("body").inner_text(timeout=4000)
            best_text = _clean_text(body_text)

        if not best_text:
            return "Could not extract forecast content from the page."

        # מגביל אורך כדי לשמור על קונטקסט יעיל למודל.
        best_text = best_text[:8000]

        city_hint = _last_city or "העיר שנבחרה"
        _debug(f"Extracted forecast content length: {len(best_text)}")
        return (
            f"Forecast page content extracted successfully for: {city_hint}\n\n"
            f"{best_text}"
        )
    except PlaywrightTimeout:
        return "Timeout while extracting forecast content."
    except Exception as e:
        return f"Failed to extract forecast content: {e}"


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
