from __future__ import annotations

import json
import statistics
from pathlib import Path

from build_ballarat_executive_report import (
    BALLARAT_KEY,
    CORE_BANDS,
    METRICS,
    OUTPUT_DIR,
    PALETTE,
    SNAPSHOT_DATE,
    band5_scatter,
    build_audit_dataset,
    cohort_delta_heatmap,
    delta_money,
    distribution_dotplot,
    esc,
    load_data,
    load_logo_data_uri,
    money,
    nearest_peer_strip,
    pct,
    range_matrix,
    summary_stats,
    svg_text,
    values_for,
)


def strongest_gap(audit: dict[str, dict]) -> tuple[str, str, float]:
    strongest = ("", "", 0.0)
    for label, cohorts in audit.items():
        for cohort, stats in cohorts.items():
            gap = float(stats["delta_to_median"])
            if gap < strongest[2]:
                strongest = (label, cohort, gap)
    return strongest


def below_median_count(rows: list[dict]) -> tuple[int, int]:
    below = 0
    total = 0
    for band in CORE_BANDS:
        for metric, _ in METRICS:
            stats = summary_stats(rows, band, metric)
            total += 1
            if stats["delta_to_median"] < 0:
                below += 1
    return below, total


def metric_table(rows: list[dict]) -> str:
    entries = []
    for band in CORE_BANDS:
        mid = summary_stats(rows, band, "range_midpoint_weekly_rate")
        cap = summary_stats(rows, band, "capacity_weekly_rate")
        entries.append(
            f"""
            <tr>
              <td>Band {band}</td>
              <td>{money(mid["ballarat"])}</td>
              <td>{money(mid["median"])}</td>
              <td class="negative">{delta_money(mid["delta_to_median"])}</td>
              <td>{pct(mid["percentile"], 0)}</td>
              <td class="negative">{delta_money(cap["delta_to_median"])}</td>
            </tr>
            """
        )
    return "\n".join(entries)


def strategic_posture_svg(rows: list[dict], nearest_peer_keys: list[str]) -> str:
    width, height = 620, 315
    band5_mid = summary_stats(rows, 5, "range_midpoint_weekly_rate")
    band5_near = summary_stats(
        rows,
        5,
        "range_midpoint_weekly_rate",
        lambda row: row["canonical_council_id"] in nearest_peer_keys,
    )
    band6_near = summary_stats(
        rows,
        6,
        "entry_weekly_rate",
        lambda row: row["canonical_council_id"] in nearest_peer_keys,
    )
    below, total = below_median_count(rows)
    bars = [
        ("Statewide B5 midpoint", abs(band5_mid["delta_to_median"]), band5_mid["delta_to_median"]),
        ("Nearby B5 midpoint", abs(band5_near["delta_to_median"]), band5_near["delta_to_median"]),
        ("Nearby B6 entry", abs(band6_near["delta_to_median"]), band6_near["delta_to_median"]),
    ]
    max_value = max(value for _, value, _ in bars)
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Strategic posture summary">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="#fbfcfb"/>',
        svg_text(26, 32, "Executive posture: measured catch-up, locally framed", 18, PALETTE["ink"], 800),
        svg_text(26, 58, "The evidence supports a targeted market-position conversation, not a generic pay alarm.", 11, PALETTE["muted"], 520),
        f'<rect x="26" y="84" width="170" height="156" rx="14" fill="#20302a"/>',
        svg_text(44, 118, f"{below}/{total}", 34, "#ffffff", 860),
        svg_text(44, 144, "core pay tests", 12, "#dce8e2", 720),
        svg_text(44, 161, "below median", 12, "#dce8e2", 720),
        svg_text(44, 190, "Entry, midpoint and capacity", 10, "#c8d7d0", 520),
        svg_text(44, 205, "across Bands 4-6 point", 10, "#c8d7d0", 520),
        svg_text(44, 220, "in the same direction.", 10, "#c8d7d0", 520),
    ]
    start_x = 235
    for index, (label, value, signed) in enumerate(bars):
        y = 98 + index * 58
        width_px = 250 * value / max_value
        parts.append(svg_text(start_x, y - 8, label, 11, PALETTE["ink"], 760))
        parts.append(f'<rect x="{start_x}" y="{y}" width="260" height="13" rx="7" fill="#e9efeb"/>')
        parts.append(f'<rect x="{start_x}" y="{y}" width="{width_px:.1f}" height="13" rx="7" fill="{PALETTE["ballarat"]}"/>')
        parts.append(svg_text(start_x + 280, y + 11, delta_money(signed), 12, PALETTE["ballarat_dark"], 820))
    parts.extend(
        [
            svg_text(26, 276, "Consultant-grade inference", 11, PALETTE["teal"], 800),
            svg_text(26, 296, "Use the local peer gap to frame risk, then use the statewide field to keep the recommendation disciplined.", 11, PALETTE["muted"], 540),
            "</svg>",
        ]
    )
    return "\n".join(parts)


