## Counts (all splits)

### correct_action at offset 0, by page

| page           |   go |   reaim |   replan |
|:---------------|-----:|--------:|---------:|
| live_dashboard |   50 |      52 |       78 |
| live_doc       |   38 |      67 |       75 |
| live_feed      |   23 |      28 |      129 |
| live_news      |   54 |      46 |       80 |
| tier0_booking  |   60 |      58 |       82 |

### correct_action by event (DOM label vs event name)

| event           |   go |   reaim |   replan |
|:----------------|-----:|--------:|---------:|
| covered         |    0 |       3 |      181 |
| gone            |    0 |       0 |      184 |
| moved           |   45 |     105 |       34 |
| moved_lookalike |   30 |     129 |       25 |
| none            |  150 |      14 |       20 |

### by motion level

| motion   |   go |   reaim |   replan |
|:---------|-----:|--------:|---------:|
| high     |   48 |      69 |      123 |
| low      |   66 |      61 |      113 |
| med      |   51 |      63 |      126 |
| none     |   60 |      58 |       82 |

### median motion_200ms and change_gap by motion level (fraction of pixels > 20/255)

| motion   |   motion_200ms |   change_gap |
|:---------|---------------:|-------------:|
| high     |         0.0047 |       0.0353 |
| low      |         0.0014 |       0.0234 |
| med      |         0.0031 |       0.0293 |
| none     |         0.0000 |       0.0040 |

Pairs whose correct action changes during the 16 s after current_b: 115 of 920

Pairs with look-alikes visible at offset 0: 306

Page JS errors: 0

### split sizes

|             |   pairs |
|:------------|--------:|
| (0, 'dev')  |      60 |
| (0, 'test') |     140 |
| (1, 'dev')  |     240 |
| (1, 'test') |     480 |

### worked set

| page           |   failed_error |   failed_silent |   success_clear |   success_small |
|:---------------|---------------:|----------------:|----------------:|----------------:|
| live_dashboard |             15 |              15 |              15 |              15 |
| live_doc       |             15 |              15 |              15 |              15 |
| live_feed      |             15 |              15 |              15 |              15 |
| live_news      |             15 |              15 |              15 |              15 |
| tier0_booking  |             15 |              15 |              15 |              15 |

| split   |   pairs |
|:--------|--------:|
| dev     |     100 |
| test    |     200 |