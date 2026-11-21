// Cleanup workflow: plan → review → confirm → execute → verify
document.addEventListener('DOMContentLoaded', () => {
    const planButton = document.getElementById('cleanup-plan');
    const planPanel = document.getElementById('cleanup-plan-panel');
    const resultsPanel = document.getElementById('cleanup-results-panel');
    const planBody = document.getElementById('cleanup-plan-body');
    const resultsBody = document.getElementById('cleanup-results-body');
    const statusEl = document.getElementById('cleanup-status');

    if (!planButton) return;

    let csrf = null;
    let planToken = null;
    const reveal = panel => {
        panel.hidden = false;
        const box = panel.closest('details');
        if (box) box.open = true;
    };

    planButton.addEventListener('click', async () => {
        statusEl.textContent = 'Planning cleanup...';
        planButton.disabled = true;
        try {
            const res = await fetch('/api/cleanup/plan');
            if (!res.ok) throw new Error('Plan request failed');
            const data = await res.json();
            csrf = data.csrf_token || null;
            planToken = data.plan_token || null;
            renderPlans(data.plans);
            reveal(planPanel);
            resultsPanel.hidden = true;
            statusEl.textContent = 'Review targets before execution.';
        } catch (e) {
            statusEl.textContent = 'Failed to plan cleanup: ' + e.message;
        } finally {
            planButton.disabled = false;
        }
    });

    // One delegated handler: each rendered plan section carries its own
    // consent checkbox and execute button (ids would be duplicated).
    planBody.addEventListener('click', async e => {
        const button = e.target.closest('button[data-checker-id]');
        if (!button) return;
        const section = button.closest('.box') || planBody;
        const consent = section.querySelector('input.cleanup-consent');
        if (!consent || !consent.checked) {
            statusEl.textContent = 'You must confirm the exact targets.';
            return;
        }
        const checkerId = button.dataset.checkerId;

        statusEl.textContent = 'Executing cleanup...';
        button.disabled = true;
        planButton.disabled = true;
        try {
            const res = await fetch('/api/cleanup/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json', 'X-OPC-CSRF': csrf || ''},
                body: JSON.stringify({checker_id: checkerId, plan_token: planToken, confirmed: true})
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.error || 'Execute request failed');
            renderResults(data);
            reveal(resultsPanel);
            planPanel.hidden = true;
            statusEl.textContent = 'Cleanup complete. Review results.';
        } catch (e) {
            statusEl.textContent = 'Cleanup failed: ' + e.message;
        } finally {
            button.disabled = false;
            planButton.disabled = false;
        }
    });

    function renderPlans(plans) {
        planBody.replaceChildren();
        for (const plan of plans) {
            // Skip saved_models - it has separate model cleanup endpoint
            if (plan.id === 'saved_models') continue;
            if (!plan.cleanup_available) continue;

            const section = document.createElement('article');
            section.className = 'box';

            const title = document.createElement('h3');
            title.textContent = plan.title || plan.id || 'Cleanup plan';
            section.append(title);

            if (plan.findings?.warning) {
                const warning = document.createElement('p');
                warning.className = 'muted';
                warning.textContent = plan.findings.warning;
                section.append(warning);
            }
            if (plan.findings?.requires_ollama_stop) {
                const stop = document.createElement('p');
                stop.className = 'has-text-warning';
                stop.textContent = '⚠️ Ollama should be stopped before proceeding.';
                section.append(stop);
            }

            const targets = Array.isArray(plan.findings?.targets) ? plan.findings.targets : [];
            const table = document.createElement('table');
            table.className = 'table is-fullwidth';
            const thead = document.createElement('thead');
            const headRow = document.createElement('tr');
            for (const label of ['Target', 'Context', 'Size', 'Modified']) {
                const th = document.createElement('th');
                th.textContent = label;
                headRow.append(th);
            }
            thead.append(headRow);
            const tbody = document.createElement('tbody');
            for (const target of targets) {
                const row = document.createElement('tr');
                const pathCell = document.createElement('td');
                pathCell.textContent = target.path ?? '—';
                const contextCell = document.createElement('td');
                contextCell.textContent = target.context ?? '—';
                const sizeCell = document.createElement('td');
                sizeCell.textContent = target.size_bytes ? formatBytes(target.size_bytes) : '—';
                const modifiedCell = document.createElement('td');
                modifiedCell.textContent = target.modified_at || '—';
                row.append(pathCell, contextCell, sizeCell, modifiedCell);
                tbody.append(row);
            }
            table.append(thead, tbody);
            section.append(table);

            const button = document.createElement('button');
            button.className = 'button is-danger';
            button.dataset.checkerId = plan.id;
            button.textContent = 'Delete selected targets';
            button.type = 'button';
            section.append(button);

            const label = document.createElement('label');
            const consent = document.createElement('input');
            consent.type = 'checkbox';
            consent.className = 'cleanup-consent';
            label.append(consent, document.createTextNode(' I approve these exact deletions'));
            section.append(label);

            planBody.append(section);
        }
        if (planBody.children.length === 0) {
            const empty = document.createElement('p');
            empty.className = 'muted';
            empty.textContent = 'No cleanup targets found. All areas are already clean.';
            planBody.append(empty);
        }
    }

    function renderResults(data) {
        resultsBody.replaceChildren();
        const result = data.result || {};
        const results = Array.isArray(result.results) ? result.results : [];
        const verification = data.verification || {};
        const counts = {};
        for (const item of results) {
            const status = item.status || 'unknown';
            counts[status] = (counts[status] || 0) + 1;
        }
        const statusLabel = {deleted: 'Deleted', failed: 'Failed', skipped: 'Skipped', access_denied: 'Access denied'};

        const heading = document.createElement('h3');
        heading.textContent = 'Execution Results';
        resultsBody.append(heading);

        const summary = document.createElement('ul');
        for (const [status, label] of Object.entries(statusLabel)) {
            if (!counts[status]) continue;
            const item = document.createElement('li');
            const strong = document.createElement('strong');
            strong.textContent = label + ':';
            item.append(strong, document.createTextNode(' ' + counts[status]));
            summary.append(item);
        }
        resultsBody.append(summary);

        if (results.length) {
            const table = document.createElement('table');
            table.className = 'table is-fullwidth';
            const thead = document.createElement('thead');
            const headRow = document.createElement('tr');
            for (const label of ['Target', 'Status', 'Detail']) {
                const th = document.createElement('th');
                th.textContent = label;
                headRow.append(th);
            }
            thead.append(headRow);
            const tbody = document.createElement('tbody');
            for (const item of results) {
                const row = document.createElement('tr');
                const targetCell = document.createElement('td');
                targetCell.textContent = item.path || item.manifest_path || '';
                const statusCell = document.createElement('td');
                statusCell.textContent = item.status || '';
                const detailCell = document.createElement('td');
                detailCell.textContent = item.reason || '';
                row.append(targetCell, statusCell, detailCell);
                tbody.append(row);
            }
            table.append(thead, tbody);
            resultsBody.append(table);
        }

        if (result.note) {
            const note = document.createElement('p');
            note.className = 'muted';
            note.textContent = result.note;
            resultsBody.append(note);
        }

        const verifyHeading = document.createElement('h3');
        verifyHeading.textContent = 'Verification';
        resultsBody.append(verifyHeading);
        const findings = verification.findings || {};
        const metrics = Object.entries(findings).filter(([, value]) => typeof value === 'number');
        if (metrics.length) {
            const list = document.createElement('ul');
            for (const [key, value] of metrics) {
                const item = document.createElement('li');
                item.textContent = key.replace(/_/g, ' ') + ': ' + value;
                list.append(item);
            }
            resultsBody.append(list);
        } else {
            const empty = document.createElement('p');
            empty.className = 'muted';
            empty.textContent = 'Post-cleanup inspection completed; no summary metrics reported.';
            resultsBody.append(empty);
        }
    }

    function formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
});