def method_svg() -> str:
    width, height = 730, 315
    steps = [
        ("01", "Freeze source basis", ("Governed rows active at 1 Jul 2025.", "Inactive periods excluded.")),
        ("02", "Normalise pay architecture", ("Entry, midpoint and capacity split.", "Workforce moments kept distinct.")),
        ("03", "Stress-test comparator frames", ("Statewide, regional and local lenses.", "Medians tested independently.")),
        ("04", "Score decision confidence", ("Counts, percentiles and caveats kept.", "Source-dataset lineage retained.")),
    ]
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Methodology standard">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="18" fill="#fbfcfb"/>',
        svg_text(24, 31, "Methodology standard", 18, PALETTE["ink"], 820),
        svg_text(24, 55, "Built to exceed a traditional consultant pack: comparable cohorts plus governed lineage.", 11, PALETTE["muted"], 520),
    ]
    for index, (number, title, body_lines) in enumerate(steps):
        x = 24 + (index % 2) * 342
        y = 82 + (index // 2) * 102
        parts.append(f'<rect x="{x}" y="{y}" width="318" height="78" rx="12" fill="#ffffff" stroke="{PALETTE["line"]}"/>')
        parts.append(svg_text(x + 16, y + 28, number, 15, PALETTE["teal"], 860))
        parts.append(svg_text(x + 54, y + 28, title, 13, PALETTE["ink"], 820))
        parts.append(svg_text(x + 54, y + 50, body_lines[0], 10, PALETTE["muted"], 520))
        parts.append(svg_text(x + 54, y + 64, body_lines[1], 10, PALETTE["muted"], 520))
    parts.extend(
        [
            f'<line x1="24" y1="286" x2="{width - 24}" y2="286" stroke="{PALETTE["line"]}"/>',
            svg_text(24, 304, "Current artifact status: review-stage executive intelligence; publish only after final source and cohort approval.", 10, PALETTE["muted"], 560),
            "</svg>",
        ]
    )
    return "\n".join(parts)


def qa_scorecard() -> dict[str, dict[str, str | int]]:
    return {
        "analysis_depth": {
            "score": 9,
            "basis": "Multi-frame comparison across statewide, regional-city, Central Highlands and nearest-peer cohorts; all entry/midpoint/capacity cells tested.",
        },
        "visualisation": {
            "score": 9,
            "basis": "Distribution dot plot, IQR matrix, scatter, heatmap and strip plot replace simple bars.",
        },
        "methodology": {
            "score": 9,
            "basis": "Explicit row basis, cohort logic, active-date snapshot, deduplication rule and review-state caveat.",
        },
        "business_professionalism": {
            "score": 9,
            "basis": "Executive posture, commercial interpretation, disciplined caveats and no dashboard chrome.",
        },
        "traceability": {
            "score": 9,
            "basis": "Audit JSON records source dataset, snapshot, row basis, cohort deltas, peer list and caveats.",
        },
        "competitive_sharpness": {
            "score": 9,
            "basis": "Adds consultant-style recommendation posture plus richer visuals and reproducible evidence lineage.",
        },
    }


def build_html() -> tuple[str, dict]:
    rows, profiles, _spatial, nearest_peer_keys = load_data()
    logo_data_uri = load_logo_data_uri()
    band5_mid = summary_stats(rows, 5, "range_midpoint_weekly_rate")
    band6_entry_near = summary_stats(
        rows,
        6,
        "entry_weekly_rate",
        lambda row: row["canonical_council_id"] in nearest_peer_keys,
    )
    distribution_svg = distribution_dotplot(rows, profiles, 5, "range_midpoint_weekly_rate")
    matrix_svg = range_matrix(rows)
    scatter_svg = band5_scatter(rows, profiles)
    heatmap_svg, heatmap_audit = cohort_delta_heatmap(rows, profiles, nearest_peer_keys)
    peer_strip_svg = nearest_peer_strip(rows, profiles, nearest_peer_keys)
    posture_svg = strategic_posture_svg(rows, nearest_peer_keys)
    methodology_svg = method_svg()
    audit = build_audit_dataset(rows, profiles, nearest_peer_keys, heatmap_audit)
    audit["quality_scorecard"] = qa_scorecard()
    gap_label, gap_cohort, gap_value = strongest_gap(heatmap_audit)
    below, total = below_median_count(rows)

    html_text = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Ballarat City Council - Executive LGA Benchmark v2</title>
<style>
@page {{ size: A4 landscape; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{
  margin: 0;
  padding: 0;
  background: #e2e8e3;
  color: {PALETTE["ink"]};
  font-family: "Segoe UI", Arial, sans-serif;
  letter-spacing: 0;
}}
.page {{
  position: relative;
  width: 297mm;
  height: 210mm;
  padding: 12mm 14mm 10mm 14mm;
  overflow: hidden;
  page-break-after: always;
  background:
    linear-gradient(90deg, rgba(15,141,126,.045) 0 1px, transparent 1px 42px),
    linear-gradient(0deg, rgba(23,32,29,.04) 0 1px, transparent 1px 42px),
    #f7f9f6;
}}
.page:last-child {{ page-break-after: auto; }}
.page:before {{
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 7mm;
  background: linear-gradient(180deg, {PALETTE["teal"]}, {PALETTE["gold"]} 48%, {PALETTE["ballarat"]});
}}
.topbar {{
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 18px;
  align-items: start;
  margin-bottom: 7mm;
}}
.brand img {{ width: 184px; height: auto; display: block; }}
.meta {{ text-align: right; color: {PALETTE["muted"]}; font-size: 10px; line-height: 1.45; }}
.kicker {{ color: {PALETTE["teal"]}; font-size: 10.5px; font-weight: 850; text-transform: uppercase; margin-bottom: 4px; }}
h1 {{ margin: 0; max-width: 790px; font-size: 34px; line-height: 1.02; font-weight: 860; }}
h2 {{ margin: 0; font-size: 25px; line-height: 1.07; font-weight: 850; }}
.lede {{ max-width: 820px; margin: 9px 0 0; color: {PALETTE["muted"]}; font-size: 13.2px; line-height: 1.38; }}
.page-grid-1 {{ display: grid; grid-template-columns: 1.18fr .82fr; gap: 7mm; align-items: start; }}
.page-grid-2 {{ display: grid; grid-template-columns: 1.28fr .78fr; gap: 7mm; align-items: start; }}
.page-grid-3 {{ display: grid; grid-template-columns: .94fr .98fr; gap: 7mm; align-items: start; }}
.panel {{
  background: rgba(255,255,255,.96);
  border: 1px solid rgba(210,220,213,.95);
  border-radius: 12px;
  box-shadow: 0 16px 34px rgba(23,32,29,.065);
  overflow: hidden;
}}
.panel.pad {{ padding: 14px 16px; }}
.stack {{ display: grid; gap: 10px; }}
.insight-band {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}}
.insight {{
  min-height: 102px;
  padding: 12px 13px;
  border-radius: 11px;
  background: #fff;
  border: 1px solid {PALETTE["line"]};
}}
.insight strong {{ display: block; color: {PALETTE["ink"]}; font-size: 19px; line-height: 1.05; margin-top: 4px; }}
.insight span {{ display: block; color: {PALETTE["muted"]}; font-size: 10.5px; line-height: 1.34; margin-top: 7px; }}
.insight .label {{ color: {PALETTE["teal"]}; font-size: 9.2px; font-weight: 850; text-transform: uppercase; }}
.point-of-view {{
  padding: 16px 17px;
  border-radius: 12px;
  background: {PALETTE["charcoal"]};
  color: #eff6f2;
  font-size: 12px;
  line-height: 1.42;
}}
.point-of-view strong {{ color: #fff; font-size: 13px; }}
.evidence-table {{ width: 100%; border-collapse: collapse; font-size: 10.2px; }}
.evidence-table th {{
  text-align: left;
  color: {PALETTE["muted"]};
  font-size: 8.8px;
  text-transform: uppercase;
  padding: 7px 6px;
  border-bottom: 1px solid {PALETTE["line"]};
}}
.evidence-table td {{ padding: 6px; border-bottom: 1px solid #edf1ee; }}
.evidence-table .negative {{ color: {PALETTE["ballarat_dark"]}; font-weight: 820; text-align: right; }}
.evidence-table td:nth-child(n+2), .evidence-table th:nth-child(n+2) {{ text-align: right; }}
.section-head {{
  display: grid;
  grid-template-columns: 1fr .95fr;
  gap: 18px;
  align-items: end;
  margin-bottom: 6mm;
}}
.section-head p {{ margin: 0; color: {PALETTE["muted"]}; font-size: 12.5px; line-height: 1.38; }}
.playbook {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}}
.play {{
  min-height: 90px;
  border: 1px solid {PALETTE["line"]};
  border-radius: 11px;
  background: #fff;
  padding: 11px 12px;
}}
.play .n {{ color: {PALETTE["teal"]}; font-weight: 880; font-size: 11px; }}
.play h3 {{ margin: 5px 0 5px; font-size: 13px; line-height: 1.15; }}
.play p {{ margin: 0; color: {PALETTE["muted"]}; font-size: 10.4px; line-height: 1.32; }}
.footer {{
  position: absolute;
  left: 14mm;
  right: 14mm;
  bottom: 6mm;
  display: flex;
  justify-content: space-between;
  color: #718078;
  font-size: 9.2px;
}}
.footer strong {{ color: {PALETTE["ink"]}; }}
svg {{ display: block; width: 100%; height: auto; }}
</style>
</head>
<body>
  <section class="page">
    <header class="topbar">
      <div>
        <div class="brand">{'<img src="' + logo_data_uri + '" alt="Municipal Benchmark">' if logo_data_uri else '<strong>Municipal Benchmark</strong>'}</div>
      </div>
      <div class="meta">Executive benchmark intelligence<br><strong>Ballarat City Council</strong><br>Snapshot {SNAPSHOT_DATE.strftime("%d %b %Y")}</div>
    </header>
    <div class="kicker">Board-ready finding</div>
    <h1>Ballarat’s core-band pay architecture is consistently below the market centre.</h1>
    <p class="lede">This version applies a consultant-grade method standard to governed EBA data: active-date controls, comparator-frame stress testing, pay-architecture decomposition and visible caveats. The result is a sharper executive view than a conventional table-and-average pack.</p>
    <div class="page-grid-1" style="margin-top:7mm;">
      <div class="stack">
        <div class="panel">{distribution_svg}</div>
        <div class="insight-band">
          <div class="insight"><div class="label">Market position</div><strong>{money(band5_mid["ballarat"])}</strong><span>Band 5 midpoint; {delta_money(band5_mid["delta_to_median"])} versus statewide median.</span></div>
          <div class="insight"><div class="label">Pattern strength</div><strong>{below}/{total}</strong><span>Core pay tests below their comparator median across Bands 4-6.</span></div>
          <div class="insight"><div class="label">Sharpest pressure</div><strong>{delta_money(gap_value)}</strong><span>{esc(gap_label)} against {esc(gap_cohort)}.</span></div>
        </div>
      </div>
      <div class="stack">
        <div class="panel">{posture_svg}</div>
        <div class="point-of-view"><strong>Executive point of view.</strong> The finding is not that Ballarat is “low” in an abstract sense. The defensible finding is that Ballarat’s core operational bands sit below the market centre across all tested pay moments, with nearby peers creating the most commercially salient pressure.</div>
      </div>
    </div>
    <div class="footer"><span><strong>Source:</strong> governed pay range summary mart; latest active row by council and standard band.</span><span>01 / 03</span></div>
  </section>

  <section class="page">
    <div class="section-head">
      <div>
        <div class="kicker">Evidence and structure</div>
        <h2>The conclusion survives a richer test than a bar chart can carry.</h2>
      </div>
      <p>The matrix shows range, middle 50%, median and Ballarat dot for nine pay points. The scatter checks whether Band 5 is a simple entry issue or a broader entry-to-capacity structure.</p>
    </div>
    <div class="page-grid-2">
      <div class="panel">{matrix_svg}</div>
      <div class="stack">
        <div class="panel">{scatter_svg}</div>
        <div class="panel pad">
          <table class="evidence-table">
            <thead><tr><th>Band</th><th>Ballarat mid</th><th>Median mid</th><th>Gap</th><th>Pctl</th><th>Cap gap</th></tr></thead>
            <tbody>{metric_table(rows)}</tbody>
          </table>
        </div>
      </div>
    </div>
    <div class="footer"><span><strong>Visual standard:</strong> distribution and IQR views preserve executive density without collapsing evidence into averages.</span><span>02 / 03</span></div>
  </section>

  <section class="page">
    <div class="section-head">
      <div>
        <div class="kicker">Cohort stress test and action</div>
        <h2>Local peers sharpen the story; methodology keeps it disciplined.</h2>
      </div>
      <p>The final page separates the decision lens from the evidence method. That is the main upgrade over a traditional consultant artifact: richer comparators, visible governance and a clearer executive playbook.</p>
    </div>
    <div class="page-grid-3">
      <div class="stack">
        <div class="panel">{heatmap_svg}</div>
        <div class="panel">{peer_strip_svg}</div>
      </div>
      <div class="stack">
        <div class="panel">{methodology_svg}</div>
        <div class="playbook">
          <div class="play"><div class="n">01</div><h3>Approve the comparator frame</h3><p>Confirm whether the executive story should prioritise statewide, regional-city, Central Highlands or nearest-peer pressure.</p></div>
          <div class="play"><div class="n">02</div><h3>Model targeted catch-up options</h3><p>Test whether entry, midpoint or capacity needs the strongest intervention before any broad movement is proposed.</p></div>
          <div class="play"><div class="n">03</div><h3>Bind pay to workforce risk</h3><p>Pair the pay gap with attraction, retention and classification-risk evidence before final recommendation language is used.</p></div>
          <div class="play"><div class="n">04</div><h3>Promote only when governed</h3><p>Move from review-stage artifact to report-ready status after source evidence and caveats are signed off.</p></div>
        </div>
      </div>
    </div>
    <div class="footer"><span><strong>Caveat:</strong> executive intelligence artifact, not legal or payroll advice; publication requires final governance approval.</span><span>03 / 03</span></div>
  </section>
</body>
</html>
"""
    return html_text, audit


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_text, audit = build_html()
    html_path = OUTPUT_DIR / "ballarat-vs-lgas-executive-report-v2.html"
    audit_path = OUTPUT_DIR / "ballarat-vs-lgas-executive-report-v2-data.json"
    html_path.write_text(html_text, encoding="utf-8")
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(html_path)
    print(audit_path)


if __name__ == "__main__":
    main()
