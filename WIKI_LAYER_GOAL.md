# Wiki Layer Goal

Status: product goal and architecture direction.

The EBA Workbench should grow a governed wiki layer from the extracted text of each enterprise agreement. The wiki should help the workbench understand each EBA as an individual legal and operational document, and also learn patterns across the full agreement set.

The first focus is `entitlements_conditions_benefits`: clause and context mapping for the conditions, benefits, obligations, and entitlement language that shape an agreement. Pay tables, uplift rules, and standard Band/Level benchmarking remain in their existing governed lanes; the wiki should describe clause meaning and context rather than become a second pay-table engine.

The front-facing wiki should be global-first: a clause map library organised by category, subcategory, source evidence, observed terms, and open questions. Council, agreement, cohort, and document filters are important inputs and evidence lenses, but they should not be the main organising principle of the wiki experience.

The wiki is not just documentation. It is the workbench knowledge layer: a source-linked, reviewable, self-improving memory that supports analysis, drafting, language mapping, report assets, audit extracts, bargaining preparation, and future specialist agents.

The wiki system should mostly just run. It should keep improving the knowledge base as source text, reviewed corrections, governed data, and analyst decisions accumulate. At the same time, it needs a front-facing clause library where a user can browse the emerging taxonomy, inspect evidence, answer direction-setting questions, review proposals, and steer mission priorities.

## Purpose

The wiki should let the operator and future agents answer questions such as:

- What does this EBA say about entitlements, conditions, benefits, obligations, and exclusions?
- Which clauses are materially similar across councils, even if the wording differs?
- Which agreement uses unusual language for a common entitlement?
- What terms, aliases, and local labels map back to a common clause or context concept?
- Which clauses are worth turning into a benchmark entity, support note, chart, or report-ready observation?
- Where is the evidence, and how confident are we?

The wiki should support high-end work products, including:

- language mapping across agreements,
- clause comparison packs,
- entitlement and condition maps,
- glossary and synonym maps,
- clause-context impact notes,
- negotiation and drafting reference notes,
- council-specific audit narratives,
- report-ready observations and briefing material.

## First Principle

The system should learn slowly and visibly.

Raw extracted text is evidence, not knowledge. Generated summaries are suggestions, not truth. Wiki pages become trusted only when they preserve source references, uncertainty, review status, and change history.

The wiki should prefer a modest, well-cited note over a confident but untraceable synthesis.

## Clause Evidence Graph Doctrine

The clause method is the `Clause Evidence Graph`.

The stack is:

1. Source Document.
2. Document Spine.
3. Clause Evidence Graph: clause containers, feature cards, reference edges, evidence spans, and review/governance state.
4. Entitlement Engine: governed-feature queries, entitlement definitions, value/unit/scope normalisation, and benchmark measures.
5. Benchmark, report, and wiki views.

The Clause Evidence Graph owns source-backed structure and evidence. The Entitlement Engine owns benchmark interpretation. The Reporting Layer owns presentation. Governance decides what is safe to promote.

The entitlement engine sits above the Clause Evidence Graph. It does not own source truth. It queries clause containers, feature cards, evidence spans, and reference edges, then converts governed feature cards into normalised benchmark measures. Where governance is absent or incomplete, it emits explicit uncertainty states rather than pretending a benchmark fact exists.

The clause is the unit of source structure. The feature card is the unit of benchmark meaning. Reference edges preserve dependencies on other clauses, schedules, definitions, the NES, awards, or external rules.

All agreement clauses should be represented as lightweight source containers in the Clause Evidence Graph. Deep interpretation should occur only through span-grounded feature cards tied to explicit benchmark definitions and governance states.

There is value in clause-carding the entire agreement, but the depth should be tiered. Every detected clause or subclause should become a lightweight source container with heading path, page range, raw text, probable family tags, cross-references, and review state. Feature cards should be created only for specific benchmarkable spans or rules. This gives the system a full document spine without pretending every clause has already been interpreted.

