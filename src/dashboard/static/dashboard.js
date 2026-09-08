/**
 * MEME RADAR AI — REAL-TIME DASHBOARD CONTROLLER
 * Design Standard: Stakent (Awsmd) Institutional Crypto Terminal
 * Strict rule: No emojis. Vector SVGs, refined typography and micro-interactions.
 */

// Global State
let currentAlerts = [];
let currentFilter = 'all';
let audioEnabled = true;
let ws = null;
let reconnectTimer = null;
let audioContext = null;

// SVG Icons Cache for dynamic rendering
const ICONS = {
  check: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`,
  x: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  alertTriangle: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
  shieldCheck: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>`,
  externalLink: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`,
  zap: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
  pill: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z"/><path d="m8.5 8.5 7 7"/></svg>`
};

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
  initWebSocket();
  fetchAllData();
  setupEventListeners();

  // Polling fallback cada 12 segundos para estadísticas y estado
  setInterval(() => {
    fetchStats();
    fetchStatus();
  }, 12000);
});

function setupEventListeners() {
  const verifyInput = document.getElementById('verify-input');
  if (verifyInput) {
    verifyInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        const val = verifyInput.value.trim();
        if (val) triggerVerify(val);
      }
    });
  }
}

// ============================================================================
// AUDIO SYNTHESIS (Clean Financial Terminal Chime)
// ============================================================================

function playTerminalChime() {
  if (!audioEnabled) return;
  try {
    if (!audioContext) {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }
    const osc = audioContext.createOscillator();
    const gain = audioContext.createGain();
    
    osc.type = 'sine';
    // Acorde agradable de dos tonos limpios
    osc.frequency.setValueAtTime(880, audioContext.currentTime); // A5
    osc.frequency.exponentialRampToValueAtTime(1320, audioContext.currentTime + 0.12); // E6
    
    gain.gain.setValueAtTime(0.08, audioContext.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.35);
    
    osc.connect(gain);
    gain.connect(audioContext.destination);
    
    osc.start();
    osc.stop(audioContext.currentTime + 0.35);
  } catch (err) {
    // Audio context may be restricted by browser policy before user interaction
  }
}

function toggleAudio() {
  audioEnabled = !audioEnabled;
  const btn = document.getElementById('audio-toggle-btn');
  const icon = document.getElementById('audio-icon');
  
  if (audioEnabled) {
    btn.classList.add('active');
    icon.innerHTML = `<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>`;
  } else {
    btn.classList.remove('active');
    icon.innerHTML = `<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/>`;
  }
}

// ============================================================================
// WEBSOCKET CLIENT
// ============================================================================

function initWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  const wsIndicator = document.getElementById('ws-indicator');
  const wsLabel = document.getElementById('ws-label');

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      if (wsIndicator) wsIndicator.classList.add('chip-status-live');
      if (wsLabel) wsLabel.textContent = 'Live Stream';
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        handleIncomingMessage(payload);
      } catch (e) {
        console.error('Error parseando WebSocket payload:', e);
      }
    };

    ws.onclose = () => {
      if (wsIndicator) wsIndicator.classList.remove('chip-status-live');
      if (wsLabel) wsLabel.textContent = 'Reconectando...';
      scheduleReconnect();
    };

    ws.onerror = () => {
      ws.close();
    };
  } catch (err) {
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (!reconnectTimer) {
    reconnectTimer = setTimeout(() => {
      initWebSocket();
    }, 3500);
  }
}

function handleIncomingMessage(data) {
  if (data.type === 'new_alert') {
    playTerminalChime();
    prependAlert(data.alert);
    fetchStats();
  } else if (data.type === 'feedback_applied') {
    updateAlertFeedbackUI(data.alert_id, data.outcome);
  }
}

// ============================================================================
// DATA FETCHING (REST APIS)
// ============================================================================

async function fetchAllData() {
  await Promise.all([
    fetchStatus(),
    fetchStats(),
    fetchAlerts(),
    fetchWeights(),
    fetchTokens(),
    fetchWallets()
  ]);
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    
    if (data.threshold_score) {
      document.getElementById('threshold-display').textContent = `Umbral: ${data.threshold_score}/100`;
    }
  } catch (err) {
    console.error('Error cargando status:', err);
  }
}

