"""
Daily News Sentiment Tracker — full-article version, ticker-driven
====================================================================

Pipeline:
  1. Given a ticker (e.g. AAPL, GC=F, GLD), build news search queries and a
     price symbol for it
  2. Fetch article links from RSS (Google News + Yahoo Finance, for redundancy)
  3. Scrape full article text, filtering out junk paragraphs (nav/ads/boilerplate)
  4. Split article into sentences
  5. Score each sentence with FinBERT (financial-domain sentiment model)
  6. Aggregate sentence scores -> one score per article
  7. Aggregate article scores -> one score per (ticker, date)
  8. Append results to a per-ticker CSV so you build a real time series across runs

Install deps:
    pip install feedparser requests beautifulsoup4 transformers torch pandas

Run (interactive ticker prompt):
    python sentiment_pipeline.py

Run (specify ticker directly):
    python sentiment_pipeline.py --ticker AAPL
    python sentiment_pipeline.py --ticker GC=F --name "gold"
"""

import re
import os
import time
import hashlib
import argparse
from datetime import date
from urllib.parse import quote

import feedparser
import requests
from bs4 import BeautifulSoup
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import yfinance as yf
import matplotlib
matplotlib.use("Agg")  # headless-safe backend, still saves PNG files fine
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from googlenewsdecoder import gnewsdecoder

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NUM_ARTICLES_PER_QUERY = 10
REQUEST_TIMEOUT = 10
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (sentiment-tracker/1.0)"}

DATA_DIR = "data"  # all per-ticker CSVs are written here

FINBERT_MODEL_NAME = "yiyanghkust/finbert-tone"
LABELS = ["Positive", "Negative", "Neutral"]  # must match model's label order

# Paragraphs shorter than this are usually nav/boilerplate, not real content
MIN_PARAGRAPH_CHARS = 40

# Phrases that mark boilerplate/junk paragraphs to drop before scoring
JUNK_PATTERNS = [
    r"sign up for", r"subscribe", r"newsletter", r"cookie", r"privacy policy",
    r"terms of (use|service)", r"all rights reserved", r"advertisement",
    r"related articles?", r"read more", r"click here", r"follow us on",
    r"share this", r"^\s*©", r"javascript", r"enable cookies",
]
JUNK_RE = re.compile("|".join(JUNK_PATTERNS), re.IGNORECASE)

# Simple sentence splitter (good enough for news prose; avoids an nltk download dependency)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


# ---------------------------------------------------------------------------
# Ticker handling
# ---------------------------------------------------------------------------

# A few well-known non-equity symbols that need a friendlier news query than
# the raw ticker (e.g. "GC=F" means nothing to a news search engine).
KNOWN_ALIASES = {
    "GC=F": "gold",
    "SI=F": "silver",
    "CL=F": "crude oil",
    "GLD": "gold ETF",
    "SLV": "silver ETF",
    "BTC-USD": "bitcoin",
    "ETH-USD": "ethereum",
}


def build_queries_for_ticker(ticker, friendly_name=None):
    """Builds a small set of news search queries for a given ticker/symbol.

    If friendly_name is given, use it directly (e.g. "gold", "Apple").
    Otherwise fall back to KNOWN_ALIASES, otherwise just use the ticker itself
    (works fine for normal equity tickers like AAPL, TSLA, NVDA).
    """
    name = friendly_name or KNOWN_ALIASES.get(ticker.upper(), ticker)
    return [
        f"{name} stock" if name == ticker else name,
        f"{name} price",
        f"{name} forecast",
    ]


def safe_filename(ticker):
    return re.sub(r"[^A-Za-z0-9_-]", "_", ticker)


def ticker_paths(ticker):
    """Per-ticker CSV paths, so each ticker has its own independent time series."""
    os.makedirs(DATA_DIR, exist_ok=True)
    fname = safe_filename(ticker)
    return {
        "daily": os.path.join(DATA_DIR, f"{fname}_daily_sentiment.csv"),
        "articles": os.path.join(DATA_DIR, f"{fname}_article_log.csv"),
        "price": os.path.join(DATA_DIR, f"{fname}_price.csv"),
        "combined": os.path.join(DATA_DIR, f"{fname}_sentiment_vs_price.csv"),
        "plot": os.path.join(DATA_DIR, f"{fname}_sentiment_plot.png"),
    }


# ---------------------------------------------------------------------------
# Price data (yfinance covers equities, ETFs, futures like GC=F, crypto like
# BTC-USD — the same symbol space as KNOWN_ALIASES above)
# ---------------------------------------------------------------------------

