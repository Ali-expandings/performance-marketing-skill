# Column mapping hints (case-insensitive, matched by analyze.py)

| Standard | Meta | Google Ads | TikTok | GA4 / Shopify |
|---|---|---|---|---|
| date | Day, Reporting starts | Day | Date, stat_time_day | Date, Created at |
| platform | (fixed) | (fixed) | (fixed) | Source / medium |
| campaign | Campaign name | Campaign | Campaign name | Campaign |
| adset | Ad set name | Ad group | Ad group name | Content |
| ad | Ad name | Ad / Asset | Ad name | Term |
| spend | Amount spent | Cost | Cost / Spend | n/a |
| impressions | Impressions | Impr. / Impressions | Impressions | n/a |
| clicks | Link clicks / Clicks (all) | Clicks | Clicks | Sessions |
| purchases | Results / Purchases | Conversions | Conversions / Purchases | Transactions / Orders |
| revenue | Purchase conversion value | Conv. value | Total purchase value | Revenue / Total sales |

Tips: Meta "Results" is objective-dependent, confirm it's purchases. Google exports have title and total rows to drop. Prefer link clicks over all clicks for CTR/CVR. Use `--map spend="Amount spent (USD)"` to override.