async function fetchStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    if (!data.success) return;

    const t = data.today || {};
    const w = data.weekly || {};

    // Precisión acumulada — usar weekly si tiene datos evaluados, sino today
    const evaluated = (w.tp || 0) + (w.fp || 0) + (w.partial || 0);
    const todayEval = (t.tp || 0) + (t.fp || 0) + (t.partial || 0);

    if (evaluated > 0) {
      document.getElementById('kpi-accuracy').textContent = `${w.accuracy.toFixed(1)}%`;
      document.getElementById('kpi-tp-fp-badge').textContent = `${w.tp || 0} TP / ${w.fp || 0} FP`;
    } else if (todayEval > 0) {
      document.getElementById('kpi-accuracy').textContent = `${t.accuracy.toFixed(1)}%`;
      document.getElementById('kpi-tp-fp-badge').textContent = `${t.tp || 0} TP / ${t.fp || 0} FP`;
    } else {
      document.getElementById('kpi-accuracy').textContent = `--`;
      document.getElementById('kpi-tp-fp-badge').textContent = `${(w.tp||0)+(t.tp||0)} TP / ${(w.fp||0)+(t.fp||0)} FP`;
    }

    // Alertas Hoy
    document.getElementById('kpi-total-today').textContent = t.total || 0;
    document.getElementById('kpi-pending-badge').textContent = `${t.pending || 0} pendientes`;

    // PnL Promedio
    const pnlList = (t.pnl_list || []).concat(w.pnl_list || []);
    const uniquePnl = [...new Set(pnlList)];
    if (uniquePnl.length > 0) {
      const avg = uniquePnl.reduce((a, b) => a + b, 0) / uniquePnl.length;
      const max = Math.max(...uniquePnl);
      document.getElementById('kpi-pnl-avg').textContent = `${avg >= 0 ? '+' : ''}${avg.toFixed(1)}%`;
      document.getElementById('kpi-pnl-max').textContent = `Máx: ${max >= 0 ? '+' : ''}${max.toFixed(1)}%`;
    }
  } catch (err) {
    console.error('Error cargando stats:', err);
  }
}

async function fetchAlerts() {
  try {
    const res = await fetch('/api/alerts?limit=40');
    const data = await res.json();
    if (data.success && Array.isArray(data.alerts)) {
      currentAlerts = data.alerts;
      renderAlerts();
    }
  } catch (err) {
    console.error('Error cargando alerts:', err);
  }
}

async function fetchWeights() {
  try {
    const res = await fetch('/api/weights');
    const data = await res.json();
    if (data.success && data.weights) {
      render5LayersWeights(data.weights.layer_weights || {});
      renderTraderLeaderboard(data.weights.trader_weights || {});
    }
  } catch (err) {
    console.error('Error cargando pesos:', err);
  }
}

async function fetchTokens() {
  try {
    const res = await fetch('/api/tokens');
    const data = await res.json();
    if (data.success && Array.isArray(data.tokens)) {
      renderTokensTable(data.tokens);
    }
  } catch (err) {
    console.error('Error cargando tokens descubiertos:', err);
  }
}

async function fetchWallets() {
  try {
    const res = await fetch('/api/wallets');
    const data = await res.json();
    if (data.success && Array.isArray(data.wallets)) {
      renderWalletsStream(data.wallets);
    }
  } catch (err) {
    console.error('Error cargando wallets:', err);
  }
}

// ============================================================================
// RENDERING FUNCTIONS
// ============================================================================

function filterAlerts(type, btnElem) {
  currentFilter = type;
  document.querySelectorAll('.filter-tabs .tab-btn').forEach(b => b.classList.remove('active'));
  if (btnElem) btnElem.classList.add('active');
  renderAlerts();
}

