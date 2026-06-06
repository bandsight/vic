export const GOVERNANCE_STATUS_CHIPS = [
  {
    "id": "machine",
    "label": "Machine",
    "description": "Produced by automated extraction or analysis."
  },
  {
    "id": "candidate",
    "label": "Candidate",
    "description": "Useful evidence or data that has not been accepted."
  },
  {
    "id": "needs_review",
    "label": "Needs review",
    "description": "Requires human review before it can move downstream."
  },
  {
    "id": "reviewed",
    "label": "Reviewed",
    "description": "Reviewed for a stated scope."
  },
  {
    "id": "accepted",
    "label": "Accepted",
    "description": "Accepted into the agreement workspace layer."
  },
  {
    "id": "blocked",
    "label": "Blocked",
    "description": "Cannot advance until source, scope, or evidence is resolved."
  },
  {
    "id": "promoted",
    "label": "Promoted",
    "description": "Promoted from reviewed evidence into a governed data lane."
  },
  {
    "id": "governed",
    "label": "Governed",
    "description": "Safe to consume for the stated scope."
  },
  {
    "id": "unwound",
    "label": "Unwound",
    "description": "Previously promoted output has been reversed."
  },
  {
    "id": "advisory",
    "label": "Advisory",
    "description": "May guide review but cannot become source truth."
  }
];

