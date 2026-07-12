// ========== Configuration ==========
const API_BASE = '';
let currentEntityId = null;
let currentMemoryType = 'user';
let messageChart = null;
let charChart = null;
let currentPeriod = 7;
let chartRefreshTimer = null;
let statusRefreshTimer = null;
let memoryRefreshTimer = null;
const STATUS_REFRESH_INTERVAL = 5000; // 5秒刷新一次Bot状态
const MEMORY_REFRESH_INTERVAL = 10000; // 10秒刷新一次记忆列表

// ========== Navigation ==========
function showPage(pageName) {
    document.querySelectorAll('.page').forEach(page => {
        page.classList.add('hidden');
    });

    const targetPage = document.getElementById(`page-${pageName}`);
    if (targetPage) {
        targetPage.classList.remove('hidden');
    }

    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.page === pageName) {
            item.classList.add('active');
        }
    });

    switch(pageName) {
        case 'dashboard':
            stopMemoryRefresh();
            loadDashboard();
            break;
        case 'config':
            stopChartRefresh();
            stopMemoryRefresh();
            loadConfig();
            break;
        case 'admins':
            stopChartRefresh();
            stopMemoryRefresh();
            loadAdmins();
            break;
        case 'memory':
            stopChartRefresh();
            loadMemoryList();
            startMemoryRefresh();
            break;
        case 'features':
            stopChartRefresh();
            stopMemoryRefresh();
            loadFeatures();
            break;
        default:
            stopMemoryRefresh();
    }
}

// 记忆页刷新定时器（不打断正在查看的 modal）
function startMemoryRefresh() {
    stopMemoryRefresh();
    memoryRefreshTimer = setInterval(() => {
        // 如果 modal 已经打开了就不刷新列表（避免打断用户查看详情）
        const modal = document.getElementById('memoryModal');
        if (modal && !modal.classList.contains('hidden')) return;
        loadMemoryList();
    }, MEMORY_REFRESH_INTERVAL);
}

function stopMemoryRefresh() {
    if (memoryRefreshTimer) {
        clearInterval(memoryRefreshTimer);
        memoryRefreshTimer = null;
    }
}

function navigateTo(pageName) {
    showPage(pageName);
}

// ========== Auth ==========
async function checkAuth() {
    try {
        const response = await fetch('/api/bot/status');
        if (response.status === 401) {
            window.location.href = '/';
            return false;
        }
        return true;
    } catch (error) {
        console.error('Auth check failed:', error);
        return false;
    }
}

// ========== Bot Status ==========
function startStatusRefresh() {
    stopStatusRefresh();
    checkBotStatus();
    statusRefreshTimer = setInterval(checkBotStatus, STATUS_REFRESH_INTERVAL);
}

function stopStatusRefresh() {
    if (statusRefreshTimer) {
        clearInterval(statusRefreshTimer);
        statusRefreshTimer = null;
    }
}

function renderService(boxId, dotId, textId, startBtnId, stopBtnId, info) {
    const dot = document.getElementById(dotId);
    const text = document.getElementById(textId);
    const startBtn = document.getElementById(startBtnId);
    const stopBtn = document.getElementById(stopBtnId);
    const box = document.getElementById(boxId);

    if (info.running) {
        dot.className = 'w-3 h-3 rounded-full bg-green-500 animate-pulse';
        text.textContent = `运行中 (PID ${info.pid || '?'})`;
        text.className = 'text-xs text-green-600';
        startBtn.disabled = true;
        startBtn.className = 'px-3 py-1.5 rounded-lg bg-gray-300 text-gray-500 text-sm cursor-not-allowed';
        stopBtn.disabled = false;
        stopBtn.className = 'px-3 py-1.5 rounded-lg bg-red-600 text-white text-sm hover:bg-red-700 transition';
    } else if (info.port_open) {
        // 端口开着但记录不到我们启动的 PID（用户手动开过）
        dot.className = 'w-3 h-3 rounded-full bg-yellow-500';
        text.textContent = '运行中（外部启动，无 PID 记录）';
        text.className = 'text-xs text-yellow-600';
        startBtn.disabled = true;
        startBtn.className = 'px-3 py-1.5 rounded-lg bg-gray-300 text-gray-500 text-sm cursor-not-allowed';
        stopBtn.disabled = true;
        stopBtn.className = 'px-3 py-1.5 rounded-lg bg-gray-300 text-gray-500 text-sm cursor-not-allowed';
    } else {
        dot.className = 'w-3 h-3 rounded-full bg-gray-400';
        text.textContent = '已停止';
        text.className = 'text-xs text-gray-500';
        startBtn.disabled = false;
        startBtn.className = 'px-3 py-1.5 rounded-lg bg-green-600 text-white text-sm hover:bg-green-700 transition';
        stopBtn.disabled = true;
        stopBtn.className = 'px-3 py-1.5 rounded-lg bg-gray-300 text-gray-500 text-sm cursor-not-allowed';
    }
    if (box) box.dataset.lastStatus = JSON.stringify(info);
}

