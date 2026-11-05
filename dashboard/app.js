/**
 * Sentinel Observability Dashboard — SPA Client (Vanilla JS)
 * Sincronizado com os esquemas canónicos de src/models.py:
 *   - CurrentStatusPayload (data/current_status.json)
 *   - HistoryPayload (data/history.json)
 *   - ForensicIncident (data/incidents/<id>.json)
 * 
 * Cumpre os 7 Estados Existenciais de .harness/invariants/ux_contract.yaml:
 *   1. EMPTY, 2. LOADING, 3. POPULATED, 4. ZERO_RESULTS,
 *   5. PARTIAL_DEGRADED, 6. ERROR, 7. SUCCESS_FEEDBACK
 */

(function () {
  'use strict';

  // Application State
  const state = {
    allStores: [],
    historyData: {},
    filteredStores: [],
    activeModalSiteId: null,
    isLoading: false,
    filters: {
      infra: 'all',
      status: 'all',
      search: ''
    }
  };

  // DOM Elements Cache
  const DOM = {
    btnRefresh: document.getElementById('btn-refresh'),
    btnRetry: document.getElementById('btn-retry'),
    btnResetFilters: document.getElementById('btn-reset-filters'),
    filterInfra: document.getElementById('filter-infra'),
    filterStatus: document.getElementById('filter-status'),
    searchInput: document.getElementById('search-input'),
    storesCountBadge: document.getElementById('stores-count-badge'),
    lastRunText: document.getElementById('last-run-text'),
    storesGrid: document.getElementById('stores-grid'),

    // Existential State Containers
    stateLoading: document.getElementById('state-loading'),
    stateEmpty: document.getElementById('state-empty'),
    stateZeroResults: document.getElementById('state-zero-results'),
    statePartialDegraded: document.getElementById('state-partial-degraded'),
    stateError: document.getElementById('state-error'),
    statePopulated: document.getElementById('state-populated'),
    metricsSummary: document.getElementById('metrics-summary'),
    errorMessageText: document.getElementById('error-message-text'),
    toastContainer: document.getElementById('toast-container'),

    // Summary Metrics
    summaryUptime: document.getElementById('summary-uptime'),
    summaryCheckout: document.getElementById('summary-checkout'),
    summaryTtfb: document.getElementById('summary-ttfb'),
    summaryIncidents: document.getElementById('summary-incidents'),

    // Forensic Modal Elements
    forensicModal: document.getElementById('forensic-modal'),
    modalStoreName: document.getElementById('modal-store-name'),
    btnCloseModal: document.getElementById('btn-close-modal'),
    btnCloseModalX: document.getElementById('btn-close-modal-x'),
    modalVerdictText: document.getElementById('modal-verdict-text'),
    modalFailedStep: document.getElementById('modal-failed-step'),
    modalErrorCode: document.getElementById('modal-error-code'),
    modalCfCache: document.getElementById('modal-cf-cache'),
    modalTtfb: document.getElementById('modal-ttfb'),
    modalRecommendationBox: document.getElementById('modal-recommendation-box'),
    modalRecommendationText: document.getElementById('modal-recommendation-text'),
    modalScreenshotImg: document.getElementById('modal-screenshot-img'),
    modalScreenshotEmpty: document.getElementById('modal-screenshot-empty'),
    modalDomExtract: document.getElementById('modal-dom-extract'),
    modalJsErrorsCount: document.getElementById('modal-js-errors-count'),
    modalCodeErrorsList: document.getElementById('modal-code-errors-list'),
    modalJsErrors: document.getElementById('modal-js-errors'),
    modalVitalTbt: document.getElementById('modal-vital-tbt'),
    modalVitalTbtStatus: document.getElementById('modal-vital-tbt-status'),
    modalVitalFcp: document.getElementById('modal-vital-fcp'),
    modalVitalDcl: document.getElementById('modal-vital-dcl'),
    modalVitalLoad: document.getElementById('modal-vital-load'),
    modalLongTasksCount: document.getElementById('modal-long-tasks-count'),
    modalLongTasksList: document.getElementById('modal-long-tasks-list'),
    modalWeightTotal: document.getElementById('modal-weight-total'),
    modalWeightJs: document.getElementById('modal-weight-js'),
    modalWeightCss: document.getElementById('modal-weight-css'),
    modalWeightImg: document.getElementById('modal-weight-img'),
    modalWeightRequests: document.getElementById('modal-weight-requests'),
    modalNetCache: document.getElementById('modal-net-cache'),
    modalNetEncoding: document.getElementById('modal-net-encoding'),
    modalNetProtocol: document.getElementById('modal-net-protocol'),
    modalNetServer: document.getElementById('modal-net-server'),
    modalSlowestTbody: document.getElementById('modal-slowest-tbody'),
    modalNetworkTbody: document.getElementById('modal-network-tbody'),

    // Tabs
    tabBtns: document.querySelectorAll('.tab-btn'),
    tabPanes: document.querySelectorAll('.tab-pane')
  };

  /**
   * Inicialização da aplicação
   */
  function initDashboard() {
    bindEvents();
    loadTelemetry();
  }

  /**
   * Registo de event listeners e atalhos de teclado
   */
  function bindEvents() {
    // Ação primária do cabeçalho
    if (DOM.btnRefresh) {
      DOM.btnRefresh.addEventListener('click', () => loadTelemetry(true));
    }

    // Ação de recuperação no estado ERROR
    if (DOM.btnRetry) {
      DOM.btnRetry.addEventListener('click', () => loadTelemetry(true));
    }

    // Restauro de filtros no estado ZERO_RESULTS
    if (DOM.btnResetFilters) {
      DOM.btnResetFilters.addEventListener('click', resetFilters);
    }

    // Filtros reativos
    if (DOM.filterInfra) {
      DOM.filterInfra.addEventListener('change', (e) => {
        state.filters.infra = e.target.value;
        applyFilters();
      });
    }

    if (DOM.filterStatus) {
      DOM.filterStatus.addEventListener('change', (e) => {
        state.filters.status = e.target.value;
        applyFilters();
      });
    }

    // Pesquisa com debounce
    if (DOM.searchInput) {
      let debounceTimeout = null;
      DOM.searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
          state.filters.search = e.target.value.trim().toLowerCase();
          applyFilters();
        }, 150);
      });
    }

    // Fecho de modal forense
    if (DOM.btnCloseModal) {
      DOM.btnCloseModal.addEventListener('click', closeForensicModal);
    }
    if (DOM.btnCloseModalX) {
      DOM.btnCloseModalX.addEventListener('click', closeForensicModal);
    }

    // Fecho por clique no backdrop
    if (DOM.forensicModal) {
      DOM.forensicModal.addEventListener('click', (e) => {
        if (e.target === DOM.forensicModal) {
          closeForensicModal();
        }
      });
    }

    // Previsibilidade Comportamental: Tecla Escape fecha elementos efémeros
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !DOM.forensicModal.classList.contains('hidden')) {
        closeForensicModal();
      }
    });

    // Navegação entre abas do modal
    DOM.tabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const targetPaneId = btn.getAttribute('aria-controls');
        switchModalTab(btn, targetPaneId);
      });
    });
  }

  /**
   * Gestão visual dos 7 estados existenciais
   */
  function setViewState(viewState) {
    // Reset de visibilidade
    DOM.stateLoading.classList.add('hidden');
    DOM.stateEmpty.classList.add('hidden');
    DOM.stateZeroResults.classList.add('hidden');
    DOM.stateError.classList.add('hidden');
    DOM.statePopulated.classList.add('hidden');

    switch (viewState) {
      case 'LOADING':
        DOM.stateLoading.classList.remove('hidden');
        if (DOM.btnRefresh) DOM.btnRefresh.disabled = true;
        break;

      case 'EMPTY':
        DOM.stateEmpty.classList.remove('hidden');
        DOM.metricsSummary.classList.add('hidden');
        if (DOM.btnRefresh) DOM.btnRefresh.disabled = false;
        break;

      case 'ZERO_RESULTS':
        DOM.stateZeroResults.classList.remove('hidden');
        DOM.metricsSummary.classList.remove('hidden');
        if (DOM.btnRefresh) DOM.btnRefresh.disabled = false;
        break;

      case 'ERROR':
        DOM.stateError.classList.remove('hidden');
        DOM.metricsSummary.classList.add('hidden');
        if (DOM.btnRefresh) DOM.btnRefresh.disabled = false;
        break;

      case 'POPULATED':
        DOM.statePopulated.classList.remove('hidden');
        DOM.metricsSummary.classList.remove('hidden');
        if (DOM.btnRefresh) DOM.btnRefresh.disabled = false;
        break;
    }
  }

  /**
   * Normalização resiliente de esquemas de dados de loja
   */
  function normalizeStore(s) {
    const statusUpper = (s.status || s.health || 'HEALTHY').toUpperCase();
    const healthLower = statusUpper.toLowerCase();
    const ttfb =
      typeof s.latest_ttfb_ms === 'number'
        ? s.latest_ttfb_ms
        : s.edge && typeof s.edge.ttfb_ms === 'number'
        ? s.edge.ttfb_ms
        : null;
    const sslDays =
      typeof s.ssl_days_remaining === 'number'
        ? s.ssl_days_remaining
        : s.edge && typeof s.edge.ssl_days_remaining === 'number'
        ? s.edge.ssl_days_remaining
        : null;
    const hasActiveCheckoutIncident = Boolean(
      s.last_incident &&
      s.last_incident.failure_phase &&
      s.last_incident.failure_phase !== 'edge_network'
    );
    const checkoutOk = !hasActiveCheckoutIncident;
    const incident = s.last_incident || s.incident || null;
    const infra = s.infrastructure_type || s.infrastructure || 'rocket_cloudflare';
    const storeUrl = s.url || s.store_url || `https://${s.site_id}.com`;

    return {
      ...s,
      site_id: s.site_id || s.id,
      name: s.name || s.site_id,
      url: storeUrl,
      store_url: storeUrl,
      health: healthLower,
      status: statusUpper,
      infrastructure: infra,
      infrastructure_type: infra,
      latest_ttfb_ms: ttfb,
      ssl_days_remaining: sslDays,
      checkout_ok: checkoutOk,
      incident: incident,
      last_incident: incident,
      edge: {
        ttfb_ms: ttfb,
        ssl_days_remaining: sslDays
      }
    };
  }

  /**
   * Carregamento assíncrono dos ficheiros de telemetria
   */
  async function loadTelemetry(showFeedback = false) {
    state.isLoading = true;
    setViewState('LOADING');

    try {
      // Carregamento paralelo resiliente com tolerância a falhas parciais
      const [currentStatusRes, historyRes] = await Promise.allSettled([
        fetch('data/current_status.json', { cache: 'no-cache' }),
        fetch('data/history.json', { cache: 'no-cache' })
      ]);

      // Validação do status principal (current_status.json)
      if (currentStatusRes.status !== 'fulfilled' || !currentStatusRes.value.ok) {
        throw new Error(
          `Falha ao obter data/current_status.json (Status: ${
            currentStatusRes.status === 'fulfilled' ? currentStatusRes.value.status : 'Network error'
          })`
        );
      }

      const currentData = await currentStatusRes.value.json();
      const rawStores = (currentData.stores || []).map(normalizeStore);

      // Tratamento do histórico (falha não-bloqueante -> PARTIAL_DEGRADED)
      let historyData = {};
      if (historyRes.status === 'fulfilled' && historyRes.value.ok) {
        try {
          const histPayload = await historyRes.value.json();
          const points = histPayload.points || [];
          const grouped = {};
          points.forEach((pt) => {
            const sid = pt.site_id;
            if (!grouped[sid]) {
              grouped[sid] = { points: [] };
            }
            grouped[sid].points.push(pt);
          });
          historyData = grouped;
          DOM.statePartialDegraded.classList.add('hidden');
        } catch (err) {
          console.warn('[Sentinel] Falha ao processar history.json:', err);
          DOM.statePartialDegraded.classList.remove('hidden');
        }
      } else {
        DOM.statePartialDegraded.classList.remove('hidden');
      }

      state.allStores = rawStores;
      state.historyData = historyData;

      // Estado 1: EMPTY se nenhuma loja estiver configurada
      const lastRunTs = currentData.updated_at || currentData.generated_at;
      if (state.allStores.length === 0) {
        setViewState('EMPTY');
        updateLastRunIndicator(lastRunTs);
        return;
      }

      // Atualizar métricas globais consolidadas
      updateMetricsSummary(rawStores, historyData);

      // Atualizar indicador da última execução
      updateLastRunIndicator(lastRunTs);

      // Aplicar filtros e renderizar cartões
      applyFilters();

      if (showFeedback) {
        showToast('Telemetria atualizada com sucesso', 'success');
      }
    } catch (error) {
      console.error('[Sentinel Error]', error);
      if (DOM.errorMessageText) {
        DOM.errorMessageText.textContent =
          error.message || 'Falha de ligação à telemetria GitOps.';
      }
      setViewState('ERROR');
      if (showFeedback) {
        showToast('Erro ao carregar telemetria', 'error');
      }
    } finally {
      state.isLoading = false;
    }
  }

  /**
   * Cálculo e exibição das métricas consolidadas
   */
  function updateMetricsSummary(stores, history) {
    if (!stores.length) return;

    let totalUptime = 0;
    let totalCheckout = 0;
    let totalTtfb = 0;
    let validTtfbCount = 0;
    let activeCriticalCount = 0;

    stores.forEach((store) => {
      const siteHist = history[store.site_id] || {};
      const uptime = siteHist.uptime_pct_30d !== undefined ? siteHist.uptime_pct_30d : 100.0;
      const checkout =
        siteHist.checkout_success_rate_pct !== undefined ? siteHist.checkout_success_rate_pct : 100.0;

      totalUptime += uptime;
      totalCheckout += checkout;

      if (store.edge && typeof store.edge.ttfb_ms === 'number') {
        totalTtfb += store.edge.ttfb_ms;
        validTtfbCount++;
      }

      if (store.health === 'critical') {
        activeCriticalCount++;
      }
    });

    const avgUptime = (totalUptime / stores.length).toFixed(1);
    const avgCheckout = (totalCheckout / stores.length).toFixed(1);
    const avgTtfb = validTtfbCount > 0 ? (totalTtfb / validTtfbCount).toFixed(0) : '--';

    if (DOM.summaryUptime) DOM.summaryUptime.textContent = `${avgUptime}%`;
    if (DOM.summaryCheckout) DOM.summaryCheckout.textContent = `${avgCheckout}%`;
    if (DOM.summaryTtfb) DOM.summaryTtfb.textContent = `${avgTtfb} ms`;
    if (DOM.summaryIncidents) DOM.summaryIncidents.textContent = activeCriticalCount.toString();
  }

  /**
   * Atualização do carimbo de data/hora no cabeçalho
   */
  function updateLastRunIndicator(isoTimestamp) {
    if (!DOM.lastRunText) return;
    if (!isoTimestamp) {
      DOM.lastRunText.textContent = 'Data não disponível';
      return;
    }
    try {
      const date = new Date(isoTimestamp);
      const formatted = date.toLocaleTimeString('pt-PT', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        day: '2-digit',
        month: '2-digit'
      });
      DOM.lastRunText.textContent = `Última ronda: ${formatted}`;
    } catch {
      DOM.lastRunText.textContent = isoTimestamp;
    }
  }

  /**
   * Aplicação dos filtros instantâneos
   */
  function applyFilters() {
    if (!state.allStores.length) {
      setViewState('EMPTY');
      return;
    }

    const { infra, status, search } = state.filters;

    state.filteredStores = state.allStores.filter((store) => {
      // Filtro de infraestrutura
      if (infra !== 'all' && store.infrastructure !== infra) {
        return false;
      }

      // Filtro de estado de saúde
      if (status !== 'all' && store.health !== status) {
        return false;
      }

      // Pesquisa por nome ou URL
      if (search) {
        const nameMatch = store.name.toLowerCase().includes(search);
        const urlMatch = store.url.toLowerCase().includes(search);
        const siteIdMatch = store.site_id.toLowerCase().includes(search);
        if (!nameMatch && !urlMatch && !siteIdMatch) {
          return false;
        }
      }

      return true;
    });

    // Atualizar badge do contador
    if (DOM.storesCountBadge) {
      const total = state.allStores.length;
      const count = state.filteredStores.length;
      DOM.storesCountBadge.textContent =
        count === total ? `${total} lojas` : `${count} de ${total} lojas`;
    }

    // Estado 4: ZERO_RESULTS se filtro não retornar correspondências
    if (state.filteredStores.length === 0) {
      setViewState('ZERO_RESULTS');
    } else {
      setViewState('POPULATED');
      renderStores(state.filteredStores);
    }
  }

  /**
   * Limpar filtros (Ação secundária no estado ZERO_RESULTS)
   */
  function resetFilters() {
    state.filters.infra = 'all';
    state.filters.status = 'all';
    state.filters.search = '';

    if (DOM.filterInfra) DOM.filterInfra.value = 'all';
    if (DOM.filterStatus) DOM.filterStatus.value = 'all';
    if (DOM.searchInput) DOM.searchInput.value = '';

    applyFilters();
    showToast('Filtros repostos', 'success');
  }

  /**
   * Mapeamento de rótulos amigáveis de infraestrutura
   */
  function getInfraLabel(infra) {
    switch (infra) {
      case 'rocket_cloudflare':
        return 'Rocket.net / Cloudflare';
      case 'vps':
        return 'Linux VPS';
      case 'bare_metal':
        return 'Bare-Metal';
      default:
        return infra || 'Desconhecida';
    }
  }

  /**
   * Mapeamento de badge de status de saúde
   */
  function getHealthBadge(health) {
    switch (health) {
      case 'healthy':
        return '<span class="badge badge-healthy">Saudável</span>';
      case 'degraded':
        return '<span class="badge badge-degraded">Degradado</span>';
      case 'critical':
        return '<span class="badge badge-critical">Crítico</span>';
      default:
        return '<span class="badge badge-infra">Desconhecido</span>';
    }
  }

  /**
   * Renderização dos cartões de loja na grelha
   */
  function renderStores(stores) {
    if (!DOM.storesGrid) return;
    DOM.storesGrid.innerHTML = '';

    stores.forEach((store) => {
      const card = document.createElement('article');
      card.className = 'store-card';
      card.setAttribute('data-site-id', store.site_id);

      const siteHist = state.historyData[store.site_id] || {};
      const uptime30d =
        typeof store.uptime_pct_30d === 'number'
          ? `${store.uptime_pct_30d.toFixed(1)}%`
          : siteHist.uptime_pct_30d !== undefined
          ? `${siteHist.uptime_pct_30d.toFixed(1)}%`
          : '--%';
      const checkout30d =
        typeof store.checkout_success_rate_pct === 'number'
          ? `${store.checkout_success_rate_pct.toFixed(1)}%`
          : siteHist.checkout_success_rate_pct !== undefined
          ? `${siteHist.checkout_success_rate_pct.toFixed(1)}%`
          : '--%';

      const ttfbVal =
        typeof store.latest_ttfb_ms === 'number'
          ? `${store.latest_ttfb_ms.toFixed(0)} ms`
          : store.edge && typeof store.edge.ttfb_ms === 'number'
          ? `${store.edge.ttfb_ms.toFixed(0)} ms`
          : '--';

      const sslDays =
        typeof store.ssl_days_remaining === 'number'
          ? `${store.ssl_days_remaining} dias`
          : store.edge && typeof store.edge.ssl_days_remaining === 'number'
          ? `${store.edge.ssl_days_remaining} dias`
          : 'N/A';

      const checkoutStatus = store.checkout_ok ? 'OK' : 'FALHA';
      const checkoutColor = store.checkout_ok ? 'var(--status-success)' : 'var(--status-error)';

      // Geração do minigráfico SVG da série temporal
      const sparklineSvg = generateSparklineSvg(siteHist.points || []);

      const hasIncident = Boolean(store.last_incident || store.incident);

      // Mini-métricas de diagnóstico avançado Tier-S
      const diag = store.diagnostics_summary || {};
      const jsErrCount = diag.js_error_count !== undefined ? diag.js_error_count : (store.last_incident?.js_errors?.length || 0);
      const jsBadge = jsErrCount === 0
        ? `<span class="badge badge-healthy">0 Erros JS</span>`
        : `<span class="badge badge-critical">${jsErrCount} ${jsErrCount === 1 ? 'Erro JS' : 'Erros JS'}</span>`;

      const tbtVal = diag.tbt_ms !== undefined ? diag.tbt_ms : 0;
      const tbtBadge = tbtVal === 0
        ? `<span class="badge badge-healthy">TBT: 0ms</span>`
        : tbtVal < 300
        ? `<span class="badge badge-degraded">TBT: ${tbtVal.toFixed(0)}ms</span>`
        : `<span class="badge badge-critical">TBT: ${tbtVal.toFixed(0)}ms</span>`;

      const cfStatus = diag.cf_cache_status || (store.edge && store.edge.cf_cache_status) || null;
      const cfBadge = cfStatus
        ? `<span class="badge ${cfStatus === 'HIT' ? 'badge-healthy' : 'badge-infra'}">CF: ${escapeHtml(cfStatus)}</span>`
        : '';

      const reqCount = diag.requests_count;
      const bytes = diag.total_transferred_bytes;
      const weightBadge = (reqCount && bytes)
        ? `<span class="badge badge-infra">${(bytes / 1024).toFixed(0)} KB (${reqCount} reqs)</span>`
        : '';

      card.innerHTML = `
        <div class="store-card-header">
          <div class="store-meta">
            <h3 class="store-name">${escapeHtml(store.name)}</h3>
            <a href="${escapeHtml(store.url)}" class="store-url" target="_blank" rel="noopener noreferrer">${escapeHtml(store.url)}</a>
          </div>
          <div>
            ${getHealthBadge(store.health)}
          </div>
        </div>

        <div>
          <span class="badge badge-infra">${escapeHtml(getInfraLabel(store.infrastructure))}</span>
        </div>

        <div class="store-metrics">
          <div class="metric-item">
            <span class="metric-label">TTFB Instantâneo</span>
            <span class="metric-value">${ttfbVal}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">SSL Restante</span>
            <span class="metric-value">${sslDays}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Checkout Sonda</span>
            <span class="metric-value" style="color: ${checkoutColor};">${checkoutStatus}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">Uptime (30d)</span>
            <span class="metric-value">${uptime30d}</span>
          </div>
        </div>

        <div class="history-section">
          <div class="history-header">
            <span>Série Temporal (30 dias)</span>
            <span>Taxa Checkout: ${checkout30d}</span>
          </div>
          ${sparklineSvg}
        </div>

        <div class="store-card-diagnostics">
          ${jsBadge}
          ${tbtBadge}
          ${cfBadge}
          ${weightBadge}
        </div>

        <div class="store-card-footer">
          <span class="card-timestamp">ID: ${escapeHtml(store.site_id)}</span>
          <button class="btn btn-secondary btn-inspect" type="button" data-site-id="${escapeHtml(store.site_id)}">
            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
            <span>Dossiê Forense</span>
          </button>
        </div>
      `;

      // Registo de clique do botão de inspeção
      const btnInspect = card.querySelector('.btn-inspect');
      if (btnInspect) {
        btnInspect.addEventListener('click', () => openForensicModal(store.site_id));
      }

      DOM.storesGrid.appendChild(card);
    });
  }

  /**
   * Geração de minigráfico SVG de série temporal
   */
  function generateSparklineSvg(points) {
    if (!points || points.length === 0) {
      return `
        <svg class="sparkline-svg" viewBox="0 0 240 32" aria-hidden="true">
          <rect width="240" height="32" fill="var(--surface-elevated)" rx="4"></rect>
          <text x="120" y="20" fill="var(--text-muted)" font-size="10" text-anchor="middle" font-family="var(--font-mono)">Sem histórico de rondas</text>
        </svg>
      `;
    }

    // Amostragem dos últimos 30 pontos
    const recent = points.slice(-30);
    const width = 240;
    const height = 32;
    const barWidth = Math.max(3, Math.floor(width / Math.max(recent.length, 1)) - 2);

    let bars = '';
    recent.forEach((pt, index) => {
      const x = index * (barWidth + 2);
      let color = 'var(--status-success)';
      let barH = 24;

      const ptStatus = (pt.status || pt.health || '').toLowerCase();
      const ptCheckout =
        pt.checkout_success !== undefined
          ? pt.checkout_success
          : pt.checkout_ok !== undefined
          ? pt.checkout_ok
          : true;

      if (ptStatus === 'critical' || ptCheckout === false) {
        color = 'var(--status-error)';
        barH = 28;
      } else if (ptStatus === 'degraded') {
        color = 'var(--status-warning)';
        barH = 18;
      } else {
        color = 'var(--status-success)';
        barH = 24;
      }

      const y = height - barH - 2;
      bars += `<rect class="sparkline-bar" x="${x}" y="${y}" width="${barWidth}" height="${barH}" fill="${color}" rx="1"></rect>`;
    });

    return `
      <svg class="sparkline-svg" viewBox="0 0 ${width} ${height}" aria-hidden="true">
        <rect width="${width}" height="${height}" fill="var(--surface-elevated)" rx="4"></rect>
        ${bars}
      </svg>
    `;
  }

  /**
   * Abertura do Modal de Investigação Forense e Dossiê Completo
   */
  async function openForensicModal(siteId) {
    const store = state.allStores.find((s) => s.site_id === siteId);
    if (!store) return;

    state.activeModalSiteId = siteId;

    if (DOM.modalStoreName) {
      DOM.modalStoreName.textContent = `${store.name} — Dossiê Forense`;
    }

    let dossier = null;
    try {
      const res = await fetch(`data/dossiers/${siteId}.json`);
      if (res.ok) {
        dossier = await res.json();
      }
    } catch (err) {
      console.warn('[Sentinel] Dossiê em disco não encontrado:', err);
    }

    // Se o dossiê não existir, tentar fallback para incidente legado
    if (!dossier) {
      let incident = store.last_incident || store.incident;
      if (!incident && (store.health === 'critical' || store.status === 'CRITICAL')) {
        try {
          const res = await fetch(`data/incidents/${siteId}.json`);
          if (res.ok) {
            incident = await res.json();
          }
        } catch (err) {
          console.warn('[Sentinel] Incidente em disco não encontrado:', err);
        }
      }
      if (incident) {
        dossier = {
          site_id: siteId,
          name: store.name,
          url: store.url,
          verdict_pt: incident.verdict_pt || incident.root_cause_verdict,
          failure_phase: incident.failure_phase || incident.step,
          error_code: incident.error_details || incident.error_code || (incident.http_status ? `HTTP ${incident.http_status}` : 'CRITICAL'),
          screenshot_path: incident.screenshot_path,
          raw_js_errors: incident.js_errors || [],
          failed_network_calls: incident.failed_ajax_calls || incident.network_errors || [],
          code_errors: [],
          long_tasks: [],
          slowest_requests: [],
          performance: null,
          edge_diagnostics: store.edge || {}
        };
      }
    }

    // Se ainda for nulo (loja saudável sem incidentes), criar objeto padrão
    if (!dossier) {
      dossier = {
        site_id: siteId,
        name: store.name,
        url: store.url,
        health: store.health || 'healthy',
        checkout_ok: store.checkout_ok !== undefined ? store.checkout_ok : true,
        verdict_pt: store.checkout_ok
          ? 'Sem anomalias ativas registadas. A última ronda de observabilidade concluiu com sucesso todos os passos de verificação de borda e checkout.'
          : 'Anomalia intercetada durante o fluxo sintético de checkout.',
        failure_phase: store.checkout_ok ? 'Nenhum (Fluxo Concluído)' : 'Desconhecido',
        error_code: store.checkout_ok ? 'HEALTHY_200' : 'CRITICAL',
        screenshot_path: null,
        raw_js_errors: [],
        code_errors: [],
        long_tasks: [],
        slowest_requests: [],
        performance: null,
        edge_diagnostics: store.edge || {}
      };
    }

    // 1. Aba Veredito
    if (DOM.modalVerdictText) {
      DOM.modalVerdictText.textContent = dossier.verdict_pt || 'Sem anomalias ativas registadas.';
    }
    if (DOM.modalFailedStep) {
      DOM.modalFailedStep.textContent = dossier.failure_phase || (store.checkout_ok ? 'Nenhum (Fluxo Concluído)' : 'N/A');
    }
    if (DOM.modalErrorCode) {
      DOM.modalErrorCode.textContent = dossier.error_code || (dossier.http_status ? `HTTP ${dossier.http_status}` : (store.checkout_ok ? 'HEALTHY_200' : 'CRITICAL'));
    }
    const edgeDiag = {
      cf_cache_status: dossier.cf_cache_status || dossier.edge_diagnostics?.cf_cache_status || store.diagnostics_summary?.cf_cache_status || store.edge?.cf_cache_status || '--',
      content_encoding: dossier.content_encoding || dossier.edge_diagnostics?.content_encoding || store.edge?.content_encoding || '--',
      http_version: dossier.http_version || dossier.edge_diagnostics?.http_version || store.edge?.http_version || 'HTTP/2',
      server: dossier.server || dossier.edge_diagnostics?.server || store.edge?.server || 'cloudflare',
    };
    if (DOM.modalCfCache) {
      DOM.modalCfCache.textContent = edgeDiag.cf_cache_status;
    }
    if (DOM.modalTtfb) {
      const ttfbNum = typeof dossier.ttfb_ms === 'number'
        ? dossier.ttfb_ms
        : typeof dossier.latest_ttfb_ms === 'number'
        ? dossier.latest_ttfb_ms
        : typeof store.latest_ttfb_ms === 'number'
        ? store.latest_ttfb_ms
        : store.edge?.ttfb_ms;
      DOM.modalTtfb.textContent = typeof ttfbNum === 'number' ? `${ttfbNum.toFixed(0)} ms` : '-- ms';
    }
    if (DOM.modalRecommendationBox && DOM.modalRecommendationText) {
      const rec = dossier.recommendation_pt;
      if (rec) {
        DOM.modalRecommendationText.textContent = rec;
        DOM.modalRecommendationBox.classList.remove('hidden');
      } else if (!store.checkout_ok) {
        DOM.modalRecommendationText.textContent = 'Verifique se regras de cache Cloudflare estão a colocar em cache endpoints dinâmicos ou se há scripts externos a quebrar a execução.';
        DOM.modalRecommendationBox.classList.remove('hidden');
      } else {
        DOM.modalRecommendationBox.classList.add('hidden');
      }
    }

    // 2. Aba Erros de Código (Runtime JS & Exceções)
    const codeErrors = dossier.code_errors || [];
    const rawJs = dossier.console_errors || dossier.raw_js_errors || [];
    const totalJsErrors = codeErrors.length || rawJs.length || dossier.js_error_count || 0;

    if (DOM.modalJsErrorsCount) {
      DOM.modalJsErrorsCount.textContent = `${totalJsErrors} ${totalJsErrors === 1 ? 'erro' : 'erros'}`;
      DOM.modalJsErrorsCount.className = totalJsErrors > 0 ? 'badge badge-critical' : 'badge badge-healthy';
    }

    if (DOM.modalCodeErrorsList) {
      DOM.modalCodeErrorsList.innerHTML = '';
      if (codeErrors.length > 0) {
        codeErrors.forEach((err) => {
          const card = document.createElement('div');
          card.className = 'code-error-card';
          const loc = err.source_file ? `${escapeHtml(err.source_file)}:${err.line_number || '?'}:${err.column_number || '?'}` : 'Origem embutida / inline';
          const stackHtml = err.stack_trace ? `<pre class="code-terminal" style="margin-top: 8px; max-height: 120px;">${escapeHtml(err.stack_trace)}</pre>` : '';
          card.innerHTML = `
            <div class="code-error-header">
              <span class="badge badge-critical">${escapeHtml(err.error_type || 'Exceção JS')}</span>
              <span class="code-error-loc">${loc}</span>
            </div>
            <div class="code-error-msg">${escapeHtml(err.message || 'Erro sem mensagem')}</div>
            ${stackHtml}
          `;
          DOM.modalCodeErrorsList.appendChild(card);
        });
      } else {
        DOM.modalCodeErrorsList.innerHTML = '<p class="state-description" style="margin: 0; color: var(--status-success);">Zero exceções de código JavaScript intercetadas durante a execução da sonda.</p>';
      }
    }

    if (DOM.modalJsErrors) {
      if (rawJs.length > 0) {
        DOM.modalJsErrors.textContent = rawJs
          .map((e) => (typeof e === 'object' ? JSON.stringify(e, null, 2) : String(e)))
          .join('\n\n');
      } else {
        DOM.modalJsErrors.textContent = 'Consola limpa: 0 erros intercetados.';
      }
    }

    // 3. Aba Gargalos & Long Tasks
    const perf = dossier.performance;
    const tbt = perf?.total_blocking_time_ms ?? dossier.tbt_ms ?? 0;
    if (DOM.modalVitalTbt) {
      DOM.modalVitalTbt.textContent = `${tbt.toFixed(0)} ms`;
    }
    if (DOM.modalVitalTbtStatus) {
      DOM.modalVitalTbtStatus.textContent = tbt === 0 ? 'Fluido' : tbt < 300 ? 'Moderado' : 'Bloqueante';
      DOM.modalVitalTbtStatus.className = tbt === 0 ? 'vital-badge badge-healthy' : tbt < 300 ? 'vital-badge badge-degraded' : 'vital-badge badge-critical';
    }
    if (DOM.modalVitalFcp) {
      const fcp = perf?.fcp_ms ?? 0;
      DOM.modalVitalFcp.textContent = fcp > 0 ? `${fcp.toFixed(0)} ms` : '-- ms';
    }
    if (DOM.modalVitalDcl) {
      const dcl = perf?.dom_content_loaded_ms ?? 0;
      DOM.modalVitalDcl.textContent = dcl > 0 ? `${dcl.toFixed(0)} ms` : '-- ms';
    }
    if (DOM.modalVitalLoad) {
      const load = perf?.load_event_ms ?? 0;
      DOM.modalVitalLoad.textContent = load > 0 ? `${load.toFixed(0)} ms` : '-- ms';
    }

    const longTasks = dossier.long_tasks || [];
    const ltCount = longTasks.length || dossier.long_tasks_count || 0;
    if (DOM.modalLongTasksCount) {
      DOM.modalLongTasksCount.textContent = `${ltCount} ${ltCount === 1 ? 'tarefa' : 'tarefas'}`;
      DOM.modalLongTasksCount.className = ltCount > 0 ? 'badge badge-degraded' : 'badge badge-healthy';
    }

    if (DOM.modalLongTasksList) {
      DOM.modalLongTasksList.innerHTML = '';
      if (longTasks.length > 0) {
        longTasks.forEach((lt) => {
          const item = document.createElement('div');
          item.className = 'long-task-item';
          item.innerHTML = `
            <div>
              <span class="badge badge-degraded">${lt.duration_ms.toFixed(0)} ms</span>
              <span style="margin-left: 8px; font-weight: 500;">${escapeHtml(lt.name || 'Tarefa longa na main thread')}</span>
            </div>
            <span class="code-error-loc">Início: ${lt.start_time_ms.toFixed(0)} ms</span>
          `;
          DOM.modalLongTasksList.appendChild(item);
        });
      } else {
        DOM.modalLongTasksList.innerHTML = '<p class="state-description" style="margin: 0; color: var(--status-success);">Nenhum congelamento superior a 50ms detetado na thread principal.</p>';
      }
    }

    if (DOM.modalWeightTotal) {
      DOM.modalWeightTotal.textContent = perf ? `${(perf.total_transferred_bytes / 1024).toFixed(1)} KB` : '0 KB';
    }
    if (DOM.modalWeightJs) {
      DOM.modalWeightJs.textContent = perf ? `${(perf.js_bytes / 1024).toFixed(1)} KB` : '0 KB';
    }
    if (DOM.modalWeightCss) {
      DOM.modalWeightCss.textContent = perf ? `${(perf.css_bytes / 1024).toFixed(1)} KB` : '0 KB';
    }
    if (DOM.modalWeightImg) {
      DOM.modalWeightImg.textContent = perf ? `${(perf.img_bytes / 1024).toFixed(1)} KB` : '0 KB';
    }
    if (DOM.modalWeightRequests) {
      DOM.modalWeightRequests.textContent = perf ? String(perf.requests_count) : '0';
    }

    // 4. Aba Rede & Waterfall
    if (DOM.modalNetCache) DOM.modalNetCache.textContent = edgeDiag.cf_cache_status || '--';
    if (DOM.modalNetEncoding) DOM.modalNetEncoding.textContent = edgeDiag.content_encoding || '--';
    if (DOM.modalNetProtocol) DOM.modalNetProtocol.textContent = edgeDiag.http_version || 'HTTP/2';
    if (DOM.modalNetServer) DOM.modalNetServer.textContent = edgeDiag.server || 'cloudflare';

    const slowest = dossier.slowest_requests || [];
    if (DOM.modalSlowestTbody) {
      DOM.modalSlowestTbody.innerHTML = '';
      if (slowest.length > 0) {
        slowest.forEach((r) => {
          const row = document.createElement('tr');
          const cacheBadge = r.cache_status === 'HIT'
            ? `<span class="badge badge-healthy">HIT</span>`
            : r.cache_status
            ? `<span class="badge badge-infra">${escapeHtml(r.cache_status)}</span>`
            : `<span class="badge badge-infra">--</span>`;
          row.innerHTML = `
            <td><span class="badge badge-infra">${escapeHtml(r.method || 'GET')}</span></td>
            <td style="word-break: break-all; max-width: 320px;">${escapeHtml(r.url)}</td>
            <td><strong>${r.duration_ms.toFixed(0)} ms</strong></td>
            <td><span class="badge badge-infra">${escapeHtml(r.resource_type || '--')}</span></td>
            <td>${cacheBadge}</td>
          `;
          DOM.modalSlowestTbody.appendChild(row);
        });
      } else {
        DOM.modalSlowestTbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-muted);">Nenhuma requisição registada na sonda.</td></tr>';
      }
    }

    const failedNet = dossier.failed_requests || dossier.failed_network_calls || [];
    if (DOM.modalNetworkTbody) {
      DOM.modalNetworkTbody.innerHTML = '';
      if (failedNet.length > 0) {
        failedNet.forEach((net) => {
          const row = document.createElement('tr');
          const reason = net.failure_reason || (net.status ? `HTTP ${net.status}` : 'Falha');
          row.innerHTML = `
            <td><span class="badge badge-infra">${escapeHtml(net.method || 'GET')}</span></td>
            <td style="word-break: break-all;">${escapeHtml(net.url || '--')}</td>
            <td><span class="badge badge-critical">${escapeHtml(String(net.status || 'ERR'))}</span></td>
            <td>${escapeHtml(reason)}</td>
          `;
          DOM.modalNetworkTbody.appendChild(row);
        });
      } else {
        DOM.modalNetworkTbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">Todas as chamadas responderam com código HTTP &lt; 400.</td></tr>';
      }
    }

    // 5. Aba Captura Forense
    if (dossier.screenshot_path) {
      const cleanPath = dossier.screenshot_path.replace(/^public[/\\]/, '');
      DOM.modalScreenshotImg.src = cleanPath;
      DOM.modalScreenshotImg.classList.remove('hidden');
      DOM.modalScreenshotEmpty.classList.add('hidden');
    } else {
      DOM.modalScreenshotImg.src = '';
      DOM.modalScreenshotImg.classList.add('hidden');
      DOM.modalScreenshotEmpty.classList.remove('hidden');
    }

    if (DOM.modalDomExtract) {
      DOM.modalDomExtract.textContent = dossier.dom_extract || 'Nenhum extrato DOM disponível.';
    }

    // Reset para a primeira aba (Veredito)
    const firstTabBtn = document.getElementById('tab-btn-verdict');
    if (firstTabBtn) {
      switchModalTab(firstTabBtn, 'pane-verdict');
    }

    // Exibir modal
    DOM.forensicModal.classList.remove('hidden');
    DOM.btnCloseModal.focus();
  }

  /**
   * Fecho do Modal Forense (Idempotente / Cancel is no-op)
   */
  function closeForensicModal() {
    if (!DOM.forensicModal) return;
    DOM.forensicModal.classList.add('hidden');
    state.activeModalSiteId = null;

    // Devolver foco para o elemento desencadeador
    if (DOM.btnRefresh) {
      DOM.btnRefresh.focus();
    }
  }

  /**
   * Alternância de abas no modal forense
   */
  function switchModalTab(clickedBtn, targetPaneId) {
    DOM.tabBtns.forEach((btn) => {
      btn.classList.remove('active');
      btn.setAttribute('aria-selected', 'false');
    });
    DOM.tabPanes.forEach((pane) => pane.classList.remove('active'));

    clickedBtn.classList.add('active');
    clickedBtn.setAttribute('aria-selected', 'true');

    const targetPane = document.getElementById(targetPaneId);
    if (targetPane) {
      targetPane.classList.add('active');
    }
  }

  /**
   * Apresentação de Toast de Notificação (Estado 7: SUCCESS_FEEDBACK)
   */
  function showToast(message, type = 'success') {
    if (!DOM.toastContainer) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.setAttribute('role', 'status');

    const iconSvg =
      type === 'success'
        ? `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>`
        : `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;

    toast.innerHTML = `
      ${iconSvg}
      <span>${escapeHtml(message)}</span>
    `;

    DOM.toastContainer.appendChild(toast);

    // Auto-dismiss em 3500ms
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      toast.style.transition = 'opacity 0.2s ease, transform 0.2s ease';
      setTimeout(() => {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 200);
    }, 3500);
  }

  /**
   * Sanitização contra injeção de HTML
   */
  function escapeHtml(str) {
    if (typeof str !== 'string') return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Expor para testes automatizados
  if (typeof window !== 'undefined') {
    window.SentinelApp = {
      state,
      initDashboard,
      applyFilters,
      resetFilters,
      openForensicModal,
      closeForensicModal,
      showToast,
      setViewState
    };
  }

  // Auto-arranque no browser
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initDashboard);
    } else {
      initDashboard();
    }
  }
})();

