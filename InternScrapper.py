import requests
from bs4 import BeautifulSoup
import re
import time
import pandas as pd
import streamlit as st
import os

# ---------------- CONFIG ----------------
BASE_URL = "https://placement.iitbhu.ac.in"
LISTING_URL = f"{BASE_URL}/forum/c/notice-board/2025-26/"

# Load session cookie from environment variable
import os

# Load session cookie from environment variable
SESSION_COOKIE = os.getenv("IITBHU_SESSION")

if not SESSION_COOKIE:
    st.error("⚠️ SESSION cookie not set. Please configure environment variable IITBHU_SESSION.")
    st.stop()

cookies = {"sessionid": SESSION_COOKIE}

ROLL_PATTERN = re.compile(r"\b\d{8}\b")  # IIT BHU roll numbers


def fetch_page(session, url):
    """Fetch a page safely with retries and error handling"""
    try:
        res = session.get(url, cookies=cookies, timeout=10)
        res.raise_for_status()
        return BeautifulSoup(res.text, "html.parser")
    except requests.exceptions.RequestException as e:
        st.warning(f"⚠️ Failed to fetch {url}: {e}")
        return BeautifulSoup("", "html.parser")


def count_offers_in_thread(session, link):
    """Count roll numbers by section inside a thread"""
    soup = fetch_page(session, link)

    counts = {"selected": 0, "waitlisted": 0, "under_review": 0}
    current_section = "selected"

    for post in soup.select("td.post-content"):
        raw = post.decode_contents().replace("<br/>", "\n")
        lines = [
            line.strip()
            for line in BeautifulSoup(raw, "html.parser").get_text().split("\n")
        ]

        for line in lines:
            lower = line.lower()

            # Flexible section detection
            if re.search(r"waitlist|wl", lower):
                current_section = "waitlisted"
                continue
            if re.search(r"under review|shortlist|sl", lower):
                current_section = "under_review"
                continue

            if ROLL_PATTERN.search(line):
                counts[current_section] += 1

    return counts


def clean_company_name(title: str) -> str:
    """Normalize company name from thread title"""
    title = re.sub(r"\[.*?\]", "", title)
    title = re.sub(r"^topic:\s*", "", title, flags=re.IGNORECASE)
    title = title.strip()
    return re.split(r"[:-]", title)[0].strip().title() if title else "Unknown"


def scrape(mode="ppo", delay=0.5, max_pages=100):
    """Scrape PPO or Intern offers until pages are exhausted"""
    offers_by_company = {}
    totals = {"selected": 0, "waitlisted": 0, "under_review": 0}

    include_filters = {
        "ppo": ["ppo", "pre-placement"],
        "intern": ["intern", "internship"],
    }
    exclude_filters = {
        "ppo": [],
        "intern": ["ppo", "pre-placement", "shortlist", "interview"],
    }

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            st.info(f"🌐 Scraping page {page} ...")
            page_url = LISTING_URL + f"?page={page}"
            soup = fetch_page(session, page_url)

            rows = soup.select("tr.topic-row")
            if not rows:  # End of available pages
                st.success(f"✅ Stopped at page {page} (no more data).")
                break

            for row in rows:
                title_tag = row.select_one("td.topic-name a")
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                title_lower = title.lower()
                link = BASE_URL + title_tag["href"]

                # Filter threads
                if any(f in title_lower for f in include_filters[mode]) and not any(
                    f in title_lower for f in exclude_filters[mode]
                ):
                    st.write(f"🔎 Checking {title} ...")
                    company_counts = count_offers_in_thread(session, link)

                    if sum(company_counts.values()) > 0:
                        company_name = clean_company_name(title)
                        if company_name not in offers_by_company:
                            offers_by_company[company_name] = {
                                "selected": 0,
                                "waitlisted": 0,
                                "under_review": 0,
                            }

                        for k in totals:
                            offers_by_company[company_name][k] += company_counts[k]
                            totals[k] += company_counts[k]

            time.sleep(delay)

    return offers_by_company, totals


# ---------------------- UI ----------------------
st.set_page_config(page_title="📊 IIT BHU Placement Scraper", layout="wide")
st.title("📊 IIT BHU Placement Scraper")

mode = st.radio("Choose mode:", ["ppo", "intern"])
if st.button("🚀 Start Scraping"):
    offers_by_company, totals = scrape(mode=mode)

    df = pd.DataFrame.from_dict(offers_by_company, orient="index")
    st.subheader("📌 Company-wise Results")
    st.dataframe(df)

    st.subheader("📊 Totals")
    st.json(totals)

    st.download_button(
        "⬇️ Download CSV",
        df.to_csv().encode("utf-8"),
        f"{mode}_results.csv",
        "text/csv",
    )