async function checkBotStatus() {
    try {
        const response = await fetch('/api/bot/status');
        const data = await response.json();
        if (data.success) {
            renderService('nbBox', 'nbStatusDot', 'nbStatusText', 'nbStartBtn', 'nbStopBtn', data.data.nonebot);
            renderService('ncBox', 'ncStatusDot', 'ncStatusText', 'ncStartBtn', 'ncStopBtn', data.data.napcat);
            document.getElementById('bot-version').textContent = data.data.version || '0.1.0';
        }
    } catch (error) {
        console.error('Bot status check failed:', error);
    }
}

async function startNonebot() {
    const btn = document.getElementById('nbStartBtn');
    btn.disabled = true;
    try {
        const r = await fetch('/api/bot/start', { method: 'POST' });
        const d = await r.json();
        if (d.success) {
            document.getElementById('nbStatusText').textContent = d.message;
            document.getElementById('nbStatusText').className = 'text-xs text-blue-600';
        } else {
            alert(d.message);
        }
    } catch (e) {
        alert('启动请求失败：' + e);
    }
    // 5 秒后重新探测
    setTimeout(checkBotStatus, 5000);
}

async function stopNonebot() {
    if (!confirm('确认停止 NoneBot？')) return;
    const btn = document.getElementById('nbStopBtn');
    btn.disabled = true;
    try {
        const r = await fetch('/api/bot/stop', { method: 'POST' });
        const d = await r.json();
        if (!d.success) alert(d.message);
    } catch (e) {
        alert('停止请求失败：' + e);
    }
    setTimeout(checkBotStatus, 3000);
}

async function startNapcat() {
    const btn = document.getElementById('ncStartBtn');
    btn.disabled = true;
    try {
        const r = await fetch('/api/napcat/start', { method: 'POST' });
        const d = await r.json();
        if (d.success) {
            document.getElementById('ncStatusText').textContent = d.message;
            document.getElementById('ncStatusText').className = 'text-xs text-blue-600';
        } else {
            alert(d.message);
        }
    } catch (e) {
        alert('启动请求失败：' + e);
    }
    setTimeout(checkBotStatus, 5000);
}

async function stopNapcat() {
    if (!confirm('确认停止 NapCat？')) return;
    const btn = document.getElementById('ncStopBtn');
    btn.disabled = true;
    try {
        const r = await fetch('/api/napcat/stop', { method: 'POST' });
        const d = await r.json();
        if (!d.success) alert(d.message);
    } catch (e) {
        alert('停止请求失败：' + e);
    }
    setTimeout(checkBotStatus, 3000);
}

// ========== Dashboard ==========
const CHART_REFRESH_INTERVAL = 5000; // 5秒刷新一次图表数据

function startChartRefresh() {
    stopChartRefresh();
    chartRefreshTimer = setInterval(() => {
        loadChart(currentPeriod, true);
    }, CHART_REFRESH_INTERVAL);
}

function stopChartRefresh() {
    if (chartRefreshTimer) {
        clearInterval(chartRefreshTimer);
        chartRefreshTimer = null;
    }
}

