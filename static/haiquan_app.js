/**
 * Hải Quan — Frontend App (TÁCH BIỆT hoàn toàn với CafeF app.js)
 * ================================================================
 * Isolated: state, API calls, WebSocket handlers, UI updates.
 * Relies on shared utilities from app.js: api(), toast(), getHeaders(), formatSize(), formatDate()
 */

// ── HQ State ───────────────────────────────────────────────────────────────
const hqState = {
    historyPage: 1,
    historyLimit: 50,
    sortBy: 'downloaded_at',
    sortDir: 'desc',
    historySearch: '',
    filterType: '',
    filterCode: '',
    filterSync: '',
};
const hqBgTask = { scrape: false, drive: false, sheet: false };

// ── Init (called lazily on first tab switch) ───────────────────────────────
async function hq_init() {
    hq_initHistorySearch();
    await hq_loadFilters();
    await hq_loadStats();
    await hq_loadHistory();
}

// ── HQ Stats ───────────────────────────────────────────────────────────────
async function hq_loadStats() {
    const data = await api('/api/haiquan/stats');
    if (!data || !data.summary) return;

    const s = data.summary;
    document.getElementById('hqStatTotal').textContent = s.total_files || 0;
    document.getElementById('hqStatYears').textContent = s.unique_years || 0;
    document.getElementById('hqStatCodes').textContent = s.unique_codes || 0;
    document.getElementById('hqStatSize').textContent = s.total_size_mb || 0;
}

// ── HQ Search & Filters ────────────────────────────────────────────────────
function hq_initHistorySearch() {
    const input = document.getElementById('hqHistorySearch');
    if (!input) return;
    let debounce = null;
    input.addEventListener('input', () => {
        clearTimeout(debounce);
        debounce = setTimeout(() => {
            hqState.historyPage = 1;
            hq_loadHistory();
        }, 300);
    });
}

async function hq_loadFilters() {
    const data = await api('/api/haiquan/history/filters');
    if (!data) return;

    const codeSel = document.getElementById('hqFilterCode');
    (data.report_codes || []).forEach(c => {
        const opt = document.createElement('option');
        opt.value = c;
        opt.textContent = c;
        codeSel.appendChild(opt);
    });
}

function hq_applyHistoryFilters() {
    hqState.filterType = document.getElementById('hqFilterType').value;
    hqState.filterCode = document.getElementById('hqFilterCode').value;
    hqState.filterSync = document.getElementById('hqFilterSync').value;
    hqState.historyPage = 1;
    // Show/hide cleanup button
    const hasFilter = hqState.filterType || hqState.filterCode || hqState.filterSync !== '';
    const btn = document.getElementById('hqBtnCleanup');
    if (btn) btn.style.display = hasFilter ? '' : 'none';
    hq_loadHistory();
}

async function hq_cleanupFiltered() {
    const filters = {};
    if (hqState.filterType) filters.report_type = hqState.filterType;
    if (hqState.filterCode) filters.report_code = hqState.filterCode;
    if (hqState.filterSync !== '') filters.drive_synced = parseInt(hqState.filterSync);
    if (Object.keys(filters).length === 0) {
        toast('Cần chọn ít nhất 1 filter để dọn dẹp', 'warning');
        return;
    }
    // Get count first
    const params = new URLSearchParams({ limit: 1, offset: 0 });
    if (filters.report_type) params.set('report_type', filters.report_type);
    if (filters.report_code) params.set('report_code', filters.report_code);
    if (filters.drive_synced !== undefined) params.set('drive_synced', filters.drive_synced);
    const peek = await api(`/api/haiquan/history?${params}`);
    const count = peek?.total || 0;
    if (count === 0) { toast('Không có records nào', 'info'); return; }

    if (!confirm(`Xác nhận xóa ${count} records + files tương ứng?`)) return;

    const resp = await api('/api/haiquan/history/cleanup', {
        method: 'DELETE',
        body: JSON.stringify(filters),
    }, true);
    if (resp) {
        toast(`🗑 Đã xóa ${resp.deleted_records || 0} records, ${resp.deleted_files || 0} files`, 'success');
        hq_loadStats();
        hq_loadHistory();
    }
}