Container and feature review states should stay scope-aware:

- `source_container_only`: found, located, preserved, and referenceable; not interpreted.
- `candidate_features_found`: one or more span-grounded feature candidates exist.
- `feature_review_required`: a likely feature or dependency needs human or stronger machine review.
- `partially_reviewed`: reviewed for one or more named scopes, but not all possible legal or payroll effects.
- `fully_reviewed_for_scope`: reviewed for a specific declared scope.
- `governed_for_scope`: safe to use for a specific governed benchmark or reporting scope.

The next technical layers should strengthen the spine without weakening the doctrine:

- document conversion that preserves layout blocks, tables, page geometry, and reading order;
- hybrid retrieval that combines alias/BM25-style exact search, semantic embeddings, and reranking;
- schema-constrained LLM proposals that must cite clause IDs and evidence spans;
- table-specific extraction for pay, allowances, schedules, and multi-page tabular provisions;
- cross-reference graph edges for definitions, schedules, NES, awards, and calculation dependencies;
- active-learning evaluation so every accepted correction becomes a reusable rule, alias, test, or review queue item.

The QA pack makes locator outputs reviewable. It does not make them true. Truth enters the system only through explicit review decisions and governance promotion.

Gold review records should keep these dimensions separate:

- `clause_found`: the locator found a plausible source container.
- `feature_found`: the system found a span-grounded feature candidate.
- `entitlement_presence`: reviewed presence, reviewed absence, not reviewed, or unclear.
- `value_status`: quantified, amount not stated, discretionary, conditional, cross-reference required, not applicable, or extraction failed.
- `governed_benchmark_measure`: a reviewed and promoted benchmark output for a declared scope.

Gold seed rows are review targets, not gold answers. Machine hints may assist review but cannot populate review decisions without human confirmation.

The review lifecycle is:

1. `not_reviewed`
2. `reviewed_correct`, `reviewed_corrected`, `reviewed_rejected`, `source_unclear`, `cross_reference_required`, `reviewed_absent`, or `amount_not_stated_confirmed`
3. `eligible_for_governance`
4. `governed_for_scope`

`governed_for_scope` must never be reachable directly from machine output or seeded gold rows. It requires an explicit review decision, reviewer metadata, a review scope, and a source evidence span or corrected evidence span.

Codex may suggest. Human decides. Governance promotes. Codex simulation suggestions must live in a sidecar file, reference gold review IDs, require human confirmation, and never populate review metadata, eligibility, or governance fields.

Human adjudication should happen through generated worksheets, not direct hand-editing of gold seed JSONL. The worksheet joins gold targets, QA evidence, and Codex advisory suggestions while leaving human review columns blank. Completed worksheets should be applied through a validator that writes reviewed gold records only after transition rules pass.

## Operating Model

The wiki should be an open-ended improvement system with two faces:

- a background engine that keeps mapping, comparing, proposing, and improving;
- a front-facing cockpit that lets the operator inspect work, answer questions, accept or reject proposals, and set priorities.

The background engine should have standing mission objectives, not merely wait for button clicks. It should look for useful work such as:

- mapping unmapped EBAs,
- improving weak document maps,
- proposing clause/context tags,
- detecting repeated language patterns,
- finding ambiguous or unusual clauses,
- building language maps,
- identifying candidate support artifacts,
- recording unresolved questions,
- suggesting better controlled-vocabulary entries,
- rechecking older maps when better rules are accepted.

The user interface should make that activity legible through a category and tree structure, with fewer command buttons and more visible knowledge structure. It should show:

- what the system is currently learning,
- which clause families, subcategories, and evidence sets are filling out,
- which proposals need review,
- which questions would improve direction,
- which artifacts are ready to generate,
- which source documents or clauses are blocking higher confidence,
- what changed since the last run.

This should feel more like a governed research partner than a batch job. The system can be self-directed, but its self-direction must remain inspectable and steerable.

