// Green Agent Leaderboard JavaScript
let leaderboardData = null;
let filteredData = null;
let currentView = 'table';
let currentFilter = 'all';

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
        filteredData = Object.values(leaderboardData.agents);
        
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
    
    updateSummaryStats();
    updateLastUpdated();
    updateLeaderboard();
    updateCharts();
}

// Update summary statistics
function updateSummaryStats() {
    const summary = leaderboardData.summary;
    const agents = leaderboardData.agents;
    
    document.getElementById('totalAgents').textContent = leaderboardData.total_agents || Object.keys(agents).length;
    document.getElementById('avgRating').textContent = summary.avg_rating || 'N/A';
    document.getElementById('avgBB').textContent = summary.avg_bb_per_100 ? formatBB(summary.avg_bb_per_100) : 'N/A';
    document.getElementById('totalHands').textContent = formatNumber(summary.total_hands_played || 0);
}

// Update last updated timestamp
function updateLastUpdated() {
    const lastUpdated = new Date(leaderboardData.last_updated);
    document.getElementById('lastUpdated').textContent = 'Last updated: ' + lastUpdated.toLocaleString();
}

// Update leaderboard display
function updateLeaderboard() {
    if (currentView === 'table') {
        updateTableView();
    } else {
        updateCardsView();
    }
}

// Update table view
function updateTableView() {
    const tbody = document.getElementById('leaderboardTableBody');
    tbody.innerHTML = '';
    
    filteredData.forEach(agent => {
        const row = createTableRow(agent);
        tbody.appendChild(row);
    });
}

