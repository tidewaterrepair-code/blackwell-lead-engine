# Stripe setup (about 20 minutes)

Pegasus handles checkout, upgrades, the customer portal, credits, add-ons, founding pricing and referral commissions. You create the products once and paste their price IDs into `.env`.

## 1. Products and prices

Create these in **Stripe → Product catalog** (test mode first). Use recurring prices for subscriptions and one-time prices for credit packs.

| Product | Price | `.env` variable |
|---|---|---|
| Pegasus Pro | $79 / month | `STRIPE_PRICE_PRO_MONTHLY` |
| Pegasus Pro | $790 / year | `STRIPE_PRICE_PRO_ANNUAL` |
| Pegasus Growth | $179 / month | `STRIPE_PRICE_GROWTH_MONTHLY` |
| Pegasus Growth | $1,790 / year | `STRIPE_PRICE_GROWTH_ANNUAL` |
| Pegasus Agent Elite | $249 / month | `STRIPE_PRICE_ELITE_MONTHLY` |
| Pegasus Agent Elite | $2,490 / year | `STRIPE_PRICE_ELITE_ANNUAL` |
| Pegasus Team | $799 / month | `STRIPE_PRICE_TEAM_MONTHLY` |
| Pegasus Team | $7,990 / year | `STRIPE_PRICE_TEAM_ANNUAL` |
| Extra territory | $29 / month | `STRIPE_PRICE_TERRITORY_ADDON` |
| Exclusive ZIP | $149 / month | `STRIPE_PRICE_EXCLUSIVE_ZIP` |
| 100 credits | $25 one-time | `STRIPE_PRICE_CREDITS_25` |
| 450 credits | $100 one-time | `STRIPE_PRICE_CREDITS_100` |
| 1,250 credits | $250 one-time | `STRIPE_PRICE_CREDITS_250` |

The amounts must match `pegasus/plans.py`, which is what the pricing page shows. Change both together.

## 2. Founding-member coupon

**Product catalog → Coupons → New**: 40% off, duration **Forever**. Put its ID in `STRIPE_COUPON_FOUNDING`. Pegasus applies it at checkout to the first 100 accounts (`founding_member`).

## 3. Webhook

**Developers → Webhooks → Add endpoint**: `https://YOUR_DOMAIN/api/stripe/webhook`, with these events:

- `checkout.session.completed`
- `customer.subscription.created`, `customer.subscription.updated` and `customer.subscription.deleted`
- `invoice.paid` (also records referral commission)
- `invoice.payment_failed`

Copy the signing secret into `STRIPE_WEBHOOK_SECRET`. Events are verified and processed idempotently, so retries are safe.

## 4. Customer portal and tax

- **Settings → Billing → Customer portal**: allow plan switching between the prices above, cancellation and payment-method updates.
- **Stripe Tax** (optional): turn it on and register where you have nexus. Virginia taxes some SaaS; ask your accountant.

## 5. Test

Use card `4242 4242 4242 4242`. Sign up, open Billing, upgrade, then check that the plan changes in the app and the event shows in Mission Control. Run `stripe listen --forward-to localhost:8000/api/stripe/webhook` for local testing.

## Referral payouts

Commissions build up in the `referrals` table (30% of each paid invoice) and show in Mission Control. Pay them monthly by PayPal, Wise or Stripe Connect, and keep W-9s for US affiliates paid $600+ a year.
