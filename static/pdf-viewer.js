import * as pdfjsLib from "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.min.mjs";
pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.0.379/pdf.worker.min.mjs";

export class PdfViewer {
  constructor(canvas, controls) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.doc = null;
    this.pageNum = 1;
    this.scale = 1.0;
    this.minScale = 0.4;
    this.maxScale = 5.0;
    this.zoomStep = 0.25;
    this.controls = controls;
    this.onPageChange = null;
    this._wireControls();
  }

  async load(url) {
    this.doc = await pdfjsLib.getDocument(url).promise;
    this.pageNum = 1;
    await this.render();
    this._updateIndicator();
  }

  async goTo(n) {
    if (!this.doc) return;
    n = Math.max(1, Math.min(n, this.doc.numPages));
    this.pageNum = n;
    await this.render();
    this._updateIndicator();
    if (this.onPageChange) this.onPageChange(this.pageNum);
  }

  async render() {
    if (!this.doc) return;
    const page = await this.doc.getPage(this.pageNum);
    const viewport = page.getViewport({ scale: this.scale * 1.5 });
    this.canvas.width = viewport.width;
    this.canvas.height = viewport.height;
    await page.render({ canvasContext: this.ctx, viewport }).promise;
  }

  _updateIndicator() {
    this.controls.indicator.textContent = `${this.pageNum} / ${this.doc ? this.doc.numPages : "–"}`;
    this.controls.jumpInput.max = this.doc ? this.doc.numPages : 1;
    this.controls.zoomLevel.textContent = `${Math.round(this.scale * 100)}%`;
  }

  _wireControls() {
    this.controls.prev.onclick = () => this.goTo(this.pageNum - 1);
    this.controls.next.onclick = () => this.goTo(this.pageNum + 1);
    this.controls.jumpBtn.onclick = () => {
      const n = parseInt(this.controls.jumpInput.value, 10);
      if (!Number.isNaN(n)) this.goTo(n);
    };
    this.controls.zoomIn.onclick = async () => {
      this.scale = Math.min(this.scale + this.zoomStep, this.maxScale);
      await this.render();
      this._updateIndicator();
    };
    this.controls.zoomOut.onclick = async () => {
      this.scale = Math.max(this.scale - this.zoomStep, this.minScale);
      await this.render();
      this._updateIndicator();
    };
  }

  currentPage() {
    return this.pageNum;
  }
}
