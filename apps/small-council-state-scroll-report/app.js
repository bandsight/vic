/* global document, window, IntersectionObserver */
import {
  escapeHtml,
  loadReportData,
} from "./data-adapter.js?v=20260514-window-balla";
import {
  renderClassificationLadder,
  hydrateCohortMap,
  renderCohortMapShell,
  renderDistributionChart,
  renderEntitlementMatrix,
  renderEvidenceChain,
  renderPayChart,
  renderUpliftVisual,
} from "./visuals.js?v=20260101-shape";

const DATA_URL = "./data/workspace-small-council-state.json?v=20260101-shape";

const appState = {
  data: null,
  distributionMode: "raw",
  payState: "state_only",
  upliftPhase: "current",
};

const root = document.getElementById("report-root");

function renderHeroMetrics(metrics) {
  return metrics.map((item) => `
    <article class="hero-metric">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.value)}</strong>
      <p>${escapeHtml(item.detail)}</p>
    </article>
  `).join("");
}

function renderPaySteps(steps) {
  return steps.map((step, index) => `
    <article
      class="story-step${index === 0 ? " is-active" : ""}"
      data-pay-state="${escapeHtml(step.visualState)}"
      data-reveal
      id="pay-step-${escapeHtml(step.id)}"
    >
      <span>${escapeHtml(step.eyebrow)}</span>
      <h3>${escapeHtml(step.title)}</h3>
      <p>${escapeHtml(step.body)}</p>
      <small>${escapeHtml(step.annotation)}</small>
    </article>
  `).join("");
}

function renderUpliftSteps(timeline) {
  return (timeline.phases || []).map((phase, index) => `
    <article
      class="story-step uplift-step${index === 0 ? " is-active" : ""}"
      data-uplift-phase="${escapeHtml(phase.id)}"
      data-reveal
    >
      <span>${escapeHtml(phase.label)}</span>
      <h3>${escapeHtml(phase.description)}</h3>
      <p>${escapeHtml(timeline.summary)}</p>
    </article>
  `).join("");
}

function renderTakeaways(takeaways) {
  return takeaways.map((item) => `
    <article class="takeaway-card" data-reveal>
      <span>${escapeHtml(item.title)}</span>
      <p>${escapeHtml(item.body)}</p>
    </article>
  `).join("");
}

