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
    username: localStorage.getItem('stockreport_user') || '',
    userPicture: localStorage.getItem('stockreport_picture') || '',
    userEmail: localStorage.getItem('stockreport_email') || '',
    // History filter & sort
    historySortBy: 'downloaded_at',
    historySortDir: 'desc',
    historyFilterExchange: '',
    historyFilterICB: '',
    historyFilterSync: '',
};

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    // User menu toggle
    const userAvatar = document.getElementById('userAvatar');
    const userMenu = document.getElementById('userMenu');
    if (userAvatar) {
        userAvatar.addEventListener('click', (e) => {
            e.stopPropagation();
            userMenu.classList.toggle('open');
        });
    }
    document.addEventListener('click', (e) => {
        if (userMenu && !userMenu.contains(e.target)) {
            userMenu.classList.remove('open');
        }
    });

    if (state.adminToken) {
        showApp();
        const params = new URLSearchParams(location.search);
        if (params.get('oauth') === 'success') {
            toast('✅ Đã kết nối Google Drive. Bạn có thể Sync Drive.', 'success');
            history.replaceState({}, '', '/');
        } else if (params.get('oauth') === 'error') {
            toast('❌ Lỗi kết nối Google: ' + (params.get('msg') || 'Unknown'), 'error');
            history.replaceState({}, '', '/');
        }
    } else {
        document.getElementById('loginScreen').classList.add('visible');
    }

    // Google Identity Services initialization
    initGoogleSignIn();
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

// ── History Search & Filters ───────────────────────────────────────────────
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

async function initHistoryFilters() {
    const data = await api('/api/history/filters');
    if (!data) return;

    const exSel = document.getElementById('filterExchange');
    (data.exchanges || []).forEach(ex => {
        const opt = document.createElement('option');
        opt.value = ex;
        opt.textContent = ex;
        exSel.appendChild(opt);
    });

    const icbSel = document.getElementById('filterICB');
    (data.icb_codes || []).forEach(code => {
        const opt = document.createElement('option');
        opt.value = code;
        opt.textContent = code;
        icbSel.appendChild(opt);
    });
}

function applyHistoryFilters() {
    state.historyFilterExchange = document.getElementById('filterExchange').value;
    state.historyFilterICB = document.getElementById('filterICB').value;
    state.historyFilterSync = document.getElementById('filterSync').value;
    state.historyPage = 1;
    // Show/hide cleanup button
    const hasFilter = state.historyFilterExchange || state.historyFilterICB || state.historyFilterSync !== '';
    const btn = document.getElementById('btnCleanup');
    if (btn) btn.style.display = hasFilter ? '' : 'none';
    loadHistory();
}

function toggleSort(col) {
    if (state.historySortBy === col) {
        state.historySortDir = state.historySortDir === 'asc' ? 'desc' : 'asc';
    } else {
        state.historySortBy = col;
        // Default directions
        if (col === 'stock_code') state.historySortDir = 'asc';
        else state.historySortDir = 'desc';
    }
    state.historyPage = 1;
    loadHistory();
    updateSortArrows();
}