async function loadDashboard() {
    startStatusRefresh();

    try {
        const response = await fetch('/api/dashboard');
        const data = await response.json();

        if (data.success) {
            document.getElementById('stat-entities').textContent = data.data.entities.total;
            document.getElementById('stat-users').textContent = data.data.entities.users;
            document.getElementById('stat-groups').textContent = data.data.entities.groups;
            document.getElementById('stat-messages').textContent = data.data.messages;
            document.getElementById('stat-summaries').textContent = data.data.summaries;
            document.getElementById('stat-admins').textContent = data.data.admins.total;
            document.getElementById('stat-private-admins').textContent = data.data.admins.private;
            // dashboard 的总回复条数/字数（来自 stats.assistant_chars）
            // 暂时用 reply_chars 估计回复条数（按每次对话 ≈ 1 条 AI 回复，这里仅作为初值占位，chart 加载后会覆盖）
            document.getElementById('stat-total-replies').textContent = data.data.messages.toLocaleString();
            document.getElementById('chartTotalReplies').querySelector('span:last-child').textContent = data.data.messages.toLocaleString();
            document.getElementById('chartTotalChars').querySelector('span:last-child').textContent = data.data.reply_chars.toLocaleString();
            document.getElementById('stat-total-user-messages').textContent = data.data.messages.toLocaleString();
            document.getElementById('stat-total-user-chars').textContent = data.data.chars.toLocaleString();
            document.getElementById('bot-version').textContent = data.data.version || '0.1.0';
        }
    } catch (error) {
        console.error('Failed to load dashboard:', error);
    }

    loadChart(currentPeriod);
    startChartRefresh();
}

function setPeriod(days) {
    currentPeriod = days;

    document.querySelectorAll('.period-btn').forEach(btn => {
        btn.className = 'period-btn px-4 py-2 rounded-lg text-sm font-medium transition bg-gray-100 text-gray-700 hover:bg-gray-200';
        if (parseInt(btn.dataset.days) === days) {
            btn.className = 'period-btn active px-4 py-2 rounded-lg text-sm font-medium transition bg-purple-600 text-white';
        }
    });

    loadChart(days);
}

async function loadChart(days, isAutoRefresh = false) {
    try {
        const response = await fetch(`/api/chart?days=${days}`);
        const data = await response.json();

        if (data.success) {
            const { labels, message_counts, char_counts, assistant_char_counts, reply_counts } = data.data;

            const totalUserMessages = message_counts.reduce((a, b) => a + b, 0);
            const totalUserChars = char_counts.reduce((a, b) => a + b, 0);
            const totalReplies = reply_counts.reduce((a, b) => a + b, 0);
            const totalReplyChars = assistant_char_counts.reduce((a, b) => a + b, 0);

            document.getElementById('stat-total-replies').textContent = totalReplies.toLocaleString();
            document.getElementById('chartTotalReplies').querySelector('span:last-child').textContent = totalReplies.toLocaleString();
            document.getElementById('chartTotalChars').querySelector('span:last-child').textContent = totalReplyChars.toLocaleString();
            document.getElementById('stat-total-user-messages').textContent = totalUserMessages.toLocaleString();
            document.getElementById('stat-total-user-chars').textContent = totalUserChars.toLocaleString();

            if (isAutoRefresh) {
                if (messageChart) {
                    messageChart.data.labels = labels;
                    messageChart.data.datasets[0].data = message_counts;
                    messageChart.update('none');
                }
                if (charChart) {
                    charChart.data.labels = labels;
                    charChart.data.datasets[0].data = assistant_char_counts;
                    charChart.update('none');
                }
                return;
            }

            const chartOptions = {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(0,0,0,0.05)' },
                        ticks: { color: '#6B7280', font: { size: 11 } }
                    },
                    y: {
                        grid: { color: 'rgba(0,0,0,0.05)' },
                        ticks: { color: '#6B7280' }
                    }
                }
            };

            if (messageChart) messageChart.destroy();
            if (charChart) charChart.destroy();

            const ctxMsg = document.getElementById('messageChart').getContext('2d');
            messageChart = new Chart(ctxMsg, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        data: message_counts,
                        backgroundColor: 'rgba(59, 130, 246, 0.7)',
                        borderColor: 'rgba(59, 130, 246, 1)',
                        borderWidth: 1,
                        borderRadius: 4,
                    }]
                },
                options: chartOptions
            });

            const ctxChar = document.getElementById('charChart').getContext('2d');
            charChart = new Chart(ctxChar, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        data: assistant_char_counts,
                        borderColor: 'rgba(16, 185, 129, 1)',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4,
                        pointBackgroundColor: 'rgba(16, 185, 129, 1)',
                        pointRadius: 3,
                    }]
                },
                options: {
                    ...chartOptions,
                    scales: {
                        ...chartOptions.scales,
                        y: {
                            ...chartOptions.scales.y,
                            ticks: {
                                color: '#6B7280',
                                callback: function(value) {
                                    if (value >= 1000) return (value / 1000).toFixed(1) + 'k';
                                    return value;
                                }
                            }
                        }
                    }
                }
            });
        }
    } catch (error) {
        console.error('Failed to load chart:', error);
    }
}

