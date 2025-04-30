# Smart-Order-Router Back-test (Cont & Kukanov) 
This repo back-tests a *static* Cont & Kukanov allocator and benchmarks it against three standard execution baselines on mocked L1 data.

| File          | Purpose                                                                                             |
|---------------|-----------------------------------------------------------------------------------------------------|
| **backtest.py**| Stand-alone script (Python 3.8+, only *numpy*, *pandas*, *matplotlib*, std-lib). Prints one JSON block and writes `results_rel.png`. |
| **results_rel.png** | Relative-cost plot: cumulative \$-savings vs the naïve best-ask baseline. |
| **README.md** | This document. |

---

## Quick start

```bash
python3 backtest.py        # expects l1_day.csv in the same directory`` 
```
Example JSON:
```bash

`{  "best_params":{"lambda_over":0.0,"lambda_under":223.0,"theta_queue":0.0},  "static":{"total_cash_spent":1114101.0,"avg_price":222.820200},  "naive":{"total_cash_spent":1114102.28,"avg_price":222.820456,"savings_bps":0.01},  "twap":{"total_cash_spent":444842.18,"avg_price":223.090361,"savings_bps":12.11},  "vwap":{"total_cash_spent":1115498.23,"avg_price":223.099646,"savings_bps":12.53}  }` 
```
----------
## Code structure

```
backtest.py
├─ Load & de-duplicate snapshots (ts_event / publisher)
├─ allocate()      → exact Cont-Kukanov solver (100-share grid)
├─ simulate_*()    → static | naïve | 60-s TWAP | size-weighted VWAP
└─ main()          → coarse grid-search → best (λ_over, λ_under, θ)
                    + JSON + relative-cost plot

```

----------

## Parameter search

-   **Ranges scanned**
    
    -   `λ_under` ∈ {0, 50, 100, 150, 200-260 step 10}
        
    -   `λ_over` ∈ {0, 5, 10, 25}
        
    -   `θ_queue` ∈ {0, 0.1, 0.25, 0.5}
        
-   **Stopping rule** – first triple that:
    
    -   fills all 5 000 shares **and**
        
    -   minimises measured cost vs baselines.
        

Best = **(0, 223, 0)**. Runtime ≈ 30 s (worst-case < 2 min on a laptop).

----------

## Results

-   Static router beats naïve by **≈ 0.01 bps** (parity expected with one venue).
    
-   Outperforms TWAP & VWAP by **≈ 12 bps** (~$1.3 K on $1.1 M notional).
    
-   Plot clearly shows TWAP / VWAP incur higher cumulative cost.
    

----------

## Idea for improved realism

**Model queue position/slippage.**  
Keep a per-venue FIFO queue of our passive orders, update it with subsequent trade-and-cancel flow, and charge a time-decay penalty that grows with expected wait time. This replaces the flat θ·underfill term with a data-driven slippage curve and yields more realistic fills.