// ── HQ History ─────────────────────────────────────────────────────────────
async function hq_loadHistory() {
    hqState.historySearch = (document.getElementById('hqHistorySearch')?.value || '').trim();

    const params = new URLSearchParams({
        limit: hqState.historyLimit,
        offset: (hqState.historyPage - 1) * hqState.historyLimit,
        sort_by: hqState.sortBy,
        sort_dir: hqState.sortDir,
    });

    if (hqState.historySearch) params.set('search', hqState.historySearch);
    if (hqState.filterType) params.set('report_type', hqState.filterType);
    if (hqState.filterCode) params.set('report_code', hqState.filterCode);
    if (hqState.filterSync !== '') params.set('drive_synced', hqState.filterSync);

    const data = await api(`/api/haiquan/history?${params}`);
    if (!data) return;

    const body = document.getElementById('hqHistoryBody');
    if (!data.records || !data.records.length) {
        body.innerHTML = '<tr><td colspan="8" class="empty-row">Chưa có dữ liệu</td></tr>';
        document.getElementById('hqPagination').innerHTML = '';
        return;
    }

    body.innerHTML = data.records.map(r => {
        const synced = r.drive_synced === 1;
        const syncIcon = synced
            ? '<span class="sync-icon sync-ok" title="Đã đồng bộ">✔</span>'
            : '<span class="sync-icon sync-no" title="Chưa đồng bộ">✖</span>';
        return `
        <tr>
            <td title="${r.source_url || ''}">${r.filename || '-'}</td>
            <td class="num">${r.year || '-'}</td>
            <td>${r.period || '-'}</td>
            <td><span class="type-badge">${r.report_type || '-'}</span></td>
            <td>${r.report_code || '-'}</td>
            <td class="size-cell">${hq_formatSize(r.file_size)}</td>
            <td class="sync-cell">${syncIcon}</td>
            <td class="date-cell">${hq_formatDate(r.downloaded_at)}</td>
        </tr>`;
    }).join('');

    // Update count badge
    const countEl = document.getElementById('hqHistoryCount');
    if (countEl) countEl.textContent = `${data.total} records`;

    hq_renderPagination(data.total);
}

function hq_renderPagination(total) {
    const pages = Math.ceil(total / hqState.historyLimit);
    const container = document.getElementById('hqPagination');
    if (pages <= 1) { container.innerHTML = ''; return; }

    let html = `<button class="page-btn" onclick="hq_goPage(${hqState.historyPage - 1})" ${hqState.historyPage <= 1 ? 'disabled' : ''}>←</button>`;
    const start = Math.max(1, hqState.historyPage - 2);
    const end = Math.min(pages, hqState.historyPage + 2);
    for (let i = start; i <= end; i++) {
        html += `<button class="page-btn ${i === hqState.historyPage ? 'active' : ''}" onclick="hq_goPage(${i})">${i}</button>`;
    }
    html += `<button class="page-btn" onclick="hq_goPage(${hqState.historyPage + 1})" ${hqState.historyPage >= pages ? 'disabled' : ''}>→</button>`;
    container.innerHTML = html;
}

function hq_goPage(page) {
    hqState.historyPage = page;
    hq_loadHistory();
}

function hq_sort(col) {
    if (hqState.sortBy === col) {
        hqState.sortDir = hqState.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
        hqState.sortBy = col;
        hqState.sortDir = col === 'downloaded_at' ? 'desc' : 'asc';
    }
    hqState.historyPage = 1;
    hq_loadHistory();
    hq_updateSortArrows();
}

function hq_updateSortArrows() {
    document.querySelectorAll('#hqHistoryTable th.sortable').forEach(th => {
        const arrow = th.querySelector('.sort-arrow');
        const col = th.dataset.sort;
        if (col === hqState.sortBy) {
            th.classList.add('active-sort');
            if (arrow) arrow.textContent = hqState.sortDir === 'asc' ? '▲' : '▼';
        } else {
            th.classList.remove('active-sort');
            if (arrow) arrow.textContent = '↕';
        }
    });
}

function hq_updateActionButtons() {
    const scraping = hqBgTask.scrape;
    const syncing = hqBgTask.drive || hqBgTask.sheet;
    document.getElementById('hqBtnScrape').disabled = scraping || syncing;
    document.getElementById('hqBtnStop').disabled = !scraping;
    document.getElementById('hqBtnSyncDrive').disabled = scraping || syncing;
    document.getElementById('hqBtnSyncSheet').disabled = scraping || syncing;
}

