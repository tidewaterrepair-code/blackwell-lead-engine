# Email

## Lifecycle sequences (automatic)

Copy: `pegasus/marketing/emails/*.yaml` (shipped with the app so the worker can read it). Each file is one sequence:

| Sequence | Who gets it | Anchor | Emails | Stops when |
|---|---|---|---|---|
| `waitlist` | Waitlist signups without an account | joined waitlist | days 0, 2, 5, 9, 14 | they create an account |
| `onboarding` | Owner of each new account | signup | days 0, 1, 2, 4, 6, 8, 10 | per-email `skip_if` (e.g. already drew an area) |
| `trial` | Trial accounts | trial end | days −3, −1, 0, +4 | they subscribe |
| `winback` | Canceled paid accounts | cancellation | days 3, 14, 30 | they resubscribe |
| `launch` | Broadcast, not automatic | n/a | 1 | n/a |

How sending works (`pegasus/lifecycle.py`, run by the daily worker job):

- An email is due on its day and stays sendable for 3 days. Turning this on never floods people with a backlog.
- Each email is sent once (`emails_sent` is stored per account and per waitlist row).
- Unsubscribed addresses (`email_suppressions` table) are skipped. Every email has a footer link and `List-Unsubscribe` / one-click headers, as Gmail and Yahoo require for bulk senders.
- An account can be opted out entirely by setting `lifecycle_emails: false` in its org settings.

Editing copy: change the YAML and run `pegasus marketing emails`, then open `marketing/dist/email/index.html` to preview all 20. Placeholders include `{first_name}`, `{org_name}`, `{trial_end}`, `{founding_left}`, `{city}`, `{app_url}`, `{signup_url}`, `{pricing_url}`, `{site_url}` and `{city_url}`. Unknown placeholders render blank and never break a send.

Conditions you can use: `stop_if` (sequence level) and `skip_if` / `only_if` (email level) with `paid`, `has_territory`, `has_contacted`, `mode_realestate`, `mode_trades`, and for the waitlist `has_account`.

## Broadcasts (Listmonk)

The launch blast and the weekly "Hot permits in {city}" newsletter go out through Listmonk (self-hosted, free). See `../automation/email.md`.

1. `pegasus marketing emails` writes `dist/email/waitlist_listmonk.csv` (unsubscribed addresses removed) and `dist/email/launch-launch-blast.html`.
2. In Listmonk, import the CSV into a "Waitlist" list, create a campaign, paste the HTML and send a test to yourself first.
