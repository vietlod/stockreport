/**
 * CafeF CBTT Report Manager — Frontend App
 * ==========================================
 * Vanilla JS: API calls, WebSocket progress, filter UI, stats, history.
 */

// ── State ──────────────────────────────────────────────────────────────────
const state = {
    stockData: null,
    selectedTickers: [],
    selectedExchanges: [],
    selectedIndustries: [],
    selectedIndexes: [],
    historyPage: 1,
    historyLimit: 50,
    activeStatsTab: 'exchange',
    ws: null,
    adminToken: localStorage.getItem('stockreport_admin') || null,
};

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    if (state.adminToken) {
        showApp();
    } else {
        document.getElementById('loginScreen').classList.add('visible');
    }
});

// ── API Helpers ────────────────────────────────────────────────────────────
function getHeaders(includeAuth = false) {
    const h = { 'Content-Type': 'application/json' };
    if (includeAuth && state.adminToken) {
        h['Authorization'] = `Bearer ${state.adminToken}`;
    }
    return h;
}

async function api(url, opts = {}, requireAuth = false) {
    try {
        const resp = await fetch(url, {
            headers: getHeaders(requireAuth),
            ...opts,
        });
        const data = await resp.json().catch(() => ({}));
        if (resp.status === 401 && requireAuth) {
            showLogin();
            return null;
        }
        return data;
    } catch (e) {
        console.error(`API error: ${url}`, e);
        toast(`Lỗi kết nối: ${e.message}`, 'error');
        return null;
    }
}

// ── Load Stock Data ────────────────────────────────────────────────────────
async function loadStockData() {
    state.stockData = await api('/api/stock-data');
    if (!state.stockData) return;

    renderExchangeGrid();
    renderIndustrySelect();
    renderIndexGrid();
}

function renderExchangeGrid() {
    const grid = document.getElementById('exchangeGrid');
    grid.innerHTML = state.stockData.exchanges.map(ex => `
        <label class="checkbox-card" data-val="${ex.code}">
            <input type="checkbox" value="${ex.code}">
            <span class="cb-label">${ex.code}</span>
            <span class="cb-count">${ex.count}</span>
        </label>
    `).join('');

    grid.querySelectorAll('.checkbox-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.tagName === 'INPUT') return;
            const cb = card.querySelector('input');
            cb.checked = !cb.checked;
            card.classList.toggle('checked', cb.checked);
            updateSelectedExchanges();
        });
        card.querySelector('input').addEventListener('change', (e) => {
            card.classList.toggle('checked', e.target.checked);
            updateSelectedExchanges();
        });
    });
}

function renderIndustrySelect() {
    const sel = document.getElementById('industrySelect');
    sel.innerHTML = '<option value="" disabled>Chọn ngành ICB (Ctrl+click để chọn nhiều)</option>' +
        state.stockData.industries.map(ind =>
            `<option value="${ind.code}">[${ind.code}] ${ind.name} (${ind.count})</option>`
        ).join('');
    if (!sel.dataset.listenerAdded) {
        sel.addEventListener('change', updateSelectedIndustries);
        sel.dataset.listenerAdded = '1';
    }
}

function updateSelectedIndustries() {
    const sel = document.getElementById('industrySelect');
    state.selectedIndustries = [...sel.selectedOptions].map(o => o.value).filter(Boolean);
}

function renderIndexGrid() {
    const grid = document.getElementById('indexGrid');
    grid.innerHTML = state.stockData.indexes.map(idx => `
        <label class="checkbox-card" data-val="${idx.code}">
            <input type="checkbox" value="${idx.code}">
            <span class="cb-label">${idx.code}</span>
            <span class="cb-count">${idx.count}</span>
        </label>
    `).join('');

    grid.querySelectorAll('.checkbox-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.tagName === 'INPUT') return;
            const cb = card.querySelector('input');
            cb.checked = !cb.checked;
            card.classList.toggle('checked', cb.checked);
            updateSelectedIndexes();
        });
        card.querySelector('input').addEventListener('change', (e) => {
            card.classList.toggle('checked', e.target.checked);
            updateSelectedIndexes();
        });
    });
}

function updateSelectedExchanges() {
    state.selectedExchanges = [...document.querySelectorAll('#exchangeGrid input:checked')].map(cb => cb.value);
}

function updateSelectedIndustries() {
    const sel = document.getElementById('industrySelect');
    if (sel) state.selectedIndustries = [...sel.selectedOptions].map(o => o.value).filter(Boolean);
}

