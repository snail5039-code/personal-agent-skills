# Agent-neutral handoff

SKILL.md and relative references are the portable instructions. openai.yaml is
optional UI metadata another harness may ignore. No private ledger, MCP, model,
login, API key or author-machine path is needed.

Minimum request:
```json
{"task":"job_research","tracks":["office","marketing"],"region":"서울","level":"any","audiences":[],"employment_types":["regular","contract"],"candidate_evidence":null,"source_constraints":[],"language":"ko"}
```

Use conversation constraints first. Generic research does not require candidate
personal information. Without evidence, keep fit conditional.
Unspecified role/seniority maps to general/any. Choose multiple tracks for mixed
duties; targeted audience routes require a user-specified audience. Preserve
existing consumer fields when reading v1 records without the optional audiences
field. Planner metadata does not apply filters on live websites.

Handoff: run JSON with schema_version, request, routes and jobs. plan creates the
skeleton; verification.md defines fields. Preserve exact URLs and timezone-bearing
timestamps. Resume by comparing request scope and dates. Never include credentials,
cookies, tokens, private messages or internal documents.

| Environment | Adaptation |
| --- | --- |
| Search only | Site-specific queries → snippets → official source; mark search-only |
| Browser | Read live public UI/DOM, record login limits |
| Connector/MCP | Use declared search/read tools and preserve public provenance |
| Python/shell | Optional offline plan/audit; still requires tools for actual search |
| No web | Return plan/dated catalog; no live hiring recommendations |

If delegation is separately authorized, split specialist, regional/university,
company/ATS work, preserve input constraints, then integrate and deduplicate.
The skill does not itself authorize spawning agents or external contact.
