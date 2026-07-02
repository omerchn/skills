# Seeding a customer POC dataset into prod — NHIs + the consumer-app graph

## Orientation

You're reading this because a sales/POC motion needs a customer's **findings**
(usually a list of discovered service accounts / NHIs, handed over as a Notion
doc or sheet) to **show up in that customer's Console** — in their *prod* org —
by a demo deadline. The org is typically **fresh and nearly empty** (created days
ago, a few discovered apps, zero identities/accounts), so you are net-new seeding
data so it renders in the **identity AuthZ access-path graph**, with each service
account shown as a privileged NHI **consumed by** the tool that holds its
credentials (e.g. IdentityIQ).

This is distinct from editing existing demo data in the staging garden
(`knowledge/theorchidgarden-demo-data.md`) — here it's **prod**, **net-new**, and
the **consumer-app graph** is the centrepiece.

The 30-second map of the pipeline you'll drive:

```
findings doc (Notion)
   │  pick scope with PM
   ▼
RAW_APPS                  ← target-system apps (instant: view over raw_apps)
RAW_USERS_SNAPSHOT        ← one source row per service account  } you write these
IDENTITIES_METADATA       ← durable NHI type                    }
   ▼  ComputeIdentityTablesWorkflow  (you run, manually)
ACCOUNTS_SNAPSHOT_V2 + CONSOLIDATED_IDENTITIES_SNAPSHOT_V2   ← compute OWNS these
   ▼
ACCOUNT_CONSUMERS         ← consumer-app graph wiring (you write, direct)
   ▼
feature flags ON (frontend)  →  visible in Console
```

Critical constraint up front: **`sfquery prod_us` authenticates as
`SNOWFLAKE_READONLY`.** You *cannot* write through it. You **prepare** the SQL and
a **colleague with a write-capable prod role runs it**; you run the Temporal
compute workflow yourself (a `workflow start` is not prod-fenced). Plan the whole
thing as "hand off SQL → colleague executes → I verify read-only."

## Mental model

There are **three independent write surfaces**, and the entire skill is knowing
which is which — because two of them you own and one you must **never** touch by
hand:

1. **Apps — `RAW_APPS` (you own; instant).** `LATEST_CONSOLIDATED_APPS` /
   `INT_CONSOLIDATED_APPS_VIEW` are plain **VIEWs over `RAW_APPS`**, not dynamic
   tables. So a single non-ignored, **named** `RAW_APPS` row (one
   `actor='DISCOVERY'` row with `APPLICATION_NAME`, `IGNORED=FALSE`) shows in the
   inventory **immediately** — no dbt, no workflow. App nodes for the accounts to
   hang off appear the moment the insert lands.