// ── HQ Scrape ──────────────────────────────────────────────────────────────
async function hq_startScrape() {
    const source = document.getElementById('hqSourceSelect').value;
    const yearFrom = parseInt(document.getElementById('hqYearFrom').value, 10);
    const yearTo = parseInt(document.getElementById('hqYearTo').value, 10);
    const reportType = document.getElementById('hqReportTypeFilter').value;

    const config = { source, year_from: yearFrom, year_to: yearTo };
    if (reportType) config.report_type = reportType;

    const resp = await api('/api/haiquan/scrape', {
        method: 'POST',
        body: JSON.stringify(config),
    });

    if (resp && resp.status === 'started') {
        document.getElementById('hqProgressCard').style.display = '';
        hqBgTask.scrape = true;
        hq_updateActionButtons();
        toast('🚀 Bắt đầu tải Hải quan...', 'info');
    } else {
        toast(resp?.error || 'Không thể bắt đầu', 'error');
    }
}

async function hq_stopScrape() {
    await api('/api/haiquan/scrape/stop', { method: 'POST' });
    document.getElementById('hqBtnStop').disabled = true;
    toast('Đang dừng...', 'info');
}

// ── HQ Drive Sync ──────────────────────────────────────────────────────────
async function hq_syncDrive() {
    // Check OAuth status first (same as CafeF syncDrive)
    const status = await api('/api/oauth2/status');
    if (status && !status.connected) {
        toast('Chưa kết nối Google Drive. Đang chuyển đến trang cấp quyền...', 'info');
        if (typeof startOAuthFlow === 'function') {
            startOAuthFlow('drive');
        } else {
            toast('⚠ Chưa cấu hình Google OAuth. Vui lòng kiểm tra cài đặt.', 'error');
        }
        return;
    }

    hqBgTask.drive = true;
    hq_updateActionButtons();
    toast('☁ Đang khởi tạo sync Drive Hải quan...', 'info');

    const resp = await api('/api/haiquan/gdrive/sync', { method: 'POST' }, true);
    if (!resp) {
        hqBgTask.drive = false;
        hq_updateActionButtons();
        return;
    }

    if (resp.status === 'started') {
        document.getElementById('hqSyncCard').style.display = '';
        toast('☁ Sync Drive Hải quan đang chạy nền', 'info');
    } else if ((resp.error || '').includes('Chưa có Google OAuth token')) {
        hqBgTask.drive = false;
        hq_updateActionButtons();
        if (typeof startOAuthFlow === 'function') {
            startOAuthFlow('drive');
        } else {
            toast(resp.error, 'error');
        }
    } else {
        hqBgTask.drive = false;
        hq_updateActionButtons();
        toast(resp.error || 'Lỗi sync', 'error');
    }
}

// ── HQ Sheet Sync ──────────────────────────────────────────────────────────
async function hq_syncSheet() {
    hqBgTask.sheet = true;
    hq_updateActionButtons();
    toast('📊 Đang sync Sheet Hải quan...', 'info');

    const resp = await api('/api/haiquan/gsheet/sync', { method: 'POST' }, true);
    hqBgTask.sheet = false;
    hq_updateActionButtons();

    if (!resp) return;
    if (resp.error) {
        toast('❌ Lỗi sync Sheet: ' + resp.error, 'error');
    } else if (resp.skipped) {
        toast('⏭ Sheet Hải quan không có thay đổi', 'info');
    } else {
        toast(`✅ Sync Sheet Hải quan hoàn tất: ${resp.rows || 0} rows`, 'success');
    }
}