def fetch_price_history(ticker, period="3mo"):
    """Pulls daily OHLC price history for the ticker and computes day-over-day
    direction (Up/Down/Flat) and % change. Returns a DataFrame indexed by date.
    """
    hist = yf.Ticker(ticker).history(period=period, interval="1d")
    if hist.empty:
        return pd.DataFrame()

    hist = hist.reset_index()
    hist["date"] = pd.to_datetime(hist["Date"]).dt.date.astype(str)
    hist["pct_change"] = hist["Close"].pct_change() * 100
    hist["direction"] = hist["pct_change"].apply(
        lambda x: "Up" if x > 0.05 else ("Down" if x < -0.05 else "Flat")
    )
    return hist[["date", "Open", "High", "Low", "Close", "Volume", "pct_change", "direction"]]


# ---------------------------------------------------------------------------
# Step 1: Fetch news links from RSS
# ---------------------------------------------------------------------------

def fetch_news_google(query, num_articles=10):
    """Google News RSS. Coverage is good but volume can fluctuate day to day."""
    rss_url = f"https://news.google.com/rss/search?q={quote(query)}"
    feed = feedparser.parse(rss_url)
    out = []
    for item in feed.entries[:num_articles]:
        out.append({
            "query": query,
            "source": "google_news",
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "published": item.get("published", ""),
        })
    return out


def fetch_news_yahoo(query, num_articles=10):
    """Yahoo Finance RSS as a second source, to backfill days Google News is thin on."""
    rss_url = f"https://news.search.yahoo.com/rss?p={quote(query)}"
    feed = feedparser.parse(rss_url)
    out = []
    for item in feed.entries[:num_articles]:
        out.append({
            "query": query,
            "source": "yahoo_news",
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "published": item.get("published", ""),
        })
    return out


def fetch_all_news(queries, num_articles_per_query=10):
    articles = []
    for query in queries:
        articles.extend(fetch_news_google(query, num_articles_per_query))
        articles.extend(fetch_news_yahoo(query, num_articles_per_query))
        time.sleep(0.5)  # be polite to the RSS endpoints
    return dedupe_articles(articles)


def dedupe_articles(articles):
    """Same story often appears across queries/sources. Dedupe by normalized title."""
    seen = set()
    unique = []
    for art in articles:
        key = re.sub(r"\W+", "", art["title"].lower())
        if key and key not in seen:
            seen.add(key)
            unique.append(art)
    return unique


# ---------------------------------------------------------------------------
# Step 2: Scrape full article text, filtering junk paragraphs
# ---------------------------------------------------------------------------

def resolve_google_news_link(url, interval=1.0):
    """Google News RSS links are encrypted redirects, not real article URLs —
    and following the HTTP redirect doesn't work because Google serves a
    JavaScript-rendered page at news.google.com instead of a server redirect.

    Uses the `googlenewsdecoder` package, which extracts the encoded article
    ID, fetches Google's signing parameters for it, and calls Google's
    internal batchexecute endpoint to recover the real publisher URL.

    `interval` adds a small delay before the decode request — Google rate
    limits (HTTP 429) this endpoint if hit too fast/too often.
    """
    if "news.google.com" not in url:
        return url
    try:
        result = gnewsdecoder(url, interval=interval)
        if result and result.get("status"):
            return result["decoded_url"]
    except Exception:
        pass
    return None  # could not decode -> caller should skip this article cleanly