function updateSelectedIndexes() {
    state.selectedIndexes = [...document.querySelectorAll('#indexGrid input:checked')].map(cb => cb.value);
}

// ── Tabs ───────────────────────────────────────────────────────────────────
function initTabs() {
    // Filter tabs
    document.querySelectorAll('.filter-tabs .tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.filter-tabs .tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(`panel-${tab.dataset.tab}`).classList.add('active');
        });
    });

    // Stats tabs
    document.querySelectorAll('.stats-tabs .tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.stats-tabs .tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            state.activeStatsTab = tab.dataset.stab;
            renderStatsTable();
        });
    });
}

// ── Year Selects ───────────────────────────────────────────────────────────
const YEAR_MIN = 2012;

function initYearSelects() {
    const now = new Date().getFullYear();
    const years = [];
    for (let y = now; y >= YEAR_MIN; y--) years.push(y);

    ['fromYear', 'toYear'].forEach(id => {
        const sel = document.getElementById(id);
        sel.innerHTML = years.map(y => `<option value="${y}">${y}</option>`).join('');
    });
    document.getElementById('toYear').value = now;
    document.getElementById('fromYear').value = YEAR_MIN;
}

// ── Ticker Autocomplete ───────────────────────────────────────────────────
function initTickerAutocomplete() {
    const input = document.getElementById('tickerInput');
    const list = document.getElementById('tickerAutocomplete');
    let debounce = null;

    input.addEventListener('input', () => {
        clearTimeout(debounce);
        const q = input.value.trim().toUpperCase();
        if (q.length < 1) { list.classList.remove('visible'); return; }

        debounce = setTimeout(async () => {
            const data = await api(`/api/tickers?search=${q}`);
            if (!data || !data.tickers.length) { list.classList.remove('visible'); return; }

            list.innerHTML = data.tickers.slice(0, 15).map(t => `
                <div class="autocomplete-item" data-ticker="${t.ticker}">
                    <span class="ticker-code">${t.ticker}</span>
                    <span class="ticker-info">${t.exchange} · ${t.icb_name || '-'}</span>
                </div>
            `).join('');
            list.classList.add('visible');

            list.querySelectorAll('.autocomplete-item').forEach(item => {
                item.addEventListener('click', () => {
                    addTicker(item.dataset.ticker);
                    input.value = '';
                    list.classList.remove('visible');
                });
            });
        }, 200);
    });

    // Enter to add
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const v = input.value.trim().toUpperCase();
            if (v) { addTicker(v); input.value = ''; list.classList.remove('visible'); }
        }
    });

    // Click outside to close
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.input-group')) list.classList.remove('visible');
    });
}

function addTicker(ticker) {
    if (state.selectedTickers.includes(ticker)) return;
    state.selectedTickers.push(ticker);
    renderSelectedTickers();
}

function removeTicker(ticker) {
    state.selectedTickers = state.selectedTickers.filter(t => t !== ticker);
    renderSelectedTickers();
}

function renderSelectedTickers() {
    const container = document.getElementById('selectedTickers');
    container.innerHTML = state.selectedTickers.map(t => `
        <span class="ticker-tag">
            ${t}
            <span class="remove" onclick="removeTicker('${t}')">×</span>
        </span>
    `).join('');
}

// ── History Search ─────────────────────────────────────────────────────────
function initHistorySearch() {
    const input = document.getElementById('historySearch');
    let debounce = null;
    input.addEventListener('input', () => {
        clearTimeout(debounce);
        debounce = setTimeout(() => {
            state.historyPage = 1;
            loadHistory();
        }, 300);
    });
}

// ── Load Stats ─────────────────────────────────────────────────────────────
let statsData = null;

async function loadStats() {
    statsData = await api('/api/stats');
    if (!statsData) return;

    // Header chips
    document.getElementById('statFiles').textContent = statsData.summary?.total_files || 0;
    document.getElementById('statStocks').textContent = statsData.summary?.unique_stocks || 0;
    document.getElementById('statSize').textContent = statsData.summary?.total_size_mb || 0;

    renderStatsTable();
}