// Create table row for agent
function createTableRow(agent) {
    const row = document.createElement('tr');
    
    const rankClass = agent.rank <= 3 ? 'rank top-' + agent.rank : 'rank';
    const bbClass = agent.weighted_bb_per_100 >= 0 ? 'bb-positive' : 'bb-negative';
    const trendClass = 'trend-' + agent.recent_performance.trend;
    
    row.innerHTML = [
        '<td><span class="' + rankClass + '">#' + agent.rank + '</span></td>',
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

// Update cards view
function updateCardsView() {
    const container = document.getElementById('cardsView');
    container.innerHTML = '';
    
    filteredData.forEach(agent => {
        const card = createAgentCard(agent);
        container.appendChild(card);
    });
}

// Create agent card
function createAgentCard(agent) {
    const card = document.createElement('div');
    card.className = 'agent-card';
    
    const rankClass = agent.rank <= 3 ? 'top-3' : '';
    const bbClass = agent.weighted_bb_per_100 >= 0 ? 'bb-positive' : 'bb-negative';
    const trendClass = `trend-${agent.recent_performance.trend}`;
    
    card.innerHTML = `
        <div class="card-header">
            <h3><span class="rank ${rankClass}">#${agent.rank}</span> ${agent.name}</h3>
            <div class="rating">${agent.composite_rating}</div>
        </div>
        <div class="card-stats">
            <div class="stat">
                <label>BB/100:</label>
                <span class="${bbClass}">${agent.weighted_bb_per_100:+.1f}</span>
            </div>
            <div class="stat">
                <label>Hands:</label>
                <span>${formatNumber(agent.total_hands)}</span>
            </div>
            <div class="stat">
                <label>Win Rate:</label>
                <span>${(agent.win_rate * 100).toFixed(0)}%</span>
            </div>
            <div class="stat">
                <label>Consistency:</label>
                <span>${(agent.consistency * 100).toFixed(0)}%</span>
            </div>
            <div class="stat">
                <label>Trend:</label>
                <span class="trend ${trendClass}">
                    <i class="fas fa-${getTrendIcon(agent.recent_performance.trend)}"></i>
                    ${agent.recent_performance.trend}
                </span>
            </div>
        </div>
        <button class="details-btn" onclick="showAgentDetails('${agent.name}')">
            <i class="fas fa-info-circle"></i> View Details
        </button>
    `;
    
    return card;
}

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
    
    switch(category) {
        case 'positive':
            filteredData = agents.filter(agent => agent.weighted_bb_per_100 > 0);
            break;
        case 'improving':
            filteredData = agents.filter(agent => agent.recent_performance.trend === 'improving');
            break;
        case 'high-volume':
            const avgHands = agents.reduce((sum, a) => sum + a.total_hands, 0) / agents.length;
            filteredData = agents.filter(agent => agent.total_hands > avgHands);
            break;
        default:
            filteredData = agents;
    }
    
    // Sort by rank
    filteredData.sort((a, b) => a.rank - b.rank);
    
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
    
    filteredData = agents.filter(agent => 
        agent.name.toLowerCase().includes(searchTerm)
    );
    
    filteredData.sort((a, b) => a.rank - b.rank);
    updateLeaderboard();
}

// Switch between table and cards view
function switchView(viewType) {
    currentView = viewType;
    
    // Update active button
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Show/hide views
    const tableView = document.getElementById('tableView');
    const cardsView = document.getElementById('cardsView');
    
    if (viewType === 'table') {
        tableView.style.display = 'block';
        cardsView.style.display = 'none';
    } else {
        tableView.style.display = 'none';
        cardsView.style.display = 'grid';
    }
    
    updateLeaderboard();
}

// Show agent details modal
function showAgentDetails(agentName) {
    const agent = leaderboardData.agents[agentName];
    if (!agent) return;
    
    document.getElementById('modalAgentName').textContent = agent.name;
    
    const modalBody = document.getElementById('modalBody');
    modalBody.innerHTML = `
        <div class="agent-details">
            <div class="detail-section">
                <h3>Performance Metrics</h3>
                <div class="detail-grid">
                    <div class="detail-item">
                        <label>Composite Rating:</label>
                        <span class="value">${agent.composite_rating}</span>
                    </div>
                    <div class="detail-item">
                        <label>BB/100:</label>
                        <span class="value ${agent.weighted_bb_per_100 >= 0 ? 'positive' : 'negative'}">
                            ${agent.weighted_bb_per_100:+.2f}
                        </span>
                    </div>
                    <div class="detail-item">
                        <label>Total Hands:</label>
                        <span class="value">${formatNumber(agent.total_hands)}</span>
                    </div>
                    <div class="detail-item">
                        <label>Win Rate:</label>
                        <span class="value">${(agent.win_rate * 100).toFixed(1)}%</span>
                    </div>
                    <div class="detail-item">
                        <label>Consistency:</label>
                        <span class="value">${(agent.consistency * 100).toFixed(1)}%</span>
                    </div>
                    <div class="detail-item">
                        <label>Technical Quality:</label>
                        <span class="value">${(agent.technical_quality * 100).toFixed(1)}%</span>
                    </div>
                </div>
            </div>
            
            <div class="detail-section">
                <h3>Behavioral Analysis</h3>
                <div class="detail-grid">
                    <div class="detail-item">
                        <label>Behavior Score:</label>
                        <span class="value">${(agent.behavior_score * 100).toFixed(1)}%</span>
                    </div>
                    <div class="detail-item">
                        <label>Illegal Actions Rate:</label>
                        <span class="value">${(agent.avg_illegal_rate * 100).toFixed(2)}%</span>
                    </div>
                    <div class="detail-item">
                        <label>Timeout Rate:</label>
                        <span class="value">${(agent.avg_timeout_rate * 100).toFixed(2)}%</span>
                    </div>
                    <div class="detail-item">
                        <label>Runs Count:</label>
                        <span class="value">${agent.runs_count}</span>
                    </div>
                </div>
            </div>
            
            <div class="detail-section">
                <h3>Recent Performance</h3>
                <div class="detail-grid">
                    <div class="detail-item">
                        <label>Trend:</label>
                        <span class="value trend-${agent.recent_performance.trend}">
                            <i class="fas fa-${getTrendIcon(agent.recent_performance.trend)}"></i>
                            ${agent.recent_performance.trend}
                        </span>
                    </div>
                    <div class="detail-item">
                        <label>Recent BB/100 Avg:</label>
                        <span class="value">${agent.recent_performance.recent_bb_avg:+.2f}</span>
                    </div>
                    <div class="detail-item">
                        <label>Recent Runs:</label>
                        <span class="value">${agent.recent_performance.recent_runs}</span>
                    </div>
                </div>
            </div>
            
            <div class="detail-section">
                <h3>Run History</h3>
                <div class="runs-list">
                    ${agent.runs_data.map(run => `
                        <div class="run-item">
                            <strong>${run.run_name}</strong>
                            <span class="${run.bb_per_100 >= 0 ? 'positive' : 'negative'}">
                                ${run.bb_per_100:+.1f} BB/100
                            </span>
                            <span class="hands">${run.hands} hands</span>
                        </div>
                    `).join('')}
                </div>
            </div>
        </div>
    `;
    
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
            range: `${i}-${i + binSize}`,
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
                            return `${context.raw.label}: Rating ${context.raw.x}, BB/100 ${context.raw.y:+.1f}`;
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

function showError(message) {
    console.error(message);
    // You could add a toast notification here
}

function showSuccess(message) {
    console.log(message);
    // You could add a toast notification here
}

// Add number formatting for template literals
Number.prototype.toFixed = function(digits) {
    return parseFloat(this).toFixed(digits);
};

// Export for external use
window.leaderboard = {
    refresh: refreshData,
    showDetails: showAgentDetails,
    filter: filterByCategory,
    search: filterAgents
};