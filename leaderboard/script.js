// Green Agent Leaderboard JavaScript
let leaderboardData = null;
let filteredData = null;
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
    filteredData = sortAgents(Object.values(leaderboardData.agents));
        
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
    // Only table view is supported
    updateTableView();
}

// Update table view
function updateTableView() {
    const tbody = document.getElementById('leaderboardTableBody');
    tbody.innerHTML = '';
    
    filteredData.forEach((agent, idx) => {
        const row = createTableRow(agent, idx + 1); // computed rank is index + 1
        tbody.appendChild(row);
    });
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
function filterByCategory(category) {
    currentFilter = category;
    
    // Update active button
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Filter data
    const agents = Object.values(leaderboardData.agents);
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
    const agents = Object.values(leaderboardData.agents);
    
    if (!searchTerm) {
        filterByCategory(currentFilter);
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
    const agent = leaderboardData.agents[agentName];
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
    
    const agents = Object.values(leaderboardData.agents);
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
    
    const agents = Object.values(leaderboardData.agents);
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