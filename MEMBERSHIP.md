# Membership & Tier Switching

## Cancellation visibility

- **When a user cancels** (via Stripe Billing Portal or after subscription ends), the membership row is **kept** with `status='canceled'` and `canceled_at` set. We no longer delete the row, so you can see who had access and lost it.
- **Admin:** `/admin` → **Membership** shows all memberships. Filter or sort by **status** to see `active` vs `canceled`. Use **canceled_at** to see when they lost access.
- **User-facing:** On the Premium page, if they have no active membership but had one that ended, they see a card: “Previous membership: X — Ended on &lt;date&gt;” so they know they no longer have access and can resubscribe.
- **Cancel at period end:** If they choose “Cancel at end of billing period” in Stripe, we set `cancel_at_period_end=True` and keep `status='active'` until the period ends. The Premium page shows “Cancels at period end” and “Access until &lt;date&gt;”.

## Tier switching (testing)

1. **Upgrade / downgrade from Premium page**
   - Log in as a user with an active subscription (e.g. Regular).
   - On `/premium`, click **Upgrade** on another tier (e.g. Gold) or **Downgrade** to a lower tier.
   - You are sent to Stripe Checkout for the new plan. The **old** subscription is canceled when the new payment succeeds (we pass `cancel_subscription_id` and cancel it in the webhook).
   - After payment you are redirected back to `/premium` with the new tier. The webhook creates the new membership and removes the old one for that user.

2. **Switching in Stripe Billing Portal**
   - User clicks “Manage subscription” and changes plan in the Stripe portal.
   - Stripe sends `customer.subscription.updated`. We update the membership’s **tier** by inferring it from the subscription’s product/price, and we update **status**, **current_period_end**, and **cancel_at_period_end** from the subscription object.

3. **What to check when testing**
   - After upgrading: Premium page shows the new tier; Admin → Membership shows one row per user with the new tier and `status=active`.
   - After canceling (portal): When they cancel, we set `cancel_at_period_end` if they chose “end of period,” or when the subscription actually ends we get `customer.subscription.deleted` and set `status=canceled` and `canceled_at`. User then sees the “Ended” card on Premium.
   - Webhook events: Ensure `customer.subscription.updated` and `customer.subscription.deleted` are sent to your webhook URL (Stripe Dashboard → Webhooks → your endpoint → Events to send).

## Gating pages by membership tier

- **Yes:** Membership (and its tier) is associated with the user. `Membership` has `user_id` and `tier` (`early_bird_gold`, `regular`, `gold`). `_get_user_membership(user_id)` returns the user’s **active** membership (or `None`).
- **Decorator:** Use `@membership_required(...)` in `SS/routes.py` to restrict a route:
  - `@login_required` then `@membership_required()` — requires any active membership.
  - `@login_required` then `@membership_required("gold", "early_bird_gold")` — only those tiers can access the page.
- **Order:** Put `@login_required` first, then `@membership_required(...)`, then the view function.
- **Behavior:** If the user isn’t logged in, they’re sent to login. If they have no active membership (or the wrong tier), they’re redirected to `/premium` with a flash message.
- **In templates:** To show/hide content by tier, pass `membership` (from `_get_user_membership(current_user.id)`) and check `membership` and `membership.tier`, e.g. `{% if membership and membership.tier in ['gold', 'early_bird_gold'] %} ... {% endif %}`.