function renderStatsTable() {
    const body = document.getElementById('statsBody');
    if (!statsData) { body.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted)">Chưa có dữ liệu</td></tr>'; return; }

    let rows = [];
    if (state.activeStatsTab === 'exchange') {
        rows = statsData.by_exchange.map(r => ({
            name: r.exchange,
            count: r.count,
            size: formatSize(r.total_size),
        }));
    } else if (state.activeStatsTab === 'industry') {
        rows = statsData.by_industry.map(r => ({
            name: `[${r.icb_code}] ${r.icb_name}`,
            count: r.count,
            size: `${r.total_size_mb} MB`,
        }));
    } else {
        rows = statsData.by_index.map(r => ({
            name: `${r.index} (${r.total_tickers} CK)`,
            count: r.count,
            size: '-',
        }));
    }

    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted)">Chưa có dữ liệu</td></tr>';
        return;
    }

    body.innerHTML = rows.map(r => `
        <tr>
            <td>${r.name}</td>
            <td class="num">${r.count}</td>
            <td class="num">${r.size}</td>
        </tr>
    `).join('');
}

// ── Load History ───────────────────────────────────────────────────────────
async function loadHistory() {
    const search = document.getElementById('historySearch').value.trim();
    const params = new URLSearchParams({
        limit: state.historyLimit,
        offset: (state.historyPage - 1) * state.historyLimit,
    });
    if (search) params.set('stock_code', search.toUpperCase());

    const data = await api(`/api/history?${params}`);
    if (!data) return;

    document.getElementById('historyCount').textContent = `${data.total} bản ghi`;

    const body = document.getElementById('historyBody');
    if (!data.records.length) {
        body.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:24px">Chưa có dữ liệu</td></tr>';
        return;
    }

    body.innerHTML = data.records.map(r => `
        <tr>
            <td><span class="icb-badge">${r.icb_code || '-'}</span></td>
            <td class="ticker-cell">${r.stock_code || '-'}</td>
            <td>${r.quarter_year || '-'}</td>
            <td>${r.report_type || '-'}</td>
            <td>${r.exchange || '-'}</td>
            <td class="size-cell">${formatSize(r.file_size)}</td>
            <td class="date-cell">${formatDate(r.downloaded_at)}</td>
        </tr>
    `).join('');

    renderPagination(data.total);
}

function renderPagination(total) {
    const pages = Math.ceil(total / state.historyLimit);
    const container = document.getElementById('historyPagination');
    if (pages <= 1) { container.innerHTML = ''; return; }

    let html = `<button class="page-btn" onclick="goPage(${state.historyPage - 1})" ${state.historyPage <= 1 ? 'disabled' : ''}>←</button>`;
    const start = Math.max(1, state.historyPage - 2);
    const end = Math.min(pages, state.historyPage + 2);
    for (let i = start; i <= end; i++) {
        html += `<button class="page-btn ${i === state.historyPage ? 'active' : ''}" onclick="goPage(${i})">${i}</button>`;
    }
    html += `<button class="page-btn" onclick="goPage(${state.historyPage + 1})" ${state.historyPage >= pages ? 'disabled' : ''}>→</button>`;
    container.innerHTML = html;
}

function goPage(page) {
    state.historyPage = page;
    loadHistory();
}

// ── Scrape Job ─────────────────────────────────────────────────────────────
async function startScrape() {
    const config = await buildScrapeConfig();
    if (!config) return;

    const resp = await api('/api/scrape', {
        method: 'POST',
        body: JSON.stringify(config),
    });

    if (resp && resp.status === 'started') {
        lastProgressStatus = 'starting';
        lastLoggedEntry = '';
        lastDownloadedForStats = -1;
        document.getElementById('progressCard').style.display = '';
        document.getElementById('btnScrape').disabled = true;
        document.getElementById('btnStop').disabled = false;
        document.getElementById('logStream').innerHTML = '';
        toast('Đã bắt đầu scraping...', 'info');
    } else {
        toast(resp?.error || 'Không thể bắt đầu', 'error');
    }
}

async function stopScrape() {
    await api('/api/scrape/stop', { method: 'POST' });
    document.getElementById('btnStop').disabled = true;
    toast('Đang dừng...', 'info');
}