2. **Identities/accounts — the V2 snapshots (compute OWNS; never hand-write).**
   `ACCOUNTS_SNAPSHOT_V2` and `CONSOLIDATED_IDENTITIES_SNAPSHOT_V2` are the
   Console's identity read path, and they are **built by
   `ComputeIdentityTablesWorkflow`** (`computeRawUsers → computeAccounts →
   computeConsolidatedIdentities`) from `RAW_USERS_SNAPSHOT` (+
   `IDENTITIES_METADATA`/`ACCOUNTS_METADATA` overrides). You seed the **sources**
   and run compute; you do **not** INSERT the snapshots directly. (Why: a direct
   snapshot write is clobbered the next time compute runs for that (org, app) —
   and a freshly-discovered app sitting in `ANALYSIS_ENGINE=VALIDATING` can
   trigger that mid-demo. Seeding the source makes the data durable because
   *compute itself* reproduces it. Field-by-field derivation + watermark detail
   live in `knowledge/v2-snapshot-compute-watermarks.md` and
   `knowledge/theorchidgarden-demo-data.md` — don't re-derive them here.)

3. **Consumer graph — `ACCOUNT_CONSUMERS` (you own; direct; never compute-built).**
   This junction powers the **consumer/owner node** drawn to the left of an
   identity in the AuthZ graph ("this service account is consumed by X"). Compute
   never builds it, so you write it directly *after* compute, and it survives
   recompute. **The resolution is `consumer_type`-switched:**
   - `consumer_type='APPLICATION'` → `consumer_id` is resolved as an
     **`application_id`** (against the app inventory).
   - `consumer_type='IDENTITY'` → `consumer_id` is resolved as an **`identity_id`**
     (against consolidated identities).
   Pick the type to match what `consumer_id` actually is. To show "consumed by the
   IdentityIQ app", use `APPLICATION` + the identityiq app's `application_id`.

The one-account-grain key everywhere is `(organization_id, identity_id,
application_id, login_identifier)`.

## How to do it

0. **Pin the org and accept the read-only reality.** Resolve the org id +
   region: `SELECT id, name, region FROM ORCHID_SECURITY.CDC.ORGANIZATIONS WHERE
   name ILIKE '%<customer>%'` (no `PUBLIC.ORGANIZATIONS`). Confirm it's the
   intended org and note it's `is_internal=false` (a real customer — extra care).
   Accept that you'll **prepare** SQL and a write-role colleague will **run** it;
   you run the compute WF.

1. **Lock the scope from the findings doc.** Get the list (Notion etc.). Agree
   in/out with the PM — e.g. defer a noisy subset for later. Parse to one row per
   service account: identity name/login, the **target system** it authenticates
   to, and which tool **consumes** the credential.

2. **Model + seed the apps (`RAW_APPS`).** Decide app granularity (one app per
   target system; you can consolidate later — see worked example). Generate
   **RFC-4122 v4 UUIDs** for app ids (`uuidgen`; they pass `z.guid()`/`z.uuid()`
   — patterned fakes can fail validation). Insert one `actor='DISCOVERY'` row per
   app: `APPLICATION_VERSION=1`, `STATUS='INITIAL_RESULTS'`, `IGNORED=FALSE`,
   `APPLICATION_NAME=<readable>`. They appear in the inventory instantly.

3. **Seed the identity sources (`RAW_USERS_SNAPSHOT` + `IDENTITIES_METADATA`).**
   One `RAW_USERS_SNAPSHOT` row per account: `source_type='DATABASE'`,
   `identity_type='NHI'`, `is_privileged=TRUE` (privilege propagates
   `raw_users → account → identity`), `vendor='DATABASE'`, `mfa_status=NULL`,
   full (even if empty) `roles`/`groups`/`permissions` arrays, `updated_at=now`.
   One `IDENTITIES_METADATA` row per identity with `identity_type='NHI'` for a
   **durable** type. Keep `vendor`/`authn_types` to `DATABASE`/`LOCAL` and
   `mfa_status=NULL` so you don't fabricate SSO/MFA findings an NHI can't have.
   **Do not write the V2 snapshots.**

4. **Run compute (you, manually).** Org-scoped (no `applicationId` ⇒ skips
   dictionary-classify + auth-methods children), `backfillFrom` earlier than the
   seed `updated_at`:
   ```bash
   TS=$(date +%s)
   bash skills/temporal-namespaces/scripts/temporal-safe.sh --env core-prod-us \
     workflow start --type ComputeIdentityTablesWorkflow --task-queue identity-task-queue \
     --workflow-id "compute-identity-tables-<org8>-manual-${TS}" \
     --search-attribute 'organizationId="<org_id>"' \
     --input '{"organizationId":"<org_id>","backfillFrom":"<before-seed-ts>"}'
   ```
   ~1 min for a small org. This builds the accounts + consolidated identities.

5. **Wire the consumer graph (`ACCOUNT_CONSUMERS`, direct, after compute).** One
   row per consumed account: the consumed key + `consumer_type` + `consumer_id`
   per the resolution rule. For "consumed by the IdentityIQ app":
   `consumer_type='APPLICATION'`, `consumer_id=<identityiq application_id>`.

6. **Flip the feature flags (frontend owner).** Rendering is FF-gated — **data
   can be perfect and the demo still shows nothing.** There are (at least) two:
   one for the **identity overview**, and one for the **insights badges on the
   graph nodes**. Tell the frontend owner the org id and which flags to enable.

7. **Verify twice — Snowflake and the UI.**
   - **SELECT back**, scoped to your seeded ids, including derived columns
     (account `is_privileged`, `identity_type`, app name resolves, every
     `account_consumers.consumer_id` resolves to the expected app). Counts +
     derived fields, not "INSERT ok".
   - **Eyeball the Console**: the identity **AuthZ graph** (consumer node = the
     right app, privileged badge present), the **application inventory** (target
     apps listed), the **accounts list / identity tile**, and an
     **account search by login**. All four are how "demo-ready" is confirmed.

8. **When the demo doesn't render, diagnose logs-first — don't re-seed.** A
   seeded org has four independent failure surfaces that look identical from the
   UI: missing **data**, a missing **grant** (the service role can't read a
   table), an **un-deployed** webapp, or an **off feature flag**. The reflex to
   re-run the seed is wrong — the data is usually fine. Instead reproduce, take
   the request's `operationId`, pull the identity-service error from Datadog
   (see Landmines), and let the *error class* tell you which layer. Fix that one
   layer and re-verify. Three of the four levers aren't yours to fix directly
   (grant → infra, deploy/FF → frontend) — your job is to pinpoint which, with
   evidence, and hand it to the owner.

9. **Cleanup of pre-existing / orphaned data is the PM's (or customer's) call,
   not eng's.** A fresh customer org often already holds data from earlier pulls
   or discovery, sometimes orphaned (see Landmines). Whether to **backfill**,
   **delete**, or **leave** it is a product/customer judgment about what's "real
   and wanted" — not an engineering default. Surface the options and their
   trade-offs, execute the chosen one, and never silently reshape a customer's
   data on your own initiative.

## Why it's like this

