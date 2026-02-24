# CE Tracker — Roadmap

## Multi-Tenancy & Role Hierarchy

### 1. Superadmin Role (Shane)
**Priority: High**
**Status: TODO**

A global superadmin role for Shane that sits above all organizations.

- Superadmin can view all tenants (organizations) and their data
- View/manage all organizations, their admins, and their users
- Access global analytics: total users, total orgs, total CE hours across platform
- Ability to create/deactivate organizations
- Impersonate or view any user's dashboard for support purposes
- Superadmin is hardcoded or seeded — not assignable through the UI

### 2. Organization Admins
**Priority: High**
**Status: TODO**

Each organization (e.g., Brooklyn Fi) gets its own admin tier.

- Org admins can invite users to their organization
- View all users within their org and their CE progress
- Assign/revoke admin role to other users within their org
- See org-level analytics (aggregate CE hours, compliance rates, etc.)
- Cannot see users or data from other organizations
- Multiple admins per org supported

### 3. User Role (Standard)
**Priority: High**
**Status: TODO**

This is the current role — individual users tracking their own CE.

- Users belong to an organization (tenant)
- Can only see their own CE records, designations, and analytics
- Can submit CE records, import/export CSVs, generate PDFs
- No access to other users' data or admin functions
- This is what exists today — needs to be scoped under an org

### Implementation Notes
- Requires a new `Organization` model (name, created_at, plan tier, etc.)
- `User` model gets an `organization_id` foreign key
- Role field on User: `superadmin`, `org_admin`, `user`
- All existing queries need tenant scoping (WHERE org_id = current user's org)
- The current `is_admin` boolean on User gets replaced by the role system

---

## Near-Term: Credential Number Tracking

### 3.5. User Credential Numbers (CFP #, CPA #, etc.)
**Priority: High**
**Status: TODO**

Users enter their credential/license numbers so org admins can manually verify compliance at third-party sites.

- Add credential number fields tied to each designation (e.g., CFP Board ID, CPA license number)
- CPA numbers are state-specific — store the issuing state alongside the number
- Numbers are visible to the user on their profile and to org admins in the admin dashboard
- Org admins get a verification view: user name, designation, credential number, and a link to the relevant third-party lookup site (e.g., CFP Board's "Find a CFP Professional", Tennessee State Board of Accountancy)
- This is the manual-first version of item #4 — admins click through and verify themselves before the automated agent exists

Implementation notes:
- New model or extend `UserDesignation` with `credential_number` (VARCHAR) and `issuing_state` (VARCHAR, nullable — only needed for state-level credentials like CPA)
- Admin view: table of users with credential numbers, sortable/filterable by designation
- Include direct links to known verification portals per designation

---

## AI-Powered Features

### 4. Third-Party Compliance Verification Agent
**Priority: Medium-High**
**Status: TODO**

An agent that checks third-party databases to verify a user's compliance status.

- User inputs their credential number (e.g., CFP Board ID)
- Agent pings the relevant authority's public database to confirm status
- Returns status like "Active", "Compliant", "Lapsed", "Not Found"
- Display compliance badge/status on the user's dashboard
- Org admins can see compliance status for all their users at a glance

Target databases to integrate:
- **CFP Board** — CFP certification status lookup
- **AICPA** — CPA license verification (varies by state)
- **CFA Institute** — CFA charterholder directory
- **IRS** — EA enrollment status
- Others as demand dictates

Considerations:
- Some databases have public APIs, others require scraping or manual lookup
- Rate limiting and caching needed to avoid hammering external services
- Store last-checked date and status so it doesn't re-query every page load
- Periodic background check (e.g., weekly) vs. on-demand check

### 5. AI PDF-to-CSV Converter
**Priority: Medium**
**Status: TODO**

Users drag in a batch of CE certificate PDFs and an AI agent extracts the data into an importable CSV.

- User uploads multiple PDFs at once (drag-and-drop UI)
- AI agent reads each PDF and extracts: course title, provider, date completed, hours, category
- Agent produces a pre-filled table the user can review and edit before importing
- User corrects any errors inline, then clicks "Import" to add all records
- Supports messy real-world PDFs (different formats, layouts, scan quality)

Implementation approach:
- PDF text extraction (PyPDF2 or pdfplumber for text-based PDFs)
- Claude API for interpreting extracted text into structured fields
- For scanned/image PDFs: OCR layer (Tesseract or cloud OCR) before sending to Claude
- Frontend: editable table with inline editing, row-level accept/reject
- Temporary storage for uploaded PDFs during processing (clean up after import)

Monetization:
- Users pay via a **credits system** — each PDF extraction costs X credits
- Payment integration: **Stripe + Link** for purchasing credit packs
- Credits are tied to the user's account, not the organization
- Stripe handles billing, receipts, and payment history

Considerations:
- This is a big lift — scope as a v2 feature after multi-tenancy is solid
- Claude API cost per extraction gets passed through to the user via credits
- Need persistent file storage (S3 or equivalent) since Railway/Render have ephemeral filesystems
- Stripe integration also opens the door to subscription billing for org-level plans later