export const WORKBENCH_CAPABILITY_TREE = [
  {
    "id": "source_custody",
    "label": "Source & Custody",
    "icon": "globe",
    "route": "#capability/source_custody",
    "description": "Source documents, agreement register, lineage, and canonical council/agreement identity.",
    "ownershipNote": "Owns the source documents, custody chain, and canonical identity facts that every downstream pipeline depends on.",
    "safeUse": "May feed extraction only after source scope and agreement identity are clear.",
    "status": "candidate",
    "countSummary": "source queue + register",
    "children": [
      {
        "id": "incoming_sources",
        "label": "Incoming",
        "route": "#incoming",
        "navId": "nav-incoming",
        "description": "New registry candidates grouped by confidence before intake processing.",
        "status": "machine",
        "countSummary": "registry candidates",
        "ownershipNote": "First view over discovered source candidates."
      },
      {
        "id": "source_documents",
        "label": "Source Documents",
        "route": "#intake",
        "navId": "nav-intake",
        "description": "Accepted source processing, PDF fetch state, and source retry work.",
        "status": "candidate",
        "countSummary": "fetch and freeze lane",
        "ownershipNote": "Tracks whether source files are usable for review."
      },
      {
        "id": "document_spine",
        "label": "Wiki Base",
        "route": "#capability/source_custody/document_spine",
        "description": "Reusable agreement page, heading, section, and source-anchor map for future wiki and evidence surfaces.",
        "status": "machine",
        "countSummary": "source map base",
        "ownershipNote": "Preserves whole-document structure before any entitlement interpretation starts."
      },
      {
        "id": "job_intake_sources",
        "label": "Job Intake",
        "route": "#job-intake",
        "navId": "nav-job-intake",
        "description": "Victorian council job-source registry, endpoint readiness, polling tier, platform family, and restricted board posture.",
        "status": "candidate",
        "countSummary": "79 council job sources",
        "ownershipNote": "Tracks official council and ATS job URLs before a production crawler is activated."
      },
      {
        "id": "job_pipeline",
        "label": "Job Pipeline",
        "route": "#job-pipeline",
        "navId": "nav-job-pipeline",
        "description": "Band-governed council job records advancing from saved intake snapshots into Stage 1 field completion.",
        "status": "candidate",
        "countSummary": "Stage 1 field completion",
        "ownershipNote": "Moves governed job rows into a fill-and-validate lane before downstream analysis."
      },
      {
        "id": "agreement_register",
        "label": "Agreement Register",
        "route": "#matrix",
        "description": "Working register of agreements in the governed review set.",
        "status": "accepted",
        "countSummary": "review set",
        "ownershipNote": "Keeps the agreement pipeline visible before specialised extraction starts."
      },
      {
        "id": "council_audit_lineage",
        "label": "Council Audit Lineage",
        "route": "#audit",
        "description": "Agreement lineage, source process, and governed changes by council.",
        "status": "reviewed",
        "countSummary": "lineage report",
        "ownershipNote": "Shows the custody story for a council without creating a second data source."
      }
    ]
  },
  {
    "id": "pay_uplift",
    "label": "Quantum & Timing",
    "icon": "funnel",
    "route": "#capability/pay_uplift",
    "description": "Pay table extraction, uplift-rule review, scenario/date alignment, and governed agreement-level pay promotion.",
    "ownershipNote": "Owns benchmarkable pay facts and the period logic that turns source tables into comparable pay movement data.",
    "safeUse": "Feeds reports only through governed pay tables, governed uplift periods, and tested scenario/date alignment.",
    "status": "needs_review",
    "countSummary": "pay evidence production",
    "children": [
      {
        "id": "agreement_workspace",
        "label": "Agreement Workspace",
        "route": "#workspace/overview",
        "description": "Validate PDF evidence, extraction drafts, section acceptance, and governed outputs for one agreement.",
        "status": "needs_review",
        "countSummary": "active agreement",
        "ownershipNote": "The operator surface for agreement-level pay and evidence work.",
        "slot": "workspace_sections"
      }
    ]
  },
  {
    "id": "clause_intelligence",
    "label": "Entitlement QA",
    "icon": "funnel",
    "route": "#capability/clause_intelligence",
    "description": "Reviewer-facing exception inbox for entitlement evidence, value judgement, blockers, and governed promotion readiness.",
    "ownershipNote": "Owns the calm human judgement surface over source-backed entitlement evidence. Machine stages stay backstage unless a reviewer needs evidence or diagnostics.",
    "safeUse": "Feeds reports only through governed entitlement measures promoted from reviewed feature cards.",
    "status": "needs_review",
    "countSummary": "human judgement queue",
    "hideOverviewLink": true,
    "artifactPaths": [
      "wiki/artifacts/entitlement-locator-qa-review/locator-qa-review-entitlement-locator-experiment-next-52-offset-0.json",
      "data/review/entitlement_locator_gold_v1.jsonl",
      "data/review/entitlement_locator_codex_suggestions_v1.jsonl",
      "wiki/artifacts/entitlement-locator-human-review/locator-human-review-worksheet-v1.csv"
    ],
    "pipelineLabel": "Background Clause Checks",
    "pipelineStages": [
      {
        "id": "source_evidence",
        "nodeId": "clause_cards",
        "label": "Source Evidence",
        "route": "#capability/clause_intelligence/clause_cards",
        "description": "Find source-backed clause windows before asking a reviewer to decide anything.",
        "status": "candidate",
        "countSummary": "clause windows"
      },
      {
        "id": "feature_facts",
        "nodeId": "feature_cards",
        "label": "Feature Facts",
        "route": "#capability/clause_intelligence/feature_cards",
        "description": "Extract benchmarkable values and scope signals from located evidence.",
        "status": "candidate",
        "countSummary": "span facts"
      },
      {
        "id": "entitlement_cards",
        "nodeId": "entitlement_cards",
        "label": "Entitlement Cards",
        "route": "#capability/clause_intelligence/entitlement_cards",
        "description": "Emit proposed report-safe facts only when review gates are clear.",
        "status": "reviewed",
        "countSummary": "proposed facts"
      },
      {
        "id": "review_worksheet",
        "nodeId": "human_review_worksheet",
        "label": "Review Worksheet",
        "route": "#capability/clause_intelligence/human_review_worksheet",
        "description": "Keep the raw review worksheet available without making it the normal workflow.",
        "status": "needs_review",
        "countSummary": "review worksheet",
        "artifactPaths": [
          "wiki/artifacts/entitlement-locator-human-review/locator-human-review-worksheet-v1.csv"
        ]
      }
    ],
    "children": [
      {
        "id": "entitlement_qa_inbox",
        "label": "QA Inbox",
        "route": "#capability/clause_intelligence",
        "description": "One calm front door showing only review exceptions, reasons, evidence, and the next action.",
        "status": "needs_review",
        "countSummary": "exceptions only",
        "ownershipNote": "The normal operator surface. Reviewers should not need to know which machine stage produced the item."
      }
    ],
    "secondarySurfaces": [
      {
        "id": "clause_cards",
        "label": "Raw Clause Cards",
        "route": "#capability/clause_intelligence/clause_cards",
        "surfaceGroup": "Advanced",
        "description": "Clause-card evidence windows used by the inbox and diagnostics.",
        "status": "machine",
        "countSummary": "source containers",
        "ownershipNote": "One card can contain many extractable facts."
      },
      {
        "id": "feature_cards",
        "label": "Feature Cards",
        "route": "#capability/clause_intelligence/feature_cards",
        "surfaceGroup": "Advanced",
        "description": "Entitlement x council fact cells and the existing evidence workspace.",
        "status": "candidate",
        "countSummary": "span facts",
        "ownershipNote": "The unit of meaning for benchmarkable entitlements."
      },
      {
        "id": "entitlement_cards",
        "label": "Entitlement Cards",
        "route": "#capability/clause_intelligence/entitlement_cards",
        "surfaceGroup": "Advanced",
        "description": "Proposed governed entitlement cards emitted only when no review gate remains.",
        "status": "reviewed",
        "countSummary": "proposed facts",
        "ownershipNote": "The proposed reportable council-entitlement fact."
      },
      {
        "id": "human_review_worksheet",
        "label": "Human Review Worksheet",
        "route": "#capability/clause_intelligence/human_review_worksheet",
        "surfaceGroup": "Advanced",
        "description": "Raw worksheet fields for human decisions, retained for audit and diagnostics.",
        "status": "needs_review",
        "countSummary": "review rows",
        "ownershipNote": "The surface where semantic judgement is recorded until writeback is productionised.",
        "artifactPaths": [
          "wiki/artifacts/entitlement-locator-human-review/locator-human-review-worksheet-v1.csv",
          "wiki/artifacts/entitlement-locator-human-review/locator-human-review-worksheet-v1.md"
        ]
      },
      {
        "id": "entitlement_library_wiki",
        "label": "Entitlement Library / Wiki",
        "route": "#wiki",
        "navId": "nav-wiki",
        "surfaceGroup": "Diagnostic",
        "description": "Inspect agreement maps, language signals, source-backed evidence, and learning backlog.",
        "status": "candidate",
        "countSummary": "library cockpit",
        "ownershipNote": "A view over evidence, not a rival source of truth."
      },
      {
        "id": "clause_evidence_graph",
        "label": "Clause Evidence Graph",
        "route": "#capability/clause_intelligence/clause_evidence_graph",
        "surfaceGroup": "Diagnostic",
        "description": "Clause containers, feature cards, reference edges, evidence spans, and review state.",
        "status": "candidate",
        "countSummary": "evidence graph",
        "ownershipNote": "Owns source-backed structure and evidence."
      },
      {
        "id": "reference_edges",
        "label": "Reference Edges",
        "route": "#capability/clause_intelligence/reference_edges",
        "surfaceGroup": "Diagnostic",
        "description": "Structured links to definitions, schedules, NES, awards, and other clauses.",
        "status": "needs_review",
        "countSummary": "dependencies",
        "ownershipNote": "Keeps cross-references out of free-text notes."
      },
      {
        "id": "entitlement_locator",
        "label": "Entitlement Locator",
        "route": "#capability/clause_intelligence/entitlement_locator",
        "surfaceGroup": "Diagnostic",
        "description": "Profile discovery over source-backed clause evidence.",
        "status": "machine",
        "countSummary": "8 profiles",
        "ownershipNote": "Finds candidates but does not make them true."
      },
      {
        "id": "qa_review_pack",
        "label": "QA Review Pack",
        "route": "#capability/clause_intelligence/qa_review_pack",
        "surfaceGroup": "Report",
        "description": "Makes machine locator outputs inspectable without making them true.",
        "status": "needs_review",
        "countSummary": "52-council artifact",
        "ownershipNote": "The review scaffold for locator evidence.",
        "artifactPaths": [
          "wiki/artifacts/entitlement-locator-qa-review/locator-qa-review-entitlement-locator-experiment-next-52-offset-0.json"
        ]
      },
      {
        "id": "gold_seed_rows",
        "label": "Gold Seed Rows",
        "route": "#capability/clause_intelligence/gold_seed_rows",
        "surfaceGroup": "Diagnostic",
        "description": "Review targets with blank human fields and locked governance defaults.",
        "status": "needs_review",
        "countSummary": "40 rows",
        "ownershipNote": "Gold seed rows are review targets, not gold answers.",
        "artifactPaths": [
          "data/review/entitlement_locator_gold_v1.jsonl"
        ]
      },
      {
        "id": "codex_suggestions",
        "label": "Codex Suggestions",
        "route": "#capability/clause_intelligence/codex_suggestions",
        "surfaceGroup": "Diagnostic",
        "description": "Advisory triage sidecar that references gold rows but cannot mutate review fields.",
        "status": "advisory",
        "countSummary": "40 suggestions",
        "ownershipNote": "Codex may suggest. Human decides. Governance promotes.",
        "artifactPaths": [
          "data/review/entitlement_locator_codex_suggestions_v1.jsonl"
        ]
      },
      {
        "id": "governed_entitlement_measures",
        "label": "Governed Entitlement Measures",
        "route": "#capability/clause_intelligence/governed_entitlement_measures",
        "surfaceGroup": "Report",
        "description": "Report-safe entitlement measures after review and promotion for a stated scope.",
        "status": "governed",
        "countSummary": "promotion target",
        "ownershipNote": "The only clause-derived facts reports should consume."
      }
    ]
  },
  {
    "id": "data_marts",
    "label": "Data Marts",
    "icon": "database",
    "route": "#capability/data_marts",
    "description": "Governed canonical datasets, analytical marts, and the app pages that expose reusable data products.",
    "ownershipNote": "Owns reusable data products after review/governance: canonical source-shaped tables, analytical marts, report-input marts, and issue marts. It does not own operator decisions or report narrative.",
    "safeUse": "Treat governed canonical rows as lineage-preserving source truth, analytical marts as derived products with status/caveats, and partial/staged marts as visible but not report-ready.",
    "status": "governed",
    "countSummary": "canonical + mart inventory",
    "children": [
      {
        "id": "datamart_inventory",
        "label": "Layer Inventory",
        "route": "#capability/data_marts/datamart_inventory",
        "description": "Materialized catalog of governed canonical datasets and analytical datamarts, with status, row counts, contracts, and caveats.",
        "status": "reviewed",
        "countSummary": "13 canonical + 19 marts",
        "ownershipNote": "The audit surface for what data products exist, including partial, staged, and blocked products."
      },
      {
        "id": "council_master_data",
        "label": "Council Master",
        "route": "#data/councils",
        "navId": "nav-analysis-councils",
        "dataAnalysisKind": "councils",
        "description": "Authoritative council names, cohorts, geography, electoral structure, and canonical agreement joins.",
        "status": "governed",
        "countSummary": "reference dimension",
        "ownershipNote": "Normalises who the agreement belongs to before any benchmark comparison."
      },
      {
        "id": "governed_pay_rows",
        "label": "Governed Pay Rows",
        "route": "#data/pay_tables",
        "navId": "nav-analysis-pay-tables",
        "dataAnalysisKind": "pay_tables",
        "description": "Flattened governed weekly pay rows standardised across agreements.",
        "status": "governed",
        "countSummary": "pay fact table",
        "ownershipNote": "The comparable pay fact table, promoted from reviewed agreement evidence."
      },
      {
        "id": "governed_uplift_rules",
        "label": "Governed Uplift Rules",
        "route": "#data/uplift_rules",
        "navId": "nav-analysis",
        "dataAnalysisKind": "uplift_rules",
        "description": "First-class governed uplift records standardised across agreements.",
        "status": "governed",
        "countSummary": "uplift entity set",
        "ownershipNote": "The cross-agreement uplift rule data product."
      },
      {
        "id": "governed_end_of_band_dollars",
        "label": "End of Band Dollars",
        "route": "#data/end_of_band_dollars",
        "navId": "nav-analysis-end-of-band-dollars",
        "dataAnalysisKind": "end_of_band_dollars",
        "description": "Band-level cash end-of-band amounts with clause evidence and calculation status.",
        "status": "governed",
        "countSummary": "EOB band-period fact table",
        "ownershipNote": "Projects current cash end-of-band clauses onto governed operative periods and bands."
      },
      {
        "id": "benchmark_chart_data",
        "label": "Benchmark Chart Data",
        "route": "#data/charts",
        "navId": "nav-analysis-charts",
        "dataAnalysisKind": "charts",
        "description": "Distribution and movement views backed by governed datamarts and report-asset contracts.",
        "status": "governed",
        "countSummary": "visual-serving mart",
        "ownershipNote": "Transforms governed pay rows into cohort comparison views without changing source facts."
      },
      {
        "id": "report_quality_marts",
        "label": "Report Inputs & Quality Issues",
        "route": "#capability/data_marts/datamart_inventory",
        "description": "Report-product input, readiness, benchmark-question, and data-quality issue marts that should stay visible even when partial.",
        "status": "needs_review",
        "countSummary": "partial work queues",
        "ownershipNote": "Keeps blockers and draft report inputs visible instead of hiding them inside build outputs."
      }
    ]
  },
  {
    "id": "reports_benchmarking",
    "label": "Reports & Benchmarking",
    "icon": "chart",
    "route": "#capability/reports_benchmarking",
    "description": "Benchmark-facing chart explorers, report packs, report exports, and downstream product prototypes built from governed data products.",
    "ownershipNote": "Owns presentation and comparison views over governed pay and governed entitlement outputs. It may consume marts, but it should not redefine the facts they contain.",
    "safeUse": "Consumes governed facts and clearly labels draft, mixed-governance, prototype, or exploratory outputs.",
    "status": "candidate",
    "countSummary": "report surfaces",
    "children": [
      {
        "id": "council_report_packs",
        "label": "Council Report Packs",
        "route": "#audit",
        "description": "Council-level lineage and report pack surface.",
        "status": "reviewed",
        "countSummary": "audit report",
        "ownershipNote": "Turns governed history into a council-facing document view."
      },
      {
        "id": "benchmark_charts",
        "label": "Benchmark Charts & Cohorts",
        "route": "#data/charts",
        "description": "Selectable cohort, distribution, and report-asset views over governed benchmark data.",
        "status": "governed",
        "countSummary": "chart workbench",
        "ownershipNote": "Compares councils without rewriting source facts, and exposes report export lifecycle controls."
      },
      {
        "id": "pay_horizon_explorer",
        "label": "Pay Horizon Explorer",
        "route": "/apps/pay-horizon-explorer/",
        "description": "Standalone governed midpoint distribution explorer backed by the service-horizon curve mart.",
        "status": "candidate",
        "countSummary": "mounted app",
        "ownershipNote": "A chart prototype over datamart outputs; useful for benchmark design before promotion into the core workbench."
      },
      {
        "id": "small_council_state_report",
        "label": "Small Council State Report",
        "route": "/apps/small-council-state-scroll-report/",
        "description": "Executive-facing scrollytelling prototype assembled from local datamarts and explicitly labelled mixed-governance where needed.",
        "status": "candidate",
        "countSummary": "report prototype",
        "ownershipNote": "A downstream report product prototype, not a governed data source."
      },
      {
        "id": "pay_entitlement_combined_views",
        "label": "Pay + Entitlement Combined Views",
        "description": "Future combined benchmarks over governed pay and governed entitlement measures.",
        "status": "needs_review",
        "countSummary": "not yet governed",
        "ownershipNote": "Not materialised yet; it should wait for governed entitlement measures instead of pretending staged taxonomy is enough."
      }
    ]
  },
  {
    "id": "governance",
    "label": "Governance",
    "icon": "shield",
    "route": "#capability/governance",
    "description": "Review decisions, promotion/unwind controls, audit trail, quality queues, and shared reference controls.",
    "ownershipNote": "Owns decisions about what is safe to promote. Governance is also shown as status chips across every branch.",
    "safeUse": "Controls promotion to governed outputs; does not replace source evidence.",
    "status": "needs_review",
    "countSummary": "decision layer",
    "children": [
      {
        "id": "review_board",
        "label": "Review Board",
        "route": "#matrix",
        "navId": "nav-matrix",
        "description": "Agreement pipeline, reviewer QA, section progress, and gated work.",
        "status": "needs_review",
        "countSummary": "review queue",
        "ownershipNote": "The workbench-wide review control surface."
      },
      {
        "id": "review_decisions",
        "label": "Section Review Decisions",
        "route": "#matrix",
        "description": "Accepted, corrected, rejected, source unclear, and cross-reference-required decisions.",
        "status": "reviewed",
        "countSummary": "decision events",
        "ownershipNote": "Human judgement enters here."
      },
      {
        "id": "promotion_queues",
        "label": "Pay Promotion & Unwind",
        "route": "#workspace/uplifts",
        "description": "Move validated pay evidence into governed outputs, unwind unsafe promotion, and keep controlled transition records.",
        "status": "promoted",
        "countSummary": "pay promotions",
        "ownershipNote": "Promotion is a controlled transition, not a display state."
      },
      {
        "id": "entitlement_governance",
        "label": "Entitlement Governance Readiness",
        "route": "#capability/clause_intelligence/governed_entitlement_measures",
        "description": "Shows whether clause-derived entitlement facts are governed enough to become report-safe measures.",
        "status": "needs_review",
        "countSummary": "entitlement gates",
        "ownershipNote": "Keeps staged entitlement taxonomy separate from governed entitlement measures."
      },
      {
        "id": "audit_trail",
        "label": "Audit Trail",
        "route": "#audit",
        "navId": "nav-audit",
        "description": "Lineage, source process, review history, and governed changes by council.",
        "status": "reviewed",
        "countSummary": "lineage report",
        "ownershipNote": "Council Audit is reachable from custody and governance, backed by one underlying view."
      },
      {
        "id": "data_quality_queue",
        "label": "Data Quality Queue",
        "route": "#capability/data_marts/datamart_inventory",
        "description": "Data-quality issue, readiness, and report-input marts that surface blockers for governance work.",
        "status": "needs_review",
        "countSummary": "issue mart",
        "ownershipNote": "Turns blocked data states into a review queue without treating them as facts."
      },
      {
        "id": "reference_controls",
        "label": "Settings / Reference Controls",
        "route": "#admin",
        "navId": "nav-admin",
        "description": "Provider status, rate caps, and shared reference controls.",
        "status": "accepted",
        "countSummary": "settings",
        "ownershipNote": "Maintains shared reference inputs used by the workbench."
      }
    ]
  }
];
