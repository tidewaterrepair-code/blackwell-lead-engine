# Weekly routine (about 30 minutes, Mondays)

1. **Data posts**: `pegasus marketing weekly-posts`. Review `dist/weekly/*.md`, schedule them in Postiz or Zapier for Tuesday, and paste them into the Listmonk newsletter.
2. **Creative refresh**: in Ads Manager, pause any ad with CTR under 0.8% after 2,000 impressions. Swap in the next banner or video from `ads/campaigns.yaml` (edit, then `pegasus marketing ads` and import).
3. **Budget**: move 20% of spend from the worst channel by cost per trial (Mission Control → by source) to the best.
4. **Source health**: Mission Control → Sources. Approve pending Source Scout proposals and look at anything marked broken.
5. **Replies**: answer every reply to lifecycle emails (they're from you, so people do reply) and note feature requests.
6. **Social proof**: with permission, turn real wins into posts. Never invent or embellish.

Monthly: pay referral commissions, review the calendar for next month (duplicate `calendar.csv`, refresh hooks that performed), and re-render banners if pricing or offers changed.

## Cron (optional)

On the VPS, render the weekly posts automatically every Monday at 6:00:

```
0 6 * * 1  cd /opt/pegasus && docker compose exec -T web pegasus marketing weekly-posts --out /data/marketing
```
