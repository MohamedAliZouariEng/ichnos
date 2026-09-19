---
type: Reference
title: Quire product overview
description: Quire is a shared notebook for small teams; users, roles, and how onboarding works today.
tags: [product, overview, onboarding]
status: stable
generated: { by: claude/opus-5, at: 2026-09-19T15:27:22Z }
verified: { by: human:MohamedAliZouariEng, at: 2026-09-19T15:27:22Z }
---

# Product

Quire is a web app where small teams keep shared notes. Each team works in a **workspace**; notes, members and settings belong to one workspace.

# Roles

| Role | Can |
| --- | --- |
| Owner | Manage billing, members and workspace settings; delete the workspace |
| Admin | Invite and remove members; manage workspace settings |
| Member | Read and write notes |

# Onboarding today

Owners and admins invite people by email. The email contains a link; opening it lets the invitee create an account and join the workspace. Invitation links never expire, and each link carries a single-use token as decided in [ADR-0001](/adr/0001-invitation-tokens.md).

When an invitation link cannot be used, the invitee sees a generic "Page not found" error.