async function buildScrapeConfig() {
    updateSelectedIndustries();
    const config = { max_pages: 0 };
    const tickerSet = new Set();

    if (state.selectedTickers.length) {
        state.selectedTickers.forEach(t => tickerSet.add(t.toUpperCase()));
    }
    if (state.selectedExchanges.length) {
        for (const ex of state.selectedExchanges) {
            const data = await api(`/api/tickers?exchange=${encodeURIComponent(ex)}`);
            if (data?.tickers) data.tickers.forEach(t => tickerSet.add(t.ticker));
        }
    }
    if (state.selectedIndustries.length) {
        for (const icb of state.selectedIndustries) {
            const data = await api(`/api/tickers?icb_code=${encodeURIComponent(icb)}`);
            if (data?.tickers) data.tickers.forEach(t => tickerSet.add(t.ticker));
        }
    }
    if (state.selectedIndexes.length) {
        for (const idx of state.selectedIndexes) {
            const data = await api(`/api/tickers?index_code=${encodeURIComponent(idx)}`);
            if (data?.tickers) data.tickers.forEach(t => tickerSet.add(t.ticker));
        }
    }

    if (tickerSet.size) {
        config.stock_code = [...tickerSet].join(',');
    }

    // Khoảng thời gian
    const fromYear = document.getElementById('fromYear')?.value;
    const toYear = document.getElementById('toYear')?.value;
    const fromQuarter = document.getElementById('fromQuarter')?.value;
    const toQuarter = document.getElementById('toQuarter')?.value;
    if (fromYear) config.from_year = parseInt(fromYear, 10);
    if (toYear) config.to_year = parseInt(toYear, 10);
    if (fromQuarter) config.from_quarter = fromQuarter;
    if (toQuarter) config.to_quarter = toQuarter;

    return config;
}

// ── Google Sync ────────────────────────────────────────────────────────────
async function syncDrive() {
    toast('Đang upload lên Google Drive...', 'info');
    const resp = await api('/api/gdrive/sync', { method: 'POST' }, true);
    if (!resp) return;
    if (resp.status === 'ok') {
        toast(`Upload thành công: ${resp.uploaded} files`, 'success');
    } else {
        toast(resp.error || 'Lỗi upload', 'error');
    }
}

async function syncSheet() {
    toast('Đang cập nhật Google Sheet...', 'info');
    const resp = await api('/api/gsheet/sync', { method: 'POST' }, true);
    if (!resp) return;
    if (resp.status === 'ok') {
        toast(`Đã cập nhật sheet: ${resp.rows} rows`, 'success');
    } else {
        toast(resp.error || 'Lỗi cập nhật', 'error');
    }
}

// ── Auth ───────────────────────────────────────────────────────────────────
async function showApp() {
    document.getElementById('loginScreen').classList.remove('visible');
    document.getElementById('appContainer').style.display = '';
    await loadStockData();
    await loadStats();
    await loadHistory();
    initYearSelects();
    initTabs();
    initTickerAutocomplete();
    initHistorySearch();
    connectWebSocket();
}

async function submitLogin(e) {
    e.preventDefault();
    const user = document.getElementById('loginUser').value.trim();
    const pass = document.getElementById('loginPass').value;
    const errEl = document.getElementById('loginError');
    errEl.textContent = '';

    const resp = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: user, password: pass }),
    });
    const data = await resp.json().catch(() => ({}));

    if (data.ok && data.token) {
        state.adminToken = data.token;
        localStorage.setItem('stockreport_admin', data.token);
        document.getElementById('loginForm').reset();
        await showApp();
    } else {
        errEl.textContent = data.error || 'Đăng nhập thất bại';
    }
    return false;
}

function logout() {
    state.adminToken = null;
    localStorage.removeItem('stockreport_admin');
    document.getElementById('appContainer').style.display = 'none';
    document.getElementById('loginScreen').classList.add('visible');
    if (state.ws) state.ws.close();
}

// ── WebSocket + Polling fallback ───────────────────────────────────────────
let wsReconnectDelay = 3000;
const WS_MAX_DELAY = 60000;
let pollInterval = null;