## Layered Model

### 1. Document Text Layer

The current workbench already extracts page text from PDFs and caches it. The wiki layer should formalise this into a durable document text surface:

- agreement ID,
- page number,
- extracted text,
- extraction method,
- source PDF hash,
- extraction timestamp,
- OCR status where relevant,
- page image/render reference where useful,
- text quality flags.

This layer remains close to the source. It does not decide meaning.

### 2. Document Map Layer

The first active wiki-building step should be document mapping. Each EBA should get a structured map before deeper synthesis, but the user-facing library should roll those maps up into global clause families rather than present each council as the primary navigation unit:

- heading and clause outline,
- page ranges,
- clause titles,
- probable clause functions,
- clause/context relevance,
- specialist/excluded context signals,
- cross-references to pay, classification, or uplift material where needed for interpretation,
- entitlement and condition signals,
- unusual language,
- missing or ambiguous structure.

The document map is the bridge between unstructured PDF text and durable wiki knowledge. In the product experience, document maps should behave as source evidence under the global clause library.

### 3. Semantic Entitlement Layer

The engine should turn mapped text into quantifiable, supportable entitlement facts under a human-friendly taxonomy.

This is the core distinction: text tags identify candidate evidence, but semantic entitlement records explain what the entitlement is, how it should be compared, whether it is present or absent, what measurable value applies, and how strongly the claim is supported.

Each report-ready entitlement should have:

- a human taxonomy path such as Leave > Additional Annual Leave or Conditions > Call Out Minimum Engagement,
- a canonical entitlement concept and working definition,
- source-linked agreement evidence,
- a presence, absence, limited, baseline, or needs-review state,
- quantified values and units where the entitlement is measurable, such as days, weeks, hours, percentages, or dollar amounts,
- a comparator normalisation basis,
- a target-council comparator posture such as aligned, stronger, weaker, mixed, unclear, or source gap,
- a supportability state that separates report semantics, source evidence, reviewed knowledge, and final governed output.

The system should prefer a small number of well-supported entitlement facts over many loose observations. If a value cannot be quantified, the wiki should say why: qualitative condition, source gap, policy reference, mixed comparator evidence, or operator review required.

#### Clause-Backed Evidence Method

For item-by-item review, each entitlement should move from exemplar text to source-clause evidence through a profiled evidence builder:

- define the entitlement profile in human terms, including inclusion terms, exclusion terms, expected value units, and standard-employee scope,
- search the cached agreement text and document maps for candidate pages,
- separate true general-workforce matches from out-of-scope signals such as shift-worker annual leave, public-holiday substitutes, or illness re-credit clauses,
- extract page, clause heading, excerpt, quantified values, and conditions,
- preserve the old report finding as a comparator note, but let the source evidence populate the displayed finding, presence state, values, and source reference,
- treat no positive match as `source_search_no_positive_match`, not final legal absence.

The first implementation of this method is `Additional Annual Leave`, using clause-backed evidence to identify source clauses while flagging other councils as source-search gaps or out-of-scope annual leave matches.

This method is now treated as a reusable machine profile, not just an output generator. For each run it records the exact hit method: page-level search terms, candidate patterns, positive concept rules, scope-control rules, scoring, accepted source clauses, rejected lookalikes, normalised values, and remaining automation load.

The initial A/B harness keeps the original 10-council comparator seed as cohort A and adds an 8-council stress extension as cohort B. The extension deliberately includes likely true positives, purchased-leave lookalikes, carer-special-needs language, and specialist MCH/nurse provisions so the profile can be tested for precision, recall, and entitlement-subclass separation.

