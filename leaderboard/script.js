// Green Agent Leaderboard JavaScript
let leaderboardData = null;
let huAgents = [];
let sixmaxRuns = [];
let filteredData = [];
let currentFilter = 'all';

function sortAgents(list) {
    // Always sort by composite rating descending; ignore any precomputed rank in JSON
    return [...list].sort((a, b) => b.composite_rating - a.composite_rating);
}

// Initialize the application
document.addEventListener('DOMContentLoaded', async function() {
    await loadLeaderboardData();
    initializeCharts();
});

// Load leaderboard data from JSON file
async function loadLeaderboardData() {
    try {
        const response = await fetch('data/leaderboard.json');
        leaderboardData = await response.json();
        huAgents = sortAgents(Object.values((leaderboardData.hu && leaderboardData.hu.agents) || {}));
        sixmaxRuns = (leaderboardData.sixmax && leaderboardData.sixmax.runs) ? [...leaderboardData.sixmax.runs] : [];
        filteredData = [...huAgents];
        
        updateUI();
        console.log('Leaderboard data loaded successfully');
    } catch (error) {
        console.error('Error loading leaderboard data:', error);
        showError('Failed to load leaderboard data. Please refresh the page.');
    }
}

// Update all UI elements
function updateUI() {
    if (!leaderboardData) return;
    
    updateLastUpdated();
    updateSixmaxBoard();
    updateLeaderboard();
    updateCharts();
}

// Update last updated timestamp
function updateLastUpdated() {
    const lastUpdated = new Date(leaderboardData.last_updated);
    document.getElementById('lastUpdated').textContent = 'Last updated: ' + lastUpdated.toLocaleString();
}

// Update leaderboard display
function updateLeaderboard() {
    // Only table view is supported (HU leaderboard)
    updateTableView();
}

// Update table view
function updateTableView() {
    const tbody = document.getElementById('leaderboardTableBody');
    tbody.innerHTML = '';
    
    if (!filteredData.length) {
        const row = document.createElement('tr');
        row.innerHTML = '<td colspan="10" class="empty-state-row">No heads-up results yet. Run HU benchmarks to populate this table.</td>';
        tbody.appendChild(row);
        return;
    }

    filteredData.forEach((agent, idx) => {
        const row = createTableRow(agent, idx + 1); // computed rank is index + 1
        tbody.appendChild(row);
    });
}

function updateSixmaxBoard() {
    const container = document.getElementById('sixmaxBoard');
    if (!container) return;

    container.innerHTML = '';

    if (!sixmaxRuns.length) {
        container.innerHTML = '<p class="empty-state">No 6-max results yet. Run a six-max benchmark to populate this board.</p>';
        return;
    }

    const globalReference = (leaderboardData.sixmax && leaderboardData.sixmax.max_abs_bb) || 1;

    sixmaxRuns.forEach(run => {
        const agents = run.agents || [];
        const reference = run.max_abs_bb > 0 ? run.max_abs_bb : globalReference;
        const card = document.createElement('div');
        card.className = 'hex-card';
        const listHtml = agents.slice(0, 6).map((agent, idx) => {
            const tone = agent.bb_per_100 >= 0 ? 'positive' : 'negative';
            return [
                '<div class="hex-player">',
                '  <span class="seat-label">Seat ' + (idx + 1) + '</span>',
                '  <span class="player-name">' + agent.name + '</span>',
                '  <span class="player-bb ' + tone + '">' + formatBB(agent.bb_per_100) + '</span>',
                '</div>'
            ].join('');
        }).join('');

        card.innerHTML = [
            '<canvas class="hex-canvas" width="500" height="500" aria-hidden="true"></canvas>',
            '<div class="hex-info">',
            '  <div class="hex-name">' + run.run_name + '</div>',
            '  <div class="hex-meta">Hands per seat: ' + formatNumber(run.hands || 0) + '</div>',
            '  <div class="hex-list">' + listHtml + '</div>',
            '</div>'
        ].join('');
        container.appendChild(card);

        const canvas = card.querySelector('canvas');
        drawRunHex(canvas, agents, reference);
    });
}

