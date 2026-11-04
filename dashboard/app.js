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
    modalScreenshotImg: document.getElementById('modal-screenshot-img'),
    modalScreenshotEmpty: document.getElementById('modal-screenshot-empty'),
    modalJsErrors: document.getElementById('modal-js-errors'),
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
      const rawStores = currentData.stores || [];

      // Tratamento do histórico (falha não-bloqueante -> PARTIAL_DEGRADED)
      let historyData = {};
      if (historyRes.status === 'fulfilled' && historyRes.value.ok) {
        try {
          const histPayload = await historyRes.value.json();
          historyData = histPayload.history || {};
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
      if (state.allStores.length === 0) {
        setViewState('EMPTY');
        updateLastRunIndicator(currentData.generated_at);
        return;
      }

      // Atualizar métricas globais consolidadas
      updateMetricsSummary(rawStores, historyData);

      // Atualizar indicador da última execução
      updateLastRunIndicator(currentData.generated_at);

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
        siteHist.uptime_pct_30d !== undefined ? `${siteHist.uptime_pct_30d.toFixed(1)}%` : '--%';
      const checkout30d =
        siteHist.checkout_success_rate_pct !== undefined
          ? `${siteHist.checkout_success_rate_pct.toFixed(1)}%`
          : '--%';

      const ttfbVal =
        store.edge && typeof store.edge.ttfb_ms === 'number' ? `${store.edge.ttfb_ms} ms` : '--';

      const sslDays =
        store.edge && typeof store.edge.ssl_days_remaining === 'number'
          ? `${store.edge.ssl_days_remaining} dias`
          : 'N/A';

      const checkoutStatus = store.checkout_ok ? 'OK' : 'FALHA';
      const checkoutColor = store.checkout_ok ? 'var(--status-success)' : 'var(--status-error)';

      // Geração do minigráfico SVG da série temporal
      const sparklineSvg = generateSparklineSvg(siteHist.points || []);

      const hasIncident = Boolean(store.incident);

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
            <span>${hasIncident ? 'Dossiê Forense' : 'Inspecionar'}</span>
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

      if (pt.health === 'critical' || !pt.checkout_ok) {
        color = 'var(--status-error)';
        barH = 28;
      } else if (pt.health === 'degraded') {
        color = 'var(--status-warning)';
        barH = 18;
      } else {
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
   * Abertura do Modal de Investigação Forense
   */
  async function openForensicModal(siteId) {
    const store = state.allStores.find((s) => s.site_id === siteId);
    if (!store) return;

    state.activeModalSiteId = siteId;

    if (DOM.modalStoreName) {
      DOM.modalStoreName.textContent = `${store.name} — Investigação Forense`;
    }

    let incident = store.incident;

    // Se o incidente não estiver embutido no status, tentar carregar ficheiro individual
    if (!incident && store.health === 'critical') {
      try {
        const res = await fetch(`data/incidents/${siteId}.json`);
        if (res.ok) {
          incident = await res.json();
        }
      } catch (err) {
        console.warn('[Sentinel] Incidente em disco não encontrado:', err);
      }
    }

    // Preenchimento dos dados do modal
    if (incident) {
      DOM.modalVerdictText.textContent =
        incident.root_cause_verdict || 'Anomalia intercetada durante o fluxo de checkout.';
      DOM.modalFailedStep.textContent = incident.step || 'N/A';
      DOM.modalErrorCode.textContent = incident.error_code || 'N/A';

      // Screenshot forense
      if (incident.screenshot_path) {
        // Ajustar caminho relativo de screenshots para o frontend
        const cleanPath = incident.screenshot_path.replace(/^public[/\\]/, '');
        DOM.modalScreenshotImg.src = cleanPath;
        DOM.modalScreenshotImg.classList.remove('hidden');
        DOM.modalScreenshotEmpty.classList.add('hidden');
      } else {
        DOM.modalScreenshotImg.src = '';
        DOM.modalScreenshotImg.classList.add('hidden');
        DOM.modalScreenshotEmpty.classList.remove('hidden');
      }

      // Erros de consola JavaScript
      if (incident.js_errors && incident.js_errors.length > 0) {
        DOM.modalJsErrors.textContent = incident.js_errors.join('\n\n');
      } else {
        DOM.modalJsErrors.textContent = 'Nenhum erro de consola JavaScript intercetado.';
      }

      // Tabela de requisições AJAX com falha
      if (incident.network_errors && incident.network_errors.length > 0) {
        DOM.modalNetworkTbody.innerHTML = '';
        incident.network_errors.forEach((net) => {
          const row = document.createElement('tr');
          row.innerHTML = `
            <td><span class="badge badge-infra">${escapeHtml(net.method || 'GET')}</span></td>
            <td style="word-break: break-all;">${escapeHtml(net.url || '--')}</td>
            <td><span class="badge badge-critical">${escapeHtml(String(net.status || 'ERR'))}</span></td>
            <td>${escapeHtml(net.failure_reason || '--')}</td>
          `;
          DOM.modalNetworkTbody.appendChild(row);
        });
      } else {
        DOM.modalNetworkTbody.innerHTML = `
          <tr>
            <td colspan="4" style="text-align: center; color: var(--text-muted);">Nenhuma chamada AJAX com falha intercetada.</td>
          </tr>
        `;
      }
    } else {
      // Estado sem incidentes para lojas saudáveis
      DOM.modalVerdictText.textContent =
        'Sem anomalias ativas registadas. A última ronda de observabilidade concluiu com sucesso todos os passos de verificação de borda e checkout.';
      DOM.modalFailedStep.textContent = 'Nenhum (Fluxo Concluído)';
      DOM.modalErrorCode.textContent = 'HEALTHY_200';
      DOM.modalScreenshotImg.src = '';
      DOM.modalScreenshotImg.classList.add('hidden');
      DOM.modalScreenshotEmpty.classList.remove('hidden');
      DOM.modalJsErrors.textContent = 'Consola limpa: 0 erros intercetados.';
      DOM.modalNetworkTbody.innerHTML = `
        <tr>
          <td colspan="4" style="text-align: center; color: var(--text-muted);">Todas as chamadas WooCommerce responderam com código HTTP &lt; 400.</td>
        </tr>
      `;
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

