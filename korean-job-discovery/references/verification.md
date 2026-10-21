# Verification and record contract

Catalog observations are dated route/function checks, not verified vacancies.

## Route record fields
Use the plan helper's JSON skeleton; preserve route ID and selection reason.
Populate fields after actual attempts:
- status: checked / no_relevant_results / access_limited / excluded_by_user / unverified.
- checked_at: actual ISO 8601 timestamp with timezone.
- scope_or_query: exact query or inspected scope.
- evidence_url: observed public page/search URL or attempted URL.
- evidence_level: body / search_index / attempt_only.
- evidence_note: concise observation; clearly identify search-only evidence.
- discovered_count: actual nonnegative count or null when not counted.
- user_exclusion_reason: required for excluded_by_user.

checked is route verification, not official job verification.
no_relevant_results means none in that query scope, not absence across the site.
access_limited records the failure, not a fabricated empty result.
Nonselected sources may remain unverified; the auditor gates selected records.

## Job record fields
For recommend/conditional jobs include employer, role, location, employment_type,
recommendation, official_url, official_source_kind, verified_at, current_status,
duties, eligibility, deadline, process, application_route, discovery_route_ids,
unknown_fields and evidence_note.

- recommendation: recommend / conditional / hold / exclude.
- official_source_kind: employer_jd / official_ats / issuer_platform.
  For issuer_platform identify employer posting ownership and disclose that no
  separate official JD was found. Social/university reposts do not qualify.
- current_status: active / inactive / unknown. recommend needs active.
- eligibility: verified_eligible / conditional / unknown / ineligible.
  verified_eligible for a person needs supplied evidence. Missing facts stay unknown.
- deadline: published datetime+timezone, date-only, until filled, not published,
  or unknown. Do not invent a time for a date-only deadline.
- process: missing coding-test text does not mean exemption. Use present /
  explicit_no_test / official_process_no_test_listed / not_mentioned / unknown.
- pay when researched: separate starting pay, contract pay and company averages.
  Do not estimate unpublished compensation.

Check work-specific conditions: licenses for regulated healthcare/childcare/
teaching roles; portfolio/audition and project vs employment terms for creative
work; hours, shifts, workplace, accommodation and pay basis for service/field
work; direct employment, dispatch, commission or freelance arrangements. Record
officially stated facts and preserve unknowns. Targeted program participation
is separate from ordinary job eligibility.

For a combined multi-role notice retain its URL plus PDF/page/role locator, not an
invented per-role URL. Deduplicate without losing discovery provenance.

## Response and limits
Lead with conclusions and scope, then jobs/routes, conditions and coverage.
Show actual sources/queries/status/evidence and remaining unknowns/access limits.
Never imply all platforms checked while selected routes are unattempted.
A passing helper audit validates records, not live page truth, completeness of
Internet coverage, or submission. Employer JD/ATS remains the final check.