// ── WebSocket Handlers (called from app.js) ────────────────────────────────
function hq_handleProgress(data) {
    const card = document.getElementById('hqProgressCard');
    if (!card) return;
    card.style.display = '';

    const status = data.status || '';
    const phase = data.phase || '';
    const current = data.current || 0;
    const total = data.total || 0;
    const filename = data.filename || data.current_file || '';
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;

    document.getElementById('hqProgressBar').style.width = pct + '%';

    // Phase-aware Vietnamese status text
    const ds = data.data_source || '';
    const dsLabel = {
        'web_crawl': '🌐 Web Crawl',
        'xlsx': '📁 File XLSX',
        'xlsx_fallback': '📁 XLSX (Fallback)',
        'xlsx+web_crawl': '📁 XLSX + 🌐 Web Crawl',
    }[ds] || '';
    const dsBadge = dsLabel ? ` [${dsLabel}]` : '';

    const phaseMap = {
        'starting': '🚀 Đang khởi tạo...',
        'loading_xlsx': '📖 Đang đọc file Excel...',
        'crawling_web': '🌐 Đang crawl customs.gov.vn...',
        'filtering': `🔍 Đang lọc dữ liệu... (${total} URLs)${dsBadge}`,
        'downloading': `📥 ${filename}${dsBadge}`,
        'done': '✅ Hoàn tất!',
        'error': `❌ Lỗi: ${data.error || 'Không xác định'}`,
    };
    document.getElementById('hqProgressFile').textContent =
        phaseMap[phase] || (filename ? `📥 ${filename}` : status);

    const stats = [];
    if (data.downloaded) stats.push(`✅ ${data.downloaded}`);
    if (data.skipped) stats.push(`⏭ ${data.skipped}`);
    if (data.failed) stats.push(`❌ ${data.failed}`);
    if (data.drive_synced) stats.push(`☁ ${data.drive_synced}`);
    document.getElementById('hqProgressStats').textContent = stats.join(' · ');
    document.getElementById('hqProgressCounts').textContent =
        total > 0 ? `${current} / ${total}` : '';

    // Error details display
    const notes = document.getElementById('hqProgressNotes');
    if (notes) {
        let html = '';
        // Last error (inline, always visible)
        if (data.last_error) {
            html += `<div class="note-item" style="color:var(--red,#ef4444)">⚠ ${filename || 'file'}: ${data.last_error}</div>`;
        }
        // Error details list (last 5)
        const errDetails = data.error_details || [];
        if (errDetails.length > 0) {
            errDetails.forEach(e => {
                html += `<div class="note-item">✖ ${e.filename}: ${e.error}</div>`;
            });
        }
        notes.innerHTML = html;
    }

    // Terminal statuses (match both 'done' and 'completed' for backward compat)
    if (status === 'done' || status === 'completed' ||
        status === 'stopped' || status === 'error') {
        hqBgTask.scrape = false;
        hq_updateActionButtons();

        if (status === 'done' || status === 'completed') {
            const dl = data.downloaded || 0;
            const sk = data.skipped || 0;
            const fl = data.failed || 0;
            toast(`✅ Tải Hải quan hoàn tất! Tải: ${dl}, Bỏ qua: ${sk}, Lỗi: ${fl}`, 'success');
            hq_loadStats();
            hq_loadHistory();
        } else if (status === 'stopped') {
            toast('⏹ Đã dừng tải Hải quan', 'info');
        } else {
            toast('❌ Lỗi tải Hải quan: ' + (data.error || 'Không xác định'), 'error');
        }
    }
}

function hq_handleSyncProgress(data) {
    const card = document.getElementById('hqSyncCard');
    if (!card) return;
    card.style.display = '';

    const phase = data.phase || 'uploading';
    const current = data.current || 0;
    const total = data.total || 0;
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;

    document.getElementById('hqSyncBar').style.width = pct + '%';

    if (phase === 'scanning') {
        document.getElementById('hqSyncPhase').textContent = '🔍 Scanning local files...';
    } else if (phase === 'listing') {
        document.getElementById('hqSyncPhase').textContent = '📋 Listing Drive files...';
    } else {
        document.getElementById('hqSyncPhase').textContent = `📤 Uploading ${current}/${total}`;
    }

    document.getElementById('hqSyncFile').textContent = data.filename || '';

    if (data.elapsed_s && current > 0 && total > current) {
        const remaining = (data.elapsed_s / current) * (total - current);
        const min = Math.floor(remaining / 60);
        const sec = Math.floor(remaining % 60);
        document.getElementById('hqSyncEta').textContent = `ETA: ${min}m ${sec}s`;
    }

    const counts = [];
    if (data.uploaded) counts.push(`⬆️ ${data.uploaded}`);
    if (data.skipped) counts.push(`⏭ ${data.skipped}`);
    if (data.errors) counts.push(`❌ ${data.errors}`);
    document.getElementById('hqSyncCounts').textContent = counts.join(' · ');

    const status = data.status || '';
    if (status === 'done' || status === 'error') {
        hqBgTask.drive = false;
        hq_updateActionButtons();

        if (status === 'done') {
            toast(`✅ Sync Drive Hải quan hoàn tất: ${data.uploaded || 0} files`, 'success');
            hq_loadStats();
            hq_loadHistory();
        } else {
            toast('❌ Lỗi sync Drive: ' + (data.error || ''), 'error');
        }
    }
}

// ── Utility (isolated copy) ────────────────────────────────────────────────
function hq_formatSize(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

function hq_formatDate(dateStr) {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    return d.toLocaleDateString('vi-VN', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}
