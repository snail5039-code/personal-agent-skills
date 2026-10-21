# Channel selection

Start from requested duties, region, experience and contract type. With no role
or experience constraints use **general / any**; don't invent an engineering,
graduate or entry-level profile. Mix tracks for overlapping duties. Presets are
routing hints, not evidence of job availability or personal eligibility.

| Track | Complementary sources / scope | Duty aliases |
| --- | --- | --- |
| general | Seven baseline boards + JobPlanet | user role + location + experience + employment type |
| office | InThisWork, Peoplenjob, JobPlanet; Businesspeople for experienced roles | 경영지원, 총무, 인사, HR, 사무보조, 행정, 비서, 법무 |
| accounting | Semoojob, InThisWork, Businesspeople | 경리, 회계, 기장, 세무, 결산, 재무; tax-office vs corporate duties |
| marketing | i-boss, InThisWork, Mediajob, Peoplenjob | 마케팅, 홍보, 광고, 퍼포먼스, 브랜드, 콘텐츠, CRM |
| sales | Peoplenjob, InThisWork; retail sources only for store sales | 영업, 해외영업, 무역, B2B, 영업지원, 거래처 관리 |
| customer_service | Work24, Incruit, InThisWork | 고객상담, 콜센터, CS, CX, 상담운영; in-house vs outsourced |
| design | Designerjob, Fashioninjob, Gamejob, InThisWork | 시각, 편집, UIUX, 패션, 제품, VMD, 아트; portfolio |
| media | Mediajob, Gamejob, i-boss, InThisWork | PD, 영상편집, 작가, 출판, 콘텐츠, 게임기획, 사업운영 |
| healthcare | Medijob, RNJOB; hospital/association careers | 간호, 간호조무, 병원행정, 원무, 보건; license per role |
| welfare | Bokji.net, social workers' association, childcare bank | 사회복지, 돌봄, 요양, 사례관리, 시설운영; certification per role |
| education | Hunjang, childcare bank; relevant education-office boards | 학원강사, 교사, 보육, 방과후, 교육운영, 교육공무직 |
| retail | Shopma, Fashioninjob, Albamon, Daangn Jobs | 판매, 매장관리, MD, 샵마스터; headquarters vs store |
| hospitality | Foodnjob, Hotelup, Albamon, Daangn Jobs | 조리, 주방, 홀, 제과제빵, 프런트, 객실, 시설; hotel type |
| trades | Construction Worknet, Construction Worker, Work24 | 건축, 토목, 설비, 안전, 기능, 노무, 일용; site/qualification |
| manufacturing | Work24, Albamon, Incruit occupation filters | 생산, 포장, 조립, 검사, 설비, 공장; shifts/dispatch |
| logistics | Work24, InThisWork, Albamon | 물류, 구매, 창고, 배송, 입출고, 지게차; office vs field |
| part_time | Albamon, Alba Heaven, Daangn Jobs, Foodnjob | 아르바이트, 단기, 시간제 + duties/hours/location |
| it | Jumpit, RocketPunch, Superookie, InThisWork; OKKY if accessible | 개발, QA, 검증, 전산, IT Support, 데이터 운영 |
| junior | Superookie, LINKareer, InThisWork, universities | 신입, 인턴, 주니어, 경력무관; not a universal default |
| finance | KOFIA member hiring, Peoplenjob, LinkedIn; bank/insurer careers | 리서치, 운용지원, 금융데이터, 은행, 보험; KOFIA is securities-focused |
| rnd | RND JOB, KIRD/K-club, NST, institute careers | 연구, 연구지원, 시험평가, 실증; degree/experience |
| public | JOB-ALIO, Cleaneye Job+, GoJobs | NCS 사무/복지/교육/기술, 공무직, 인턴; institution type |
| foreign | Peoplenjob, KOTRA board, LinkedIn | Korean/English duties + Korean workplace |
| overseas | WorldJob+, LinkedIn | country + occupation; visa/workplace |
| startup | RocketPunch, THE VC, Startup Alliance, D.CAMP, TIPS | sector → employer → careers; any relevant function |
| bio | BRIC if accessible, KIRD/K-club, lab careers | 연구원, 실험지원; degree/license |

The baseline is Saramin, Wanted, Catch, Jasoseol, JobKorea, Incruit and Work24.
They overlap; honor user-required/excluded sources. --no-baseline removes them.
Occupation filters on general boards cover duties without dedicated boards
(e.g. logistics, production, legal); don't invent specialist databases.
InThisWork skews new/junior, Businesspeople experienced. The helper prioritizes
Peoplenjob/Businesspeople for experienced office requests; adapt further to the
actual role and years of experience. It doesn't inspect eligibility or apply site filters.

## Optional audience supplements

Only add these when the user requests the audience or relevant support program.
Keep ordinary role-based boards alongside them. Never infer age, gender,
disability or career interruption from names, photos or the chosen occupation.

| Audience key | Route | Conditions to verify |
| --- | --- | --- |
| midcareer | Work24 Middle-aged Career Centers | service age/area; counseling vs actual hiring |
| senior | Seniorro | age, project category, local provider, participant criteria |
| career_return_women | Women's New Employment Centers (Saeil) | user-stated context; service audience; training/internship vs hiring |
| disability | KEAD | user-requested disability employment; role/program eligibility |

## Geography, modes and expansion

Regional portals, universities, education offices and industrial parks must match
the requested geography. Busan/Gyeongnam/Gyeonggi seeds are examples; find equivalent
official routes elsewhere. A school repost doesn't prove recommendation eligibility.
The helper selects an occupation-specific regional seed only for matching tracks.
Healthcare/education searches should expand hospital, facility, school and education
office official notices where relevant, not only the listed specialist examples.

- channels: operation, filters, audience and methods; no individual-job claims.
- broad: multiple employers; use relevant directories where useful, then official
  careers. Startup/industrial rosters aren't forced on office/service/general tasks.
- company: employer careers/ATS plus name and duties; no unrelated rosters.

Start with complementary sources (usually two per track); --per-track changes this
helper heuristic. Expand remaining related routes/duty aliases for sparse results,
without relaxing hard conditions. Record selection/nonselection reasons; agent
omissions aren't excluded_by_user. Recheck historical observations.

ATS and PDF searches supplement all occupations. For small/local employers the
employer's authenticated platform posting may be its only official notice; check
ownership and application route and disclose the lack of a separate JD. Public
social posts are leads, not employer verification. Don't mandate any curator.

## Query templates (not executed searches)

```text
site:career.greetinghr.com (총무 OR 인사 OR "영업지원") 채용
site:jobs.lever.co (Korea OR Seoul) (marketing OR sales OR operations)
site:jobs.ashbyhq.com (Korea OR Seoul) (design OR content OR support)
site:ac.kr (채용 OR 추천채용) (행정 OR 사무 OR 회계)
site:go.kr filetype:pdf 채용 (교육공무직 OR 돌봄 OR 시설)
("매장관리" OR "판매직") (시간제 OR 정규직) 지역명
("창고" OR "입출고" OR "생산") 채용 지역명
```

Some searches don't support OR/quotes; search aliases separately. Read underlying
sources. Custom domains/unindexed careers need inspection through official homepages.
