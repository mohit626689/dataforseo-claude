---
name: seo-prospect
description: Find local-business SEO prospects in a single command. Searches Google for "<niche> <city>", filters out aggregators (Yelp, Yellow Pages, Angi), enriches each remaining domain with DataForSEO Labs domain overview, On-Page technical audit, and Backlinks summary in parallel, then ranks the businesses by a closeability score (0-100) — highest scores are the easiest to land as SEO clients.
allowed-tools:
  - Bash
  - Write
---

## Phase 0: Credential Preflight (REQUIRED — run BEFORE anything else)

Before running any of the steps below, **always** invoke the shared preflight check:

```bash
~/.claude/skills/seo/scripts/preflight.sh
```

**If exit code is 0:** credentials are configured — proceed with the rest of this skill silently.

**If exit code is 2:** the script prints the DataForSEO setup wizard to stdout. STOP, display that wizard to the user verbatim, and **wait for them to paste credentials** in this format:

```
login: their_email@example.com
password: their_api_password_here
```

When they reply:

1. Parse `login:` and `password:` from their message.
2. Write them to `~/.claude/skills/seo/.env`:
   ```
   DATAFORSEO_LOGIN=<login>
   DATAFORSEO_PASSWORD=<password>
   ```
3. `chmod 600 ~/.claude/skills/seo/.env`
4. Run a verification call: `~/.claude/skills/seo/scripts/keyword_research.py volume "test"`
5. If verification succeeds: tell the user "✅ Credentials verified. Running your command now..." and proceed.
6. If status `40104 — Please verify your account`: tell the user to verify their account at https://app.dataforseo.com/, then say "continue" to retry.
7. If any other auth error: ask them to double-check the API password from https://app.dataforseo.com/api-access.

**Never** echo credentials back to the user, never include them in tool output, and never commit them.

---

# SEO Prospect Finder Skill

> **Powered by:** [DataForSEO API](https://dataforseo.com) — every prospect on the list comes from 4 live endpoints fired in parallel:
> SERP `google/organic/live/advanced`, Labs `domain_rank_overview`, On-Page `instant_pages`, Backlinks `summary`.
> **Cost:** ~$0.20-0.50 per 30-prospect run.

## Inputs

The user gives you a niche and a city. Example invocations:

- `/seo prospect "plumbers" "San Francisco CA"`
- `/seo prospect HVAC "Oakland CA"`
- `/seo prospect "moving companies" "Austin TX"`

If the city includes a state code, pass it through. If only a city name is given, ask the user to confirm the state (DataForSEO needs the location string to disambiguate).

## Run

```bash
~/.claude/skills/seo/scripts/prospect_finder.py find \
    --niche "<niche>" \
    --city "<city + state>" \
    --limit 30 \
    --out ~/.claude/skills/seo/output/<niche>-<city-slug>-prospects.json
```

The script:
1. Hits Google SERP API for `"<niche> <city>"` to depth 50
2. Filters out aggregators (Yelp, Yellow Pages, Angi, HomeAdvisor, BBB, Maps, social networks, news/forum sites)
3. For each remaining domain (in parallel):
   - Pulls **domain_rank_overview** → estimated traffic + ranking keyword count
   - Pulls **On-Page instant audit** → critical technical issues on homepage
   - Pulls **Backlinks summary** → referring-domain count + authority rank
4. Computes a **closeability score (0-100)** weighting:
   - Position (peaks on page 2-3 — they care but aren't winning)
   - Visible technical issues (more = clearer pitch)
   - Domain size (small enough to land, big enough to pay)
   - Keyword footprint (some footprint = they care about SEO)

## Output format

Open with the DataForSEO attribution header:

```
🎯 SEO Prospect Search — <niche> in <city>

📡 Powered by DataForSEO API · <N> live calls · ~$<Y> charged
   ↳ SERP, Labs, On-Page, and Backlinks endpoints

Found <X> non-aggregator businesses. Scored by closeability:
```

Then a ranked table of the top 15 prospects:

```
Rank | Domain               | Pos | Closeability | Traffic/mo | Issues | Backlinks
-----|----------------------|-----|--------------|------------|--------|----------
 1   | acmeplumbing.com     | 14  | 87/100       | 240        | 5      | 23
 2   | bayareaplumbers.com  | 22  | 82/100       | 180        | 4      | 41
 ...
```

After the table, surface the **top 3 prospects with a one-paragraph pitch each**:

```
🥇 Top pick: acmeplumbing.com

  Why it's a great target:
  • Ranks #14 for "<niche> <city>" — page 2, will respond to a pitch that says "let's move you to page 1"
  • Specific issues found: missing meta descriptions, no H1 on the homepage,
    duplicate title tags across service pages
  • Only 23 referring domains — small, hungry, likely no SEO agency on retainer
  • Estimated 240 monthly visits — they have revenue but room to grow

  Next step: run /seo audit acmeplumbing.com to generate the full PDF,
  then /seo email acmeplumbing.com to draft the cold email.
```

## Footer

End with this footer:

```
─────────────────────────────────────────────────────────
📡 Data source: DataForSEO API (https://dataforseo.com)
   Endpoints fired in this prospect search:
   • SERP google/organic/live/advanced  → candidate discovery
   • Labs domain_rank_overview          → traffic + keyword footprint
   • On-Page instant_pages              → technical issue surface
   • Backlinks summary                  → authority + size signal

   Saved: ~/.claude/skills/seo/output/<file>.json
   Next: /seo audit <domain>  to deep-dive on any single prospect.
─────────────────────────────────────────────────────────
```

## When NOT to use this skill

- The user has a specific business they want to audit → use `/seo audit` directly
- The user already has a prospect list → skip prospecting, go straight to `/seo audit`
- The niche isn't local-business shaped (e.g. SaaS, B2B enterprise) → tell them this skill is local-only