function connectWebSocket() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws/progress`);

    ws.onopen = () => {
        wsReconnectDelay = 3000;
        state.ws = ws;
        stopPolling();
    };

    ws.onmessage = (msg) => {
        try {
            const data = JSON.parse(msg.data);
            if (data.type === 'progress') handleProgress(data);
        } catch (e) {
            console.error('WS parse error', e);
        }
    };

    ws.onclose = () => {
        state.ws = null;
        startPolling();
        const delay = wsReconnectDelay;
        wsReconnectDelay = Math.min(wsReconnectDelay * 1.5, WS_MAX_DELAY);
        setTimeout(connectWebSocket, delay);
    };

    ws.onerror = () => ws.close();

    const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        else clearInterval(pingInterval);
    }, 25000);
}

function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(async () => {
        const data = await api('/api/scrape/status');
        if (data?.progress && Object.keys(data.progress).length) {
            handleProgress({ type: 'progress', ...data.progress });
        }
    }, 2000);
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

let lastProgressStatus = '';
let lastLoggedEntry = '';
let lastDownloadedForStats = -1;

function handleProgress(data) {
    const card = document.getElementById('progressCard');
    card.style.display = '';

    // Progress bar
    if (data.total_pages > 0) {
        const pct = Math.round((data.current_page / data.total_pages) * 100);
        document.getElementById('progressBar').style.width = pct + '%';
    }

    // Text
    const statusMap = {
        'starting': '🚀 Đang khởi động...',
        'running': `📃 Trang ${data.current_page || '?'}/${data.total_pages || '?'}`,
        'completed': '✅ Hoàn thành!',
        'stopped': '⛔ Đã dừng',
        'error': `❌ Lỗi: ${data.error || ''}`,
    };
    document.getElementById('progressText').textContent = statusMap[data.status] || data.status;

    // Stats - luôn hiển thị từ data
    const d = data.downloaded ?? 0, s = data.skipped ?? 0, f = data.failed ?? 0;
    const fs = data.filtered_stock ?? 0, ft = data.filtered_time ?? 0;
    const ds = data.drive_synced ?? 0;
    let statsText = `Tải: ${d} | Bỏ qua: ${s} | Lỗi: ${f}`;
    if (ds > 0) statsText += ` | Drive: ${ds}`;
    if (fs > 0 || ft > 0) {
        statsText += ` | Lọc bỏ: ${fs} (mã) + ${ft} (thời gian)`;
    }
    document.getElementById('progressStats').textContent = statsText;

    // Cập nhật header + bảng thống kê tức thì khi có dữ liệu mới
    if (data.stats_summary) {
        document.getElementById('statFiles').textContent = data.stats_summary.total_files ?? 0;
        document.getElementById('statStocks').textContent = data.stats_summary.unique_stocks ?? 0;
        document.getElementById('statSize').textContent = data.stats_summary.total_size_mb ?? 0;
    }
    if (data.status === 'running' && d > lastDownloadedForStats) {
        lastDownloadedForStats = d;
        loadStats();
    }

    // Log entry - chỉ thêm khi khác entry trước (tránh lặp do polling)
    if (data.current_entry && data.current_entry !== lastLoggedEntry) {
        lastLoggedEntry = data.current_entry;
        addLog(data.current_entry, data.status === 'error' ? 'err' : 'ok');
    }

    // Completed → re-enable buttons, reload data
    if (data.status === 'completed' || data.status === 'stopped' || data.status === 'error') {
        document.getElementById('btnScrape').disabled = false;
        document.getElementById('btnStop').disabled = true;
        document.getElementById('progressBar').style.width = '100%';
        stopPolling();
        loadStats();
        loadHistory();
        if (data.status === 'completed' && lastProgressStatus !== 'completed') {
            let msg = `Scraping hoàn thành! Tải: ${d}, Bỏ qua: ${s}, Lỗi: ${f}`;
            if (d === 0 && s === 0 && f === 0 && (fs > 0 || ft > 0)) {
                msg += `. Tất cả entry bị lọc bỏ (mã: ${fs}, thời gian: ${ft}). Thử mở rộng bộ lọc hoặc bỏ chọn Ngành/Sàn/Chỉ số để tải tất cả.`;
            }
            toast(msg, d > 0 ? 'success' : 'info');
        }
        lastProgressStatus = data.status;
    } else {
        lastProgressStatus = data.status;
    }
}

function addLog(text, cls = '') {
    const stream = document.getElementById('logStream');
    const el = document.createElement('div');
    el.className = `log-entry ${cls ? 'log-' + cls : ''}`;
    el.textContent = `${new Date().toLocaleTimeString('vi')} — ${text}`;
    stream.appendChild(el);
    stream.scrollTop = stream.scrollHeight;

    // Keep max 200 entries
    while (stream.children.length > 200) stream.removeChild(stream.firstChild);
}

// ── Utilities ──────────────────────────────────────────────────────────────
function formatSize(bytes) {
    if (!bytes) return '-';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

function formatDate(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return d.toLocaleDateString('vi') + ' ' + d.toLocaleTimeString('vi', { hour: '2-digit', minute: '2-digit' });
}

function toast(message, type = 'info') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(100%)';
        el.style.transition = '0.3s ease';
        setTimeout(() => el.remove(), 300);
    }, 4000);
}
