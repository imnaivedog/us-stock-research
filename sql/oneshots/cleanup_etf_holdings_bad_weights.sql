DELETE FROM etf_holdings_latest
WHERE weight IS NULL
   OR weight <= 0
   OR weight > 1.05;
