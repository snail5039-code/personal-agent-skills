---
name: korean-job-discovery
description: 한국의 전 직군·경력 수준 채용을 범용·직무별·지역·대상별 플랫폼과 공식 원문에서 조사한다. 사무·영업·디자인·의료·복지·교육·서비스·현장직 등을 포함한 채용 탐색·추천·비교 및 검색 경로 다양화 요청에 사용한다.
license: MIT
---

# Korean Job Discovery

Research Korean hiring using the user's role, region, seniority, employment type,
and scope. Support **channel research** and **job research**. Reply in the user's
language. Use available search/browser/connector tools; no particular MCP, model,
OS, private career ledger, or Python installation is needed for these instructions.

## References to load

- Read [channel selection](references/channel-selection.md) before choosing routes.
- Read relevant rows of [the catalog](references/channel-catalog.md).
  [channels.json](references/channels.json) provides stable IDs and URLs for tools.
- For actual jobs, read [verification](references/verification.md).
- For structured output, resumption, or authorized delegation, read
  [agent handoff](references/agent-handoff.md).
- [Examples](references/examples.md) illustrate scope decisions.

## Workflow

1. Resolve consequential constraints from the request and available context.
   Ask only for missing information that changes scope or eligibility.
   User/local instructions override default routing.
   If no role or seniority is given, start with general boards and unrestricted
   experience levels; do not assume engineering, a degree, or entry level.
   Audience-specific programs are optional supplements only when requested;
   never infer age, gender, disability, or career interruption.
2. Choose complementary general, specialist/association, regional/university,
   and employer channels. Do not force every catalog source into every request.
3. Where useful for broad employer discovery, add a relevant directory, investor portfolio,
   exhibition, or industrial-park roster → company → official careers path.
   Use duty aliases and official ATS domains/PDFs to fill gaps. For one-company
   requests, focus on that employer rather than unrelated company rosters.
4. Search selected routes **live**. Record exact query/scope, observation time
   with timezone, evidence URL, access level and result. Try public search or
   available browser UI when a fetch fails; preserve remaining access limits.
   Catalog observations dated 2026-10-06 are historical seeds, not current checks.
5. Deduplicate by official ID or employer + role + location + hiring round,
   preserving discovery routes. In channel mode, stop at route functionality
   and methods rather than inventing job recommendations.
6. In job mode, verify current status, duties, eligibility, workplace, employment
   type, deadline, process and application route on official employer JD/ATS.
   Preserve unknowns; personalize fit only with supplied candidate evidence.
7. Return conclusions, source coverage, conditions and remaining limits.
   Do not claim full coverage while selected routes remain unattempted.

## Optional offline helper

Python 3.10+ is optional. It plans routes and checks records; it does **not**
search websites or establish live verification. Run relative to this directory,
or use the absolute script path from elsewhere.

```sh
python scripts/discovery.py plan --out plan.json
python scripts/discovery.py plan --tracks office,marketing --region 서울 --level experienced --out plan.json
python scripts/discovery.py audit run.json
python scripts/discovery.py catalog-check
```

A generated plan is not a completed search. An audit pass verifies record
consistency only, not truth, browser rendering, or live hiring availability.

## Boundaries

Company directories/investments, school reposts, social posts and past events
are discovery signals, not current hiring or employer safety evidence.
Distinguish school recommendations, degree requirements, military-service
posts, internships, contracts, and direct vs agency employment.
Check licenses for regulated roles, and shifts, hours, pay basis, employment vs
freelance/commission arrangements for service, creative and field work.

Invoking this research skill does not authorize submission, external contact,
publication, subscriptions, scheduled monitoring, credential collection, or
account changes. It does not itself authorize spawning agents.