function updateSortArrows() {
    document.querySelectorAll('#historyTable th.sortable').forEach(th => {
        const arrow = th.querySelector('.sort-arrow');
        const col = th.dataset.sort;
        if (col === state.historySortBy) {
            th.classList.add('active-sort');
            arrow.textContent = state.historySortDir === 'asc' ? '▲' : '▼';
        } else {
            th.classList.remove('active-sort');
            arrow.textContent = '↕';
        }
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
        sort_by: state.historySortBy,
        sort_dir: state.historySortDir,
    });
    if (search) params.set('stock_code', search.toUpperCase());
    if (state.historyFilterExchange) params.set('exchange', state.historyFilterExchange);
    if (state.historyFilterICB) params.set('icb_code', state.historyFilterICB);
    if (state.historyFilterSync !== '') params.set('drive_synced', state.historyFilterSync);

    const data = await api(`/api/history?${params}`);
    if (!data) return;

    document.getElementById('historyCount').textContent = `${data.total} bản ghi`;

    const body = document.getElementById('historyBody');
    if (!data.records.length) {
        body.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:24px">Chưa có dữ liệu</td></tr>';
        return;
    }

    body.innerHTML = data.records.map(r => {
        const synced = r.drive_synced === 1;
        const syncIcon = synced
            ? '<span class="sync-icon sync-ok" title="Đã đồng bộ lên Drive">✔</span>'
            : '<span class="sync-icon sync-no" title="Chưa đồng bộ">✖</span>';
        const tickerDisplay = r.drive_file_id
            ? `<a href="https://drive.google.com/file/d/${r.drive_file_id}/view" target="_blank" class="ticker-link">${r.stock_code || '-'}</a>`
            : (r.stock_code || '-');
        return `
        <tr>
            <td><span class="icb-badge">${r.icb_code || '-'}</span></td>
            <td class="ticker-cell">${tickerDisplay}</td>
            <td>${r.quarter_year || '-'}</td>
            <td>${r.report_type || '-'}</td>
            <td>${r.exchange || '-'}</td>
            <td class="size-cell">${formatSize(r.file_size)}</td>
            <td class="sync-cell">${syncIcon}</td>
            <td class="date-cell">${formatDate(r.downloaded_at)}</td>
        </tr>`;
    }).join('');

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

async function cleanupFiltered() {
    // Build filter description
    const filters = [];
    if (state.historyFilterExchange) filters.push(`Sàn: ${state.historyFilterExchange}`);
    if (state.historyFilterICB) filters.push(`ICB: ${state.historyFilterICB}`);
    if (state.historyFilterSync === '1') filters.push('Đã đồng bộ');
    else if (state.historyFilterSync === '0') filters.push('Chưa đồng bộ');

    const search = document.getElementById('historySearch').value.trim();
    if (search) filters.push(`Mã: ${search.toUpperCase()}`);

    if (!filters.length) {
        showToast('Chọn ít nhất 1 bộ lọc trước khi dọn dẹp', 'error');
        return;
    }

    // Get total count from current data
    const countEl = document.getElementById('historyCount');
    const countText = countEl ? countEl.textContent : '';

    const msg = `⚠️ Xóa tất cả files theo filter:\n\n• ${filters.join('\n• ')}\n\n${countText}\n\nHành động này không thể hoàn tác. Tiếp tục?`;
    if (!confirm(msg)) return;

    // Build query params
    const params = new URLSearchParams();
    if (search) params.set('stock_code', search.toUpperCase());
    if (state.historyFilterExchange) params.set('exchange', state.historyFilterExchange);
    if (state.historyFilterICB) params.set('icb_code', state.historyFilterICB);
    if (state.historyFilterSync !== '') params.set('drive_synced', state.historyFilterSync);

    const result = await api(`/api/history/cleanup?${params}`, { method: 'DELETE' });
    if (!result) return;

    if (result.error) {
        showToast(result.error, 'error');
        return;
    }

    const freedMB = (result.freed_bytes / 1024 / 1024).toFixed(1);
    showToast(`🗑 Đã xóa ${result.deleted} records (${freedMB}MB)`, 'success');

    // Reload
    state.historyPage = 1;
    loadHistory();
    loadStats();
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
    const btn = document.getElementById('btnSyncDrive');
    const status = await api('/api/oauth2/status');
    if (status && !status.connected) {
        toast('Chưa kết nối Google Drive. Đang chuyển đến trang cấp quyền...', 'info');
        startOAuthFlow('drive');
        return;
    }
    btn.disabled = true;
    toast('Đang khởi tạo sync Drive...', 'info');
    const resp = await api('/api/gdrive/sync', { method: 'POST' }, true);
    if (!resp) { btn.disabled = false; return; }
    if (resp.status === 'started') {
        toast('☁ Sync Drive đang chạy nền. Có thể đóng tab.', 'info');
    } else if ((resp.error || '').includes('Chưa có Google OAuth token')) {
        btn.disabled = false;
        startOAuthFlow('drive');
    } else {
        btn.disabled = false;
        toast(resp.error || 'Lỗi upload', 'error');
    }
}

async function startOAuthFlow(forWhat = 'drive') {
    const data = await api('/api/oauth2/start', {}, true);
    if (data?.url) {
        toast('Đang chuyển đến Google để cấp quyền...', 'info');
        window.location.href = data.url;
    } else {
        toast(data?.detail || 'Lỗi OAuth', 'error');
    }
}

async function syncSheet() {
    const btn = document.getElementById('btnSyncSheet');
    const status = await api('/api/oauth2/status');
    if (status && !status.connected) {
        toast('Chưa kết nối Google. Đang chuyển đến trang cấp quyền...', 'info');
        startOAuthFlow('sheet');
        return;
    }
    btn.disabled = true;
    toast('Đang khởi tạo sync Sheet...', 'info');
    const resp = await api('/api/gsheet/sync', { method: 'POST' }, true);
    if (!resp) { btn.disabled = false; return; }
    if (resp.status === 'started') {
        toast('📊 Sync Sheet đang chạy nền. Có thể đóng tab.', 'info');
    } else {
        btn.disabled = false;
        toast(resp.error || 'Lỗi cập nhật', 'error');
    }
}

// ── Settings & Cleanup ─────────────────────────────────────────────────────

function openSettings() {
    // Close user dropdown
    const userMenu = document.getElementById('userMenu');
    if (userMenu) userMenu.classList.remove('open');

    loadSettings();
    document.getElementById('settingsModal').style.display = '';
}

function closeSettings() {
    document.getElementById('settingsModal').style.display = 'none';
}

async function loadSettings() {
    const data = await api('/api/settings');
    if (data && data.retention) {
        document.getElementById('retentionSelect').value = data.retention;
    }
}

async function saveSettings() {
    const retention = document.getElementById('retentionSelect').value;
    const resp = await api('/api/settings', {
        method: 'POST',
        body: JSON.stringify({ retention }),
    }, true);
    if (resp && resp.status === 'ok') {
        toast('✅ Đã lưu cài đặt', 'success');
        closeSettings();
    } else {
        toast(resp?.error || 'Lỗi lưu cài đặt', 'error');
    }
}

async function runCleanupNow() {
    if (!confirm('Xóa tất cả files đã hết hạn lưu trữ?')) return;
    const btn = document.getElementById('btnCleanupNow');
    btn.disabled = true;
    btn.textContent = 'Đang xóa...';
    const resp = await api('/api/cleanup/run', { method: 'POST' }, true);
    btn.disabled = false;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M5.5 5.5A.5.5 0 016 6v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm2.5 0a.5.5 0 01.5.5v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm3 .5a.5.5 0 00-1 0v6a.5.5 0 001 0V6z"/><path fill-rule="evenodd" d="M14.5 3a1 1 0 01-1 1H13v9a2 2 0 01-2 2H5a2 2 0 01-2-2V4h-.5a1 1 0 01-1-1V2a1 1 0 011-1H6a1 1 0 011-1h2a1 1 0 011 1h3.5a1 1 0 011 1v1zM4.118 4L4 4.059V13a1 1 0 001 1h6a1 1 0 001-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/></svg> Dọn dẹp ngay`;
    if (resp && resp.status === 'ok') {
        if (resp.skipped) {
            toast('⏭ Chế độ "Không xóa" — không có file nào bị xóa', 'info');
        } else if (resp.deleted > 0) {
            toast(`🗑 Đã xóa ${resp.deleted} files (${resp.freed_mb} MB)`, 'success');
            await loadStats();
            await loadHistory();
        } else {
            toast('✅ Không có file nào hết hạn', 'info');
        }
    } else {
        toast(resp?.error || 'Lỗi dọn dẹp', 'error');
    }
}

// Close modal on ESC or overlay click
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSettings();
});
document.addEventListener('click', (e) => {
    if (e.target.id === 'settingsModal') closeSettings();
});

// ── Auth ───────────────────────────────────────────────────────────────────
async function showApp() {
    document.getElementById('loginScreen').classList.remove('visible');
    document.getElementById('appContainer').style.display = '';
    updateUserMenu();
    await loadStockData();
    await loadStats();
    await loadHistory();
    initYearSelects();
    initTabs();
    initTickerAutocomplete();
    initHistorySearch();
    initHistoryFilters();
    connectWebSocket();
}

function updateUserMenu() {
    const name = state.username || 'User';
    const picture = state.userPicture || localStorage.getItem('stockreport_picture');
    const email = state.userEmail || localStorage.getItem('stockreport_email') || '';
    const initial = name.charAt(0).toUpperCase();

    const avatarInitial = document.getElementById('avatarInitial');
    const avatarImg = document.getElementById('avatarImg');
    const dropdownAvatarInitial = document.getElementById('dropdownAvatarInitial');
    const dropdownAvatarImg = document.getElementById('dropdownAvatarImg');
    const usernameEl = document.getElementById('dropdownUsername');
    const emailEl = document.getElementById('dropdownEmail');

    if (picture) {
        if (avatarImg) { avatarImg.src = picture; avatarImg.style.display = ''; }
        if (avatarInitial) avatarInitial.style.display = 'none';
        if (dropdownAvatarImg) { dropdownAvatarImg.src = picture; dropdownAvatarImg.style.display = ''; }
        if (dropdownAvatarInitial) dropdownAvatarInitial.style.display = 'none';
    } else {
        if (avatarImg) avatarImg.style.display = 'none';
        if (avatarInitial) { avatarInitial.textContent = initial; avatarInitial.style.display = ''; }
        if (dropdownAvatarImg) dropdownAvatarImg.style.display = 'none';
        if (dropdownAvatarInitial) { dropdownAvatarInitial.textContent = initial; dropdownAvatarInitial.style.display = ''; }
    }
    if (usernameEl) usernameEl.textContent = name;
    if (emailEl) emailEl.textContent = email;
}

// ── Google Sign-In ─────────────────────────────────────────────────────────
async function initGoogleSignIn() {
    try {
        const resp = await fetch('/api/auth/config');
        const config = await resp.json();
        if (!config.google_client_id) {
            console.error('GOOGLE_CLIENT_ID not configured on server');
            return;
        }
        google.accounts.id.initialize({
            client_id: config.google_client_id,
            callback: handleGoogleSignIn,
            auto_select: !!state.adminToken,
        });
        const btnEl = document.getElementById('googleSignInBtn');
        if (btnEl) {
            google.accounts.id.renderButton(btnEl, {
                theme: 'filled_blue',
                size: 'large',
                shape: 'pill',
                text: 'signin_with',
                locale: 'vi_VN',
                width: 300,
            });
        }
    } catch (e) {
        console.error('Failed to init Google Sign-In:', e);
    }
}

async function handleGoogleSignIn(response) {
    const errEl = document.getElementById('loginError');
    if (errEl) errEl.textContent = '';

    try {
        const resp = await fetch('/api/auth/google', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ credential: response.credential }),
        });
        const data = await resp.json().catch(() => ({}));

        if (data.ok && data.token) {
            state.adminToken = data.token;
            state.username = data.name || data.email;
            state.userPicture = data.picture || '';
            state.userEmail = data.email || '';
            localStorage.setItem('stockreport_admin', data.token);
            localStorage.setItem('stockreport_user', state.username);
            localStorage.setItem('stockreport_picture', state.userPicture);
            localStorage.setItem('stockreport_email', state.userEmail);
            await showApp();
        } else {
            if (errEl) errEl.textContent = data.error || 'Đăng nhập thất bại';
        }
    } catch (e) {
        if (errEl) errEl.textContent = 'Lỗi kết nối server';
    }
}

function logout() {
    state.adminToken = null;
    state.username = '';
    state.userPicture = '';
    state.userEmail = '';
    localStorage.removeItem('stockreport_admin');
    localStorage.removeItem('stockreport_user');
    localStorage.removeItem('stockreport_picture');
    localStorage.removeItem('stockreport_email');
    document.getElementById('appContainer').style.display = 'none';
    document.getElementById('loginScreen').classList.add('visible');
    const userMenu = document.getElementById('userMenu');
    if (userMenu) userMenu.classList.remove('open');
    if (state.ws) state.ws.close();
    // Revoke Google auto-select
    try { google.accounts.id.disableAutoSelect(); } catch (_) { }
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
            else if (data.type === 'sync_progress') handleSyncProgress(data);
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

    // Text — multi-ticker aware
    let tickerPrefix = '';
    if (data.total_tickers > 1 && data.current_ticker) {
        tickerPrefix = `🏷 [${data.current_ticker}] (${data.ticker_index}/${data.total_tickers}) — `;
    } else if (data.total_tickers === 1 && data.current_ticker) {
        tickerPrefix = `🏷 [${data.current_ticker}] `;
    }
    const statusMap = {
        'starting': '🚀 Đang khởi động...',
        'running': `${tickerPrefix}📃 Trang ${data.current_page || '?'}/${data.total_pages || '?'}`,
        'completed': '✅ Hoàn thành!',
        'stopped': '⛔ Đã dừng',
        'error': `❌ Lỗi: ${data.error || ''}`,
    };
    document.getElementById('progressText').textContent = statusMap[data.status] || data.status;

    // Stats - chỉ hiển thị thông tin tải chính, không có lỗi/lọc
    const d = data.downloaded ?? 0, s = data.skipped ?? 0;
    const ds = data.drive_synced ?? 0;
    let statsText = `Tải: ${d} | Bỏ qua: ${s}`;
    if (ds > 0) statsText += ` | Drive: ${ds}`;
    if (data.total_tickers > 1) statsText += ` | Tickers: ${data.ticker_index}/${data.total_tickers}`;
    document.getElementById('progressStats').textContent = statsText;

    // Notes - lỗi + lọc thọi gian (màu đỏ, in nghiêng, tách biệt)
    const notes = document.getElementById('progressNotes');
    if (notes) {
        let html = '';
        // Error details
        const errDetails = data.error_details || [];
        if (errDetails.length > 0) {
            errDetails.forEach(e => {
                html += `<div class="note-item">⚠ ${e.ticker}: ${e.file} — ${e.error}</div>`;
            });
        }
        // Filter info
        const ft = data.filtered_time ?? 0;
        if (ft > 0) {
            const timeRange = data.time_range || '';
            html += `<div class="note-item">⏭ ${ft} entries ngoài khoảng thời gian ${timeRange ? '(' + timeRange + ')' : ''}</div>`;
        }
        notes.innerHTML = html;
    }

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
            const f = data.failed ?? 0;
            let msg = `Scraping hoàn thành! Tải: ${d}, Bỏ qua: ${s}`;
            if (f > 0) msg += `, Lỗi: ${f}`;
            toast(msg, d > 0 ? 'success' : 'info');
        }
        lastProgressStatus = data.status;
    } else {
        lastProgressStatus = data.status;
    }
}

let lastSyncStatus = '';
let syncAutoHideTimers = {};

function formatEta(seconds) {
    if (!seconds || seconds <= 0) return '';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins > 0) return `${mins}m${secs > 0 ? secs + 's' : ''}`;
    return `${secs}s`;
}

function handleSyncProgress(data) {
    const st = data.status;
    const syncType = data.sync_type;
    const phase = data.phase || '';
    const card = document.getElementById('syncStatusCard');

    // ── Drive ──────────────────────────────────────────────
    if (syncType === 'drive') {
        const row = document.getElementById('syncDriveRow');
        const badge = document.getElementById('syncDriveBadge');
        const bar = document.getElementById('syncDriveBar');
        const detail = document.getElementById('syncDriveDetail');

        card.style.display = '';
        row.style.display = '';

        // Clear any pending auto-hide
        if (syncAutoHideTimers.drive) {
            clearTimeout(syncAutoHideTimers.drive);
            syncAutoHideTimers.drive = null;
        }

        if (st === 'running') {
            badge.textContent = phase === 'listing' ? 'đang quét' : phase === 'scanning' ? 'khởi tạo' : 'đang đồng bộ';
            badge.className = 'sync-badge running';
            bar.classList.remove('shimmer');

            if (phase === 'scanning') {
                bar.style.width = '0%';
                const totalLocal = data.total || 0;
                detail.innerHTML = `<span>Đang quét ${totalLocal} files local...</span>`;

            } else if (phase === 'listing') {
                bar.style.width = '5%';
                const totalLocal = data.total || 0;
                detail.innerHTML = `<span>Đang quét files trên Drive... (${totalLocal} files local)</span>`;

            } else if (phase === 'uploading') {
                const current = data.current_index || 0;
                const total = data.total || 0;
                const uploaded = data.uploaded || 0;
                const skipped = data.skipped || 0;
                const errors = data.errors || 0;
                const file = data.current_file || '';
                const folder = data.current_folder || '';
                const eta = data.eta_s || 0;
                const action = data.action || '';

                // Progress bar
                if (total > 0) {
                    const pct = Math.round((current / total) * 100);
                    bar.style.width = `${pct}%`;
                }

                // Detail text
                let html = '';
                // File info
                if (folder) {
                    html += `<span class="sync-file">📁 [${folder}] ${file}</span>`;
                } else if (file) {
                    html += `<span class="sync-file">${file}</span>`;
                }
                // Stats
                html += `<span class="sync-stats">${current}/${total} — ↑${uploaded} ⏭${skipped}`;
                if (errors > 0) html += ` ✖${errors}`;
                html += '</span>';
                // ETA
                const etaStr = formatEta(eta);
                if (etaStr) {
                    html += `<span class="sync-eta">ETA: ${etaStr}</span>`;
                }
                // Error on current file
                if (action === 'error' && data.error_msg) {
                    html += `<span class="sync-error">⚠ ${data.error_msg}</span>`;
                }
                detail.innerHTML = html;
            }

        } else if (st === 'completed') {
            const u = data.uploaded || 0;
            const s = data.skipped || 0;
            const e = data.errors || 0;
            badge.textContent = '✅ hoàn thành';
            badge.className = 'sync-badge completed';
            bar.classList.remove('shimmer');
            bar.style.width = '100%';
            detail.innerHTML = `<span class="sync-stats">↑${u} uploaded | ⏭${s} skipped | ✖${e} errors</span>`;
            toast(`✅ Drive sync hoàn tất: ${u} uploaded, ${s} skipped, ${e} errors`, u > 0 ? 'success' : 'info');
            // Re-enable button
            const btnDrive = document.getElementById('btnSyncDrive');
            if (btnDrive) btnDrive.disabled = false;
            // Auto-hide after 10s
            syncAutoHideTimers.drive = setTimeout(() => {
                row.style.display = 'none';
                if (!document.getElementById('syncSheetRow').style.display ||
                    document.getElementById('syncSheetRow').style.display === 'none') {
                    card.style.display = 'none';
                }
            }, 10000);

        } else if (st === 'error') {
            const err = data.error || 'Unknown';
            badge.textContent = '❌ lỗi';
            badge.className = 'sync-badge error';
            bar.classList.remove('shimmer');
            bar.style.width = '100%';
            bar.style.background = 'var(--red)';
            detail.innerHTML = `<span class="sync-error">${err}</span>`;
            if ((err + '').includes('Chưa có Google OAuth token')) {
                toast('Chưa kết nối Google Drive. Đang chuyển đến trang cấp quyền...', 'info');
                startOAuthFlow('drive');
            } else {
                toast(`❌ Drive sync lỗi: ${err}`, 'error');
            }
            // Re-enable button
            const btnDrive = document.getElementById('btnSyncDrive');
            if (btnDrive) btnDrive.disabled = false;
        }
    }

    // ── Sheet ──────────────────────────────────────────────
    if (syncType === 'sheet') {
        const row = document.getElementById('syncSheetRow');
        const badge = document.getElementById('syncSheetBadge');
        const bar = document.getElementById('syncSheetBar');
        const detail = document.getElementById('syncSheetDetail');

        card.style.display = '';
        row.style.display = '';

        // Clear any pending auto-hide
        if (syncAutoHideTimers.sheet) {
            clearTimeout(syncAutoHideTimers.sheet);
            syncAutoHideTimers.sheet = null;
        }

        if (st === 'running') {
            badge.textContent = 'đang đồng bộ';
            badge.className = 'sync-badge running';
            bar.classList.add('shimmer');

            const phaseLabels = {
                'reading_db': '📖 Đang đọc dữ liệu từ database...',
                'computing_hash': `🔍 Đang kiểm tra thay đổi... (${data.rows || 0} dòng)`,
                'writing_sheet': `📝 Đang ghi ${data.rows || 0} dòng lên Sheet...`,
            };
            detail.innerHTML = `<span>${phaseLabels[phase] || 'Đang xử lý...'}</span>`;

        } else if (st === 'completed') {
            const rows = data.rows || 0;
            badge.textContent = '✅ hoàn thành';
            badge.className = 'sync-badge completed';
            bar.classList.remove('shimmer');
            bar.style.width = '100%';
            if (data.skipped) {
                detail.innerHTML = `<span class="sync-stats">⏭ Dữ liệu không thay đổi (${rows} dòng)</span>`;
                toast(`⏭ Sheet sync: dữ liệu không thay đổi (${rows} rows)`, 'info');
            } else {
                detail.innerHTML = `<span class="sync-stats">✅ Đã ghi ${rows} dòng lên Google Sheets</span>`;
                toast(`✅ Sheet sync hoàn tất: ${rows} rows`, 'success');
            }
            // Auto-hide after 10s
            syncAutoHideTimers.sheet = setTimeout(() => {
                row.style.display = 'none';
                if (!document.getElementById('syncDriveRow').style.display ||
                    document.getElementById('syncDriveRow').style.display === 'none') {
                    card.style.display = 'none';
                }
            }, 10000);
            // Re-enable button
            const btnSheet = document.getElementById('btnSyncSheet');
            if (btnSheet) btnSheet.disabled = false;

        } else if (st === 'error') {
            const err = data.error || 'Unknown';
            badge.textContent = '❌ lỗi';
            badge.className = 'sync-badge error';
            bar.classList.remove('shimmer');
            bar.style.width = '100%';
            bar.style.background = 'var(--red)';
            detail.innerHTML = `<span class="sync-error">${err}</span>`;
            if ((err + '').includes('Chưa có Google OAuth token')) {
                toast('Chưa kết nối Google. Đang chuyển đến trang cấp quyền...', 'info');
                startOAuthFlow('sheet');
            } else {
                toast(`❌ Sheet sync lỗi: ${err}`, 'error');
            }
            // Re-enable button
            const btnSheet = document.getElementById('btnSyncSheet');
            if (btnSheet) btnSheet.disabled = false;
        }
    }

    lastSyncStatus = `${syncType}_${st}`;
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
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    container.appendChild(el);
    // Max 3 visible toasts
    while (container.children.length > 3) {
        container.removeChild(container.firstChild);
    }
    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(100%)';
        el.style.transition = '0.3s ease';
        setTimeout(() => el.remove(), 300);
    }, 4000);
}
