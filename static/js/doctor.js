document.addEventListener('DOMContentLoaded', () => {
    const patientLinks = document.querySelectorAll('.patient-link');
    const patientDetailsContainer = document.getElementById('patient-details-container');
    let charts = {};
    let currentPatientUid = null;

    patientLinks.forEach(link => {
        link.addEventListener('click', async (e) => {
            e.preventDefault();
            patientLinks.forEach(l => l.classList.remove('active'));
            e.currentTarget.classList.add('active');
            currentPatientUid = e.currentTarget.dataset.uid;
            
            patientDetailsContainer.innerHTML = '<div id="patient-details"><p>Loading analysis...</p></div>';
            
            try {
                const response = await fetch(`/analyze-chats/${currentPatientUid}`);
                const data = await response.json();
                if (data.error) throw new Error(data.error);
                
                renderDashboard(data);
                attachSendButtonListener();

            } catch (error) {
                patientDetailsContainer.innerHTML = `<div id="patient-details"><p>Could not load analysis: ${error.message}</p></div>`;
            }
        });
    });

    function renderDashboard(data) {
        patientDetailsContainer.innerHTML = `
            <div id="patient-details">
                <h3>Clinical Summary</h3>
                <p>${data.summary || 'Not available.'}</p>
                <div class="charts-grid">
                    <div class="chart-card"><h4>Mood Timeline</h4><div id="moodTimelineChart"></div></div>
                    <div class="chart-card"><h4>Activity</h4><div id="activityChart"></div></div>
                    <div class="chart-card"><h4>Urgency</h4><div id="urgencyDoughnutChart"></div></div>
                    <div class="chart-card"><h4>Emotion Analysis</h4><div id="emotionRadarChart"></div></div>
                </div>
                <div class="chart-card"><h4>Highlights</h4><div id="highlights"></div></div>
                <div class="chart-card"><h4>Critical Flags</h4><div id="critical-flags"></div></div>
                <div class="chart-card"><h4>Keywords</h4><div id="keywords"></div></div>
                <div class="chart-card"><h4>Emoji Cloud</h4><div id="emoji-cloud"></div></div>
                <div id="direct-message-container">
                    <h3>Direct Message</h3>
                    <textarea id="direct-message-input" placeholder="Write a message..."></textarea>
                    <button id="send-direct-message-btn" class="btn">Send</button>
                </div>
            </div>
        `;
        renderAllCharts(data);
        renderInsights(data);
    }

    function renderAllCharts(data) {
        destroyCharts();
        if (data.moodTimeline) renderMoodTimeline(data.moodTimeline);
        if (data.activity) renderActivity(data.activity);
        if (data.urgencyDistribution) renderUrgencyChart(data.urgencyDistribution);
        if (data.emotionRadar) renderEmotionChart(data.emotionRadar);
    }

    function destroyCharts() {
        Object.values(charts).forEach(chart => {
            try {
                if (!chart) return;
                if (typeof chart.dispose === 'function') {
                    chart.dispose(); // ECharts
                } else if (typeof chart.destroy === 'function') {
                    chart.destroy(); // Chart.js or others
                } else if (typeof chart.detach === 'function') {
                    chart.detach(); // Chartist
                }
            } catch (e) {
                // noop
            }
        });
        charts = {};
    }

    function renderMoodTimeline(chartData) {
        const el = document.getElementById('moodTimelineChart');
        const chart = echarts.init(el);
        charts.mood = chart;
        chart.setOption({
            grid: { left: 40, right: 20, top: 10, bottom: 30 },
            xAxis: { type: 'category', data: chartData.labels, boundaryGap: false },
            yAxis: { type: 'value', min: -1, max: 1 },
            tooltip: { trigger: 'axis' },
            series: [{ type: 'line', data: chartData.data, smooth: true, areaStyle: {}, showSymbol: false }]
        });
    }

    function renderUrgencyChart(chartData) {
        const el = document.getElementById('urgencyDoughnutChart');
        const chart = echarts.init(el);
        charts.urgency = chart;
        chart.setOption({
            tooltip: { trigger: 'item' },
            series: [{
                type: 'pie', radius: ['60%', '85%'],
                data: chartData.labels.map((l, i) => ({ value: chartData.data[i], name: l })),
                animationDuration: 600
            }]
        });
    }

    function renderEmotionChart(chartData) {
        const el = document.getElementById('emotionRadarChart');
        const chart = echarts.init(el);
        charts.emotion = chart;
        chart.setOption({
            radar: { indicator: chartData.labels.map(l => ({ name: l, max: 10 })) },
            series: [{ type: 'radar', data: [{ value: chartData.data, name: 'Emotions' }] }]
        });
    }

    function renderActivity(chartData) {
        const el = document.getElementById('activityChart');
        const chart = echarts.init(el);
        charts.activity = chart;
        chart.setOption({
            grid: { left: 40, right: 10, top: 10, bottom: 30 },
            xAxis: { type: 'category', data: chartData.labels },
            yAxis: { type: 'value' },
            series: [{ type: 'bar', data: chartData.data }]
        });
    }

    function renderInsights(data) {
        const highlights = document.getElementById('highlights');
        const flags = document.getElementById('critical-flags');
        const keywords = document.getElementById('keywords');
        const emojiCloud = document.getElementById('emoji-cloud');

        if (Array.isArray(data.highlights)) {
            highlights.innerHTML = data.highlights.map(h => `<div class="inbox-message"><div class="message-header"><span class="timestamp">${h.timestamp || ''}</span></div><p>${h.message || ''}</p><small>${h.reason || ''}</small></div>`).join('');
        }
        if (Array.isArray(data.criticalFlags)) {
            flags.innerHTML = data.criticalFlags.map(f => `<div class="inbox-message"><div class="message-header"><strong>${f.category || 'Flag'}</strong><span class="timestamp">${f.timestamp || ''}</span></div><p>${f.message || ''}</p><small>Severity: ${f.severity ?? ''}</small></div>`).join('');
        }
        if (Array.isArray(data.keywords)) {
            keywords.innerHTML = data.keywords.map(k => `<span class="tag">${k.term} (${k.count})</span>`).join(' ');
        }
        if (Array.isArray(data.emojiCloud)) {
            emojiCloud.innerHTML = data.emojiCloud.map(e => `<span class="tag">${e.emoji} ${e.count}</span>`).join(' ');
        }
    }

    function getChartOptions() { return {}; }

    function attachSendButtonListener() {
        const sendBtn = document.getElementById('send-direct-message-btn');
        if (sendBtn) {
            sendBtn.addEventListener('click', async () => {
                const messageInput = document.getElementById('direct-message-input');
                const message = messageInput.value.trim();
                if (!message || !currentPatientUid) return;
                
                try {
                    const response = await fetch(`/send-direct-message/${currentPatientUid}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message })
                    });
                    const result = await response.json();
                    if (result.success) {
                        messageInput.value = '';
                        alert('Message sent!');
                    } else {
                        throw new Error(result.error);
                    }
                } catch (error) {
                    alert(`Error sending message: ${error.message}`);
                }
            });
        }
    }
});