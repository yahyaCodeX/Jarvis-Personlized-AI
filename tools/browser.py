"""
Playwright-controlled browser (SDG 10 assistive navigation + checkout).

One persistent Chromium window, reused across calls. All tools that touch it
run on the server's single "playwright-worker" thread.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import urllib.parse

import requests

from config import load_profile
from ._shared import ask_gemini
from .registry import tool

log = logging.getLogger("jarvis.tools")

USER_PROFILES = load_profile()
ADDRESS_CHOICES = ", ".join(
    f"'{key}' ({addr.get('city', key)})"
    for key, addr in (USER_PROFILES.get("addresses") or {}).items()
) or "'home'"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# ─── PERSISTENT SINGLETON PLAYWRIGHT BROWSER (SDG 10) ───────────────
_playwright_context = None
_browser = None
_active_page = None
_playwright_thread_id = None


def stealth_sync(page):
    """Applies Playwright stealth evasions to hide automation flags."""
    try:
        from playwright_stealth import stealth_sync as _ss
        _ss(page)
    except ImportError:
        try:
            from playwright_stealth.stealth import Stealth
            Stealth().apply_stealth_sync(page)
        except Exception as err:
            log.warning(f"[STEALTH WARNING] Could not apply stealth evasions: {err}")


def get_active_page():
    """
    Returns the active singleton Playwright browser page instance with stealth anti-bot protection.
    Auto-heals if the user closed the window, or if invoked from a different thread (greenlet thread boundary).
    ALWAYS tracks the most recently opened tab/popup so target=_blank links never lose focus.
    """
    global _playwright_context, _browser, _active_page, _playwright_thread_id
    current_thread = threading.get_ident()

    try:
        if (
            _browser is None
            or not _browser.is_connected()
            or _playwright_context is None
            or _playwright_thread_id != current_thread
        ):
            from playwright.sync_api import sync_playwright
            if _playwright_context:
                try:
                    _playwright_context.stop()
                except Exception:
                    pass
            _playwright_context = sync_playwright().start()
            _browser = _playwright_context.chromium.launch(
                headless=False,
                slow_mo=100,
                args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
            )
            _active_page = _browser.new_page(
                user_agent=_UA
            )
            _playwright_thread_id = current_thread
            try:
                stealth_sync(_active_page)
            except Exception as stealth_err:
                log.warning(f"[STEALTH WARNING] {stealth_err}")

        # ALWAYS track the most recently opened tab or popup (handles target="_blank" links)
        try:
            if _browser.contexts:
                pages = _browser.contexts[0].pages
                if pages:
                    _active_page = pages[-1]
                    try:
                        _active_page.bring_to_front()
                    except Exception:
                        pass
        except Exception as tab_err:
            log.debug(f"[TAB TRACKER] Could not update active tab: {tab_err}")

        # Final guard: if _active_page is somehow still None or closed, open a fresh page
        if _active_page is None or _active_page.is_closed():
            _active_page = _browser.new_page(
                user_agent=_UA
            )

    except Exception as e:
        log.info(f"[PLAYWRIGHT ENGINE] Re-initializing browser session on thread {current_thread} due to: {e}")
        from playwright.sync_api import sync_playwright
        _playwright_context = sync_playwright().start()
        _browser = _playwright_context.chromium.launch(
            headless=False,
            slow_mo=100,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        _active_page = _browser.new_page(
            user_agent=_UA
        )
        _playwright_thread_id = current_thread
        try:
            stealth_sync(_active_page)
        except Exception:
            pass

    return _active_page


def resolve_brand_url(target_name: str) -> str:
    """
    Resolves a brand or search term to its official direct URL using DuckDuckGo HTML link extraction.
    Bypasses DuckDuckGo/Google redirect traps and CAPTCHAs.
    """
    try:
        ddg_html_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(target_name)}"
        resp = requests.get(ddg_html_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}, timeout=8)
        if resp.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            first_link = soup.select_one("a.result__url")
            if first_link and first_link.get("href"):
                href = first_link.get("href")
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                real_url = parsed.get("uddg", [None])[0]
                if real_url:
                    return real_url
    except Exception as err:
        log.warning(f"[URL RESOLVER WARNING] {err}")
    return None


def safe_goto(url, timeout=15000):
    """
    Safely navigates to a URL using get_active_page().
    Auto-heals if the target page, context, or browser was closed.
    """
    global _active_page
    try:
        page = get_active_page()
        page.goto(url, timeout=timeout)
        return page
    except Exception as err:
        err_str = str(err).lower()
        if any(k in err_str for k in ["closed", "target", "greenlet", "context", "destroyed"]):
            log.info(f"[PLAYWRIGHT AUTO-HEAL] Re-creating browser page due to closed target: {err}")
            _active_page = None
            page = get_active_page()
            page.goto(url, timeout=timeout)
            return page
        else:
            raise err


@tool("Universal smart navigation in Jarvis's own browser window. Actions: 'search' (DuckDuckGo search), "
      "'open_url' (open a URL or brand name), 'click_result' (click the 1st/2nd/3rd SEARCH ENGINE result, NOT for "
      "product grids), 'click_text' (click any visible element by its exact displayed text: use this for e-commerce "
      "products, buttons and links), 'play_youtube' (search and play a video), 'new_tab', 'close_tab', 'switch_tab', "
      "'scroll_down', 'scroll_up'.",
      params={"action": "What to do",
              "target": "Search query, URL, result rank (1/2/3), exact product/button text to click, or YouTube query"},
      enums={"action": ["search", "open_url", "click_result", "click_text", "play_youtube",
                        "new_tab", "close_tab", "switch_tab", "scroll_down", "scroll_up"]})
def assistive_web_action(action: str, target: str = "") -> str:
    """
    Universal Smart Navigation Tool for SDG 10 visually impaired accessibility.
    Actions:
    - 'search': Searches DuckDuckGo for target query.
    - 'open_url': Opens specific site directly or uses DuckDuckGo !ducky bang auto-redirect.
    - 'click_result': Clicks search result by number (1-based index).
    - 'scroll_down': Injects JS DOM scroll down by 800px.
    - 'scroll_up': Injects JS DOM scroll up by 800px.
    - 'click_text': Intelligently finds and clicks element with target text.
    """
    global _active_page, _playwright_thread_id
    act = (action or "search").lower().strip()
    target_clean = (target or "").strip()

    # 1. Fix Variable Scope: Define page at the absolute top of the function
    page = get_active_page()

    try:
        if act == "open_url":
            if not target_clean:
                return "Please provide a URL to open, sir."

            target_nav = target_clean
            if not target_nav.startswith("http"):
                # Safely encode the auto-redirect command
                encoded_query = urllib.parse.quote(f"!ducky {target_nav}")
                target_nav = f"https://duckduckgo.com/?q={encoded_query}"

            try:
                log.info(f"[ASSISTIVE WEB] Navigating to target: {target_nav}...")
                page.goto(target_nav, timeout=15000)
                try:
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
                page_title = page.title() or target_clean
                return f"Opened website '{page_title}' on screen, sir."
            except Exception as e:
                return f"Failed to load page: {e}"

        elif act == "search":
            if not target_clean:
                return "Please specify what to search for, sir."
            encoded_query = urllib.parse.quote(target_clean)
            search_url = f"https://duckduckgo.com/?q={encoded_query}"
            log.info(f"[ASSISTIVE WEB] Searching DuckDuckGo for '{target_clean}'...")
            try:
                page.goto(search_url, timeout=15000)
                page_title = page.title() or target_clean
                return f"Searched and opened '{page_title}' on screen, sir."
            except Exception as e:
                return f"Failed to perform search: {e}"

        elif act in ["click_result", "open_result"] or (act in ["click_text", "click"] and (re.search(r'\b(1st|first|top|1|2nd|second|2|3rd|third|3|4th|fourth|4)\b', target_clean, re.IGNORECASE) or "result" in target_clean.lower() or "site" in target_clean.lower() or "link" in target_clean.lower())):
            try:
                # Convert target (e.g., "1") or ordinal to a zero-based index
                index = 0
                ord_match = re.search(r'\b(1st|first|top|1|2nd|second|2|3rd|third|3|4th|fourth|4)\b', target_clean, re.IGNORECASE)
                if ord_match:
                    w = ord_match.group(1).lower()
                    if w in ["2nd", "second", "2"]:
                        index = 1
                    elif w in ["3rd", "third", "3"]:
                        index = 2
                    elif w in ["4th", "fourth", "4"]:
                        index = 3
                elif target_clean.isdigit():
                    index = int(target_clean) - 1

                log.info(f"[ASSISTIVE WEB] Clicking search result index #{index + 1}...")
                # Locate the search result link and click it
                page.locator('h3, a[data-testid="result-title-a"], article h2 a, .result__title a').nth(index).click(timeout=5000)
                # Wait for the new page to load
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass
                page_title = page.title() or f"result #{index + 1}"
                return f"Successfully clicked search result number {index + 1} ('{page_title}')."
            except Exception as e:
                return f"Failed to click search result {target_clean}. Error: {e}"

        elif act == "scroll_down":
            log.info("[ASSISTIVE WEB] Injecting JS scrollBy(0, 800)...")
            page.evaluate("window.scrollBy(0, 800)")
            return "Scrolled down the page, sir."

        elif act == "scroll_up":
            log.info("[ASSISTIVE WEB] Injecting JS scrollBy(0, -800)...")
            page.evaluate("window.scrollBy(0, -800)")
            return "Scrolled up the page, sir."

        elif act in ["click_text", "click"]:
            if not target_clean:
                return "Please specify text to click on the page, sir."
            log.info(f"[ASSISTIVE WEB] Clicking element with text: '{target_clean}'...")
            try:
                # Tier 1: Native Playwright text locator — works on any element type (spans, divs, anchors)
                # This is the most reliable for e-commerce product grids where text is inside nested divs
                try:
                    page.locator(f"text={target_clean}").first.click(timeout=4000)
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                    return f"Successfully clicked on '{target_clean}'."
                except Exception:
                    pass

                # Tier 2: Partial text match on clickable elements (links, buttons, headings)
                try:
                    page.locator(
                        f"a:has-text('{target_clean}'), button:has-text('{target_clean}'), "
                        f"h1:has-text('{target_clean}'), h2:has-text('{target_clean}'), "
                        f"h3:has-text('{target_clean}'), span:has-text('{target_clean}')"
                    ).first.click(timeout=4000)
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                    return f"Successfully clicked on '{target_clean}'."
                except Exception:
                    pass

                # Tier 3: First keyword of the phrase (handles truncated product titles in grids)
                first_word = target_clean.split()[0] if target_clean.split() else target_clean
                if len(first_word) > 3:
                    try:
                        page.locator(
                            f"a:has-text('{first_word}'), h3:has-text('{first_word}'), "
                            f"span:has-text('{first_word}'), div:has-text('{first_word}')"
                        ).first.click(timeout=4000)
                        page.wait_for_load_state("domcontentloaded", timeout=5000)
                        return f"Clicked item containing '{first_word}' on page, sir."
                    except Exception:
                        pass

                # Tier 4: get_by_text fallback (broader match, lower precision)
                try:
                    page.get_by_text(target_clean, exact=False).first.click(timeout=3000)
                    return f"Clicked '{target_clean}' on page, sir."
                except Exception:
                    pass

                return f"Could not find '{target_clean}' on screen. Try scrolling down and asking again, sir."

            except Exception as click_err:
                log.info(f"[ASSISTIVE WEB] Text click error: {click_err}")
                return f"Failed to click '{target_clean}'. It might not be visible on screen. Error: {click_err}"

        elif act == "play_youtube":
            if not target_clean:
                return "Please specify what to play on YouTube, sir."
            encoded = urllib.parse.quote(target_clean)
            log.info(f"[ASSISTIVE WEB] Searching YouTube for '{target_clean}'...")
            try:
                page.goto(f"https://www.youtube.com/results?search_query={encoded}", timeout=15000)
                page.locator('a#video-title').first.click(timeout=5000)
                page_title = page.title() or target_clean
                return f"Playing '{target_clean}' on YouTube, sir."
            except Exception as e:
                return f"Failed to play YouTube video: {e}"

        elif act == "new_tab":
            try:
                _active_page = _browser.new_page(
                    user_agent=_UA
                )
                _playwright_thread_id = threading.get_ident()
                return "Opened a new browser tab, sir."
            except Exception as e:
                return f"Failed to open new tab: {e}"

        elif act == "close_tab":
            try:
                page.close()
                pages = _browser.contexts[0].pages if _browser.contexts else []
                if pages:
                    _active_page = pages[-1]
                    _active_page.bring_to_front()
                else:
                    _active_page = _browser.new_page(
                        user_agent=_UA
                    )
                return "Closed current tab, sir."
            except Exception as e:
                return f"Failed to close tab: {e}"

        elif act == "switch_tab":
            try:
                pages = _browser.contexts[0].pages if _browser.contexts else []
                if pages:
                    current_idx = pages.index(_active_page) if _active_page in pages else 0
                    _active_page = pages[(current_idx + 1) % len(pages)]
                    _active_page.bring_to_front()
                    page_title = _active_page.title() or "new tab"
                    return f"Switched to tab: '{page_title}', sir."
                return "No other tabs open, sir."
            except Exception as e:
                return f"Failed to switch tab: {e}"

        else:
            return f"Unknown web action '{action}', sir."

    except Exception as e:
        log.error(f"[ASSISTIVE WEB ERROR] {e}")
        return f"Encountered an issue executing '{action}': {e}"


def _summarize_checkout(args: dict) -> str:
    choice = args.get("address_choice", "home")
    phone = (args.get("custom_phone") or USER_PROFILES.get("default_phone") or "").strip()
    tail = f" and phone ending in {phone[-4:]}" if len(phone) >= 4 else ""
    return f"fill this checkout page with your {choice} address{tail}"


@tool(f"Fills the user's saved shipping details into the checkout page open in Jarvis's browser. Use ONLY when "
      f"the user is already on a checkout page and has said which address ({ADDRESS_CHOICES}) and phone to use.",
      params={"address_choice": f"Saved address key: {ADDRESS_CHOICES}",
              "custom_phone": "Optional phone number if different from the user's saved default"},
      confirm=_summarize_checkout)
def assistive_checkout(address_choice: str = "home", custom_phone: str = "") -> str:
    """
    Contextual Checkout Tool for SDG 10 visually impaired accessibility.
    Dynamically extracts visible form fields from ANY e-commerce checkout page,
    uses Gemini LLM to map user profile data to the form inputs, and fills them via Playwright.
    """
    addresses = USER_PROFILES.get("addresses") or {}
    if not addresses:
        return "No saved addresses found, sir. Add them to profile.json first."

    addr_type = (address_choice or "home").lower().strip()
    if addr_type not in addresses:
        addr_type = "home" if "home" in addresses else next(iter(addresses))

    target_profile = addresses[addr_type]
    target_address = target_profile.get("address", "")
    city_name = target_profile.get("city", "")
    phone_val = custom_phone.strip() if custom_phone and custom_phone.strip() else USER_PROFILES["default_phone"]
    selected_email = USER_PROFILES["email"]

    user_data = {
        "name": USER_PROFILES["name"],
        "first_name": USER_PROFILES["first_name"],
        "last_name": USER_PROFILES["last_name"],
        "email": selected_email,
        "phone": phone_val,
        "address": target_address,
        "city": city_name,
        "province": target_profile.get("province", ""),
    }

    try:
        page = get_active_page()
        log.info(f"[ASSISTIVE CHECKOUT] Extracting visible form fields from active page ({addr_type} profile)...")

        # 1. Dynamic Field Extraction via JS DOM evaluate
        extracted_fields = page.evaluate("""
            () => {
                const fields = [];
                const elements = document.querySelectorAll('input, textarea, select');
                elements.forEach(el => {
                    const style = window.getComputedStyle(el);
                    if (style.display !== 'none' && style.visibility !== 'hidden' && el.type !== 'hidden' && el.type !== 'submit' && el.type !== 'button') {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {
                            fields.push({
                                id: el.id || '',
                                name: el.name || '',
                                type: el.type || 'text',
                                placeholder: el.placeholder || '',
                                aria_label: el.getAttribute('aria-label') || '',
                                autocomplete: el.getAttribute('autocomplete') || ''
                            });
                        }
                    }
                });
                return fields;
            }
        """)

        log.info(f"[ASSISTIVE CHECKOUT] Extracted {len(extracted_fields)} visible form input fields.")

        # 2. LLM-Powered Mapping using Gemini Client
        dynamic_mapping = {}
        if extracted_fields:
            prompt = f"""You are an AI web automation assistant. Map the user's profile data to the correct HTML 'name' or 'id' attributes from this list of input fields. Return ONLY a valid JSON object where keys are the field 'name' or 'id', and values are the user's exact data to be typed.