The next learning pass adds a validation batch and converts more outcomes into explicit subclasses. The boundary for inclusion is leave above the NES or ordinary annual leave baseline for standard employees. `Service / End-of-Band Recognition Leave` and `Annual Leave Management Bonus Leave` are accepted subclasses of `Additional Annual Leave`; `Purchased Leave`, `Top-of-Band Payment`, `Specialist Cohort Additional Leave`, `Carer Special Needs Additional Leave`, public-holiday/shift-worker substitutes, and work-area/roster-specific clauses are held as adjacent or excluded subclasses. This makes the profile reusable for ad hoc agreements rather than a one-off comparator page.

The evidence builder can now be run against supplied agreements through `--agreement Council=ae123456`, with `--only-agreements` available for single-purpose processing. That is the intended path toward processing agreements as needed while preserving the same method, subclassing, scoring, and evidence trace.

The profile can also be run across every cached agreement with `--all-cached`. This produces an all-cached evidence artifact while retaining the curated comparator cohort as the training/validation trail. For `Additional Annual Leave`, the all-cached pass is now the preferred way to find missed aliases, reduce `Needs Review` candidates, and decide which adjacent leave concepts deserve their own entitlement pages.

### Interim Comparator Seed Pilot

An interim training goal is to use the councils and entitlement report shape from the supplied Ballarat entitlement benchmark exemplar as a thought starter and comparator-cohort seed.

The pilot objective is not to blindly copy the report. It is to teach the wiki to recreate the report from source EBAs for the same comparator cohort, then measure how close the recreated output is to the seed exemplar. A sensible target is approximately 95% row-semantic agreement for standard employees, with the remaining differences flagged for review rather than forced into false certainty. The supplied report starts the taxonomy and council choice; the latest known source EBA for each council decides final truth.

The pilot should be standard-employees first. Specialist-cohort material, such as nursing, early-years, child-care, aquatic, senior-officer, or other specialist lane provisions, should be excluded from the gold target unless the operator explicitly opens a specialist lane.

#### Exhaustive Normal-Staff Recreation Goal

The next large goal is to turn the single successful `Additional Annual Leave` profile into an entitlement-by-entitlement recreation program for the standard-employee rows in the reference benchmark.

The program should work through every in-scope entitlement from the reference document and add as many source-backed entitlement profiles as the evidence supports. Each profile should follow the same pattern as `Additional Annual Leave`: start with the reference definition and expected numbers, define the standard-employee scope, resolve each council to its latest known canonical agreement, search source EBAs, classify true matches and lookalikes, extract quantified values and conditions, preserve `source_ref`, compare the recreated numbers against the reference, and record the reasoning trail.

For each entitlement, the goal is to produce the same numbers as the reference document when the source evidence and logic support them. If the numbers do not reconcile, the profile should keep reasoning until the available routes are exhausted: missed aliases, hidden cross-references, table language, scoped modifiers, excluded cohorts, source gaps, and comparator interpretation differences. Only then should it move on, with a clear explanation of the best current answer, the evidence used, and why the reference could not be matched.

The loop for every entitlement is:

- ingest the reference row, comparator councils, expected values, and target-council posture,
- define the canonical entitlement concept, accepted subclasses, exclusions, expected units, and `standard_band_core` scope,
- run source search across the comparator cohort and, where useful, across all cached agreements,
- separate normal-staff evidence from specialist, roster-specific, policy-only, purchased, or adjacent entitlement evidence,
- extract source-linked values, clauses, page references, conditions, and confidence state,
- compare recreated values and counts with the reference numbers,
- explain agreement or disagreement in plain terms,
- encode the learned patterns so the next run is stronger,
- stop only when the entitlement is matched, logically contradicted by source evidence, blocked by a source gap, or no further reasonable search route remains.

Completion for this phase means every standard-employee entitlement in the reference exemplar has either a reusable clause-backed profile, a source-backed disagreement note, or an explicit exhausted-route review item. The system should not promote any profile to governed entitlement truth until source references, reasoning, cohort scope, and review state are preserved.

The comparator should score agreement across:

- category and entitlement row presence,
- canonical entitlement concept and working definition,
- source-linked presence or absence state,
- quantified value and unit where measurable,
- target-council comparator posture,
- supportability and review state.