- **Why source-seed + compute instead of writing the snapshots directly?**
  Durability. The snapshots are derived; compute rebuilds them and overwrites
  hand-edits. Seeding the source means the rebuild *reproduces* your rows, so a
  recompute (scheduled, or triggered by the customer's still-analysing app) can't
  wipe the demo. It's also the only honest way to get self-consistent rollups
  (counts, flags) without hand-maintaining them.
- **Why a `DISCOVERY` `raw_apps` row is enough for an app to appear.** The read
  surface is a *view* over `raw_apps`; there's no consolidation lag to wait on.
- **Why the consumer lives in its own junction.** The "who consumes this account"
  edge isn't derivable from identity data — it's an asserted relationship, so it's
  a direct-write table the compute pipeline never touches.
- **Why NHI / `mfa_status=NULL` / `DATABASE` vendor.** These are non-human
  service accounts; MFA/SSO are human-auth concepts, so `NULL` = not applicable
  (what real NHI rows use) and avoids a bogus "privileged without MFA" finding.

## Landmines

- **`sfquery prod_us` is read-only — don't waste time trying to write through
  it.** Prepare SQL, hand it to the colleague with the write role. (You *can*
  run the compute `workflow start` yourself.)
- **Never hand-INSERT `ACCOUNTS_SNAPSHOT_V2` / `CONSOLIDATED_IDENTITIES_SNAPSHOT_V2`.**
  They're compute-owned. Seed `RAW_USERS_SNAPSHOT` + `IDENTITIES_METADATA` and
  recompute. (Deleting from them for cleanup is fine — see the move-account note.)
- **The `seed-ai-agent-identity` `account-consumers.md` doc is STALE.** It says
  "`consumer_id` MUST be an identity_id; an app id → Unknown." Reality today is
  the opposite for apps: `consumer_type='APPLICATION'` → `consumer_id` is an
  **application_id**; an *identity* id under type `APPLICATION` renders
  **"Unknown."** Use `IDENTITY` only when `consumer_id` is genuinely an identity.
  (This cost a full debugging cycle this session.)
- **`ARRAY_CONSTRUCT()` (and functions generally) are rejected in `INSERT … VALUES`.**
  Use `INSERT … SELECT …` for any row carrying an array/expression.
- **The `sfquery --read-only` guard does a naive keyword scan.** A pure `SELECT`
  is blocked if the text contains `drop`/`update`/`delete`/`insert` **anywhere —
  including inside a comment or a word like "dropped"/"stale-update".** Strip
  those words from read-back queries.
- **Identity-level `is_privileged` is `NULL` even for privileged identities — and
  that's normal.** A real prod org (RTX-Prod, 171k identities) has it `NULL` for
  100% of rows. The UI uses `privileged_accounts_count` + the **account-level**
  `is_privileged`. Don't chase the identity flag.
- **Compute has no `DELETE` (one exception).** When you **move** an account to a
  different app (e.g. consolidating per-forest AD apps into one), recompute builds
  the new account but **leaves the old one** — you must `DELETE` the stale
  `ACCOUNTS_SNAPSHOT_V2` rows yourself, or the identity shows duplicate accounts.
  The single exception is `reconcileAdDomainStaleAccounts` (CORE-3657), which only
  deletes **AD-domain-method-derived** accounts — DATABASE-source NHIs aren't in
  its scope, but know it exists.
- **A "fresh" org may already hold a few `raw_users` rows.** Scope verification to
  *your* seeded ids; compute will also (re)build accounts for the pre-existing
  rows — expected, not a bug.
- **Backslash logins (`DOMAIN\user`) render in the graph but the account
  deep-link can 404** (ts-rest path params aren't URL-encoded). Cosmetic for the
  graph demo.
- **FFs are a separate failure mode from data.** If the graph/consumer/badges
  don't show, check the flags before re-checking Snowflake.
- **"I don't see X" → pull the real error first, don't theorise.** The BFF
  returns a generic `500 / "Internal Server Error"` with an `operationId`; the
  actual cause only lives in the *identity-service* log. Take that `operationId`
  (or reproduce and read it off the network tab), then `ddlogs "<operationId>"`
  (finds the BFF hop) → `ddlogs "env:prod-eu service:identity* status:error"`
  for the real Snowflake error a moment later. Classify by what comes back:
  `errorCode 002003 / sqlState 42S02` *"object … does not exist or not
  authorized"* on a plain `SELECT` = the service role can't **see** the object
  (the table is there — it's a privilege issue, an infra lever, not a missing
  table); a clean **empty** result = data / watermark; a **200 with nothing
  drawn** = a frontend render gate or an un-deployed webapp. Theorising before
  reading the log costs a cycle (this session: guessed a render gate; the log
  showed something else entirely).
- **A blank consumer node on an NHI can be a webapp-deploy lag, not your data.**
  The AuthZ consumer/owner column historically rendered only for
  `identity_type='AI_AGENT'`; `core`#4158 (CORE-3667) removed that gate so it
  renders for any type that has `account_consumers` rows. Until that build is
  actually **deployed to the env** — prod can trail staging by days, so check
  the *Console promote staging→production* run, not just the merge date — a
  perfectly-seeded `NHI` shows an empty consumer panel. Confirm the deploy
  before re-touching Snowflake.
- **Patching a DB-pulled identity's `display_name` is a *situational* fix, and
  you patch the source, not the snapshot.** Two traps in one. (1) The durable
  source `computeRawUsers` reads is `USERS_FROM_DATABASES` (via
  `INT_USERS_FROM_DATABASES_VIEW`, `WHERE updated_at > watermark`); editing
  `RAW_USERS_SNAPSHOT` directly is re-blanked on the next compute (the clobber
  trap), so `UPDATE users_from_databases SET display_name = login_identifier`
  and bump `updated_at`. (2) Even done right, the value only *sticks* while the
  source query is **inactive/deleted**. If the query template is **active**, the
  next agent pull MERGEs the source rows again and overwrites your value (the
  MERGE writes only the template's *mapped* columns), so it reverts. With a live
  template the real fix is the template's `mapping.identityInsights` (map a
  name/email column) + re-pull — not a one-off `UPDATE`. Reach for the manual
  backfill **only** for orphaned data from a dead pull.
- **Deleting a query template does NOT delete the rows it already pulled.** They
  persist in `USERS_FROM_DATABASES` carrying the now-dead `query_id`, and flow
  through compute into the read-path as real identities. So "the app shows **no
  query templates**" ≠ "no pulled users" — you can have hundreds of orphaned
  identities with no visible template to explain them. A **login-only** pull
  (the query selected just the username column) leaves
  `display_name`/`email`/`title` blank at every layer downstream; the blank
  consolidated-identity name is the *symptom*, the empty source column is the
  *cause* — it is **not** a compute bug, compute faithfully propagates the blank.

## Worked example (Ascension IIQ, prod US)

- **Org:** Ascension `c2af65f4-6a73-4c3e-8edd-0b458985d6be`, prod US, ~3 weeks
  old — only 4 discovered apps (`identityiq`, `iiqsandbox`, two Varonis exes),
  zero identities/accounts. Findings: the Notion "Ascension IIQ Security
  Findings" credential inventory (SailPoint IIQ service accounts recoverable
  because most are `1:ACP` default-key encrypted).
- **Scope:** 17 non-DB NHIs — 10 AD-forest accounts, 1 IQService, 6 SaaS (Oracle
  ERP/HCM/EPM, ServiceNow ×2, UKG Kronos). DB-Server section deferred per PM.
- **Seed:** 16 target-system apps into `raw_apps` (one `DISCOVERY` row each,
  instant), 17 `raw_users_snapshot` + `identities_metadata` rows
  (`source_type=DATABASE`, NHI, privileged). Ran `ComputeIdentityTablesWorkflow`
  org-scoped (`backfillFrom=2026-06-01`) → 17 NHI accounts, privileged, each
  under its target app.
- **Consumer wiring — the instructive miss:** first attempt seeded an
  `IdentityIQ` *identity* and pointed `account_consumers.consumer_id` at it with
  `consumer_type='APPLICATION'` → UI showed **"Unknown."** Fix: keep
  `consumer_type='APPLICATION'` and set `consumer_id` to the real **identityiq
  app** id `a85e5ea7-…`; dropped the stray identity. All 17 then resolved to the
  identityiq app.
- **App consolidation (move-account pattern):** later collapsed the 10 per-forest
  AD apps into one "Active Directory": renamed one app, deleted the other 9
  `raw_apps`, re-pointed the 10 AD `raw_users.application_id`, **deleted the 10
  stale accounts**, recompute, then moved the 10 `account_consumers` rows.
  Distinct `login_identifier`s (forest prefix) keep them 10 separate accounts
  under one app.
- **SQL artefacts:** the two runnable scripts are embedded in full below
  (originals: `ascension-iiq-nhi-seed.sql`, `ascension-ad-consolidation.sql` at
  repo root) — concrete instances of the runbook. Swap the org id, app/identity
  UUIDs (regenerate with `uuidgen`), and the seed list for the next customer.

## Worked example 2 (ISS Global / RTVISS, prod EU)

A second instance of the same class — and the one that exercised the *debugging*
half of this doc, because the seed itself was routine but the demo didn't render
for two unrelated reasons.

- **Org:** ISS Global `1c3c5fdf-…`, **prod EU** (`region='EU'` ⇒ profile
  `prod_eu`, Temporal `core-prod-eu`), `is_internal=false` — a real customer, so
  every write was scoped, reviewed, and handed to a write-role colleague.
- **Scope (3 NHIs):** three DB/AD service accounts the RTVISS app authenticates
  with (`FI-SQL.Innof.RTVISS`, `FI-SQL.Inno.FMPISS`, `ISSREGION\ISSFI-sa.FMPISS`).
  Modelled exactly like Ascension: each account homed under the **target system**
  it authenticates to (two new `MSSQL — …` `raw_apps`), **consumed by** the web
  apps that hold its credential (RTVISS, RTVISSWebService, FMPISS — all
  already-discovered apps, reused as consumers, not recreated).
- **A PK nuance worth knowing:** one account can have **multiple consumers** —
  `FI-SQL.Innof.RTVISS` got two `account_consumers` rows (RTVISS +
  RTVISSWebService) without colliding, because the PK is all six business columns
  so distinct `consumer_id`s coexist.
- **Rollback was id-scoped, not org-scoped.** Unlike Ascension (an empty org
  where org-wide deletes were safe), ISS Global already held discovered apps and
  ~907 pulled users, so every cleanup/rollback targeted only the seeded
  `identity_id`s / `application_id`s.
- **Then the demo didn't render — two independent causes, found logs-first:**
  (a) the consumer panel `500`'d on `consumers/search` — root-caused via
  `operationId` → identity-service log to an infra-side permission issue (since
  resolved); (b) for the `NHI`s, the `#4158` consumer render gate had not yet
  deployed to prod-EU. Neither was a data problem; the seed verified clean. This
  is the canonical reason step 8 exists.
- **A red herring worth recognising:** the org also showed ~907 identities with
  **blank names**. Not the seed — an **orphaned** login-only DB pull (`query_id
  ffc40e3c…`, run months earlier, template since removed). See the
  situational-backfill landmine: a `display_name = login_identifier` backfill on
  `users_from_databases` was viable here *only* because that template is dead.
- **SQL artefacts:** `issglobal-rtviss-nhi-seed.sql` and
  `issglobal-rtviss-displayname-backfill.sql` at repo root.

## Worked-example SQL — the seed script

Phases A/B/D are written on a **write path** (a colleague runs them); Phase C is
the compute WF you run. Note the `INSERT … SELECT` for the array columns (a
`VALUES` clause rejects `ARRAY_CONSTRUCT()`), and the consumer wired as
`consumer_type='APPLICATION'` + the identityiq **app** id.

```sql
-- =====================================================================
-- Seed: NHI service accounts into a customer prod org (non-DB scope)
-- Pipeline: seed upstream sources, let compute build the read-path (durable).
-- Org: Ascension c2af65f4-6a73-4c3e-8edd-0b458985d6be (prod US)
-- Consumer node: identityiq APP a85e5ea7-... (consumer_type='APPLICATION'
--   => consumer_id is the consuming app's id, NOT an identity)
-- NEVER hand-write ACCOUNTS_SNAPSHOT_V2 / CONSOLIDATED_IDENTITIES_SNAPSHOT_V2 —
-- compute owns them. Direct writes only: raw_apps, raw_users_snapshot,
-- identities_metadata, account_consumers. UUIDs are RFC-4122 v4 (z.guid()-valid).
-- =====================================================================

-- ---- PHASE A — target-system apps (LATEST_CONSOLIDATED_APPS is a VIEW over
-- ---- RAW_APPS, so a named non-ignored DISCOVERY row shows in the inventory now)
INSERT INTO orchid_security.public.raw_apps
  (organization_id, application_id, application_version, actor, application_name,
   status, ignored, is_removed, created_at, updated_at)
VALUES
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','d9bf1ee5-1430-450e-8682-2065f39cd3ce',1,'DISCOVERY','Active Directory — ABSM.alexian.corp',     'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','386164e1-5935-4f3e-a9e7-9c728c129568',1,'DISCOVERY','Active Directory — aid.ascension.org',     'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','3cccf3c2-6d71-46e2-a1c3-d323b35e7ffa',1,'DISCOVERY','Active Directory — amita.amitahealth.org', 'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','6071fd02-7bad-4ae2-b441-55a9c2b660bd',1,'DISCOVERY','Active Directory — crittenton.net',        'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','67af3bec-5ad6-4c19-a371-78e86a1d274d',1,'DISCOVERY','Active Directory — fr.sjhs (sjmc.org)',    'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','55802308-f6b2-40aa-8ecf-633dc90b7816',1,'DISCOVERY','Active Directory — medxcelfm.com',         'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','e417a487-701e-4b07-aed3-792e68ab8f11',1,'DISCOVERY','Active Directory — mistrhghts.abs-tpa.com','INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','d485ecad-373a-44ca-be04-8d94b7ec85cb',1,'DISCOVERY','Active Directory — presencehealth.net',    'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','9fa0ac91-fab5-483e-876f-b4ab315fdc1a',1,'DISCOVERY','Active Directory — via-christi.org',       'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','6935aa21-bd02-4c9c-8262-ffc8a4e0e6bb',1,'DISCOVERY','Active Directory — wfsi.priv',            'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','311a2656-abc2-4c5b-8f6d-fcbdb10f2d07',1,'DISCOVERY','IQService (AHNATWAPP2101.ds.sjhs.com)',    'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','89beeaea-0bee-4fa8-9361-e9bcdda5dec0',1,'DISCOVERY','Oracle Fusion Cloud ERP',                 'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','4ac192cc-60ea-423a-a53c-7e295acb9193',1,'DISCOVERY','Oracle Fusion Cloud HCM',                 'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','94535026-1f9a-4425-9058-5d8fe2f9387a',1,'DISCOVERY','Oracle EPM Cloud',                        'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','76789ea4-8b76-47d4-b14c-9a1d17f8e0fb',1,'DISCOVERY','ServiceNow',                              'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz),
  ('c2af65f4-6a73-4c3e-8edd-0b458985d6be','fe26a112-b04c-44fa-89a4-4bc47a52ebde',1,'DISCOVERY','UKG Kronos',                              'INITIAL_RESULTS',FALSE,FALSE,CURRENT_TIMESTAMP()::timestamp_ntz,CURRENT_TIMESTAMP()::timestamp_ntz);

-- ---- PHASE B — upstream identity sources (staging table -> raw_users + metadata)
CREATE OR REPLACE TEMPORARY TABLE orchid_security.public.tmp_ascension_nhi_seed (
  identity_id text, login_identifier text, target_app_id text, target_system text, is_privileged boolean
);
INSERT INTO orchid_security.public.tmp_ascension_nhi_seed VALUES
  ('dec6e566-09c9-4d3f-8e99-e08b8034b971','ALEXIAN\\sailpoint-ahscn-dev',        'd9bf1ee5-1430-450e-8682-2065f39cd3ce','Active Directory — ABSM.alexian.corp (LDAPS 636)',                TRUE),
  ('ccb7117a-0151-4922-811b-0c1c92315724','aid\\sailpoint-aid-test',             '386164e1-5935-4f3e-a9e7-9c728c129568','Active Directory — aid.ascension.org (LDAPS 636 + GC 3268)',      TRUE),
  ('a2c7e410-9065-41a7-97af-869b19630153','AMITA\\sailpointdev-AMITA',           '3cccf3c2-6d71-46e2-a1c3-d323b35e7ffa','Active Directory — amita.amitahealth.org (LDAPS 636)',            TRUE),
  ('af72d3ea-f58d-456d-80aa-0b34c8f8d301','CRITTENTON-NET\\spiq-miroc-pwc-dev',  '6071fd02-7bad-4ae2-b441-55a9c2b660bd','Active Directory — crittenton.net (LDAPS 636)',                   TRUE),
  ('0b8b8444-cafd-4f98-a0b3-3a5203d6dfdd','sjmc\\spiq-oktul-pwc-dev',            '67af3bec-5ad6-4c19-a371-78e86a1d274d','Active Directory — fr.sjhs / sjmc.org (LDAPS 636)',               TRUE),
  ('6e48f098-568f-4aab-850e-36eef2aedccf','MEDXCELFM\\spiq-medxc-pwc-dev',       '55802308-f6b2-40aa-8ecf-633dc90b7816','Active Directory — medxcelfm.com (LDAPS 636)',                    TRUE),
  ('57b5930e-2e27-4d79-9e02-db4e0519ec65','ABSALPHA4100\\spiq-acmho-pwc-dev',    'e417a487-701e-4b07-aed3-792e68ab8f11','Active Directory — mistrhghts.abs-tpa.com (PLAINTEXT 389)',       TRUE),
  ('6d64db0f-3ba7-47bf-80ea-3c934619b214','presencehealth\\S_sailpoint-PRESENCE','d485ecad-373a-44ca-be04-8d94b7ec85cb','Active Directory — presencehealth.net (PLAINTEXT 389 + GC 3268)', TRUE),
  ('1cb0cd7c-09be-47c7-9e02-3b2507da080a','VCHS_NT_DOMAIN\\spiq-kswic-pwc-dev',  '9fa0ac91-fab5-483e-876f-b4ab315fdc1a','Active Directory — via-christi.org (LDAPS 636, 3 DCs)',           TRUE),
  ('bc83ace0-7dec-4258-8527-9edd620341d7','WFSI\\spiq-wigle-pwc-dev',            '6935aa21-bd02-4c9c-8262-ffc8a4e0e6bb','Active Directory — wfsi.priv (PLAINTEXT 389)',                    TRUE),
  ('9c8dbfda-612b-4b35-9936-b5a6abacd216','ds\\sailpointtomcat-ds',              '311a2656-abc2-4c5b-8f6d-fcbdb10f2d07','IQService — AHNATWAPP2101.ds.sjhs.com:5050/5052',                 TRUE),
  ('fda6ed05-9efd-4210-a64a-7195bcbf3115','orcsvcerpiam',                        '89beeaea-0bee-4fa8-9361-e9bcdda5dec0','Oracle Fusion Cloud ERP',                                        TRUE),
  ('ebd6629d-0f3f-42da-8654-8bf6fea6c5df','orcsvchcmsailpoint',                  '4ac192cc-60ea-423a-a53c-7e295acb9193','Oracle Fusion Cloud HCM',                                        TRUE),
  ('bef97408-ec81-47ef-b1ab-bee1b2d83262','orcsvcepmsailpointsit1',              '94535026-1f9a-4425-9058-5d8fe2f9387a','Oracle EPM Cloud (EPM / EPCM / EDMCS)',                           TRUE),
  ('d10a39b4-35b2-466c-86df-dc9bda7be864','sailpoint_subprod_svc',               '76789ea4-8b76-47d4-b14c-9a1d17f8e0fb','ServiceNow (ITSM SaaS)',                                         TRUE),
  ('7466a50b-575e-4542-a3d2-433cb797c4ec','sail_IGC',                            '76789ea4-8b76-47d4-b14c-9a1d17f8e0fb','ServiceNow (ITSM SaaS) — CLEARTEXT creds',                       TRUE),
  ('aa596b9c-d2ce-4740-8920-695479845eec','API-SAILPOINT',                       'fe26a112-b04c-44fa-89a4-4bc47a52ebde','UKG Kronos (workforce mgmt SaaS)',                               TRUE);

-- B1) RAW_USERS_SNAPSHOT — INSERT…SELECT (VALUES rejects ARRAY_CONSTRUCT())
INSERT INTO orchid_security.public.raw_users_snapshot
  (organization_id, application_id, identity_id, login_identifier, source_type,
   display_name, identity_type, vendor, is_privileged, is_disabled, is_locked,
   roles, groups, permissions, status, created_at, updated_at)
SELECT
  'c2af65f4-6a73-4c3e-8edd-0b458985d6be',
  target_app_id, identity_id, login_identifier, 'DATABASE',
  login_identifier, 'NHI', 'DATABASE', is_privileged, FALSE, FALSE,
  ARRAY_CONSTRUCT(), ARRAY_CONSTRUCT(), ARRAY_CONSTRUCT(), 'ACTIVE',
  CURRENT_TIMESTAMP()::timestamp_ntz, CURRENT_TIMESTAMP()::timestamp_ntz
FROM orchid_security.public.tmp_ascension_nhi_seed;

-- B2) IDENTITIES_METADATA — durable identity_type = NHI
INSERT INTO orchid_security.public.identities_metadata
  (organization_id, identity_id, identity_type, created_at, updated_at)
SELECT
  'c2af65f4-6a73-4c3e-8edd-0b458985d6be', identity_id, 'NHI',
  CURRENT_TIMESTAMP()::timestamp_ntz, CURRENT_TIMESTAMP()::timestamp_ntz
FROM orchid_security.public.tmp_ascension_nhi_seed;

-- ---- PHASE C — build the read-path (run manually; NOT through sfquery):
--   TS=$(date +%s)
--   bash skills/temporal-namespaces/scripts/temporal-safe.sh --env core-prod-us \
--     workflow start --type ComputeIdentityTablesWorkflow --task-queue identity-task-queue \
--     --workflow-id "compute-identity-tables-c2af65f4-manual-${TS}" \
--     --search-attribute 'organizationId="c2af65f4-6a73-4c3e-8edd-0b458985d6be"' \
--     --input '{"organizationId":"c2af65f4-6a73-4c3e-8edd-0b458985d6be","backfillFrom":"2026-06-01T00:00:00.000Z"}'

-- ---- PHASE D — consumer wiring (write path, AFTER Phase C). consumer_id = the
-- ---- identityiq APP id; account_consumers is never built by compute.
INSERT INTO orchid_security.public.account_consumers
  (organization_id, identity_id, application_id, login_identifier,
   consumer_type, consumer_id, created_at, updated_at)
SELECT
  'c2af65f4-6a73-4c3e-8edd-0b458985d6be',
  identity_id, target_app_id, login_identifier,
  'APPLICATION', 'a85e5ea7-5848-4d08-b6e0-0d31d9eb58a6',
  CURRENT_TIMESTAMP()::timestamp_ntz, CURRENT_TIMESTAMP()::timestamp_ntz
FROM orchid_security.public.tmp_ascension_nhi_seed;

DROP TABLE IF EXISTS orchid_security.public.tmp_ascension_nhi_seed;
```

Rollback (org-scoped is exact only because this org had no other identity/app
data; otherwise scope to your seeded ids):

```sql
DELETE FROM orchid_security.public.account_consumers                    WHERE organization_id='c2af65f4-6a73-4c3e-8edd-0b458985d6be';
DELETE FROM orchid_security.public.accounts_snapshot_v2                 WHERE organization_id='c2af65f4-6a73-4c3e-8edd-0b458985d6be';
DELETE FROM orchid_security.public.consolidated_identities_snapshot_v2  WHERE organization_id='c2af65f4-6a73-4c3e-8edd-0b458985d6be';
DELETE FROM orchid_security.public.raw_users_snapshot                   WHERE organization_id='c2af65f4-6a73-4c3e-8edd-0b458985d6be';
DELETE FROM orchid_security.public.identities_metadata                  WHERE organization_id='c2af65f4-6a73-4c3e-8edd-0b458985d6be';
-- raw_apps: delete only the 16 seeded target-app ids (keep real discovered apps).
```

## Worked-example SQL — the app-consolidation (move-account) pattern

How to collapse many apps into one *after* accounts already exist under them.
The load-bearing trick: re-point the source (`raw_users`), **delete the now-stale
snapshot accounts by hand** (compute won't), recompute, then move the junction.

```sql
-- STEP 1 (write path) — consolidate 10 per-forest AD apps into one "Active Directory"
-- 1a) keep one app (rename), drop the other 9
UPDATE orchid_security.public.raw_apps
SET application_name='Active Directory', updated_at=CURRENT_TIMESTAMP()::timestamp_ntz
WHERE organization_id='c2af65f4-6a73-4c3e-8edd-0b458985d6be'
  AND application_id='d9bf1ee5-1430-450e-8682-2065f39cd3ce';
DELETE FROM orchid_security.public.raw_apps
WHERE organization_id='c2af65f4-6a73-4c3e-8edd-0b458985d6be'
  AND application_id IN ('386164e1-5935-4f3e-a9e7-9c728c129568','3cccf3c2-6d71-46e2-a1c3-d323b35e7ffa',
    '6071fd02-7bad-4ae2-b441-55a9c2b660bd','67af3bec-5ad6-4c19-a371-78e86a1d274d','55802308-f6b2-40aa-8ecf-633dc90b7816',
    'e417a487-701e-4b07-aed3-792e68ab8f11','d485ecad-373a-44ca-be04-8d94b7ec85cb','9fa0ac91-fab5-483e-876f-b4ab315fdc1a',
    '6935aa21-bd02-4c9c-8262-ffc8a4e0e6bb');
-- 1b) re-point the 10 AD raw_users to the surviving app (bump updated_at to clear the watermark)
UPDATE orchid_security.public.raw_users_snapshot
SET application_id='d9bf1ee5-1430-450e-8682-2065f39cd3ce', updated_at=CURRENT_TIMESTAMP()::timestamp_ntz
WHERE organization_id='c2af65f4-6a73-4c3e-8edd-0b458985d6be'
  AND identity_id IN ('dec6e566-09c9-4d3f-8e99-e08b8034b971','ccb7117a-0151-4922-811b-0c1c92315724',
    'a2c7e410-9065-41a7-97af-869b19630153','af72d3ea-f58d-456d-80aa-0b34c8f8d301','0b8b8444-cafd-4f98-a0b3-3a5203d6dfdd',
    '6e48f098-568f-4aab-850e-36eef2aedccf','57b5930e-2e27-4d79-9e02-db4e0519ec65','6d64db0f-3ba7-47bf-80ea-3c934619b214',
    '1cb0cd7c-09be-47c7-9e02-3b2507da080a','bc83ace0-7dec-4258-8527-9edd620341d7');
-- 1c) DELETE the now-stale per-forest accounts (compute has no DELETE; recompute rebuilds under the new app)
DELETE FROM orchid_security.public.accounts_snapshot_v2
WHERE organization_id='c2af65f4-6a73-4c3e-8edd-0b458985d6be'
  AND identity_id IN ('dec6e566-09c9-4d3f-8e99-e08b8034b971','ccb7117a-0151-4922-811b-0c1c92315724',
    'a2c7e410-9065-41a7-97af-869b19630153','af72d3ea-f58d-456d-80aa-0b34c8f8d301','0b8b8444-cafd-4f98-a0b3-3a5203d6dfdd',
    '6e48f098-568f-4aab-850e-36eef2aedccf','57b5930e-2e27-4d79-9e02-db4e0519ec65','6d64db0f-3ba7-47bf-80ea-3c934619b214',
    '1cb0cd7c-09be-47c7-9e02-3b2507da080a','bc83ace0-7dec-4258-8527-9edd620341d7');
-- 1d) move the AD account_consumers links onto the surviving app (consumer stays the identityiq app)
UPDATE orchid_security.public.account_consumers
SET application_id='d9bf1ee5-1430-450e-8682-2065f39cd3ce', updated_at=CURRENT_TIMESTAMP()::timestamp_ntz
WHERE organization_id='c2af65f4-6a73-4c3e-8edd-0b458985d6be'
  AND identity_id IN ('dec6e566-09c9-4d3f-8e99-e08b8034b971','ccb7117a-0151-4922-811b-0c1c92315724',
    'a2c7e410-9065-41a7-97af-869b19630153','af72d3ea-f58d-456d-80aa-0b34c8f8d301','0b8b8444-cafd-4f98-a0b3-3a5203d6dfdd',
    '6e48f098-568f-4aab-850e-36eef2aedccf','57b5930e-2e27-4d79-9e02-db4e0519ec65','6d64db0f-3ba7-47bf-80ea-3c934619b214',
    '1cb0cd7c-09be-47c7-9e02-3b2507da080a','bc83ace0-7dec-4258-8527-9edd620341d7');

-- STEP 2 (you, manual) — re-run ComputeIdentityTablesWorkflow (same command as Phase C above)
-- STEP 3 — verify: exactly 1 AD app; 10 AD accounts under d9bf1ee5; 0 rows under the 9 dropped app ids.
```

## Where to look / who to ask

- **Snowflake (`ORCHID_SECURITY.PUBLIC`):** `RAW_APPS`, `LATEST_CONSOLIDATED_APPS`
  (view), `RAW_USERS_SNAPSHOT`, `IDENTITIES_METADATA`, `ACCOUNTS_SNAPSHOT_V2`,
  `CONSOLIDATED_IDENTITIES_SNAPSHOT_V2`, `ACCOUNT_CONSUMERS`; for DB-pulled users
  `USERS_FROM_DATABASES` (+ `INT_USERS_FROM_DATABASES_VIEW`) — it carries
  `query_id`, the pulling template, and the provenance fields (`correlated_by`,
  `created_at`, `id_in_source_db`); org lookup in `CDC.ORGANIZATIONS`.
- **Compute source (`Orchid-Security/core`):**
  `apps/identity/src/temporal-worker/sql/{compute-raw-users,compute-accounts,compute-consolidated-identities}.sql.ts`
  — `compute-raw-users` is where the DB branch reads `INT_USERS_FROM_DATABASES_VIEW`
  `WHERE updated_at > watermark` and maps `display_name` through.
- **Logs:** `ddlogs "<operationId>"` then
  `ddlogs "env:prod-eu service:identity* status:error"`; the real Snowflake error
  sits at `.data[].attributes.attributes.ctx.error` in raw (`-r`) output.
- **Sibling docs:** `knowledge/v2-snapshot-compute-watermarks.md` (why upstream
  data doesn't reach the Console; watermark/backfill mechanics),
  `knowledge/theorchidgarden-demo-data.md` (field→source derivation, junction
  privilege, snapshot-only vs raw_users-backed).
- **Skills:** `seed-ai-agent-identity` (+ `references/durable-upstream-seeding.md`;
  **but treat `references/account-consumers.md`'s consumer_id claim as stale** —
  see Landmines), `diagnose-query-template-pull-failure` (orphaned / mis-mapped
  DB pulls), `snowflake-query`, `temporal-namespaces`,
  `orchid-application-data-model`.
- **People / ownership — the four levers (you hand off all but the compute):**
  - **Write-path prod SQL** — a colleague with a write-capable Snowflake role;
    `prod_eu`/`prod_us` profiles are `SNOWFLAKE_READONLY`. You prepare + review,
    they execute.
  - **Snowflake grants** — the infra team, via the `snowflake-infrastructure`
    terragrunt (`orchid/<account>/account/permissions/roles_privileges/`) + an
    apply; not self-serve.
  - **Feature flags / webapp deploy** — frontend (Sagi this round): the
    identity-overview FF, the graph-node insights-badges FF, and confirming the
    relevant webapp build is actually promoted to the env.
  - **Temporal compute (`ComputeIdentityTablesWorkflow`)** — the one self-serve
    lever (`workflow start` is not prod-fenced); usually coordinated, but you can
    run it yourself.
  - **Findings, scope & data-cleanup decisions** — sales/PM (Alon / Galit this
    round): they hand the findings doc, decide in/out, and own the
    backfill-vs-delete-vs-leave call on pre-existing data.