User Profile Data:
{json.dumps(user_data, indent=2)}

List of Input Fields:
{json.dumps(extracted_fields, indent=2)}

Rules:
- Output MUST be a valid JSON object where key is the field 'name' or 'id' (prefer 'name', fallback to 'id'), and value is the exact string from User Profile Data.
- Do NOT output extra text or explanations outside JSON.
"""
            raw_response = ask_gemini(prompt, "ASSISTIVE CHECKOUT") or ""
            try:
                clean_json = raw_response
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0].strip()
                if clean_json:
                    dynamic_mapping = json.loads(clean_json)
            except (json.JSONDecodeError, IndexError) as parse_err:
                log.error(f"[ASSISTIVE CHECKOUT] Could not parse the field mapping: {parse_err}")

        # 3. Dynamic Injection based on Gemini LLM mapping
        if dynamic_mapping:
            log.info(f"[ASSISTIVE CHECKOUT] Injecting LLM-mapped fields: {dynamic_mapping}")
            for field_identifier, user_value in dynamic_mapping.items():
                if not field_identifier or user_value is None:
                    continue
                try:
                    page.locator(f"[name='{field_identifier}'], [id='{field_identifier}']").first.fill(str(user_value), timeout=2000)
                    log.info(f"[ASSISTIVE CHECKOUT] Filled '{field_identifier}' -> '{user_value}'")
                except Exception as fill_err:
                    log.warning(f"[ASSISTIVE CHECKOUT WARNING] Could not fill '{field_identifier}': {fill_err}")

        else:
            # Fallback heuristic form filling if LLM mapping was unavailable
            log.info("[ASSISTIVE CHECKOUT] Using heuristic fallback form filling...")
            try:
                page.locator('input[name="checkout[email_or_phone]"], input[name="checkout[email]"], input[type="email"], input[id="checkout_email_or_phone"]').first.fill(selected_email, timeout=2000)
            except Exception: pass
            try:
                page.locator('input[placeholder*="First name" i], input[name="checkout[shipping_address][first_name]"]').first.fill(USER_PROFILES["first_name"], timeout=2000)
            except Exception: pass
            try:
                page.locator('input[placeholder*="Last name" i], input[name="checkout[shipping_address][last_name]"]').first.fill(USER_PROFILES["last_name"], timeout=2000)
            except Exception: pass
            try:
                page.locator('input[placeholder*="Address" i], input[name="checkout[shipping_address][address1]"]').first.fill(target_address, timeout=2000)
            except Exception: pass
            try:
                page.locator('input[placeholder*="City" i], input[name="checkout[shipping_address][city]"]').first.fill(city_name, timeout=2000)
            except Exception: pass
            try:
                page.locator('input[name="checkout[shipping_address][phone]"], input[name="phone"], input[placeholder*="Phone" i]').last.fill(phone_val, timeout=2000)
            except Exception: pass

        # 4. Universal Cash on Delivery Selection
        try:
            page.wait_for_timeout(1000)
            page.locator('label:has-text("Cash on Delivery"), label:has-text("COD")').first.click(timeout=3000)
            log.info("[ASSISTIVE CHECKOUT] Clicked Cash on Delivery (COD) payment option.")
        except Exception:
            log.info("[Playwright] COD option not found, might require navigating to the next page first.")

        # Freeze browser for visual inspection
        log.info("[ASSISTIVE CHECKOUT] Freezing browser for visual verification...")
        page.wait_for_timeout(15000)
        return "Checkout details injected successfully using dynamic LLM form mapping. Please verify the screen."

    except Exception as e:
        log.error(f"[ASSISTIVE CHECKOUT ERROR] {e}")
        return f"Checkout details injected. Please verify the screen. Error: {e}"
