---
name: seo-email
description: Draft a personalized cold email to a prospect based on the SEO audit findings. Reads the audit JSON for the given domain, picks the 2-3 most impactful issues, and writes an outreach email that references specific data (current ranking, traffic value, named issues) so it doesn't look like spam.
allowed-tools:
  - Read
  - Write
---

## Phase 0: Credential Preflight (REQUIRED — run BEFORE anything else)

Before running any of the steps below, **always** invoke the shared preflight check:

```bash
~/.claude/skills/seo/scripts/preflight.sh
```

**If exit code is 0:** credentials are configured — proceed with the rest of this skill silently.

**If exit code is 2:** the script prints the DataForSEO setup wizard to stdout. STOP, display that wizard to the user verbatim, and **wait for them to paste credentials**.

When they reply, parse `login:` and `password:`, write to `~/.claude/skills/seo/.env` (chmod 600), verify with `keyword_research.py volume "test"`, and proceed only after success. Never echo credentials.

---

# SEO Cold Email Drafter

> **Powered by:** Reads the audit JSON produced by `/seo audit` (built from live [DataForSEO API](https://dataforseo.com) data). No new API calls — purely a drafting step.

## Prerequisite

`/seo audit <domain>` must have run first and saved
`~/.claude/skills/seo/output/<domain>-audit.json`. If that file doesn't exist,
tell the user to run the audit first.

## Inputs

The user provides a domain:

- `/seo email acmeplumbing.com`
- `/seo email <domain>`

Optionally they can supply their own name/signature — otherwise use a generic placeholder.

## Workflow

1. Read `~/.claude/skills/seo/output/<domain>-audit.json`
2. Pick the **2-3 most impactful findings** from `audit.issues` — prioritize critical and high-priority issues that have clear business impact (lost traffic, lost revenue, broken pages indexable).
3. Pull the **single highest-leverage keyword opportunity** from `audit.top_keywords` — ideally one where they currently rank position 4-30 with decent volume and CPC. Compute its estimated monthly value: `search_volume × CPC × 0.3` (rough CTR for that position band).
4. Draft an email that:
   - Has a **short, specific subject** that references their domain or the issue (not "I do SEO")
   - Opens by referencing something specific you noticed (not "I came across your website")
   - Lists **2-3 specific findings** in bullet form — concrete, not generic ("you're missing meta descriptions on 12 service pages" not "your SEO needs work")
   - Quantifies the value of one specific opportunity in dollars
   - Offers to send the **full PDF audit** as a soft ask (no hard pitch)
   - Ends with a low-pressure sign-off
5. Output the email in this format (copy-pasteable):

```
─────────────────────────────────────────────────────────
TO:      [find their contact email manually]
SUBJECT: <short, specific subject>

Hi [Owner / first name if you can find it],

<2-3 sentence opening that references something specific>

<bullet list of 2-3 concrete findings with numbers>

<one quantified opportunity — e.g. "for example, you're #14 for 'plumbers san francisco' which is ~2,400 searches/mo at $14 CPC, so moving to top 3 is worth roughly $X/month in click value">

I put together a quick 1-page PDF audit that shows 5-7 specific fixes
ranked by impact. Want me to send it over?

[Your name]
─────────────────────────────────────────────────────────
```

## Tone rules

- **Specific over generic** — every sentence should reference data from THEIR audit, not boilerplate
- **Numbers over adjectives** — say "240 monthly visits" not "decent traffic"
- **One ask only** — "want me to send the PDF?" — don't pitch services in the first email
- **Under 150 words** — long emails get ignored
- **No "I" sentences at the start** — start with "Saw" or "Noticed" or "Your..."
- **No exclamation points** — keeps it professional, not spammy
- **No "leverage," "synergy," "optimize"** or other agency-speak

## Output extras

After the email itself, also surface:

1. **Send time recommendation:** "Tuesday-Thursday, 9-11am their local time gets the best open rates for cold outreach."
2. **Follow-up cadence note:** "If no reply in 4 business days, send a short bump: 'Hey, did this get buried? Happy to send the PDF if you're curious.'"
3. **Reminder:** "Find their actual contact email via their site's /contact page, Google Business Profile, or LinkedIn — the audit doesn't include that."

## When NOT to use this skill

- The audit hasn't run yet → run `/seo audit <domain>` first
- The user wants a generic SEO outreach template → tell them this skill only writes personalized emails grounded in real audit data