The engine may disagree with the gold exemplar where the source evidence supports a different interpretation, but every disagreement must carry source references, a plain explanation, and a review queue item.

### 4. Tags And Controlled Vocabulary

Tags should be controlled enough to support analysis but flexible enough to learn from messy agreement language.

Initial tag families:

- `context_scope`: agreement coverage, all-employee context, employment type, classification context, service area, schedule context, specialist occupation, external/excluded context, implementation context.
- `clause_function`: allowances, hours, overtime and penalties, leave families, public holidays, consultation, dispute resolution, flexibility, redundancy/redeployment, higher duties, on-call/standby, rostering, training, union rights, family violence, workload, remote work, termination, superannuation, accident make-up pay.
- `clause_context_relevance`: core_clause, context, needs_review, exclusion, none.
- `evidence_type`: clause_text, table, schedule, definition, cross_reference, note, extracted_value, analyst_decision.
- `language_role`: canonical_term, local_alias, synonym, ambiguous_term, obsolete_term, bargaining_phrase.
- `risk_signal`: legal, payroll, implementation, equity, operational, political, drafting, data_quality.
- `review_state`: proposed, needs_review, accepted, rejected, superseded.

The vocabulary should grow through reviewed proposals, not uncontrolled one-off labels.

### 5. Wiki Page Layer

The wiki should create several page types:

- Clause library pages: global category and subcategory nodes for benefits, entitlements, conditions, obligations, scope controls, and related clause families.
- Agreement pages: what this EBA contains, key entitlement/condition/benefit clauses, unusual features, extraction state.
- Clause pages: source wording, page references, function tags, context scope, related clauses, plain-English notes, review state.
- Language map pages: canonical term, aliases, local variants, examples, source references, interpretation notes.
- Pattern pages: cross-agreement observations such as common leave wording or common classification structures.
- Issue pages: conflicts, ambiguities, missing evidence, weak extraction, or questions for analyst/legal review.
- Support artifact pages: briefing notes, comparison packs, drafting notes, report observations, and export-ready source packs.

### 6. Set Learning Layer

The system should learn across EBAs by comparing maps and reviewed wiki pages:

- repeated clause patterns,
- unusual wording,
- local aliases for standard concepts,
- common exclusions or specialist contexts,
- common entitlement structures,
- clause families with high variation,
- clauses that need better extraction prompts or tag rules.

Set-level learning must stay traceable back to the individual agreements that support it.

## Self-Improvement System

The wiki should have an explicit drive to improve, but that drive should be governed.

It should maintain a learning backlog containing:

- new tag proposals,
- possible synonym or alias mappings,
- weak or failed extractions,
- conflicting interpretations,
- high-value language patterns,
- candidate support artifacts,
- documents that need remapping after better rules are created.

It should regularly ask:

- What did we fail to classify?
- What did the analyst correct?
- What terms recur across agreements but are not in the vocabulary?
- Which accepted pages suggest a reusable rule?
- Which support documents would save the operator time next?
- Which low-confidence pages block better analysis?

The system can propose improvements automatically, but it should not silently rewrite accepted knowledge. Improvements should move through states such as:

1. observed,
2. proposed,
3. reviewed,
4. accepted,
5. applied,
6. superseded.

## Question-Asking Loop

The wiki should ask questions when answers would materially improve its direction. Questions should be specific and tied to a decision, not generic chatter.

Useful question types:

- priority questions: which artifact, clause family, council group, or risk area matters most next?
- interpretation questions: should a repeated phrase be treated as a synonym, local alias, or materially different concept?
- scope questions: is this a general clause, specialist context, excluded context, implementation note, or reference-only signal?
- review questions: should this proposed tag, pattern, or language map be accepted?
- escalation questions: does this issue need human legal, IR, HR, payroll, or political judgement before it becomes trusted wiki knowledge?

