import os
import re
import time
import random
import datetime
from dataclasses import dataclass, asdict, field

import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
import gradio as gr


# ------------------------------
# Data Models
# ------------------------------
@dataclass
class Business:
    name: str = None
    address: str = None
    domain: str = None
    website: str = None
    phone_number: str = None
    email: str = None
    category: str = None
    location: str = None

    def __hash__(self):
        hash_fields = [self.name or ""]
        if self.domain:
            hash_fields.append(f"domain:{self.domain}")
        if self.website:
            hash_fields.append(f"website:{self.website}")
        if self.phone_number:
            hash_fields.append(f"phone:{self.phone_number}")
        return hash(tuple(hash_fields))


@dataclass
class BusinessList:
    business_list: list[Business] = field(default_factory=list)
    _seen_businesses: set = field(default_factory=set, init=False)
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    save_at = os.path.join("GMaps_Data", today)
    os.makedirs(save_at, exist_ok=True)

    def add_business(self, business: Business):
        business_hash = hash(business)
        if business_hash not in self._seen_businesses:
            self.business_list.append(business)
            self._seen_businesses.add(business_hash)

    def dataframe(self):
        return pd.json_normalize((asdict(b) for b in self.business_list), sep="_")

    def save_to_excel(self, filename: str) -> str:
        file_path = os.path.join(self.save_at, f"{filename}.xlsx")
        df = self.dataframe()
        if not df.empty:
            df.to_excel(file_path, index=False)
        else:
            with pd.ExcelWriter(file_path) as writer:
                pd.DataFrame().to_excel(writer, index=False)
        return file_path

    def save_to_csv(self, filename: str) -> str:
        file_path = os.path.join(self.save_at, f"{filename}.csv")
        df = self.dataframe()
        df.to_csv(file_path, index=False, encoding="utf-8-sig")
        return file_path


# ------------------------------
# Helpers
# ------------------------------
EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

def _safe_text(page, selector_or_locator):
    try:
        loc = page.locator(selector_or_locator) if isinstance(selector_or_locator, str) else selector_or_locator
        if loc.count():
            return loc.first.inner_text().strip()
    except Exception:
        pass
    return ""


def scrape_email_from_website(browser_context, url: str) -> str:
    email = ""
    page = browser_context.new_page()
    try:
        page.set_default_timeout(15000)
        page.goto(url, timeout=20000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except PWTimeoutError:
            pass
        time.sleep(random.uniform(1.5, 2.5))
        html = page.content()
        matches = EMAIL_REGEX.findall(html or "")
        if matches:
            email = matches[0]
    except Exception:
        pass
    finally:
        page.close()
    return email


# ------------------------------
# Scraper Core
# ------------------------------
def scrape_businesses_core(query: str, total: int = 100, headless: bool = True, filetype: str = "Excel") -> str:
    # Parse category/location from "X in Y" pattern
    parts = [p.strip() for p in query.split(" in ")]
    category = parts[0] if parts else query
    location = parts[1] if len(parts) > 1 else ""

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(locale="en-GB")
        gmaps_page = context.new_page()
        gmaps_page.set_default_timeout(45000)

        # Google Maps
        gmaps_page.goto("https://www.google.com/maps", timeout=60000)

        # Search
        search_input = gmaps_page.locator('//input[@id="searchboxinput"]')
        search_input.fill(query)
        time.sleep(random.uniform(0.8, 1.2))
        gmaps_page.keyboard.press("Enter")
        time.sleep(4)

        # Nudge results pane
        try:
            gmaps_page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')
        except Exception:
            pass

        # Scroll/collect
        previously_counted = 0
        max_scroll_loops = 50
        for _ in range(max_scroll_loops):
            gmaps_page.mouse.wheel(0, 8000)
            time.sleep(random.uniform(1.6, 2.4))
            count_now = gmaps_page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').count()
            if count_now >= total:
                break
            if count_now == previously_counted:
                break
            previously_counted = count_now

        anchors = gmaps_page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()
        if not anchors:
            browser.close()
            raise RuntimeError("No listings found. Try a different query or increase wait time.")

        listings = [a.locator("xpath=..") for a in anchors][:total]
        business_list = BusinessList()

        # Selectors (with fallbacks)
        name_sel_primary = "h1.DUwDvf"
        name_sel_fallback = "h1.fontHeadlineLarge"
        address_xpath = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
        website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
        phone_xpath = '//button[starts-with(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'

        for idx, listing in enumerate(listings, start=1):
            try:
                listing.click()
                time.sleep(random.uniform(1.7, 2.7))

                business = Business()
                # Name
                name_txt = _safe_text(gmaps_page, name_sel_primary) or _safe_text(gmaps_page, name_sel_fallback) or _safe_text(gmaps_page, "h1")
                business.name = name_txt

                # Address
                business.address = _safe_text(gmaps_page, address_xpath)

                # Website/domain
                website_text = _safe_text(gmaps_page, website_xpath)
                if website_text:
                    business.domain = website_text
                    business.website = website_text if website_text.startswith("http") else f"https://www.{website_text}"
                else:
                    business.website = ""

                # Phone
                business.phone_number = _safe_text(gmaps_page, phone_xpath)

                # Email (if website exists)
                if business.website:
                    business.email = scrape_email_from_website(context, business.website) or ""
                else:
                    business.email = ""

                business.category = category
                business.location = location

                business_list.add_business(business)
                time.sleep(random.uniform(0.6, 1.2))
            except Exception as e:
                print(f"[{idx}] Error: {e}")

        safe_name = re.sub(r"[^\w\-]+", "_", query).strip("_")
        if filetype.lower() == "csv":
            file_path = business_list.save_to_csv(safe_name)
        else:
            file_path = business_list.save_to_excel(safe_name)

        browser.close()
        return file_path


# ------------------------------
# Gradio Frontend
# ------------------------------
def run_scraper(query: str, num_results: int, filetype: str, headless: bool):
    if not query or not query.strip():
        raise gr.Error("Please enter a search query, e.g. `ecommerce stores in united kingdom`.")
    if num_results < 10 or num_results > 200:
        raise gr.Error("Number of results must be between 10 and 200.")
    return scrape_businesses_core(query.strip(), int(num_results), headless=headless, filetype=filetype)


with gr.Blocks(title="Google Maps Business Scraper") as demo:
    gr.Markdown("## 🕵️ Google Maps Business Scraper (Railway)")
    with gr.Row():
        query = gr.Textbox(label="Enter your search query", placeholder="e.g. ecommerce stores in united kingdom")
        num_results = gr.Slider(10, 200, value=50, step=10, label="Number of results")
    with gr.Row():
        filetype = gr.Radio(choices=["Excel", "CSV"], value="Excel", label="Save as")
        headless = gr.Checkbox(value=True, label="Headless (server-safe)")
    run_btn = gr.Button("Start Scraping", variant="primary")
    file_output = gr.File(label="Download file", interactive=False)
    run_btn.click(fn=run_scraper, inputs=[query, num_results, filetype, headless], outputs=file_output)

# ⬇️ CHANGE IS HERE: remove unsupported argument
try:
    demo.queue(max_size=20, status_update_rate=1)
except TypeError:
    # fallback for very old/new versions: just enable queue with defaults
    demo.queue()

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", "7860")), show_error=True)