function renderReport(data) {
  const expectedSources = data.reportManifest.sourceDatasetsExpectedLater || [];
  root.innerHTML = `
    <section class="hero-section report-section" aria-labelledby="hero-title">
      <div class="hero-background" aria-hidden="true">
        <svg viewBox="0 0 1200 800" preserveAspectRatio="none">
          <path d="M80 600 C220 470 310 510 440 380 C610 210 755 285 915 150 C1010 70 1110 120 1180 55"></path>
          <path d="M0 300 C190 240 260 180 410 220 C590 268 690 170 820 240 C940 306 1020 260 1200 190"></path>
          <g>
            <circle cx="150" cy="560" r="4"></circle>
            <circle cx="310" cy="510" r="5"></circle>
            <circle cx="440" cy="380" r="4"></circle>
            <circle cx="610" cy="235" r="5"></circle>
            <circle cx="755" cy="285" r="4"></circle>
            <circle cx="915" cy="150" r="5"></circle>
            <circle cx="1070" cy="108" r="4"></circle>
          </g>
        </svg>
      </div>
      <div class="section-inner hero-inner">
        <div class="prototype-label">${escapeHtml(data.metadata.prototypeLabel)}</div>
        <p class="eyebrow">EBA Workbench downstream reporting prototype</p>
        <h1 id="hero-title">${escapeHtml(data.metadata.title)}</h1>
        <p class="hero-subhead">${escapeHtml(data.metadata.subtitle)}</p>
        <div class="hero-metrics" aria-label="Report framing metrics">
          ${renderHeroMetrics(data.heroMetrics)}
        </div>
      </div>
    </section>

    <section class="report-section distribution-section distribution-feature-section" aria-labelledby="distribution-title">
      <div class="section-inner distribution-feature-header" data-reveal>
        <p class="eyebrow">Distribution view</p>
        <h2 id="distribution-title">${escapeHtml(data.distribution.question)}</h2>
        <p>${escapeHtml(data.distribution.summary)}</p>
        <div class="asset-meta-strip">
          <span>Active snapshot</span>
          <strong>As at ${escapeHtml(data.distribution.asOfDate || data.metadata.asOfDate || "not specified")}</strong>
        </div>
        <p class="fine-print">${escapeHtml(data.distribution.inclusionRule || "")}</p>
        <p class="fine-print">${escapeHtml(data.distribution.caveat)}</p>
      </div>
      <div class="section-inner distribution-feature-visual" data-reveal>
        <div class="visual-frame">
          <div class="distribution-mode-bar">
            <div class="segmented-control distribution-mode-toggle" role="group" aria-label="Distribution value basis">
              <button type="button" data-distribution-mode="raw" aria-pressed="true">Raw</button>
              <button type="button" data-distribution-mode="smoothed" aria-pressed="false">Smoothed</button>
            </div>
          </div>
          <div id="distribution-visual" aria-live="polite"></div>
        </div>
      </div>
    </section>

    <section class="report-section why-section" aria-labelledby="why-title">
      <div class="section-inner editorial-grid">
        <div data-reveal>
          <p class="eyebrow">Why the question matters</p>
          <h2 id="why-title">A statewide average can be a blunt instrument.</h2>
        </div>
        <div class="editorial-copy" data-reveal>
          <p>Small councils are not simply smaller versions of metropolitan or regional city employers. Their pay position can be shaped by council scale, classification mix, agreement timing, uplift dates, local labour market pressure, entitlement strategy, and attraction or retention context.</p>
          <p>The reporting layer has to separate those effects. The value is not just a chart. It is a governed argument that shows what is exposed, what is resilient, and what still needs evidence.</p>
        </div>
      </div>
    </section>

    <section class="report-section cohort-section" aria-labelledby="cohort-title">
      <div class="section-inner split-section">
        <div class="section-copy" data-reveal>
          <p class="eyebrow">Cohort definition</p>
          <h2 id="cohort-title">${escapeHtml(data.cohort.title)}</h2>
          <p>${escapeHtml(data.cohort.definition)}</p>
          <p>${escapeHtml(data.cohort.productionCaveat)}</p>
        </div>
        <div data-reveal>
          ${renderCohortMapShell(data.cohort)}
        </div>
      </div>
    </section>

    <section class="report-section evidence-section" aria-labelledby="evidence-title">
      <div class="section-inner">
        <div class="section-header" data-reveal>
          <p class="eyebrow">Evidence and governance frame</p>
          <h2 id="evidence-title">The report is an output of governed machinery, not loose spreadsheet theatre.</h2>
          <p>In production, each claim should carry lineage back through the workbench: source, extraction, review status, mart, and report manifest.</p>
        </div>
        ${renderEvidenceChain(data.evidenceChain)}
      </div>
    </section>

    <section class="report-section pay-section" aria-labelledby="pay-title">
      <div class="section-inner pay-header" data-reveal>
        <p class="eyebrow">Pay position by band</p>
        <h2 id="pay-title">${escapeHtml(data.payByBand.question)}</h2>
        <p>${escapeHtml(data.payByBand.takeaway)}</p>
      </div>
      <div class="scrolly-grid section-inner">
        <div class="story-steps">
          ${renderPaySteps(data.narrativeSteps)}
        </div>
        <aside class="sticky-visual pay-visual-shell" aria-label="Pay position chart">
          <div class="visual-frame">
            <div class="visual-meta">
              <span>${escapeHtml(data.payByBand.metric)}</span>
              <span>${escapeHtml(data.payByBand.currentPeriod)}</span>
            </div>
            <div id="pay-visual" aria-live="polite"></div>
            <p class="visual-caveat">${escapeHtml(data.metadata.prototypeLabel)}. ${escapeHtml(data.metadata.caveat)}</p>
          </div>
        </aside>
      </div>
    </section>

    <section class="report-section classification-section" aria-labelledby="classification-title">
      <div class="section-inner split-section">
        <div class="section-copy" data-reveal>
          <p class="eyebrow">Classification and workforce shape</p>
          <h2 id="classification-title">${escapeHtml(data.classificationContext.question)}</h2>
          <p>${escapeHtml(data.classificationContext.summary)}</p>
          <p class="fine-print">${escapeHtml(data.classificationContext.productionNote)}</p>
        </div>
        <div data-reveal>
          ${renderClassificationLadder(data.classificationContext)}
        </div>
      </div>
    </section>

    <section class="report-section uplift-section" aria-labelledby="uplift-title">
      <div class="section-inner pay-header" data-reveal>
        <p class="eyebrow">Uplift timing / pay horizon</p>
        <h2 id="uplift-title">${escapeHtml(data.upliftTimeline.question)}</h2>
        <p>${escapeHtml(data.upliftTimeline.summary)}</p>
      </div>
      <div class="scrolly-grid uplift-grid section-inner">
        <div class="story-steps">
          ${renderUpliftSteps(data.upliftTimeline)}
        </div>
        <aside class="sticky-visual uplift-visual-shell" aria-label="Uplift timing visual">
          <div class="visual-frame">
            <div class="visual-meta">
              <span>${escapeHtml(data.upliftTimeline.metric)}</span>
              <span>${escapeHtml(`${data.upliftTimeline.snapshotDate} to ${data.upliftTimeline.horizonDate}`)}</span>
            </div>
            <div id="uplift-visual" aria-live="polite"></div>
            <p class="visual-caveat">${escapeHtml(data.upliftTimeline.caveat)}</p>
          </div>
        </aside>
      </div>
    </section>

    <section class="report-section entitlement-section" aria-labelledby="entitlement-title">
      <div class="section-inner">
        <div class="section-header" data-reveal>
          <p class="eyebrow">Employment value / entitlements</p>
          <h2 id="entitlement-title">${escapeHtml(data.entitlements.question)}</h2>
          <p>${escapeHtml(data.entitlements.summary)}</p>
        </div>
        <div data-reveal>
          ${renderEntitlementMatrix(data.entitlements)}
        </div>
        <p class="fine-print" data-reveal>${escapeHtml(data.entitlements.caveat)}</p>
      </div>
    </section>

    <section class="report-section synthesis-section" aria-labelledby="synthesis-title">
      <div class="section-inner">
        <div class="synthesis-copy" data-reveal>
          <p class="eyebrow">Executive synthesis</p>
          <h2 id="synthesis-title">So what?</h2>
          <p>Small councils do not simply sit below the state. They compete through a different mix of pay position, timing, and employment value. The question is not only whether they pay more or less - it is where they are exposed, where they are resilient, and how that position changes over time.</p>
        </div>
        <div class="takeaway-grid">
          ${renderTakeaways(data.executiveTakeaways)}
        </div>
      </div>
    </section>

    <section class="report-section product-note-section" aria-labelledby="product-note-title">
      <div class="section-inner product-note" data-reveal>
        <p class="eyebrow">Prototype to governed report</p>
        <h2 id="product-note-title">This page is structured as a report asset, ready for real marts.</h2>
        <p>The current prototype reads a single placeholder JSON file. The production version can replace it with a governed report payload assembled from canonical council identity, pay datamarts, uplift rule outputs, entitlement summaries, evidence references, and a report manifest.</p>
        <div class="source-chip-grid" aria-label="Future governed sources">
          ${expectedSources.map((source) => `<span>${escapeHtml(source)}</span>`).join("")}
        </div>
      </div>
    </section>
  `;

  renderDistributionVisual();
  renderPayVisual();
  renderUpliftVisualState();
  hydrateCohortMap(data.cohort);
  setupDistributionToggle();
  setupObservers();
  scrollToHashTarget();
}