function renderAlerts() {
  const container = document.getElementById('alerts-container');
  if (!container) return;

  const filtered = currentAlerts.filter(a => {
    if (currentFilter === 'all') return true;
    const st = a.signal_type || a.type || '';
    return st.toLowerCase() === currentFilter.toLowerCase();
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 48px; color: var(--text-muted); font-size: 13px;">
        Sin alertas registradas para este filtro en los últimos 7 días.
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map(a => createAlertCardHtml(a)).join('');
}

function prependAlert(alert) {
  currentAlerts.unshift(alert);
  renderAlerts();
}

function createAlertCardHtml(alert) {
  const symbol = alert.token || 'UNKNOWN';
  const score = alert.score || 0;
  const signalType = (alert.signal_type || alert.type || 'CONVERGENCE').toUpperCase();
  const layers = alert.layers || [];
  const metrics = alert.metrics_at_alert || {};
  const mc = metrics.market_cap || 'N/A';
  const liq = metrics.liquidity || 'N/A';
  const vol = metrics.volume_5m || 'N/A';
  const mint = alert.mint || '';
  const outcome = alert.outcome;
  const id = alert.id;
  const traders = alert.traders_involved || [];
  const tradersStr = traders.length > 0 ? traders.join(', ') : 'Análisis Algorítmico';

  const scoreClass = score >= 75 ? 'score-high' : 'score-mid';

  // Audit
  const audit = alert.audit || {};
  const isSafe = audit.risk === 'Good' || audit.risk === 'Low' || audit.honeypot === false;
  const auditTag = isSafe ? 
    `<span class="audit-safe">${ICONS.shieldCheck} Antirug Verificado</span>` : 
    `<span style="color: var(--amber);">${ICONS.alertTriangle} Auditoría Estándar</span>`;

  // 1-Click Execution links
  const bullxUrl = mint ? `https://bullx.io/terminal?chainId=1399811149&address=${mint}` : `https://bullx.io`;
  const photonUrl = mint ? `https://photon-sol.tinyastro.io/en/lp/${mint}` : `https://photon-sol.tinyastro.io`;
  const pumpUrl = mint.endsWith('pump') ? `https://pump.fun/coin/${mint}` : null;
  const dexUrl = mint ? `https://dexscreener.com/solana/${mint}` : `https://dexscreener.com/search?q=${symbol}`;

  // Outcome label badge
  let outcomeBadge = '';
  if (outcome === 'true_positive') {
    outcomeBadge = `<span style="font-size: 11px; font-family: var(--font-mono); color: var(--mint); background: rgba(0,245,160,0.1); padding: 3px 8px; border-radius: 4px;">Acertó (TP)</span>`;
  } else if (outcome === 'false_positive') {
    outcomeBadge = `<span style="font-size: 11px; font-family: var(--font-mono); color: var(--rose); background: rgba(248,113,113,0.1); padding: 3px 8px; border-radius: 4px;">Falló (FP)</span>`;
  } else if (outcome === 'partial') {
    outcomeBadge = `<span style="font-size: 11px; font-family: var(--font-mono); color: var(--amber); background: rgba(251,191,36,0.1); padding: 3px 8px; border-radius: 4px;">Parcial</span>`;
  }

  return `
    <div class="alert-card" id="card-${id}">
      <div class="alert-top">
        <div class="token-identity">
          <div class="token-avatar">${symbol.slice(0, 2).toUpperCase()}</div>
          <div class="token-name-group">
            <h4>$${symbol} <span style="font-size: 11px; color: var(--text-muted); font-weight: 500;">(${signalType})</span></h4>
            <span>${tradersStr}</span>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          ${outcomeBadge}
          <div class="score-badge ${scoreClass}">
            <span>${score}</span>
            <span style="font-size: 10px; opacity: 0.7;">/100</span>
          </div>
        </div>
      </div>

      <!-- 5 Layers Participating -->
      <div class="layers-pill-row">
        ${layers.map(l => {
          const isPump = l.toLowerCase().includes('pump');
          return `<span class="layer-badge ${isPump ? 'active-pump' : 'active'}">${l}</span>`;
        }).join('')}
      </div>

      <!-- Key Metrics Box -->
      <div class="metrics-pill-row">
        <div class="metric-item">
          <span class="metric-label">Market Cap</span>
          <span class="metric-val">${mc}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">Liquidez</span>
          <span class="metric-val">${liq}</span>
        </div>
        <div class="metric-item">
          <span class="metric-label">Volumen 5m</span>
          <span class="metric-val">${vol}</span>
        </div>
      </div>

      <!-- Audit and 1-Click Execution Action Buttons -->
      <div class="alert-actions-row">
        <div class="audit-chip-row">
          ${auditTag}
        </div>

        <div class="execution-btns">
          <a href="${bullxUrl}" target="_blank" rel="noopener noreferrer" class="btn-exec btn-bullx" title="Operar en BullX Terminal">
            ${ICONS.zap} BullX
          </a>
          <a href="${photonUrl}" target="_blank" rel="noopener noreferrer" class="btn-exec btn-photon" title="Operar en Photon LP">
            ${ICONS.externalLink} Photon
          </a>
          ${pumpUrl ? `
          <a href="${pumpUrl}" target="_blank" rel="noopener noreferrer" class="btn-exec btn-pump" title="Ver en Pump.fun">
            ${ICONS.pill} Pump
          </a>` : ''}
          <a href="${dexUrl}" target="_blank" rel="noopener noreferrer" class="btn-exec" title="Ver gráfica en DexScreener">
            ${ICONS.externalLink} Dex
          </a>
        </div>

        <div class="feedback-btns">
          <button class="btn-feedback tp" onclick="sendFeedback('${id}', 'true_positive', this)" title="Calificar como Acertó">
            ${ICONS.check} TP
          </button>
          <button class="btn-feedback fp" onclick="sendFeedback('${id}', 'false_positive', this)" title="Calificar como Falso Positivo">
            ${ICONS.x} FP
          </button>
        </div>
      </div>
    </div>
  `;
}

// ============================================================================
// 5 LAYERS PROGRESS BARS (STAKENT STYLE)
// ============================================================================

function render5LayersWeights(layerWeights) {
  const container = document.getElementById('layers-stack-container');
  if (!container) return;

  const defaultLayers = [
    { key: 'X', label: 'Capa X (Twitter Buzz)', colorClass: 'fill-cyan', max: 40 },
    { key: 'FOMO', label: 'Capa FOMO (Smart Flow)', colorClass: 'fill-mint', max: 40 },
    { key: 'Pump.fun', label: 'Capa Pump.fun (Curva)', colorClass: 'fill-violet', max: 40 },
    { key: 'DexScreener', label: 'Capa DexScreener (Liq)', colorClass: 'fill-amber', max: 40 },
    { key: 'Seguridad', label: 'Capa Seguridad (RugCheck)', colorClass: 'fill-slate', max: 40 }
  ];

  container.innerHTML = defaultLayers.map(dl => {
    const val = layerWeights[dl.key] || 20;
    const pct = Math.min(100, Math.round((val / dl.max) * 100));
    return `
      <div class="layer-progress-item">
        <div class="layer-progress-header">
          <span class="layer-name">${dl.label}</span>
          <span class="layer-weight-val">${val} pts</span>
        </div>
        <div class="progress-track">
          <div class="progress-fill ${dl.colorClass}" style="width: ${pct}%;"></div>
        </div>
      </div>
    `;
  }).join('');
}

// ============================================================================
// TRADER LEADERBOARD & COPYTRADE STREAM
// ============================================================================

function renderTraderLeaderboard(traderWeights) {
  const container = document.getElementById('traders-leaderboard');
  if (!container) return;

  const sorted = Object.entries(traderWeights).sort((a, b) => b[1] - a[1]).slice(0, 5);

  if (sorted.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); font-size: 12px;">Sin datos aún</div>`;
    return;
  }

  container.innerHTML = sorted.map(([handle, weight], idx) => {
    const rankClass = idx === 0 ? 'rank-1' : (idx === 1 ? 'rank-2' : (idx === 2 ? 'rank-3' : ''));
    return `
      <div class="trader-rank-item">
        <div class="trader-info">
          <span class="rank-badge ${rankClass}">${idx + 1}</span>
          <span class="trader-name">@${handle}</span>
        </div>
        <span class="trader-winrate">${weight} pts</span>
      </div>
    `;
  }).join('');
}

function renderWalletsStream(wallets) {
  const container = document.getElementById('wallets-tx-container');
  if (!container) return;

  if (wallets.length === 0) {
    container.innerHTML = `<div style="color: var(--text-muted); font-size: 12px; padding: 12px;">Cargando wallets monitoreadas...</div>`;
    return;
  }

  container.innerHTML = wallets.slice(0, 5).map(w => {
    const addr = w.address || '';
    const short = addr ? `${addr.slice(0, 4)}...${addr.slice(-4)}` : '';
    const solscanUrl = addr ? `https://solscan.io/account/${addr}` : '#';
    return `
      <div class="wallet-tx-item">
        <div class="tx-main-desc">
          <span class="tx-trader">@${w.handle} (${w.alias})</span>
          <a href="${solscanUrl}" target="_blank" rel="noopener noreferrer" class="tx-action" style="text-decoration: none;">
            ${short} ${ICONS.externalLink}
          </a>
        </div>
        <span class="tx-amount">${w.weight} pts</span>
      </div>
    `;
  }).join('');
}

// ============================================================================
// DISCOVERED TOKENS TABLE
// ============================================================================

function renderTokensTable(tokens) {
  const tbody = document.getElementById('tokens-table-body');
  const countLabel = document.getElementById('tokens-count-label');
  if (!tbody) return;

  if (countLabel) countLabel.textContent = `${tokens.length} tokens descubiertos`;

  if (tokens.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 32px;">
          No hay tokens descubiertos registrados aún.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = tokens.slice(0, 25).map(t => {
    const sym = t.symbol || 'TOKEN';
    const traders = Array.isArray(t.traders) ? t.traders.join(', ') : (t.traders || 'Smart Money');
    const firstSeen = t.first_seen ? t.first_seen.slice(11, 16) : 'N/A';
    const dexUrl = `https://dexscreener.com/search?q=${sym}`;
    return `
      <tr>
        <td>
          <div class="token-cell">
            <div class="token-avatar" style="width: 26px; height: 26px; font-size: 10px;">${sym.slice(0, 2).toUpperCase()}</div>
            <span class="token-cell-symbol">$${sym}</span>
          </div>
        </td>
        <td class="mono-cell">${traders}</td>
        <td class="mono-cell">${t.mention_count || 1}x</td>
        <td class="mono-cell">${t.market_cap || 'N/A'}</td>
        <td class="mono-cell">${t.liquidity || 'N/A'}</td>
        <td class="mono-cell">${t.volume_5m || 'N/A'}</td>
        <td class="mono-cell">${firstSeen}</td>
        <td>
          <a href="${dexUrl}" target="_blank" rel="noopener noreferrer" class="btn-exec" style="padding: 3px 8px; font-size: 10.5px;">
            ${ICONS.externalLink} Dex
          </a>
        </td>
      </tr>
    `;
  }).join('');
}

// ============================================================================
// FEEDBACK & RADIOGRAPHY MODAL
// ============================================================================

async function sendFeedback(alertId, outcome, btnElem) {
  try {
    const res = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ alert_id: alertId, outcome: outcome })
    });
    const data = await res.json();
    if (data.success) {
      updateAlertFeedbackUI(alertId, outcome);
    }
  } catch (err) {
    console.error('Error enviando feedback:', err);
  }
}