function drawRunHex(canvas, agents, reference) {
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const outerRadius = Math.min(width, height) * 0.34;

    ctx.clearRect(0, 0, width, height);

    drawHexagon(ctx, centerX, centerY, outerRadius, false, 'rgba(255,255,255,0.12)');
    drawHexagon(ctx, centerX, centerY, outerRadius * 0.55, false, 'rgba(255,255,255,0.06)');

    const seats = agents.slice(0, 6);
    if (seats.length < 3) {
        drawHexagon(ctx, centerX, centerY, outerRadius * 0.25, true, 'rgba(255,255,255,0.08)');
        return;
    }

    const angleStep = (Math.PI * 2) / seats.length;
    const points = seats.map((agent, idx) => {
        const normalized = reference ? agent.bb_per_100 / reference : 0;
        const clamped = Math.max(-1, Math.min(1, normalized));
        const magnitude = Math.abs(clamped);
        const baseRadius = outerRadius * 0.65;
        const negativeFloor = outerRadius * 0.25;
        let radius;
        if (clamped >= 0) {
            radius = baseRadius + (outerRadius - baseRadius) * magnitude;
        } else {
            radius = baseRadius - (baseRadius - negativeFloor) * magnitude;
        }
        radius = Math.max(radius, outerRadius * 0.05);
        const angle = -Math.PI / 2 + idx * angleStep;
        return {
            x: centerX + radius * Math.cos(angle),
            y: centerY + radius * Math.sin(angle),
            positive: clamped >= 0,
            angle,
            label: agent.name,
        };
    });

    const positiveShare = points.filter(pt => pt.positive).length / points.length;
    const fillColor = positiveShare >= 0.5
        ? 'rgba(67, 160, 71, 0.28)'
        : 'rgba(229, 57, 53, 0.28)';
    const strokeColor = positiveShare >= 0.5
        ? 'rgba(129, 199, 132, 0.9)'
        : 'rgba(240, 98, 100, 0.9)';

    ctx.beginPath();
    points.forEach((pt, idx) => {
        if (idx === 0) {
            ctx.moveTo(pt.x, pt.y);
        } else {
            ctx.lineTo(pt.x, pt.y);
        }
    });
    ctx.closePath();
    ctx.fillStyle = fillColor;
    ctx.fill();
    ctx.lineWidth = 2.2;
    ctx.strokeStyle = strokeColor;
    ctx.stroke();

    ctx.beginPath();
    points.forEach(pt => {
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(pt.x, pt.y);
    });
    ctx.strokeStyle = 'rgba(255,255,255,0.08)';
    ctx.lineWidth = 1;
    ctx.stroke();

    points.forEach(pt => {
        ctx.beginPath();
        ctx.arc(pt.x, pt.y, 4, 0, Math.PI * 2);
        ctx.fillStyle = pt.positive ? 'rgba(129,199,132,0.9)' : 'rgba(239,83,80,0.9)';
        ctx.fill();
    });

    ctx.font = '12px "Segoe UI", sans-serif';

    points.forEach((pt, idx) => {
        const cosA = Math.cos(pt.angle);
        const sinA = Math.sin(pt.angle);
        const horizontalMargin = 20;
        const verticalMargin = 24;

        let align = 'center';
        if (cosA > 0.25) {
            align = 'left';
        } else if (cosA < -0.25) {
            align = 'right';
        }
        ctx.textAlign = align;
        ctx.textBaseline = 'middle';

        let seatRadius = outerRadius + 18;
        let nameRadius = outerRadius + 36;
        let seatX = centerX + seatRadius * cosA;
        let seatY = centerY + seatRadius * sinA;
        let nameX = centerX + nameRadius * cosA;
        let nameY = centerY + nameRadius * sinA;

        if (align === 'left') {
            seatX = Math.min(seatX, width - horizontalMargin);
            nameX = Math.min(nameX, width - horizontalMargin);
        } else if (align === 'right') {
            seatX = Math.max(seatX, horizontalMargin);
            nameX = Math.max(nameX, horizontalMargin);
        }

        if (sinA >= 0.3) {
            seatY = Math.min(seatY + 10, height - verticalMargin);
            nameY = Math.min(nameY + 28, height - verticalMargin);
        } else if (sinA <= -0.3) {
            seatY = Math.max(seatY - 14, verticalMargin);
            nameY = Math.max(nameY - 32, verticalMargin);
        } else {
            seatY = Math.max(Math.min(seatY - 2, height - verticalMargin), verticalMargin);
            nameY = Math.max(Math.min(nameY + (sinA >= 0 ? 18 : -18), height - verticalMargin), verticalMargin);
        }

        ctx.fillStyle = 'rgba(255,255,255,0.92)';
        ctx.fillText('Seat ' + (idx + 1), seatX, seatY);

        ctx.fillStyle = 'rgba(255,255,255,0.72)';
        ctx.fillText(truncateName(pt.label, 18), nameX, nameY);
    });
}