function renderDistributionVisual() {
  const target = document.getElementById("distribution-visual");
  if (!target || !appState.data) return;
  target.innerHTML = renderDistributionChart(appState.data.distribution, appState.distributionMode);
}

function setDistributionMode(nextMode) {
  if (!nextMode || appState.distributionMode === nextMode) return;
  appState.distributionMode = nextMode;
  document.querySelectorAll("[data-distribution-mode]").forEach((button) => {
    const isActive = button.dataset.distributionMode === nextMode;
    button.classList.toggle("is-active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
  renderDistributionVisual();
}

function setupDistributionToggle() {
  document.querySelectorAll("[data-distribution-mode]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.distributionMode === appState.distributionMode);
    button.addEventListener("click", () => setDistributionMode(button.dataset.distributionMode));
  });
}

function renderPayVisual() {
  const target = document.getElementById("pay-visual");
  if (!target || !appState.data) return;
  target.innerHTML = renderPayChart(appState.data.payByBand, appState.payState);
}

function renderUpliftVisualState() {
  const target = document.getElementById("uplift-visual");
  if (!target || !appState.data) return;
  target.innerHTML = renderUpliftVisual(appState.data.upliftTimeline, appState.upliftPhase);
}

function setPayState(nextState) {
  if (!nextState || appState.payState === nextState) return;
  appState.payState = nextState;
  document.querySelectorAll("[data-pay-state]").forEach((step) => {
    step.classList.toggle("is-active", step.dataset.payState === nextState);
  });
  renderPayVisual();
}

function setUpliftPhase(nextPhase) {
  if (!nextPhase || appState.upliftPhase === nextPhase) return;
  appState.upliftPhase = nextPhase;
  document.querySelectorAll("[data-uplift-phase]").forEach((step) => {
    step.classList.toggle("is-active", step.dataset.upliftPhase === nextPhase);
  });
  renderUpliftVisualState();
}

function chooseActiveStep(steps, datasetKey, callback) {
  const viewportCenter = window.innerHeight * 0.52;
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  steps.forEach((step) => {
    const rect = step.getBoundingClientRect();
    if (rect.bottom < 0 || rect.top > window.innerHeight) return;
    const stepCenter = rect.top + rect.height / 2;
    const distance = Math.abs(stepCenter - viewportCenter);
    if (distance < bestDistance) {
      best = step;
      bestDistance = distance;
    }
  });
  if (best) callback(best.dataset[datasetKey]);
}

function setupStepObserver(selector, datasetKey, callback) {
  const steps = Array.from(document.querySelectorAll(selector));
  if (!steps.length) return;
  if (!("IntersectionObserver" in window)) {
    callback(steps[0].dataset[datasetKey]);
    return;
  }
  const observer = new IntersectionObserver(() => chooseActiveStep(steps, datasetKey, callback), {
    rootMargin: "-18% 0px -34% 0px",
    threshold: [0.05, 0.25, 0.5, 0.75],
  });
  steps.forEach((step) => observer.observe(step));
  window.addEventListener("resize", () => chooseActiveStep(steps, datasetKey, callback), { passive: true });
}

function setupRevealObserver() {
  const revealItems = Array.from(document.querySelectorAll("[data-reveal]"));
  if (!("IntersectionObserver" in window)) {
    revealItems.forEach((item) => item.classList.add("is-visible"));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    });
  }, {
    rootMargin: "0px 0px -12% 0px",
    threshold: 0.12,
  });
  revealItems.forEach((item) => observer.observe(item));
}

function setupObservers() {
  setupRevealObserver();
  setupStepObserver("[data-pay-state]", "payState", setPayState);
  setupStepObserver("[data-uplift-phase]", "upliftPhase", setUpliftPhase);
}

function scrollToHashTarget() {
  const hash = window.location.hash;
  if (!hash || hash.length < 2) return;
  const target = document.getElementById(hash.slice(1));
  if (!target) return;
  window.setTimeout(() => target.scrollIntoView({ block: "start" }), 0);
}

async function init() {
  try {
    appState.data = await loadReportData(DATA_URL);
    renderReport(appState.data);
  } catch (error) {
    root.innerHTML = `
      <section class="report-section error-section">
        <div class="section-inner">
          <p class="eyebrow">Prototype load error</p>
          <h1>Could not load the report data.</h1>
          <p>${escapeHtml(error.message || String(error))}</p>
        </div>
      </section>
    `;
  }
}

init();
