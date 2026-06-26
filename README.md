# Sentiment_Analyzer
## what does it do?

> The complete system works like a **sentiment-driven stock analysis engine**. 

Think of it as a process that tries to answer: "When the news about a company is positive or negative, does the stock tend to move in the same direction?"

# Overall Workflow

When you run the program, it asks you for a ticker (or you provide one through the command line).

Example:

* AAPL
* TSLA
* NVDA
* RELIANCE.NS
* TCS.NS
* BTC-USD
* GC=F (Gold Futures)

Once the ticker is chosen, everything else is automatic.

---

# Step 1: Build News Search Terms

The program first determines **what keywords should be searched**.

For example,

Ticker:

```
AAPL
```

becomes searches like

* Apple
* Apple price
* Apple forecast

For Gold Futures,

```
GC=F
```

becomes

* gold
* gold price
* gold forecast

This increases the chances of finding relevant news instead of simply searching the ticker symbol.

---

# Step 2: Download News Articles

Next it searches multiple news RSS feeds.

Instead of reading only headlines, it collects links to many news articles.

For every search term, it gathers articles from more than one source to improve coverage.

If the same article appears twice, duplicates are removed.

The result is a clean list of unique articles.

---

# Step 3: Download the Actual Article

News RSS feeds only provide titles and links.

The program visits each article and downloads the **full article text**.

While doing so, it removes things like

* advertisements
* navigation menus
* cookie notices
* subscription prompts
* copyright notices
* social media buttons
* other unwanted webpage text

Only meaningful news paragraphs are kept.

---

# Step 4: Break the Article into Sentences

Rather than treating the entire article as one block,

it splits it into individual sentences.

Example:

Original article

> Apple announced record earnings. Investors welcomed the results. Analysts increased their price targets.

becomes

Sentence 1

Sentence 2

Sentence 3

Each sentence will be evaluated independently.

---

# Step 5: Determine Sentiment of Every Sentence

Every sentence receives a sentiment score.

Possible outcomes include:

* Positive
* Negative
* Neutral

Instead of only assigning labels, every sentence also receives a numerical score between roughly

```
-1  -------------------- 0 -------------------- +1
Very Negative         Neutral            Very Positive
```

This gives a much richer measure than simple positive/negative classification.

---

# Step 6: Compute the Overall Article Sentiment

Once every sentence has been scored,

the article's overall sentiment is calculated.

The program gives **more importance to the first few sentences**, because news articles usually present the key information at the beginning.

For example,

If an article contains

Positive

Positive

Neutral

Negative

Neutral

the final article score might still be positive because the important early sentences carry greater weight.

Each article finally receives

* average sentiment score
* overall sentiment label
* number of analysed sentences

---

# Step 7: Save Every Article

Every analysed article is stored in a log.

The log includes information like

* date
* ticker
* article title
* source
* article URL
* sentiment score
* sentiment label
* number of sentences analysed

Each article also gets a unique identifier.

This prevents analysing the same article again in future runs.

So if you run the program tomorrow,

old articles are skipped automatically.

Only new articles are analysed.

---

# Step 8: Calculate Daily Sentiment

After analysing all articles for the day,

the program combines them into **one daily sentiment value**.

Suppose today's articles are

| Article | Score |
| ------- | ----- |
| 1       | 0.65  |
| 2       | 0.30  |
| 3       | -0.20 |
| 4       | 0.50  |

The daily sentiment becomes approximately

```
Mean sentiment = 0.31
```

It also records

* number of articles analysed
* number of positive articles
* number of negative articles
* number of neutral articles

So instead of dozens of article scores,

you get one summary for the day.

---

# Step 9: Keep Historical Records

The program does not overwrite previous results.

Instead,

every day's sentiment is appended to a historical database.

Over time your file becomes something like

| Date    | Mean Sentiment |
| ------- | -------------- |
| June 20 | 0.45           |
| June 21 | -0.12          |
| June 22 | 0.31           |
| June 23 | 0.18           |

Eventually this forms a complete sentiment time series.

---

# Step 10: Download Historical Price Data

Next,

the program downloads recent market prices for the same ticker.

For every trading day it records

* Open
* High
* Low
* Close
* Volume
* Daily percentage return

It also classifies the day's movement as

* Up
* Down
* Flat

---

# Step 11: Match Sentiment with Price

Now the interesting part.

The sentiment history is matched with price history.

For every date,

the program compares

Daily sentiment

↓

Market movement

Example

| Date      | Sentiment | Market |
| --------- | --------- | ------ |
| Monday    | Positive  | Up     |
| Tuesday   | Negative  | Down   |
| Wednesday | Positive  | Down   |

The program checks whether sentiment correctly predicted the direction.

For every day,

it records

```
Match = True
```

or

```
Match = False
```

---

# Step 12: Calculate Agreement Rate

Finally,

the program computes

> "How often did news sentiment agree with the actual market movement?"

Example

```
30 trading days

Correct = 19

Agreement Rate = 63.3%
```

This gives an indication of how closely same-day news sentiment aligns with price direction. It is descriptive rather than a true predictive backtest.

---

# Step 13: Display a Comparison Table

The program prints a table like

| Date   | Sentiment | Articles | Price Change | Market Direction | Match |
| ------ | --------- | -------- | ------------ | ---------------- | ----- |
| 24 Jun | 0.43      | 12       | +1.8%        | Up               | ✓     |
| 25 Jun | -0.21     | 8        | -0.9%        | Down             | ✓     |
| 26 Jun | 0.18      | 10       | -0.5%        | Down             | ✗     |

This makes it easy to compare news sentiment with actual market behaviour day by day.

---

# Step 14: Create a Visualization

The program also saves a graph with two panels.

### Upper panel

Shows

Daily sentiment score

Positive days appear above zero.

Negative days appear below zero.

You can immediately see periods of optimistic or pessimistic news.

### Lower panel

Shows

Closing stock price

Since both panels share the same dates,

you can visually inspect whether

* improving sentiment preceded price increases,
* worsening sentiment coincided with declines,
* or whether there was little relationship.

---

# Files Created

For each ticker, the program creates several files:

* **Article log:** Every analysed news article and its sentiment.
* **Daily sentiment history:** One aggregated sentiment record per day.
* **Price history:** Historical market prices for the ticker.
* **Combined dataset:** Sentiment and price data merged by date.
* **Plot image:** A chart comparing sentiment and price over time.

Each ticker has its own separate set of files, so analyses remain independent.

# In summary

The code builds a complete **news sentiment tracking pipeline**:

1. Accept a ticker.
2. Search for relevant news.
3. Download full articles.
4. Clean the article text.
5. Evaluate sentiment sentence by sentence.
6. Aggregate to an article-level sentiment.
7. Aggregate to a daily sentiment score.
8. Save historical sentiment data without duplicating articles.
9. Fetch historical price data.
10. Compare daily sentiment with same-day price movement.
11. Calculate how often sentiment and price direction agree.
12. Produce a comparison table and a time-series plot.

Over repeated daily runs, it accumulates a historical dataset that can be used to study the relationship between news sentiment and market movements for any supported financial instrument.

