# Test notes: 20-day momentum signal on the sector ETF basket

Test design: each Friday from week 1 to week 36 of 2026 the 20-day momentum signal was computed for an equal-weight basket of 11 sector ETFs and standardized to a z-score against its trailing 52-week history. The outcome is the basket's return over the following week, in percent. No transaction costs are included.

Regime labels come from the strategy desk: a week is "bull" when the basket closed above its 200-day moving average on the signal date and "bear" otherwise.

The signal follows the cross-sectional momentum idea of Jegadeesh and Titman (1993, Journal of Finance), applied here in time series to a single basket.

Known limits: 36 weekly observations is a short sample, the weeks overlap with one rate-hiking cycle, and the regime label was assigned after the fact.