// ========== Config ==========
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        const data = await response.json();

        if (data.success) {
            document.getElementById('apiKey').value = data.data.api_key || '';
            document.getElementById('apiUrl').value = data.data.api_url || '';
            document.getElementById('model').value = data.data.model || '';
            document.getElementById('systemPrompt').value = data.data.system_prompt || '';
        }
    } catch (error) {
        console.error('Failed to load config:', error);
        showNotification('加载配置失败', 'error');
    }
}

async function saveConfig() {
    const apiKey = document.getElementById('apiKey').value.trim();
    const apiUrl = document.getElementById('apiUrl').value.trim();
    const model = document.getElementById('model').value.trim();
    const systemPrompt = document.getElementById('systemPrompt').value;

    if (!apiUrl || !model) {
        showNotification('API URL 和模型名称不能为空', 'error');
        return;
    }

    try {
        const payload = {
            api_url: apiUrl,
            model: model,
            system_prompt: systemPrompt
        };

        if (apiKey) {
            payload.api_key = apiKey;
        }

        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        const data = await response.json();

        if (data.success) {
            showNotification('配置已保存！', 'success');
            document.getElementById('apiKey').value = '';
        } else {
            showNotification(data.message || '保存失败', 'error');
        }
    } catch (error) {
        console.error('Failed to save config:', error);
        showNotification('保存配置失败', 'error');
    }
}

// ========== Admins ==========
async function loadAdmins() {
    try {
        const response = await fetch('/api/admins');
        const data = await response.json();

        if (data.success) {
            const superAdminList = document.getElementById('superAdminList');
            superAdminList.innerHTML = `
                <div class="flex items-center justify-between p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                    <div>
                        <p class="font-semibold text-gray-800">${data.data.super_admin || '未设置'}</p>
                        <p class="text-sm text-gray-500">总管理员</p>
                    </div>
                    <i class="fas fa-crown text-yellow-500 text-xl"></i>
                </div>
            `;

            const privateAdminList = document.getElementById('privateAdminList');
            if (data.data.private_admins.length === 0) {
                privateAdminList.innerHTML = '<p class="text-gray-500 text-center py-4">暂无私聊管理员</p>';
            } else {
                privateAdminList.innerHTML = data.data.private_admins.map(adminId => `
                    <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                        <div>
                            <p class="font-semibold text-gray-800">${adminId}</p>
                            <p class="text-sm text-gray-500">私聊管理员</p>
                        </div>
                        <button onclick="removeAdmin('${adminId}')" class="text-red-600 hover:text-red-800 transition">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `).join('');
            }
        }
    } catch (error) {
        console.error('Failed to load admins:', error);
        showNotification('加载管理员列表失败', 'error');
    }
}

async function addAdmin() {
    const adminId = document.getElementById('newAdminId').value.trim();

    if (!adminId || !adminId.match(/^\d+$/)) {
        showNotification('请输入有效的QQ号', 'error');
        return;
    }

    try {
        const response = await fetch('/api/admins', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ admin_id: adminId }),
        });

        const data = await response.json();

        if (data.success) {
            showNotification('管理员添加成功！', 'success');
            document.getElementById('newAdminId').value = '';
            loadAdmins();
        } else {
            showNotification(data.message || '添加失败', 'error');
        }
    } catch (error) {
        console.error('Failed to add admin:', error);
        showNotification('添加管理员失败', 'error');
    }
}

async function removeAdmin(adminId) {
    if (!confirm(`确定要移除管理员 ${adminId} 吗？`)) return;

    try {
        const response = await fetch(`/api/admins/${adminId}`, { method: 'DELETE' });
        const data = await response.json();

        if (data.success) {
            showNotification('管理员已移除', 'success');
            loadAdmins();
        } else {
            showNotification(data.message || '移除失败', 'error');
        }
    } catch (error) {
        console.error('Failed to remove admin:', error);
        showNotification('移除管理员失败', 'error');
    }
}

