/**
 * CafeF CBTT Report Manager — Frontend App
 * ==========================================
 * Vanilla JS: API calls, WebSocket progress, filter UI, stats, history.
 */

// ── State ──────────────────────────────────────────────────────────────────
const state = {
    stockData: null,        // {exchanges, industries, indexes}
    selectedTickers: [],    // manually selected tickers
    selectedExchanges: [],
    selectedIndustries: [],
    selectedIndexes: [],
    historyPage: 1,
    historyLimit: 50,
    activeStatsTab: 'exchange',
    ws: null,
};

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    await loadStockData();
    await loadStats();
    await loadHistory();
    initYearSelects();
    initTabs();
    initTickerAutocomplete();
    initHistorySearch();
    connectWebSocket();
});

// ── API Helpers ────────────────────────────────────────────────────────────
async function api(url, opts = {}) {
    try {
        const resp = await fetch(url, {
            headers: { 'Content-Type': 'application/json' },
            ...opts,
        });
        return await resp.json();
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
    sel.innerHTML = state.stockData.industries.map(ind =>
        `<option value="${ind.code}">[${ind.code}] ${ind.name} (${ind.count})</option>`
    ).join('');
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
function initYearSelects() {
    const now = new Date().getFullYear();
    const years = [];
    for (let y = now; y >= now - 10; y--) years.push(y);

    ['fromYear', 'toYear'].forEach(id => {
        const sel = document.getElementById(id);
        sel.innerHTML = years.map(y => `<option value="${y}">${y}</option>`).join('');
    });
    document.getElementById('toYear').value = now;
    document.getElementById('fromYear').value = now - 2;
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
    const config = buildScrapeConfig();

    const resp = await api('/api/scrape', {
        method: 'POST',
        body: JSON.stringify(config),
    });

    if (resp && resp.status === 'started') {
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

function buildScrapeConfig() {
    const config = {};

    // Tickers / groups
    if (state.selectedTickers.length) {
        config.stock_code = state.selectedTickers.join(',');
    }

    // MAX_PAGES: 0 = fetch all
    config.max_pages = 0;

    return config;
}

// ── Google Sync ────────────────────────────────────────────────────────────
async function syncDrive() {
    toast('Đang upload lên Google Drive...', 'info');
    const resp = await api('/api/gdrive/sync', { method: 'POST' });
    if (resp?.status === 'ok') {
        toast(`Upload thành công: ${resp.uploaded} files`, 'success');
    } else {
        toast(resp?.error || 'Lỗi upload', 'error');
    }
}

async function syncSheet() {
    toast('Đang cập nhật Google Sheet...', 'info');
    const resp = await api('/api/gsheet/sync', { method: 'POST' });
    if (resp?.status === 'ok') {
        toast(`Đã cập nhật sheet: ${resp.rows} rows`, 'success');
    } else {
        toast(resp?.error || 'Lỗi cập nhật', 'error');
    }
}

// ── WebSocket ──────────────────────────────────────────────────────────────
function connectWebSocket() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${location.host}/ws/progress`);

    ws.onopen = () => { console.log('WS connected'); };

    ws.onmessage = (msg) => {
        try {
            const data = JSON.parse(msg.data);
            if (data.type === 'progress') handleProgress(data);
        } catch (e) {
            console.error('WS parse error', e);
        }
    };

    ws.onclose = () => {
        console.log('WS disconnected, reconnecting in 3s...');
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = () => ws.close();

    state.ws = ws;

    // Keepalive ping
    setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
            ws.send('ping');
        }
    }, 30000);
}

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

    // Stats
    document.getElementById('progressStats').textContent =
        `Tải: ${data.downloaded || 0} | Bỏ qua: ${data.skipped || 0} | Lỗi: ${data.failed || 0}`;

    // Log entry
    if (data.current_entry) {
        addLog(data.current_entry, data.status === 'error' ? 'err' : 'ok');
    }

    // Completed → re-enable buttons, reload data
    if (data.status === 'completed' || data.status === 'stopped' || data.status === 'error') {
        document.getElementById('btnScrape').disabled = false;
        document.getElementById('btnStop').disabled = true;
        document.getElementById('progressBar').style.width = '100%';
        loadStats();
        loadHistory();
        if (data.status === 'completed') toast('Scraping hoàn thành!', 'success');
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