function drawHexagon(ctx, cx, cy, radius, fill = false, fillStyle = '#fff', strokeStyle = 'rgba(255,255,255,0.3)', lineWidth = 1.5) {
    const sides = 6;
    const angleStep = (Math.PI * 2) / sides;
    ctx.beginPath();
    for (let i = 0; i <= sides; i++) {
        const angle = -Math.PI / 2 + i * angleStep;
        const x = cx + radius * Math.cos(angle);
        const y = cy + radius * Math.sin(angle);
        if (i === 0) {
            ctx.moveTo(x, y);
        } else {
            ctx.lineTo(x, y);
        }
    }
    if (fill) {
        ctx.fillStyle = fillStyle;
        ctx.fill();
    }
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
}

// Create table row for agent
function createTableRow(agent, computedRank) {
    const row = document.createElement('tr');
    
    const rank = computedRank;
    const rankClass = rank <= 3 ? 'rank top-' + rank : 'rank';
    const bbClass = agent.weighted_bb_per_100 >= 0 ? 'bb-positive' : 'bb-negative';
    const trendClass = 'trend-' + agent.recent_performance.trend;
    
    row.innerHTML = [
        '<td><span class="' + rankClass + '">#' + rank + '</span></td>',
        '<td>',
        '  <div class="agent-name">',
        '    <div class="agent-avatar">' + agent.name.charAt(0) + '</div>',
        '    ' + agent.name,
        '  </div>',
        '</td>',
        '<td><span class="rating">' + agent.composite_rating + '</span></td>',
        '<td><span class="' + bbClass + '">' + formatBB(agent.weighted_bb_per_100) + '</span></td>',
        '<td>' + formatNumber(agent.total_hands) + '</td>',
        '<td>',
        '  <div class="progress-bar">',
        '    <div class="progress-fill" style="width: ' + (agent.win_rate * 100) + '%"></div>',
        '  </div>',
        '  <small>' + (agent.win_rate * 100).toFixed(0) + '%</small>',
        '</td>',
        '<td>',
        '  <div class="progress-bar">',
        '    <div class="progress-fill" style="width: ' + (agent.consistency * 100) + '%"></div>',
        '  </div>',
        '  <small>' + (agent.consistency * 100).toFixed(0) + '%</small>',
        '</td>',
        '<td>',
        '  <div class="progress-bar">',
        '    <div class="progress-fill" style="width: ' + (agent.technical_quality * 100) + '%"></div>',
        '  </div>',
        '  <small>' + (agent.technical_quality * 100).toFixed(0) + '%</small>',
        '</td>',
        '<td>',
        '  <div class="trend ' + trendClass + '">',
        '    <i class="fas fa-' + getTrendIcon(agent.recent_performance.trend) + '"></i>',
        '    ' + agent.recent_performance.trend,
        '  </div>',
        '</td>',
        '<td>',
        '  <button class="details-btn" onclick="showAgentDetails(\'' + agent.name + '\')">',
        '    <i class="fas fa-info-circle"></i> Details',
        '  </button>',
        '</td>'
    ].join('');
    
    return row;
}

// Card view removed

// Get trend icon
function getTrendIcon(trend) {
    switch(trend) {
        case 'improving': return 'arrow-up';
        case 'declining': return 'arrow-down';
        case 'stable': return 'minus';
        default: return 'question';
    }
}

// Filter agents by category
function filterByCategory(category, button = null) {
    currentFilter = category;
    
    // Update active button
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    if (!button) {
        button = document.querySelector('.filter-btn[data-default]') || document.querySelector('.filter-btn');
    }
    if (button) {
        button.classList.add('active');
    }
    
    // Filter data
    const agents = [...huAgents];
    let results = agents;
    
    switch(category) {
        case 'positive':
            results = agents.filter(agent => agent.weighted_bb_per_100 > 0);
            break;
        case 'improving':
            results = agents.filter(agent => agent.recent_performance.trend === 'improving');
            break;
        case 'high-volume':
            const avgHands = agents.reduce((sum, a) => sum + a.total_hands, 0) / agents.length;
            results = agents.filter(agent => agent.total_hands > avgHands);
            break;
        default:
            results = agents;
    }
        results = sortAgents(results);
        filteredData = results;
    updateLeaderboard();
}

