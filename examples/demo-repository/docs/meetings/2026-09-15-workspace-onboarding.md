---
type: Meeting Note
title: Workspace onboarding sync
description: Product and engineering discussion about invitation expiry, resending and error handling.
tags: [meeting, onboarding, invitations]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T15:27:22Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T15:27:22Z }
meeting_date: 2026-09-15
attendees: [Lina (product), Omar (engineering lead), Sara (support), Yusuf (backend)]
---

# Context

A customer on an enterprise trial reported that a former contractor joined their workspace using an invitation link forwarded months earlier. Support has seen similar cases.

# Discussion

- Lina: invitations must stop working after a while. She proposed **7 days** by default, and wants workspace owners to be able to change it.
- Omar suggested limiting the setting to **1–30 days**. He is unsure the admin settings screen can take on another field this cycle.
- Sara: people who open a dead link today get a generic "Page not found". They need a clear message saying the invitation expired, and a way to ask for a new one.
- Admins must be able to **resend** an invitation. Resending replaces the old link; the old one must stop working.
- Yusuf: tokens are already single-use and stored as hashes ([ADR-0001](/adr/0001-invitation-tokens.md)), so expiry is mostly a new timestamp and a check at acceptance. Resend needs a new token, because the old one cannot be recovered.
- Lina would like this live before the enterprise trial ends in early November. No firm date was agreed.

# Decisions

- Invitations expire. The default is 7 days.
- Resending an invitation invalidates the previous link.

# Out of scope

- Changing the email provider or email templates beyond the link itself.
- SSO and SCIM provisioning.

# Open questions

- Do invitations that already exist get an expiry date at rollout, or keep working until used?
- Is the expiry period set per workspace or once for the whole product? Lina prefers per workspace; Omar is concerned about the settings screen.
- Should the expired-link page show who sent the invitation?

# Action items

- Lina: turn this discussion into requirements.
- Yusuf: confirm how invitation lookup by token hash behaves when an invitation is resent.
