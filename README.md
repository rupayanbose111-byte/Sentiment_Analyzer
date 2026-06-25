# Sentiment_Analyzer
## what does it do?

> The complete system works like a **sentiment-driven stock analysis engine**. 

Think of it as a process that tries to answer: "When the news about a company is positive or negative, does the stock tend to move in the same direction?"

### Step 1: Choose a Stock

You enter any stock ticker, such as:

* Reliance
* TCS
* Infosys
* Apple
* Microsoft

The ticker determines which company will be analyzed.

## Step 2: Collect News Articles

The system searches multiple financial and news sources for recent articles related to the chosen company.

For example, if you select Reliance, it gathers articles discussing:

* Reliance Industries
* Reliance stock
* Reliance business developments
* Reliance earnings
* Reliance acquisitions
* Reliance investments

Using multiple sources helps reduce the risk of missing important news.

## Step 3: Extract the Actual Article Content

News websites contain many things besides the article itself:

* Advertisements
* Navigation menus
* Subscription prompts
* Related article links
* Social media buttons

The system removes these unwanted elements and keeps only the main article text.

The goal is to analyze what the article is actually saying.

## Step 4: Break the Article into Sentences

A news article can contain:

> Reliance reported record profits this quarter.

> The company plans a major expansion into renewable energy.

> Market analysts remain optimistic about growth.

Instead of evaluating the entire article at once, the system evaluates each sentence individually.

This provides more accurate sentiment measurement.

## Step 5: Measure Financial Sentiment

Each sentence is classified as:

* Positive
* Negative
* Neutral

Examples:

| Sentence                           | Sentiment |
| ---------------------------------- | --------- |
| Company reports record profits     | Positive  |
| Earnings decline sharply           | Negative  |
| Board meeting scheduled next month | Neutral   |

Financial language differs from normal language.

For example:

> "Operating margin expanded by 300 basis points"

is positive financially even though it contains no obvious emotional words.

The model is specifically trained on financial news.

## Step 6: Create an Article Score

After scoring all sentences, the system creates one sentiment score for the entire article.

Example:

| Article                    | Score |
| -------------------------- | ----- |
| Strong earnings beat       | +0.75 |
| Regulatory concerns emerge | -0.62 |
| New product launch         | +0.28 |

Positive values indicate bullish news.

Negative values indicate bearish news.

Values near zero indicate neutral news.

---

## Step 7: Aggregate All Articles for the Day

A company may have many news articles in one day.

Example:

| Article              | Score |
| -------------------- | ----- |
| Earnings beat        | +0.80 |
| New expansion        | +0.50 |
| Management reshuffle | -0.10 |

Daily sentiment becomes the average of all article scores.

Example:

```
(+0.80 + 0.50 - 0.10) / 3
= +0.40
```

The final daily sentiment is:

**+0.40 (Positive Day)**

---

## Step 8: Build a Sentiment Time Series

Every day a new sentiment value is stored.

Example:

| Date  | Sentiment |
| ----- | --------- |
| Jan 1 | +0.40     |
| Jan 2 | +0.12     |
| Jan 3 | -0.35     |
| Jan 4 | +0.55     |

Over time this becomes a historical sentiment database.

This is extremely important because a single day's sentiment is not useful for analysis.

You need months of data.

---

## Step 9: Download Historical Stock Prices

The system then downloads stock prices for the same dates.

Example:

| Date  | Close Price |
| ----- | ----------- |
| Jan 1 | 2500        |
| Jan 2 | 2525        |
| Jan 3 | 2480        |
| Jan 4 | 2510        |

---

## Step 10: Determine Daily Price Direction

For every trading day:

| Previous Close | Current Close | Direction |
| -------------- | ------------- | --------- |
| 2500           | 2525          | Up        |
| 2525           | 2480          | Down      |
| 2480           | 2510          | Up        |

Only the direction matters at this stage.

---

## Step 11: Match Sentiment With Price Movement

The system aligns:

| Date  | Sentiment | Price Direction |
| ----- | --------- | --------------- |
| Jan 1 | Positive  | Up              |
| Jan 2 | Positive  | Up              |
| Jan 3 | Negative  | Down            |
| Jan 4 | Positive  | Up              |

This allows direct comparison between news and stock behavior.

---

## Step 12: Calculate Predictive Accuracy

The key question becomes:

### Did positive news lead to an up day?

### Did negative news lead to a down day?

If yes:

✔ Correct prediction

If no:

✘ Incorrect prediction

Example:

| Day | Sentiment | Market Move | Result    |
| --- | --------- | ----------- | --------- |
| 1   | Positive  | Up          | Correct   |
| 2   | Positive  | Down        | Incorrect |
| 3   | Negative  | Down        | Correct   |
| 4   | Negative  | Up          | Incorrect |

Accuracy:

```
Correct Predictions
------------------
Total Predictions
```

Example:

```
65%
```

This tells you how often sentiment agrees with actual stock movement.

---

## Step 13: Interactive Visualization

The dashboard displays:

### Upper Panel

Stock price movement through time.

You can see:

* Uptrends
* Downtrends
* Major turning points

### Lower Panel

Daily sentiment values.

You can visually compare:

* News becoming positive
* News becoming negative
* How the stock reacts afterward

---

## Step 14: Highlight Winning Predictions

Special markers show:

### Green Marker

Positive sentiment and stock moved up.

or

Negative sentiment and stock moved down.

These are successful sentiment signals.

### Red Marker

Positive sentiment but stock fell.

or

Negative sentiment but stock rose.

These are failed signals.

---

## Step 15: What You Can Learn

After collecting several months of data, you can answer:

### Is sentiment useful for this stock?

Some stocks react strongly to news.

Others do not.

---

### Does sentiment lead price?

You can test:

* Same-day effect
* Next-day effect
* Two-day effect

Often next-day sentiment prediction is more useful than same-day prediction.

---

### Which stocks respond most to news?

You can compare:

* Reliance
* TCS
* Infosys
* HDFC Bank
* Apple
* Tesla

and identify which stocks are most sentiment-driven.

---

### Can sentiment improve trading strategies?

You can eventually create rules such as:

* Buy when sentiment > +0.3
* Sell when sentiment < -0.3
* Hold otherwise

and backtest whether these rules outperform buy-and-hold.

In essence, the entire pipeline converts **unstructured news articles → quantified daily sentiment → comparison with actual stock returns → measurement of predictive power**, creating a framework for testing whether news sentiment contains exploitable information for trading or investment decisions.