// Filter agents by search term
function filterAgents() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    const agents = [...huAgents];
    
    if (!searchTerm) {
        const activeBtn = document.querySelector('.filter-btn.active');
        filterByCategory(currentFilter, activeBtn);
        return;
    }
    
        let results = agents.filter(agent => 
        agent.name.toLowerCase().includes(searchTerm)
    );
    
        results = sortAgents(results);
        filteredData = results;
    updateLeaderboard();
}

// Switch between table and cards view
// View toggle removed; only table is available

// Show agent details modal
function showAgentDetails(agentName) {
    const agent = (leaderboardData.hu && leaderboardData.hu.agents && leaderboardData.hu.agents[agentName]) ||
                  (leaderboardData.sixmax && leaderboardData.sixmax.agents && leaderboardData.sixmax.agents[agentName]);
    if (!agent) return;
    
    document.getElementById('modalAgentName').textContent = agent.name;
    
    const modalBody = document.getElementById('modalBody');
    
    const runsHtml = agent.runs_data.map(run => 
        '<div class="run-item">' +
        '<strong>' + run.run_name + '</strong>' +
        '<span class="' + (run.bb_per_100 >= 0 ? 'positive' : 'negative') + '">' +
        formatBB(run.bb_per_100) + ' BB/100</span>' +
        '<span class="hands">' + run.hands + ' hands</span>' +
        '</div>'
    ).join('');
    
    modalBody.innerHTML = [
        '<div class="agent-details">',
        '  <div class="detail-section">',
        '    <h3>Performance Metrics</h3>',
        '    <div class="detail-grid">',
        '      <div class="detail-item">',
        '        <label>Composite Rating:</label>',
        '        <span class="value">' + agent.composite_rating + '</span>',
        '      </div>',
        '      <div class="detail-item">',
        '        <label>BB/100:</label>',
        '        <span class="value ' + (agent.weighted_bb_per_100 >= 0 ? 'positive' : 'negative') + '">',
        '          ' + formatBB(agent.weighted_bb_per_100),
        '        </span>',
        '      </div>',
        '      <div class="detail-item">',
        '        <label>Total Hands:</label>',
        '        <span class="value">' + formatNumber(agent.total_hands) + '</span>',
        '      </div>',
        '      <div class="detail-item">',
        '        <label>Win Rate:</label>',
        '        <span class="value">' + (agent.win_rate * 100).toFixed(1) + '%</span>',
        '      </div>',
        '      <div class="detail-item">',
        '        <label>Consistency:</label>',
        '        <span class="value">' + (agent.consistency * 100).toFixed(1) + '%</span>',
        '      </div>',
        '      <div class="detail-item">',
        '        <label>Technical Quality:</label>',
        '        <span class="value">' + (agent.technical_quality * 100).toFixed(1) + '%</span>',
        '      </div>',
        '    </div>',
        '  </div>',
        '  <div class="detail-section">',
        '    <h3>Behavioral Analysis</h3>',
        '    <div class="detail-grid">',
        '      <div class="detail-item">',
        '        <label>Behavior Score:</label>',
        '        <span class="value">' + (agent.behavior_score * 100).toFixed(1) + '%</span>',
        '      </div>',
        '      <div class="detail-item">',
        '        <label>Illegal Actions Rate:</label>',
        '        <span class="value">' + (agent.avg_illegal_rate * 100).toFixed(2) + '%</span>',
        '      </div>',
        '      <div class="detail-item">',
        '        <label>Timeout Rate:</label>',
        '        <span class="value">' + (agent.avg_timeout_rate * 100).toFixed(2) + '%</span>',
        '      </div>',
        '      <div class="detail-item">',
        '        <label>Runs Count:</label>',
        '        <span class="value">' + agent.runs_count + '</span>',
        '      </div>',
        '    </div>',
        '  </div>',
        '  <div class="detail-section">',
        '    <h3>Recent Performance</h3>',
        '    <div class="detail-grid">',
        '      <div class="detail-item">',
        '        <label>Trend:</label>',
        '        <span class="value trend-' + agent.recent_performance.trend + '">',
        '          <i class="fas fa-' + getTrendIcon(agent.recent_performance.trend) + '"></i>',
        '          ' + agent.recent_performance.trend,
        '        </span>',
        '      </div>',
        '      <div class="detail-item">',
        '        <label>Recent BB/100 Avg:</label>',
        '        <span class="value">' + formatBB(agent.recent_performance.recent_bb_avg) + '</span>',
        '      </div>',
        '      <div class="detail-item">',
        '        <label>Recent Runs:</label>',
        '        <span class="value">' + agent.recent_performance.recent_runs + '</span>',
        '      </div>',
        '    </div>',
        '  </div>',
        '  <div class="detail-section">',
        '    <h3>Run History</h3>',
        '    <div class="runs-list">',
        runsHtml,
        '    </div>',
        '  </div>',
        '</div>'
    ].join('');
    
    document.getElementById('agentModal').style.display = 'block';
}

