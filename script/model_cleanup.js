// Model cleanup UI - separate from general cleanup for safety
// DISABLED until plan binding and shared-blob protection are implemented
document.addEventListener('DOMContentLoaded', () => {
    const planButton = document.getElementById('model-cleanup-plan');
    const planPanel = document.getElementById('model-cleanup-plan-panel');
    const planBody = document.getElementById('model-cleanup-plan-body');
    const statusEl = document.getElementById('model-cleanup-status');

    if (!planButton) return;

    planButton.addEventListener('click', async () => {
        statusEl.textContent = 'Planning model cleanup...';
        planButton.disabled = true;
        try {
            const res = await fetch('/api/model-cleanup/plan');
            if (!res.ok) throw new Error('Plan request failed');
            const data = await res.json();
            renderModelPlan(data);
            planPanel.hidden = false;
            statusEl.textContent = 'Review model cleanup targets.';
        } catch (e) {
            statusEl.textContent = 'Failed to plan model cleanup: ' + e.message;
        } finally {
            planButton.disabled = false;
        }
    });

    function renderModelPlan(plan) {
        planBody.replaceChildren();
        const section = document.createElement('div');
        section.className = 'box';

        const title = document.createElement('h3');
        title.textContent = plan.title || 'Model cleanup';
        section.append(title);

        if (!plan.cleanup_available) {
            const empty = document.createElement('p');
            empty.className = 'muted';
            empty.textContent = 'No model cleanup targets found.';
            section.append(empty);
            planBody.append(section);
            return;
        }

        if (plan.findings?.warning) {
            const warning = document.createElement('p');
            warning.className = 'muted';
            warning.textContent = plan.findings.warning;
            section.append(warning);
        }

        const disabled = document.createElement('p');
        disabled.className = 'has-text-danger';
        disabled.textContent = '⚠️ Model cleanup is currently DISABLED.';
        section.append(disabled);

        const reason = document.createElement('p');
        reason.className = 'muted';
        reason.textContent = 'Model cleanup requires plan binding and shared-blob protection before it can be safely enabled.';
        section.append(reason);

        const scope = document.createElement('p');
        scope.className = 'muted';
        scope.textContent = 'When enabled, this will delete manifests containing message layers (saved sessions) and their associated message blobs. Model weights and other layers will never be deleted.';
        section.append(scope);

        const targets = Array.isArray(plan.findings?.targets) ? plan.findings.targets : [];
        const table = document.createElement('table');
        table.className = 'table is-fullwidth';
        const thead = document.createElement('thead');
        const headRow = document.createElement('tr');
        for (const label of ['Manifest', 'Context', 'Message Blobs']) {
            const th = document.createElement('th');
            th.textContent = label;
            headRow.append(th);
        }
        thead.append(headRow);
        const tbody = document.createElement('tbody');
        for (const target of targets) {
            const row = document.createElement('tr');
            const manifestCell = document.createElement('td');
            manifestCell.textContent = target.manifest_path ?? '—';
            const contextCell = document.createElement('td');
            contextCell.textContent = target.context ?? '—';
            const blobsCell = document.createElement('td');
            blobsCell.textContent = Array.isArray(target.message_blobs) ? target.message_blobs.length + ' blob(s)' : '—';
            row.append(manifestCell, contextCell, blobsCell);
            tbody.append(row);
        }
        table.append(thead, tbody);
        section.append(table);

        const button = document.createElement('button');
        button.className = 'button is-danger';
        button.disabled = true;
        button.textContent = 'Delete model targets (DISABLED)';
        button.type = 'button';
        section.append(button);

        const note = document.createElement('p');
        note.className = 'muted';
        note.textContent = 'Execution is disabled until safety features are implemented.';
        section.append(note);

        planBody.append(section);
    }
});