The system should not block all progress while waiting for answers. It should continue doing lower-risk work and keep unanswered questions in the learning backlog.

## Mission Objectives

Standing mission objectives should guide autonomous work:

1. Improve the map of every EBA in the working set.
2. Keep pay-table and uplift benchmarking separate from the wiki's clause/context knowledge.
3. Build a reusable language map for entitlement, condition, benefit, obligation, and context concepts.
4. Turn repeated clause patterns into explainable cross-agreement knowledge.
5. Surface uncertainty early, especially where legal, HR, payroll, implementation, or political risk is present.
6. Generate support artifacts that save the operator time and improve decision quality.
7. Learn from analyst corrections and use them to propose better tags, prompts, maps, and review checks.
8. Keep every useful claim traceable to source evidence or an explicit operator note.

## Agent Relationship

The future Workbench Expert should use the wiki as its main long-term memory.

The agent should be able to:

- search source text and wiki pages,
- explain which pages and source references support an answer,
- propose new wiki pages from document maps,
- detect gaps and conflicts,
- draft support artifacts from accepted wiki knowledge,
- ask for review when legal, HR, IR, political, or data confidence is uncertain.

The agent should not treat raw extraction as approved knowledge. It should distinguish source text, proposed wiki notes, accepted wiki pages, and governed data sets.

## Minimum Useful Product

The first useful version should not try to become a complete legal knowledge system.

It should:

1. expose a global clause library organised by category and subcategory,
2. build a document map for each EBA from extracted page text,
3. tag clauses for entitlement, condition, benefit, obligation, and context relevance,
4. detect specialist/excluded contexts so they stay visible without taking over the main clause map,
5. create a searchable language map for common clause/context terms,
6. propose wiki pages with source page references,
7. store review state for each map/wiki item,
8. surface gaps, conflicts, and improvement proposals,
9. run as a repeatable background improvement loop,
10. provide a front-facing review and direction-setting interface,
11. generate at least one support artifact type, such as a language mapping pack or clause comparison note.

## Data Shape Direction

Likely directories:

- `wiki/clause-library`: global category and subcategory records.
- `wiki/document-maps`: one structured map per agreement.
- `wiki/pages`: durable wiki pages.
- `wiki/language-maps`: canonical terms, aliases, and examples.
- `wiki/patterns`: cross-agreement observations.
- `wiki/issues`: unresolved questions and weak evidence.
- `wiki/learning-backlog`: proposed improvements and remapping tasks.
- `wiki/questions`: open, answered, and superseded direction-setting questions.
- `wiki/runs`: background run summaries, changes proposed, questions raised, and artifacts generated.
- `wiki/artifacts`: generated support documents and source packs.

Likely file format:

- YAML or JSON for machine-owned structured records.
- Markdown for human-readable wiki pages and support artifacts.
- Source references should use agreement ID, page number, and optional clause/heading label.

## Governance Rules

- Every wiki claim needs a source reference or an explicit "operator note" marker.
- Accepted wiki knowledge should be changed through a revision or supersession event, not overwritten casually.
- Cross-agreement synthesis should list supporting agreements and known exceptions.
- Legal, IR, HR, and political interpretations should carry review flags where they go beyond source description.
- The wiki should support expert judgement, not replace it.

## Near-Term Build Sequence

1. Create the wiki directory contract and manifest.
2. Add a document-map builder from existing extracted page text.
3. Add controlled tag vocabulary for clause/context relevance and clause function.
4. Generate document maps for a small pilot set.
5. Roll document maps into a global clause-library tree.
6. Add review states and learning-backlog records.
7. Add run summaries and a question queue so background work can be inspected.
8. Generate first language-map pages from reviewed document maps.
9. Add a Workbench Expert retrieval surface over source text, document maps, and accepted wiki pages.
10. Add the first front-facing clause library for taxonomy browsing, evidence review, proposals, questions, and artifact generation.
11. Produce the first support artifact: a clause-context language mapping pack.