function updateAlertFeedbackUI(alertId, outcome) {
  const card = document.getElementById(`card-${alertId}`);
  if (!card) return;
  const btns = card.querySelector('.feedback-btns');
  if (btns) {
    const label = outcome === 'true_positive' ? 'Acertó' : (outcome === 'false_positive' ? 'Falló' : 'Parcial');
    const color = outcome === 'true_positive' ? 'var(--mint)' : (outcome === 'false_positive' ? 'var(--rose)' : 'var(--amber)');
    btns.innerHTML = `<span style="font-size: 11px; font-family: var(--font-mono); color: ${color}; font-weight: 600;">Feedback: ${label}</span>`;
  }
}

async function triggerVerify(query) {
  const modal = document.getElementById('verify-modal');
  const title = document.getElementById('modal-title');
  const content = document.getElementById('modal-content');
  
  if (!modal || !content) return;
  
  modal.style.display = 'flex';
  title.textContent = `Radiografía // $${query.toUpperCase()}`;
  content.innerHTML = `<div style="text-align: center; padding: 24px; color: var(--text-muted);">Consultando DexScreener, Pump.fun y Smart Money...</div>`;

  try {
    const res = await fetch('/api/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    const data = await res.json();
    if (!data.success || !data.result) {
      content.innerHTML = `<div style="color: var(--rose);">Error al verificar token.</div>`;
      return;
    }

    const r = data.result;
    const m = r.market || {};
    const b = r.bonding_curve || {};
    const c = r.cope || {};

    content.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 10px;">
        <div style="background: rgba(255,255,255,0.03); padding: 12px; border-radius: 8px;">
          <div style="font-weight: 600; color: var(--text-white); margin-bottom: 6px;">Métricas On-Chain</div>
          <div>Market Cap: <b style="color: var(--text-white);">${m.market_cap || 'N/A'}</b> | Liquidez: <b style="color: var(--text-white);">${m.liquidity || 'N/A'}</b></div>
          <div>Precio: <b style="color: var(--text-white);">${m.price_usd || 'N/A'}</b> | Vol 5m: <b style="color: var(--text-white);">${m.volume_5m || 'N/A'}</b></div>
        </div>

        ${b.progress_pct ? `
        <div style="background: rgba(124,58,237,0.08); border: 1px solid rgba(124,58,237,0.25); padding: 12px; border-radius: 8px;">
          <div style="font-weight: 600; color: var(--violet); margin-bottom: 4px;">Curva Pump.fun (three.ws)</div>
          <div>Progreso: <b style="color: var(--text-white);">${b.progress_pct}%</b> | SOL en curva: <b style="color: var(--text-white);">${b.sol_in_curve} SOL</b></div>
        </div>
        ` : ''}

        <div style="background: rgba(0,245,160,0.06); border: 1px solid rgba(0,245,160,0.2); padding: 12px; border-radius: 8px;">
          <div style="font-weight: 600; color: var(--mint); margin-bottom: 4px;">Smart Money / Cope API</div>
          <div>${c.verified ? `Holders Élite: <b style="color: var(--text-white);">${c.smart_money_holders}</b> (Convicción: ${c.conviction_label})` : (c.reason || 'Sin datos adicionales')}</div>
        </div>
      </div>
    `;
  } catch (err) {
    content.innerHTML = `<div style="color: var(--rose);">Error de conexión al verificar.</div>`;
  }
}

function closeModal() {
  const modal = document.getElementById('verify-modal');
  if (modal) modal.style.display = 'none';
}

function switchView(viewName) {
  // Actualizar navegación activa
  document.querySelectorAll('.sidebar-nav .nav-item').forEach(n => n.classList.remove('active'));
  const activeNav = document.getElementById(`nav-${viewName}`);
  if (activeNav) activeNav.classList.add('active');

  // Secciones controlables
  const kpiGrid    = document.querySelector('.kpi-grid');
  const feedPanel  = document.getElementById('feed-panel');
  const tablePanel = document.querySelector('.table-panel');
  const rightCol   = document.querySelector('.right-column');

  // Mostrar/ocultar según la vista
  switch (viewName) {
    case 'alerts':
      // Vista principal: todo visible
      if (kpiGrid)    kpiGrid.style.display = '';
      if (feedPanel)  { feedPanel.style.display = ''; feedPanel.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
      if (tablePanel) tablePanel.style.display = '';
      if (rightCol)   rightCol.style.display = '';
      break;

    case 'tokens':
      // Solo KPIs + tabla de tokens descubiertos
      if (kpiGrid)    kpiGrid.style.display = '';
      if (feedPanel)  feedPanel.style.display = 'none';
      if (tablePanel) { tablePanel.style.display = ''; tablePanel.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
      if (rightCol)   rightCol.style.display = 'none';
      break;

    case 'copytrade':
      // Solo KPIs + columna derecha (copytrade on-chain)
      if (kpiGrid)    kpiGrid.style.display = '';
      if (feedPanel)  feedPanel.style.display = 'none';
      if (tablePanel) tablePanel.style.display = 'none';
      if (rightCol)   { rightCol.style.display = ''; rightCol.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
      break;

    case 'layers':
      // Solo KPIs + columna derecha (5 capas + ranking)
      if (kpiGrid)    kpiGrid.style.display = '';
      if (feedPanel)  feedPanel.style.display = 'none';
      if (tablePanel) tablePanel.style.display = 'none';
      if (rightCol)   { rightCol.style.display = ''; rightCol.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
      break;

    default:
      // Restaurar todo
      [kpiGrid, feedPanel, tablePanel, rightCol].forEach(el => { if (el) el.style.display = ''; });
  }
}