// Close modal
function closeModal() {
    document.getElementById('agentModal').style.display = 'none';
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('agentModal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
}

// Initialize charts
function initializeCharts() {
    // Wait for data to load
    if (!leaderboardData) {
        setTimeout(initializeCharts, 100);
        return;
    }
    
    createRatingChart();
    createScatterChart();
}

// Create rating distribution chart
function createRatingChart() {
    const ctx = document.getElementById('ratingChart');
    if (!ctx) return;
    
    const agents = huAgents;
    if (!agents.length) return;
    const ratings = agents.map(agent => agent.composite_rating);
    
    // Create histogram bins
    const bins = [];
    const binSize = 100;
    const minRating = Math.floor(Math.min(...ratings) / binSize) * binSize;
    const maxRating = Math.ceil(Math.max(...ratings) / binSize) * binSize;
    
    for (let i = minRating; i <= maxRating; i += binSize) {
        bins.push({
            range: i + '-' + (i + binSize),
            count: ratings.filter(r => r >= i && r < i + binSize).length
        });
    }
    
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: bins.map(bin => bin.range),
            datasets: [{
                label: 'Number of Agents',
                data: bins.map(bin => bin.count),
                backgroundColor: 'rgba(52, 152, 219, 0.6)',
                borderColor: 'rgba(52, 152, 219, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                }
            }
        }
    });
}

// Create scatter chart
function createScatterChart() {
    const ctx = document.getElementById('scatterChart');
    if (!ctx) return;
    
    const agents = huAgents;
    if (!agents.length) return;
    const data = agents.map(agent => ({
        x: agent.composite_rating,
        y: agent.weighted_bb_per_100,
        label: agent.name
    }));
    
    new Chart(ctx, {
        type: 'scatter',
        data: {
            datasets: [{
                label: 'Agents',
                data: data,
                backgroundColor: 'rgba(52, 152, 219, 0.6)',
                borderColor: 'rgba(52, 152, 219, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            scales: {
                x: {
                    title: {
                        display: true,
                        text: 'Composite Rating'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'BB/100'
                    }
                }
            },
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.raw.label + ': Rating ' + context.raw.x + ', BB/100 ' + formatBB(context.raw.y);
                        }
                    }
                }
            }
        }
    });
}

// Update charts
function updateCharts() {
    // Charts will be recreated when data changes
    setTimeout(() => {
        const ratingChart = Chart.getChart('ratingChart');
        const scatterChart = Chart.getChart('scatterChart');
        
        if (ratingChart) ratingChart.destroy();
        if (scatterChart) scatterChart.destroy();
        
        createRatingChart();
        createScatterChart();
    }, 100);
}

// Refresh data
async function refreshData() {
    const refreshBtn = document.getElementById('refreshBtn');
    const originalText = refreshBtn.innerHTML;
    
    refreshBtn.innerHTML = '<div class="loading"></div> Refreshing...';
    refreshBtn.disabled = true;
    
    try {
        await loadLeaderboardData();
        showSuccess('Leaderboard data refreshed successfully!');
    } catch (error) {
        showError('Failed to refresh data. Please try again.');
    } finally {
        refreshBtn.innerHTML = originalText;
        refreshBtn.disabled = false;
    }
}

// Utility functions
function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function formatBB(bbValue) {
    const sign = bbValue >= 0 ? '+' : '';
    return sign + bbValue.toFixed(1);
}

function truncateName(name, maxLength) {
    if (!name) return '';
    return name.length > maxLength ? name.slice(0, maxLength - 1) + '…' : name;
}

function showError(message) {
    console.error(message);
    // You could add a toast notification here
}

function showSuccess(message) {
    console.log(message);
    // You could add a toast notification here
}

// Export for external use
window.leaderboard = {
    refresh: refreshData,
    showDetails: showAgentDetails,
    filter: filterByCategory,
    search: filterAgents
};
