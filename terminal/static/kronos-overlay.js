/* Owns pending forecasts: duplicate polls share one request; obsolete responses never render. */
class KronosOverlay {
  constructor({ request, render, clear, status, now = Date.now }) {
    Object.assign(this, { request, render, clear, status, now });
    this.key = null;
    this.revision = 0;
    this.pending = null;
    this.controller = null;
    this.ready = false;
    this.retryAt = 0;
  }

  reset() {
    this.revision++;
    this.controller?.abort();
    this.controller = null;
    this.pending = null;
    this.key = null;
    this.ready = false;
    this.retryAt = 0;
    this.clear();
  }

  sync(selection) {
    if (!selection) {
      this.reset();
      this.status('idle', 'Scénarios désactivés.');
      return Promise.resolve();
    }
    const key = JSON.stringify(selection);
    if (key !== this.key) {
      this.reset();
      this.key = key;
    }
    if (this.ready || this.pending || this.now() < this.retryAt) return this.pending || Promise.resolve();
    const revision = this.revision;
    this.controller = new AbortController();
    const signal = this.controller.signal;
    this.status('loading', 'Calcul des 50 scénarios…');
    this.pending = (async () => {
      try {
        const data = await this.request(selection, signal);
        if (revision !== this.revision || signal.aborted) return;
        if (data.sym !== selection.sym || data.tf !== selection.tf || data.source !== selection.src || data.src !== selection.market ||
            data.model !== selection.model || data.start.time !== selection.bar) {
          throw new Error('Les bougies ont changé. Actualisation de la prévision en cours.');
        }
        this.clear();
        this.render(data);
        this.ready = true;
        this.status('ready', `${data.model_label} · ${data.horizon} bougies ${data.tf} · 50 scénarios`);
      } catch (error) {
        if (revision !== this.revision || signal.aborted) return;
        this.clear();
        this.retryAt = this.now() + 15000;
        this.status('error', error.message || 'Prévision indisponible.');
      } finally {
        if (revision === this.revision) {
          this.pending = null;
          this.controller = null;
        }
      }
    })();
    return this.pending;
  }
}

if (typeof module !== 'undefined') module.exports = { KronosOverlay };