// ========== Memory ==========
async function loadMemoryList() {
    try {
        const response = await fetch(`/api/memory?type=${currentMemoryType}`);
        const data = await response.json();

        const cardList = document.getElementById('memoryCardList');

        if (!data.success || data.data.length === 0) {
            cardList.innerHTML = `
                <div class="col-span-full text-center py-12 text-gray-500">
                    <i class="fas fa-inbox text-4xl mb-4"></i>
                    <p>暂无${currentMemoryType === 'user' ? '个人' : '群聊'}记忆</p>
                </div>
            `;
            return;
        }

        cardList.innerHTML = data.data.map(entity => `
            <div class="bg-gray-50 rounded-xl p-4 hover:shadow-md transition cursor-pointer border border-gray-200" onclick="viewMemory('${entity.id}')">
                <div class="flex items-center justify-between mb-3">
                    <span class="status-badge ${entity.type === 'user' ? 'active' : 'inactive'}">
                        ${entity.type === 'user' ? '个人' : '群聊'}
                    </span>
                    <span class="text-gray-400 text-xs font-mono">${entity.number}</span>
                </div>
                <div class="grid grid-cols-2 gap-2 mb-3">
                    <div class="bg-white rounded-lg p-2 text-center">
                        <p class="text-2xl font-bold text-blue-600">${entity.messages}</p>
                        <p class="text-xs text-gray-500">消息数</p>
                    </div>
                    <div class="bg-white rounded-lg p-2 text-center">
                        <p class="text-2xl font-bold text-green-600">${entity.summaries}</p>
                        <p class="text-xs text-gray-500">总结数</p>
                    </div>
                </div>
                <div class="flex gap-2">
                    <button onclick="event.stopPropagation(); viewMemory('${entity.id}')" class="flex-1 bg-purple-100 text-purple-700 text-xs py-2 rounded-lg hover:bg-purple-200 transition">
                        <i class="fas fa-eye mr-1"></i>查看
                    </button>
                    <button onclick="event.stopPropagation(); exportMemory('${entity.id}')" class="flex-1 bg-green-100 text-green-700 text-xs py-2 rounded-lg hover:bg-green-200 transition">
                        <i class="fas fa-download mr-1"></i>导出
                    </button>
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Failed to load memory list:', error);
        showNotification('加载记忆列表失败', 'error');
    }
}

function switchMemoryTab(type) {
    currentMemoryType = type;

    document.querySelectorAll('.memory-tab').forEach(tab => {
        tab.className = 'memory-tab px-6 py-3 rounded-lg font-semibold transition bg-gray-200 text-gray-700 hover:bg-gray-300';
    });

    const activeTab = document.getElementById(`tab-${type}`);
    activeTab.className = 'memory-tab active px-6 py-3 rounded-lg font-semibold transition bg-purple-600 text-white';

    document.getElementById('memoryListTitle').textContent = type === 'user' ? '个人记忆' : '群聊记忆';

    loadMemoryList();
}

async function viewMemory(entityId) {
    currentEntityId = entityId;

    try {
        const response = await fetch(`/api/memory/${entityId}`);
        const data = await response.json();

        if (data.success) {
            const modal = document.getElementById('memoryModal');
            const title = document.getElementById('modalTitle');
            const content = document.getElementById('modalContent');

            title.textContent = `记忆详情 - ${entityId}`;

            let html = '<div class="space-y-6">';

            if (data.data.summaries && data.data.summaries.length > 0) {
                html += `<div><h4 class="text-lg font-semibold text-gray-800 mb-3"><i class="fas fa-brain text-purple-500 mr-2"></i>历史总结 (共 ${data.data.summaries.length} 条)</h4>`;
                html += '<div class="space-y-3 max-h-96 overflow-y-auto">';
                data.data.summaries.forEach((s) => {
                    const ts = s.timestamp ? new Date(s.timestamp * 1000).toLocaleString('zh-CN') : '';
                    html += `<div class="bg-purple-50 p-4 rounded-lg border-l-4 border-purple-400">
                        <div class="flex justify-between items-center mb-2">
                            <span class="text-xs font-semibold text-purple-700">#${s.index}</span>
                            <span class="text-xs text-gray-500">${ts} · ${s.length || 0} 字</span>
                        </div>
                        <p class="text-sm text-gray-700 whitespace-pre-wrap">${s.content || '(空)'}</p>
                    </div>`;
                });
                html += '</div></div>';
            }

            if (data.data.messages && data.data.messages.length > 0) {
                html += '<div><h4 class="text-lg font-semibold text-gray-800 mb-3"><i class="fas fa-comments text-blue-500 mr-2"></i>最近消息</h4>';
                html += '<div class="space-y-2 max-h-80 overflow-y-auto">';
                data.data.messages.forEach(msg => {
                    const isUser = msg.role === 'user';
                    html += `<div class="p-3 rounded-lg ${isUser ? 'bg-blue-50 border-l-4 border-blue-400' : 'bg-gray-50 border-l-4 border-gray-400'}">
                        <p class="text-xs text-gray-500 mb-1">${isUser ? '用户' : '助手'}</p>
                        <p class="text-sm text-gray-700">${msg.content || '(无内容)'}</p>
                    </div>`;
                });
                html += '</div></div>';
            }

            if ((!data.data.summaries || data.data.summaries.length === 0) && (!data.data.messages || data.data.messages.length === 0)) {
                html += '<p class="text-center text-gray-500 py-8">暂无记忆内容</p>';
            }

            html += '</div>';
            content.innerHTML = html;

            modal.classList.remove('hidden');
            modal.classList.add('flex');
        }
    } catch (error) {
        console.error('Failed to load memory detail:', error);
        showNotification('加载记忆详情失败', 'error');
    }
}

function closeModal() {
    const modal = document.getElementById('memoryModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

async function exportMemory(entityId) {
    try {
        const response = await fetch(`/api/memory/${entityId}/export`);

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const contentDisposition = response.headers.get('content-disposition');
            let filename = `${entityId}_memory.txt`;
            if (contentDisposition) {
                const match = contentDisposition.match(/filename=(.+)/);
                if (match) filename = match[1].replace(/"/g, '');
            }
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            showNotification('导出成功！', 'success');
        } else {
            showNotification('导出失败', 'error');
        }
    } catch (error) {
        console.error('Failed to export memory:', error);
        showNotification('导出失败', 'error');
    }
}

function exportCurrentMemory() {
    if (currentEntityId) {
        exportMemory(currentEntityId);
    }
}

// ========== Features ==========
async function loadFeatures() {
    try {
        const response = await fetch('/api/features');
        const data = await response.json();

        if (data.success) {
            const grid = document.getElementById('featuresGrid');
            grid.innerHTML = Object.entries(data.data).map(([key, feature]) => `
                <div class="bg-white rounded-xl shadow p-6 card">
                    <div class="flex items-start justify-between mb-4">
                        <div>
                            <h3 class="text-xl font-bold text-gray-800">${feature.name}</h3>
                            <p class="text-gray-600 text-sm mt-1">${feature.description}</p>
                        </div>
                        <span class="status-badge ${feature.enabled ? 'active' : 'inactive'}">
                            ${feature.enabled ? '已启用' : '未启用'}
                        </span>
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('Failed to load features:', error);
        showNotification('加载功能状态失败', 'error');
    }
}

// ========== Notifications ==========
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// ========== Event Listeners ==========
document.addEventListener('DOMContentLoaded', async () => {
    const isAuthenticated = await checkAuth();
    if (!isAuthenticated) return;

    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const pageName = item.dataset.page;
            showPage(pageName);
        });
    });

    document.getElementById('logoutBtn').addEventListener('click', async () => {
        try {
            await fetch('/api/logout', { method: 'POST' });
            window.location.href = '/';
        } catch (error) {
            console.error('Logout failed:', error);
        }
    });

    document.getElementById('configForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveConfig();
    });

    document.getElementById('memorySearch')?.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        document.querySelectorAll('#memoryCardList .cursor-pointer').forEach(card => {
            const text = card.textContent.toLowerCase();
            card.style.display = text.includes(searchTerm) ? '' : 'none';
        });
    });

    document.getElementById('newAdminId')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addAdmin();
    });

    document.getElementById('memoryModal')?.addEventListener('click', (e) => {
        if (e.target.id === 'memoryModal') closeModal();
    });

    showPage('dashboard');
});
