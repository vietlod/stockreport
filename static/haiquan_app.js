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
    filterYear: '',
    filterType: '',
    filterCode: '',
    filterSync: '',
};

// ── Init (called lazily on first tab switch) ───────────────────────────────
async function hq_init() {
    await hq_loadStats();
    await hq_loadHistory();
    await hq_loadFilters();
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

// ── HQ Filters ─────────────────────────────────────────────────────────────
async function hq_loadFilters() {
    const data = await api('/api/haiquan/history/filters');
    if (!data) return;

    const yearSel = document.getElementById('hqFilterYear');
    (data.years || []).forEach(y => {
        const opt = document.createElement('option');
        opt.value = y;
        opt.textContent = y;
        yearSel.appendChild(opt);
    });

    const codeSel = document.getElementById('hqFilterCode');
    (data.report_codes || []).forEach(c => {
        const opt = document.createElement('option');
        opt.value = c;
        opt.textContent = c;
        codeSel.appendChild(opt);
    });
}

// ── HQ History ─────────────────────────────────────────────────────────────
async function hq_loadHistory() {
    hqState.filterYear = document.getElementById('hqFilterYear').value;
    hqState.filterType = document.getElementById('hqFilterType').value;
    hqState.filterCode = document.getElementById('hqFilterCode').value;
    hqState.filterSync = document.getElementById('hqFilterSync').value;

    const params = new URLSearchParams({
        limit: hqState.historyLimit,
        offset: (hqState.historyPage - 1) * hqState.historyLimit,
        sort_by: hqState.sortBy,
        sort_dir: hqState.sortDir,
    });

    if (hqState.filterYear) params.set('year', hqState.filterYear);
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
        document.getElementById('hqBtnScrape').disabled = true;
        document.getElementById('hqBtnStop').disabled = false;
        document.getElementById('hqBtnSyncDrive').disabled = true;
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
    document.getElementById('hqBtnSyncDrive').disabled = true;
    document.getElementById('hqBtnScrape').disabled = true;
    toast('☁ Đang khởi tạo sync Drive Hải quan...', 'info');

    const resp = await api('/api/haiquan/gdrive/sync', { method: 'POST' }, true);
    if (!resp) {
        document.getElementById('hqBtnSyncDrive').disabled = false;
        document.getElementById('hqBtnScrape').disabled = false;
        return;
    }

    if (resp.status === 'started') {
        document.getElementById('hqSyncCard').style.display = '';
        toast('☁ Sync Drive Hải quan đang chạy nền', 'info');
    } else {
        document.getElementById('hqBtnSyncDrive').disabled = false;
        document.getElementById('hqBtnScrape').disabled = false;
        toast(resp.error || 'Lỗi sync', 'error');
    }
}

// ── WebSocket Handlers (called from app.js) ────────────────────────────────
function hq_handleProgress(data) {
    const card = document.getElementById('hqProgressCard');
    if (!card) return;
    card.style.display = '';

    const status = data.status || '';
    const current = data.current || 0;
    const total = data.total || 0;
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;

    document.getElementById('hqProgressBar').style.width = pct + '%';
    document.getElementById('hqProgressFile').textContent = data.filename || status;

    const stats = [];
    if (data.downloaded) stats.push(`✅ ${data.downloaded}`);
    if (data.skipped) stats.push(`⏭ ${data.skipped}`);
    if (data.failed) stats.push(`❌ ${data.failed}`);
    document.getElementById('hqProgressStats').textContent = stats.join(' · ');
    document.getElementById('hqProgressCounts').textContent = `${current} / ${total}`;

    if (status === 'done' || status === 'stopped' || status === 'error') {
        document.getElementById('hqBtnScrape').disabled = false;
        document.getElementById('hqBtnStop').disabled = true;
        document.getElementById('hqBtnSyncDrive').disabled = false;

        if (status === 'done') {
            toast('✅ Tải Hải quan hoàn tất!', 'success');
            hq_loadStats();
            hq_loadHistory();
        } else if (status === 'stopped') {
            toast('⏹ Đã dừng tải Hải quan', 'info');
        } else {
            toast('❌ Lỗi tải Hải quan: ' + (data.error || ''), 'error');
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
        document.getElementById('hqBtnSyncDrive').disabled = false;
        document.getElementById('hqBtnScrape').disabled = false;

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