def fetch_article_text(url, verbose=False):
    """Download the article and return cleaned body text, or None if it fails.
    If verbose, prints the specific reason for failure (useful for debugging
    a site or batch that's failing more than expected).
    """
    real_url = resolve_google_news_link(url)
    if real_url is None:
        if verbose:
            print("    [reason: could not decode Google News redirect to a real URL]")
        return None

    try:
        resp = requests.get(real_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        if verbose:
            print(f"    [reason: request failed - {e}]")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    clean_paragraphs = [
        p for p in paragraphs
        if len(p) >= MIN_PARAGRAPH_CHARS and not JUNK_RE.search(p)
    ]

    if not clean_paragraphs:
        if verbose:
            print(f"    [reason: 0 usable paragraphs out of {len(paragraphs)} <p> tags found "
                  f"| final URL: {real_url[:90]}]")
        return None

    return " ".join(clean_paragraphs)


def split_sentences(text):
    """Lightweight sentence splitter — no external download required."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = SENTENCE_SPLIT_RE.split(text)
    # Drop fragments that are too short to carry real sentiment signal
    return [s.strip() for s in sentences if len(s.strip()) >= 15]


# ---------------------------------------------------------------------------
# Step 3: FinBERT sentence-level scoring
# ---------------------------------------------------------------------------

class FinBertScorer:
    """Loads FinBERT once and scores text at the sentence level."""

    def __init__(self, model_name=FINBERT_MODEL_NAME):
        print(f"Loading FinBERT model '{model_name}'... (first run downloads ~400MB)")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.eval()

    def score_sentence(self, sentence):
        """Returns (signed_score, label) for one sentence.
        signed_score is in [-1, 1]: positive_prob - negative_prob.
        """
        inputs = self.tokenizer(
            sentence, return_tensors="pt", truncation=True, max_length=512
        )
        with torch.no_grad():
            logits = self.model(**inputs).logits
        probs = torch.softmax(logits, dim=1).numpy()[0]

        prob_map = dict(zip(LABELS, probs))
        signed_score = prob_map["Positive"] - prob_map["Negative"]
        label = LABELS[probs.argmax()]
        return float(signed_score), label

    def score_article(self, full_text, use_lead_weighting=True):
        """Scores an article by averaging sentence-level scores.

        use_lead_weighting: news articles front-load the actual news in the
        first few sentences; later sentences are often background/boilerplate
        that survived paragraph filtering. Weighting the lead sentences more
        heavily reduces dilution from that tail.

        Returns dict with article-level score, label, and sentence count.
        """
        sentences = split_sentences(full_text)
        if not sentences:
            return {"score": 0.0, "label": "Neutral", "n_sentences": 0}

        scores = []
        weights = []
        for i, sent in enumerate(sentences):
            score, _ = self.score_sentence(sent)
            scores.append(score)
            if use_lead_weighting:
                # First 3 sentences get weight 2.0, rest get weight 1.0
                weights.append(2.0 if i < 3 else 1.0)
            else:
                weights.append(1.0)

        weighted_avg = sum(s * w for s, w in zip(scores, weights)) / sum(weights)

        if weighted_avg > 0.10:
            label = "Positive"
        elif weighted_avg < -0.10:
            label = "Negative"
        else:
            label = "Neutral"

        return {"score": weighted_avg, "label": label, "n_sentences": len(sentences)}


# ---------------------------------------------------------------------------
# Step 4 + 5: Run pipeline, aggregate, persist
# ---------------------------------------------------------------------------

def article_id(url):
    """Stable id so re-running the pipeline doesn't double-count an article
    you've already scored in a previous run."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def load_seen_article_ids(path):
    try:
        df = pd.read_csv(path)
        return set(df["article_id"].astype(str))
    except FileNotFoundError:
        return set()


def run_pipeline(ticker, friendly_name=None, num_articles_per_query=NUM_ARTICLES_PER_QUERY):
    paths = ticker_paths(ticker)
    queries = build_queries_for_ticker(ticker, friendly_name)

    scorer = FinBertScorer()
    today = date.today().isoformat()

    print(f"\nTicker: {ticker}  |  News queries: {queries}")
    articles = fetch_all_news(queries, num_articles_per_query)
    print(f"Found {len(articles)} unique articles after dedup.")

    already_seen = load_seen_article_ids(paths["articles"])

    rows = []
    for i, art in enumerate(articles, 1):
        aid = article_id(art["link"])
        if aid in already_seen:
            continue  # already scored this exact article in a previous run

        print(f"[{i}/{len(articles)}] Scraping: {art['title'][:70]}")
        text = fetch_article_text(art["link"], verbose=True)
        if not text:
            print("    -> could not retrieve usable article text, skipping")
            continue

        result = scorer.score_article(text)
        print(f"    -> {result['label']} (score={result['score']:+.3f}, "
              f"{result['n_sentences']} sentences scored)")

        rows.append({
            "article_id": aid,
            "date": today,
            "ticker": ticker,
            "query": art["query"],
            "source": art["source"],
            "title": art["title"],
            "link": art["link"],
            "published": art["published"],
            "sentiment_score": result["score"],
            "sentiment_label": result["label"],
            "n_sentences": result["n_sentences"],
        })

    if not rows:
        print("\nNo new articles to score (all already seen or unscrapable). "
              "Using existing history for comparison/plot.")
        return paths

    new_df = pd.DataFrame(rows)

    # Append to per-article log
    write_header = True
    try:
        pd.read_csv(paths["articles"], nrows=1)
        write_header = False
    except FileNotFoundError:
        pass
    new_df.to_csv(paths["articles"], mode="a", header=write_header, index=False)

    # Aggregate today's new articles -> one row per date (single ticker per file)
    daily_agg = (
        new_df.groupby(["date", "ticker"])
        .agg(
            mean_sentiment=("sentiment_score", "mean"),
            n_articles=("sentiment_score", "count"),
            n_positive=("sentiment_label", lambda s: (s == "Positive").sum()),
            n_negative=("sentiment_label", lambda s: (s == "Negative").sum()),
            n_neutral=("sentiment_label", lambda s: (s == "Neutral").sum()),
        )
        .reset_index()
    )

    # If we already have a row for today, merge (re-running same day adds new
    # articles' worth of signal rather than creating a duplicate day row).
    daily_agg = merge_today_row(paths["daily"], daily_agg, today, ticker)

    print(f"\nScored {len(rows)} new articles.")
    print(f"Per-article log -> {paths['articles']}")
    print(f"Daily aggregate -> {paths['daily']}")
    print("\nToday's aggregate:")
    print(daily_agg.to_string(index=False))

    return paths


def run_comparison_and_plot(paths, ticker, price_period="3mo"):
    """Joins sentiment history with price history, prints a comparison table,
    and saves a two-panel plot. Safe to call even with just one day of data
    (the table/plot will just be thin until more days accumulate)."""
    combined = combine_sentiment_and_price(paths, ticker, price_period=price_period)
    print_comparison_table(combined, ticker)
    plot_sentiment_and_price(combined, ticker, paths["plot"])
    return combined


def merge_today_row(daily_csv_path, new_today_agg, today, ticker):
    """Combine a newly-computed "today" aggregate row with any existing row
    for today already in the CSV (handles multiple runs per day correctly,
    weighting by article count rather than just overwriting)."""
    try:
        existing = pd.read_csv(daily_csv_path)
    except FileNotFoundError:
        new_today_agg.to_csv(daily_csv_path, index=False)
        return new_today_agg

    mask = (existing["date"] == today) & (existing["ticker"] == ticker)
    if mask.any():
        old_row = existing[mask].iloc[0]
        new_row = new_today_agg.iloc[0]
        old_n, new_n = old_row["n_articles"], new_row["n_articles"]
        total_n = old_n + new_n
        combined_mean = (old_row["mean_sentiment"] * old_n + new_row["mean_sentiment"] * new_n) / total_n

        existing.loc[mask, "mean_sentiment"] = combined_mean
        existing.loc[mask, "n_articles"] = total_n
        existing.loc[mask, "n_positive"] = old_row["n_positive"] + new_row["n_positive"]
        existing.loc[mask, "n_negative"] = old_row["n_negative"] + new_row["n_negative"]
        existing.loc[mask, "n_neutral"] = old_row["n_neutral"] + new_row["n_neutral"]
    else:
        existing = pd.concat([existing, new_today_agg], ignore_index=True)

    existing.to_csv(daily_csv_path, index=False)
    result = existing[(existing["date"] == today) & (existing["ticker"] == ticker)]
    return result


# ---------------------------------------------------------------------------
# Step 6: Combine sentiment with price direction, plot both
# ---------------------------------------------------------------------------

def combine_sentiment_and_price(paths, ticker, price_period="3mo"):
    """Loads the full daily sentiment history for this ticker, fetches matching
    price history, joins them on date, and writes a combined CSV with sentiment
    alongside that day's price direction/% change.
    """
    try:
        sentiment_df = pd.read_csv(paths["daily"])
    except FileNotFoundError:
        print("No daily sentiment history yet — run the pipeline at least once first.")
        return None

    sentiment_df["date"] = sentiment_df["date"].astype(str)

    print(f"Fetching price history for {ticker}...")
    price_df = fetch_price_history(ticker, period=price_period)
    if price_df.empty:
        print(f"Could not fetch price data for '{ticker}'. Check the symbol is "
              f"valid on Yahoo Finance (e.g. AAPL, GC=F, BTC-USD, GLD).")
        return None
    price_df.to_csv(paths["price"], index=False)

    combined = pd.merge(sentiment_df, price_df, on="date", how="inner")
    combined = combined.sort_values("date").reset_index(drop=True)

    # Did sentiment direction agree with price direction that day?
    def sentiment_direction(score):
        if score > 0.10:
            return "Up"
        elif score < -0.10:
            return "Down"
        return "Flat"

    combined["sentiment_direction"] = combined["mean_sentiment"].apply(sentiment_direction)
    combined["agrees_with_price"] = combined["sentiment_direction"] == combined["direction"]

    combined.to_csv(paths["combined"], index=False)
    return combined


def print_comparison_table(combined, ticker):
    """Neat console table: date | sentiment | price direction | % change | match?"""
    if combined is None or combined.empty:
        print("Nothing to compare yet.")
        return

    print(f"\n--- Sentiment vs Price Movement: {ticker} ---")
    display_df = combined[[
        "date", "mean_sentiment", "sentiment_direction", "n_articles",
        "pct_change", "direction", "agrees_with_price"
    ]].rename(columns={
        "mean_sentiment": "sentiment_score",
        "sentiment_direction": "sentiment_says",
        "pct_change": "price_%_change",
        "direction": "price_says",
        "agrees_with_price": "match",
    })
    display_df["sentiment_score"] = display_df["sentiment_score"].round(3)
    display_df["price_%_change"] = display_df["price_%_change"].round(2)
    print(display_df.to_string(index=False))

    match_rate = combined["agrees_with_price"].mean() * 100
    print(f"\nSentiment direction matched same-day price direction on "
          f"{match_rate:.1f}% of days ({combined['agrees_with_price'].sum()}/{len(combined)}).")
    print("Note: small sample sizes (few days/articles) make this rate noisy — "
          "treat it as illustrative, not a robust backtest.")


def plot_sentiment_and_price(combined, ticker, save_path):
    """Two-panel plot: top = sentiment score over time (bar, colored by sign),
    bottom = closing price over time (line), sharing the same date axis so
    you can visually line up sentiment swings against price moves.
    """
    if combined is None or combined.empty:
        print("Nothing to plot yet.")
        return

    dates = pd.to_datetime(combined["date"])

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 7), sharex=True,
        gridspec_kw={"height_ratios": [1, 1.2]}
    )

    # --- Panel 1: daily mean sentiment ---
    colors = combined["mean_sentiment"].apply(lambda s: "#2ca02c" if s > 0 else "#d62728")
    ax1.bar(dates, combined["mean_sentiment"], color=colors, width=0.7)
    ax1.axhline(0, color="black", linewidth=0.8)
    ax1.set_ylabel("Mean sentiment\n(-1 to +1)")
    ax1.set_title(f"{ticker}: Daily News Sentiment vs. Closing Price")
    ax1.grid(axis="y", alpha=0.3)

    # --- Panel 2: closing price ---
    ax2.plot(dates, combined["Close"], color="#1f77b4", marker="o", markersize=4)
    ax2.set_ylabel("Close price")
    ax2.set_xlabel("Date")
    ax2.grid(axis="y", alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate(rotation=45)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"Plot saved -> {save_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def prompt_for_ticker():
    """Interactive ticker picker when no --ticker is passed on the command line."""
    print("Examples: AAPL, TSLA, NVDA, GC=F (gold futures), GLD (gold ETF), BTC-USD")
    ticker = input("Enter a ticker to analyze: ").strip().upper()
    friendly = input(
        "Optional: friendly name for news search (press Enter to auto-detect, "
        "e.g. 'Apple' for AAPL): "
    ).strip()
    return ticker, (friendly or None)


def main():
    parser = argparse.ArgumentParser(description="Daily full-article sentiment tracker")
    parser.add_argument("--ticker", help="Ticker symbol, e.g. AAPL, GC=F, GLD, BTC-USD")
    parser.add_argument("--name", help="Friendly name to use in news search queries "
                                        "(e.g. 'Apple' instead of raw ticker 'AAPL')")
    parser.add_argument("--num-articles", type=int, default=NUM_ARTICLES_PER_QUERY,
                         help="Articles fetched per query per source")
    parser.add_argument("--price-period", default="3mo",
                         help="How much price history to pull for the comparison/plot "
                              "(yfinance period string, e.g. 1mo, 3mo, 6mo, 1y)")
    parser.add_argument("--skip-news", action="store_true",
                         help="Skip fetching/scoring new articles; just regenerate the "
                              "comparison table and plot from existing saved history")
    args = parser.parse_args()

    if args.ticker:
        ticker, friendly_name = args.ticker.upper(), args.name
    else:
        ticker, friendly_name = prompt_for_ticker()

    paths = ticker_paths(ticker)

    if args.skip_news:
        if not os.path.exists(paths["daily"]):
            print(f"No saved sentiment history for {ticker} yet at {paths['daily']}. "
                  f"Run once without --skip-news first.")
            return
    else:
        paths = run_pipeline(ticker, friendly_name, args.num_articles)

    run_comparison_and_plot(paths, ticker, price_period=args.price_period)


if __name__ == "__main__":
    main()