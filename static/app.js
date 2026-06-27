/* SalesAI Pro — Frontend Logic */
const API = '';
let allLeads = [];
let campaigns = [];
let pipelineChart = null;
let currentUser = null;

// ── Auth ───────────────────────────────────────────────────────────────────────

function getToken() { return localStorage.getItem('token'); }

function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  window.location.href = '/login';
}

async function initAuth() {
  const token = getToken();
  if (!token) { window.location.href = '/login'; return false; }
  try {
    const res = await fetch('/auth/me', { headers: { 'Authorization': 'Bearer ' + token } });
    if (!res.ok) { logout(); return false; }
    currentUser = await res.json();
    localStorage.setItem('user', JSON.stringify(currentUser));
    // Update sidebar
    document.getElementById('planBadge').textContent = currentUser.plan.toUpperCase() + ' PLAN';
    document.getElementById('userEmail').textContent = currentUser.email;
    maybeShowGuide();
    return true;
  } catch(e) { logout(); return false; }
}

// ── Navigation ─────────────────────────────────────────────────────────────

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.querySelectorAll('.nav-link').forEach(l => {
    if (l.textContent.toLowerCase().includes(name.substring(0, 5))) l.classList.add('active');
  });
  const titles = {
    dashboard: 'Dashboard', leads: 'Leads', pipeline: 'Pipeline',
    campaigns: 'Campaigns', callcenter: 'Call Center', scraper: 'Lead Finder', settings: 'Settings'
  };
  document.getElementById('pageTitle').textContent = titles[name] || name;

  if (name === 'dashboard') { loadDashboard(); }
  else if (name === 'leads') { loadLeads(); }
  else if (name === 'pipeline') { loadPipeline(); }
  else if (name === 'campaigns') { loadCampaigns(); }
  else if (name === 'callcenter') { loadCallCenter(); }
  else if (name === 'scraper') { loadScraperPage(); }
  else if (name === 'settings') { checkSettings(); }
}

function loadAll() { showPage(document.getElementById('pageTitle').textContent.toLowerCase().replace(' ', '')); }

function showHelp() {
  new bootstrap.Modal(document.getElementById('welcomeModal')).show();
}

function maybeShowGuide() {
  if (!localStorage.getItem('guideShown')) {
    setTimeout(() => new bootstrap.Modal(document.getElementById('welcomeModal')).show(), 800);
  }
}

// ── API Helpers ─────────────────────────────────────────────────────────────

async function apiFetch(url, options = {}) {
  const token = getToken();
  try {
    const res = await fetch(API + url, {
      headers: { 'Content-Type': 'application/json', 'Authorization': token ? 'Bearer ' + token : '', ...options.headers },
      ...options,
    });
    if (res.status === 401) { logout(); return; }
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    return res.status === 204 ? null : res.json();
  } catch (e) {
    showToast(e.message, 'danger');
    throw e;
  }
}

function showToast(msg, type = 'success') {
  const t = document.getElementById('toast');
  const m = document.getElementById('toastMsg');
  t.className = `toast align-items-center text-white border-0 bg-${type}`;
  m.textContent = msg;
  new bootstrap.Toast(t, { delay: 4000 }).show();
}

// ── Dashboard ───────────────────────────────────────────────────────────────

async function loadDashboard() {
  try {
    const stats = await apiFetch('/scraper/dashboard-stats');
    document.getElementById('s-total').textContent = stats.total_leads;
    document.getElementById('s-interested').textContent = (stats.by_status.interested || 0) + (stats.by_status.qualified || 0);
    document.getElementById('s-won').textContent = stats.by_status.won || 0;
    document.getElementById('s-pending').textContent = stats.pending_followups;
    document.getElementById('s-calls').textContent = stats.calls_today;
    document.getElementById('s-sms').textContent = stats.sms_today;
    document.getElementById('s-emails').textContent = stats.emails_today;
    document.getElementById('s-conv').textContent = stats.conversion_rate + '%';

    const labels = Object.keys(stats.by_status);
    const values = Object.values(stats.by_status);
    const colors = labels.map(l => ({
      new:'#3b82f6', contacted:'#f59e0b', interested:'#10b981',
      qualified:'#8b5cf6', proposal:'#ec4899', won:'#22c55e', lost:'#ef4444'
    }[l] || '#6b7280'));

    if (pipelineChart) pipelineChart.destroy();
    const ctx = document.getElementById('pipelineChart').getContext('2d');
    pipelineChart = new Chart(ctx, {
      type: 'bar',
      data: { labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: 6 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } } }
    });

    loadActivityFeed();
  } catch (e) { /* handled */ }
}

async function loadActivityFeed() {
  try {
    const leads = await apiFetch('/leads?limit=5');
    const feed = document.getElementById('activityFeed');
    if (!leads.length) { feed.innerHTML = '<div class="text-muted text-center py-3">No activity yet</div>'; return; }
    feed.innerHTML = leads.map(l => `
      <div class="d-flex align-items-center py-2 border-bottom">
        <div class="me-3"><span class="badge rounded-pill badge-${l.status}">${l.status}</span></div>
        <div><div class="fw-semibold small">${l.name}</div><div class="text-muted" style="font-size:.75rem">${l.company || '—'} · ${l.health_interest || 'general wellness'}</div></div>
        <div class="ms-auto"><button class="btn btn-sm btn-outline-success" onclick="dialModal(${l.id},'${l.name}')"><i class="bi bi-telephone"></i></button></div>
      </div>`).join('');
  } catch (e) { /* handled */ }
}

// ── Leads ───────────────────────────────────────────────────────────────────

async function loadLeads() {
  const status = document.getElementById('statusFilter')?.value || '';
  const search = document.getElementById('leadSearch')?.value || '';
  let url = '/leads?limit=200';
  if (status) url += `&status=${status}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;
  try {
    allLeads = await apiFetch(url);
    renderLeadsTable(allLeads);
    loadCampaignDropdowns();
  } catch (e) { /* handled */ }
}

function filterLeads() { loadLeads(); }

function renderLeadsTable(leads) {
  const tb = document.getElementById('leadsTable');
  if (!leads.length) { tb.innerHTML = '<tr><td colspan="9" class="text-center py-4 text-muted">No leads found</td></tr>'; return; }
  tb.innerHTML = leads.map(l => `
    <tr>
      <td onclick="event.stopPropagation()"><input type="checkbox" class="lead-checkbox" value="${l.id}" onchange="updateSelection()"></td>
      <td onclick="openLeadModal(${l.id})" style="cursor:pointer"><div class="fw-semibold">${l.name}</div><div class="text-muted small">${l.company || '—'}</div></td>
      <td><a href="tel:${l.phone}" class="text-decoration-none">${l.phone || '—'}</a></td>
      <td><a href="mailto:${l.email}" class="text-decoration-none">${l.email || '—'}</a></td>
      <td><span class="badge rounded-pill badge-${l.status}">${l.status}</span></td>
      <td>
        <div class="d-flex align-items-center gap-2">
          <div class="score-bar flex-grow-1"><div class="score-fill" style="width:${l.score}%"></div></div>
          <small>${Math.round(l.score)}</small>
        </div>
      </td>
      <td><small class="text-muted">${l.health_interest || '—'}</small></td>
      <td><small class="text-muted">${l.created_at?.substring(0,10) || ''}</small></td>
      <td>
        <div class="d-flex gap-1">
          <button class="btn btn-sm btn-outline-success" title="Call" onclick="quickDial(${l.id})"><i class="bi bi-telephone"></i></button>
          <button class="btn btn-sm btn-outline-primary" title="SMS" onclick="quickSMS(${l.id})"><i class="bi bi-chat-text"></i></button>
          <button class="btn btn-sm btn-outline-warning" title="Email" onclick="quickEmail(${l.id})"><i class="bi bi-envelope"></i></button>
          <button class="btn btn-sm btn-outline-secondary" title="Edit" onclick="editLead(${l.id})"><i class="bi bi-pencil"></i></button>
          <button class="btn btn-sm btn-outline-danger" title="Delete" onclick="deleteLead(${l.id},'${l.name}')"><i class="bi bi-trash"></i></button>
        </div>
      </td>
    </tr>`).join('');
}

function toggleSelectAll(cb) {
  document.querySelectorAll('.lead-checkbox').forEach(c => c.checked = cb.checked);
  updateSelection();
}

function updateSelection() {
  const selected = document.querySelectorAll('.lead-checkbox:checked');
  const count = selected.length;
  document.getElementById('selectedCount').style.display = count ? '' : 'none';
  document.getElementById('selectedCount').textContent = count + ' selected';
  document.getElementById('callListBtn').style.display = count ? '' : 'none';
  document.getElementById('deleteSelectedBtn').style.display = count ? '' : 'none';
}

function getSelectedIds() {
  return [...document.querySelectorAll('.lead-checkbox:checked')].map(c => parseInt(c.value));
}

async function deleteLead(id, name) {
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
  try {
    await apiFetch(`/leads/${id}`, { method: 'DELETE' });
    showToast(`${name} deleted.`, 'success');
    loadLeads();
  } catch (e) { /* handled */ }
}

async function deleteSelected() {
  const ids = getSelectedIds();
  if (!ids.length) return;
  if (!confirm(`Delete ${ids.length} leads? This cannot be undone.`)) return;
  let done = 0;
  for (const id of ids) {
    try { await apiFetch(`/leads/${id}`, { method: 'DELETE' }); done++; } catch (e) {}
  }
  showToast(`${done} leads deleted.`, 'success');
  loadLeads();
}

async function editLead(id) {
  try {
    const lead = await apiFetch(`/leads/${id}`);
    document.getElementById('edit-id').value = lead.id;
    document.getElementById('edit-name').value = lead.name || '';
    document.getElementById('edit-company').value = lead.company || '';
    document.getElementById('edit-phone').value = lead.phone || '';
    document.getElementById('edit-email').value = lead.email || '';
    document.getElementById('edit-address').value = lead.address || '';
    document.getElementById('edit-status').value = lead.status || 'new';
    document.getElementById('edit-interest').value = lead.health_interest || '';
    document.getElementById('edit-painpoints').value = lead.pain_points || '';
    document.getElementById('edit-notes').value = lead.notes || '';
    new bootstrap.Modal(document.getElementById('editLeadModal')).show();
  } catch (e) { /* handled */ }
}

async function saveEditLead() {
  const id = document.getElementById('edit-id').value;
  const data = {
    name: document.getElementById('edit-name').value.trim(),
    company: document.getElementById('edit-company').value.trim(),
    phone: document.getElementById('edit-phone').value.trim(),
    email: document.getElementById('edit-email').value.trim(),
    address: document.getElementById('edit-address').value.trim(),
    status: document.getElementById('edit-status').value,
    health_interest: document.getElementById('edit-interest').value.trim(),
    pain_points: document.getElementById('edit-painpoints').value.trim(),
    notes: document.getElementById('edit-notes').value.trim(),
  };
  try {
    await apiFetch(`/leads/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
    bootstrap.Modal.getInstance(document.getElementById('editLeadModal')).hide();
    showToast('Lead updated!', 'success');
    loadLeads();
  } catch (e) { /* handled */ }
}

async function startCallList() {
  const ids = getSelectedIds();
  if (!ids.length) return;
  if (!confirm(`Start calling ${ids.length} leads one by one? Each call will be placed with a 5-second delay.`)) return;
  let called = 0, failed = 0;
  for (const id of ids) {
    try {
      await apiFetch(`/calls/dial/${id}`, { method: 'POST' });
      called++;
      showToast(`Call ${called}/${ids.length} initiated...`, 'success');
    } catch (e) { failed++; }
    if (id !== ids[ids.length - 1]) await new Promise(r => setTimeout(r, 5000));
  }
  showToast(`Call list complete: ${called} initiated, ${failed} failed.`, called > 0 ? 'success' : 'danger');
  loadLeads();
}

async function openLeadModal(leadId) {
  const modal = new bootstrap.Modal(document.getElementById('leadModal'));
  const body = document.getElementById('leadModalBody');
  body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-success"></div></div>';
  modal.show();
  try {
    const [lead, interactions, followups] = await Promise.all([
      apiFetch(`/leads/${leadId}`),
      apiFetch(`/leads/${leadId}/interactions`),
      apiFetch(`/leads/${leadId}/followups`),
    ]);
    document.getElementById('leadModalTitle').textContent = lead.name + ' — ' + (lead.company || '');
    body.innerHTML = `
      <div class="col-md-4">
        <div class="mb-2"><strong>Status:</strong> <span class="badge rounded-pill badge-${lead.status}">${lead.status}</span></div>
        <div class="mb-2"><strong>Score:</strong> ${Math.round(lead.score)}/100</div>
        <div class="mb-2"><strong>Phone:</strong> ${lead.phone || '—'}</div>
        <div class="mb-2"><strong>Email:</strong> ${lead.email || '—'}</div>
        <div class="mb-2"><strong>Address:</strong> <small>${lead.address || '—'}</small></div>
        <div class="mb-2"><strong>Health Interest:</strong> <small>${lead.health_interest || '—'}</small></div>
        <div class="mb-2"><strong>Pain Points:</strong> <small>${lead.pain_points || '—'}</small></div>
        <div class="mb-2"><strong>Source:</strong> <span class="badge bg-secondary">${lead.source}</span></div>
        <hr>
        <div class="d-flex flex-column gap-2">
          <button class="btn btn-success btn-sm" onclick="quickDial(${lead.id})"><i class="bi bi-telephone me-1"></i>Call Now</button>
          <button class="btn btn-primary btn-sm" onclick="quickSMS(${lead.id})"><i class="bi bi-chat-text me-1"></i>Send SMS</button>
          <button class="btn btn-warning btn-sm" onclick="quickEmail(${lead.id})"><i class="bi bi-envelope me-1"></i>Send Email</button>
          <button class="btn btn-outline-secondary btn-sm" onclick="rescoreLead(${lead.id})"><i class="bi bi-stars me-1"></i>Re-score Lead</button>
          <button class="btn btn-outline-secondary btn-sm" onclick="bootstrap.Modal.getInstance(document.getElementById('leadModal')).hide();editLead(${lead.id})"><i class="bi bi-pencil me-1"></i>Edit Lead</button>
          <button class="btn btn-outline-danger btn-sm" onclick="bootstrap.Modal.getInstance(document.getElementById('leadModal')).hide();deleteLead(${lead.id},'${lead.name}')"><i class="bi bi-trash me-1"></i>Delete Lead</button>
        </div>
      </div>
      <div class="col-md-4">
        <div class="card"><div class="card-header" style="font-size:.85rem">Interaction History (${interactions.length})</div>
        <div class="card-body p-2" style="max-height:300px;overflow-y:auto">
          ${interactions.length ? interactions.map(i => `
            <div class="border-bottom py-2">
              <div class="d-flex justify-content-between"><span class="badge bg-secondary">${i.type}</span><small class="text-muted">${i.created_at?.substring(0,10)}</small></div>
              <small class="text-muted">${i.outcome || '—'}</small>
              ${i.recording_url ? `<br><a href="${i.recording_url}" target="_blank" class="small"><i class="bi bi-play-circle me-1"></i>Listen</a>` : ''}
            </div>`).join('') : '<p class="text-muted small text-center py-2">No interactions yet</p>'}
        </div></div>
      </div>
      <div class="col-md-4">
        <div class="card"><div class="card-header" style="font-size:.85rem">Scheduled Follow-ups</div>
        <div class="card-body p-2" style="max-height:300px;overflow-y:auto">
          ${followups.length ? followups.map(f => `
            <div class="border-bottom py-2">
              <div class="d-flex justify-content-between">
                <span class="badge bg-${f.status === 'sent' ? 'success' : f.status === 'failed' ? 'danger' : 'info'}">${f.type}</span>
                <small class="text-muted">${f.scheduled_at?.substring(0,10)}</small>
              </div>
              <small class="text-muted">${f.status}</small>
            </div>`).join('') : '<p class="text-muted small text-center py-2">No follow-ups scheduled</p>'}
        </div></div>
      </div>`;
  } catch (e) { body.innerHTML = '<div class="text-danger">Failed to load lead details</div>'; }
}

async function addLead() {
  const data = {
    name: document.getElementById('ln-name').value.trim(),
    company: document.getElementById('ln-company').value.trim(),
    phone: document.getElementById('ln-phone').value.trim(),
    email: document.getElementById('ln-email').value.trim(),
    address: document.getElementById('ln-address').value.trim(),
    health_interest: document.getElementById('ln-interest').value.trim(),
    notes: document.getElementById('ln-notes').value.trim(),
    campaign_id: document.getElementById('ln-campaign').value || null,
  };
  if (!data.name) { showToast('Name is required', 'warning'); return; }
  try {
    await apiFetch('/leads?auto_schedule=true', { method: 'POST', body: JSON.stringify(data) });
    bootstrap.Modal.getInstance(document.getElementById('addLeadModal')).hide();
    showToast('Lead added! Follow-up sequence scheduled.', 'success');
    loadLeads();
  } catch (e) { /* handled */ }
}

async function importCSV() {
  const file = document.getElementById('csvFile').files[0];
  if (!file) { showToast('Select a CSV file first', 'warning'); return; }
  const campaignId = document.getElementById('import-campaign').value;
  const form = new FormData();
  form.append('file', file);
  const url = `/leads/import/csv${campaignId ? '?campaign_id=' + campaignId : ''}`;
  try {
    const res = await fetch(API + url, { method: 'POST', body: form });
    const data = await res.json();
    const div = document.getElementById('importResult');
    div.style.display = '';
    div.className = `alert alert-${res.ok ? 'success' : 'danger'}`;
    div.innerHTML = res.ok
      ? `<strong>${data.imported} leads imported!</strong> ${data.errors.length ? data.errors.length + ' skipped.' : ''}`
      : `Import failed: ${data.detail}`;
    if (res.ok) loadLeads();
  } catch (e) { showToast('Import failed: ' + e.message, 'danger'); }
}

// ── Pipeline ─────────────────────────────────────────────────────────────────

async function loadPipeline() {
  try {
    const leads = await apiFetch('/leads?limit=500');
    const statuses = ['new','contacted','interested','qualified','proposal','won','lost'];
    const colors = { new:'#3b82f6', contacted:'#f59e0b', interested:'#10b981', qualified:'#8b5cf6', proposal:'#ec4899', won:'#22c55e', lost:'#ef4444' };
    const board = document.getElementById('pipelineBoard');
    board.innerHTML = statuses.map(s => {
      const items = leads.filter(l => l.status === s);
      return `<div class="pipeline-col flex-shrink-0" style="width:220px">
        <div class="pipeline-header" style="border-left:3px solid ${colors[s]}">
          ${s.toUpperCase()} <span class="badge" style="background:${colors[s]}">${items.length}</span>
        </div>
        ${items.map(l => `
          <div class="pipeline-card" onclick="openLeadModal(${l.id})" style="border-color:${colors[s]}">
            <div class="fw-semibold">${l.name}</div>
            <div class="text-muted" style="font-size:.78rem">${l.company || '—'}</div>
            <div class="mt-1" style="font-size:.75rem">${l.health_interest || 'general wellness'}</div>
            <div class="score-bar mt-2"><div class="score-fill" style="width:${l.score}%"></div></div>
          </div>`).join('')}
      </div>`;
    }).join('');
  } catch (e) { /* handled */ }
}

// ── Campaigns ────────────────────────────────────────────────────────────────

async function setupIgnytLaunch(btn) {
  if (!confirm('This will create 2 Ignyt campaigns:\n\n1. Ignyt Pre-Launch — running now until July 4th\n2. Ignyt Freedom Run — Live (for July 4th onwards)\n\nAI will generate call scripts, SMS, and email templates for both. Continue?')) return;

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Creating campaigns & generating scripts...';

  const campaigns = [
    {
      name: 'Ignyt Freedom Run — Pre-Launch',
      company_brand: 'Ignyt',
      shop_url_override: 'https://ignyt.biz/healme',
      product_focus: 'Ignyt Metabolic Booster — natural energy and metabolism supplement launching July 4th',
      target_audience: 'health-conscious entrepreneurs, network marketers, and wellness enthusiasts',
      goal: 'Get leads to reserve their FREE spot at ignyt.biz/healme before the July 4th Freedom Run launch — the countdown is on, urgency is critical, deadline is July 4th',
    },
    {
      name: 'Ignyt Freedom Run — Live July 4th',
      company_brand: 'Ignyt',
      shop_url_override: 'https://ignyt.biz/healme',
      product_focus: 'Ignyt Metabolic Booster — now live, 50% instant payout available for distributors today',
      target_audience: 'pre-launch leads who reserved spots plus new prospects wanting energy supplements and home income',
      goal: 'Convert to buyers or distributors — Ignyt launched July 4th, 50% instant payout starts now, visit ignyt.biz/healme to join today',
    },
  ];

  let created = 0;
  for (const data of campaigns) {
    try {
      await apiFetch('/campaigns?auto_generate=true', { method: 'POST', body: JSON.stringify(data) });
      created++;
      showToast(`Campaign ${created}/2 created — generating AI scripts...`, 'info');
    } catch (e) {
      showToast(`Failed to create: ${data.name}`, 'danger');
    }
  }

  btn.disabled = false;
  btn.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i>Done!';

  if (created === 2) {
    showToast('Both Ignyt campaigns created with AI scripts! Assign leads to "Pre-Launch" to start calling.', 'success');
    document.getElementById('ignytSetupBanner')?.remove();
  }
  loadCampaigns();
  loadCampaignDropdowns();
}

async function loadCampaigns() {
  try {
    campaigns = await apiFetch('/campaigns');
    const grid = document.getElementById('campaignsGrid');
    if (!campaigns.length) { grid.innerHTML = '<div class="col-12 text-center text-muted py-4">No campaigns yet. Create your first one!</div>'; return; }
    grid.innerHTML = campaigns.map(c => `
      <div class="col-md-6 col-lg-4">
        <div class="card h-100">
          <div class="card-body">
            <div class="d-flex justify-content-between align-items-start mb-2">
              <h6 class="card-title mb-0">${c.name}</h6>
              <span class="badge bg-${c.status === 'active' ? 'success' : 'secondary'}">${c.status}</span>
            </div>
            ${c.company_brand ? `<div class="mb-2"><span class="badge" style="background:#1a5c38;font-size:.75rem"><i class="bi bi-building me-1"></i>${c.company_brand}</span>${c.shop_url_override ? ` <a href="${c.shop_url_override}" target="_blank" class="small text-muted">${c.shop_url_override.replace('https://','')}</a>` : ''}</div>` : ''}
            <div class="text-muted small mb-1"><i class="bi bi-box-seam me-1"></i>${c.product_focus || '—'}</div>
            <div class="text-muted small mb-1"><i class="bi bi-people me-1"></i>${c.target_audience || '—'}</div>
            <div class="text-muted small mb-3"><i class="bi bi-bullseye me-1"></i>${c.goal || '—'}</div>
            <div class="d-flex gap-2">
              <button class="btn btn-sm btn-outline-success flex-grow-1" onclick="viewCampaignScript(${c.id})"><i class="bi bi-file-text me-1"></i>View Script</button>
              <button class="btn btn-sm btn-outline-secondary" onclick="regenerateTemplates(${c.id})" title="Regenerate AI templates"><i class="bi bi-arrow-clockwise"></i></button>
            </div>
          </div>
        </div>
      </div>`).join('');
  } catch (e) { /* handled */ }
}

async function createCampaign() {
  const data = {
    name: document.getElementById('cn-name').value.trim(),
    company_brand: document.getElementById('cn-brand').value.trim() || null,
    shop_url_override: document.getElementById('cn-shopurl').value.trim() || null,
    product_focus: document.getElementById('cn-product').value.trim(),
    target_audience: document.getElementById('cn-audience').value.trim(),
    goal: document.getElementById('cn-goal').value.trim(),
  };
  if (!data.name) { showToast('Campaign name required', 'warning'); return; }
  const btn = document.querySelector('#addCampaignModal .btn-green');
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Generating AI templates...';
  btn.disabled = true;
  try {
    await apiFetch('/campaigns?auto_generate=true', { method: 'POST', body: JSON.stringify(data) });
    bootstrap.Modal.getInstance(document.getElementById('addCampaignModal')).hide();
    showToast('Campaign created with AI-generated templates!', 'success');
    loadCampaigns();
    loadCampaignDropdowns();
  } catch (e) { /* handled */ }
  finally { btn.innerHTML = '<i class="bi bi-magic me-1"></i>Create + Generate Templates'; btn.disabled = false; }
}

async function viewCampaignScript(id) {
  const c = await apiFetch(`/campaigns/${id}`);
  alert(`CALL SCRIPT:\n\n${c.call_script_template || 'Not generated yet'}\n\n---\nSMS:\n${c.sms_template || '—'}`);
}

async function regenerateTemplates(id) {
  if (!confirm('Regenerate AI templates for this campaign?')) return;
  try {
    await apiFetch(`/campaigns/${id}/regenerate-templates`, { method: 'POST' });
    showToast('Templates regenerated!', 'success');
  } catch (e) { /* handled */ }
}

// ── Call Center ───────────────────────────────────────────────────────────────

async function loadCallCenter() {
  try {
    const leads = await apiFetch('/leads?limit=200');
    const sel = document.getElementById('dialLeadSelect');
    sel.innerHTML = '<option value="">-- Select Lead --</option>' +
      leads.map(l => `<option value="${l.id}">${l.name} ${l.company ? '(' + l.company + ')' : ''} — ${l.phone || 'no phone'}</option>`).join('');

    // Load recent interactions
    const recent = await apiFetch('/leads?limit=20');
    // Would need a dedicated endpoint in production; using leads for now
    document.getElementById('callsTable').innerHTML = '<tr><td colspan="6" class="text-center py-3 text-muted">Use the dial button to start calls</td></tr>';
  } catch (e) { /* handled */ }
}

async function dialLead() {
  const leadId = document.getElementById('dialLeadSelect').value;
  const productFocus = document.getElementById('dialProductFocus').value.trim();
  if (!leadId) { showToast('Select a lead first', 'warning'); return; }
  const btn = event.target;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Initiating call...';
  btn.disabled = true;
  try {
    const result = await apiFetch(`/calls/dial/${leadId}${productFocus ? '?product_focus=' + encodeURIComponent(productFocus) : ''}`, { method: 'POST' });
    showToast(`Call initiated! SID: ${result.call_sid}`, 'success');
  } catch (e) { /* handled */ }
  finally { btn.innerHTML = '<i class="bi bi-telephone-fill me-2"></i>Start AI Call'; btn.disabled = false; }
}

function setObj(text) { document.getElementById('objectionInput').value = text; }

async function getObjectionResponse() {
  const objection = document.getElementById('objectionInput').value.trim();
  if (!objection) { showToast('Enter an objection first', 'warning'); return; }
  const btn = event.target;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Thinking...';
  btn.disabled = true;
  try {
    const result = await apiFetch(`/calls/objection-response?objection=${encodeURIComponent(objection)}`, { method: 'POST' });
    const div = document.getElementById('objectionResponse');
    div.style.display = '';
    div.innerHTML = `<i class="bi bi-robot me-2 text-success"></i><em>${result.response}</em>`;
  } catch (e) { /* handled */ }
  finally { btn.innerHTML = '<i class="bi bi-robot me-2"></i>Get AI Response'; btn.disabled = false; }
}

// ── Scraper ──────────────────────────────────────────────────────────────────

async function loadScraperPage() {
  try {
    const res = await apiFetch('/scraper/suggested-queries');
    const chips = document.getElementById('queryChips');
    chips.innerHTML = res.queries.slice(0, 8).map(q =>
      `<span class="objection-chip" onclick="document.getElementById('scraperQuery').value='${q}'">${q}</span>`
    ).join('');
    loadCampaignDropdowns();
    loadScraperJobs();

    // Wire up bulk search live counter
    document.getElementById('bulkCities')?.addEventListener('input', updateBulkJobCount);
    document.querySelectorAll('.bulk-query').forEach(cb => cb.addEventListener('change', updateBulkJobCount));
    updateBulkJobCount();

    // Populate bulk campaign dropdown
    const bulkSel = document.getElementById('bulkCampaign');
    if (bulkSel && campaigns.length) {
      bulkSel.innerHTML = '<option value="">None</option>' + campaigns.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
    }
  } catch (e) { /* handled */ }
}

async function startScrape() {
  const data = {
    source: document.getElementById('scraperSource').value,
    query: document.getElementById('scraperQuery').value.trim(),
    location: document.getElementById('scraperLocation').value.trim(),
    max_results: parseInt(document.getElementById('scraperMax').value) || 50,
    campaign_id: document.getElementById('scraperCampaign').value || null,
  };
  if (!data.query || !data.location) { showToast('Query and location are required', 'warning'); return; }
  try {
    const result = await apiFetch('/scraper/start', { method: 'POST', body: JSON.stringify(data) });
    showToast(`Search started! Job ID: ${result.job_id}. Refreshing status...`, 'info');
    setTimeout(loadScraperJobs, 3000);
    setTimeout(loadScraperJobs, 10000);
    setTimeout(loadScraperJobs, 30000);
  } catch (e) { /* handled */ }
}

async function loadScraperJobs() {
  try {
    const jobs = await apiFetch('/scraper/jobs');
    const tb = document.getElementById('scraperJobs');
    if (!jobs.length) { tb.innerHTML = '<tr><td colspan="8" class="text-center py-3 text-muted">No searches yet — use Bulk Search above to get started</td></tr>'; return; }
    tb.innerHTML = jobs.map(j => `
      <tr>
        <td onclick="event.stopPropagation()"><input type="checkbox" class="job-checkbox" value="${j.id}" onchange="updateJobSelection()"></td>
        <td>${j.query}</td>
        <td>${j.location}</td>
        <td><span class="badge bg-secondary">${j.source}</span></td>
        <td>${j.leads_found ?? 0}</td>
        <td class="fw-semibold text-success">${j.leads_imported ?? 0}</td>
        <td>
          <span class="badge bg-${j.status === 'completed' ? 'success' : j.status === 'failed' ? 'danger' : 'warning'}">${j.status}</span>
          ${j.error_message ? `<div class="small text-muted mt-1" style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${j.error_message}">${j.error_message}</div>` : ''}
        </td>
        <td>
          <button type="button" class="btn btn-sm btn-outline-danger" onclick="deleteJob(${j.id})" title="Delete this job and its imported leads"><i class="bi bi-trash"></i></button>
        </td>
      </tr>`).join('');
  } catch (e) { /* handled */ }
}

function toggleSelectAllJobs(cb) {
  document.querySelectorAll('.job-checkbox').forEach(c => c.checked = cb.checked);
  updateJobSelection();
}

function updateJobSelection() {
  const selected = document.querySelectorAll('.job-checkbox:checked');
  const count = selected.length;
  const countEl = document.getElementById('jobSelectedCount');
  const btnEl = document.getElementById('deleteSelectedJobsBtn');
  const allCb = document.getElementById('jobSelectAll');
  if (countEl) { countEl.style.display = count ? '' : 'none'; countEl.textContent = count + ' selected'; }
  if (btnEl) btnEl.style.display = count ? '' : 'none';
  if (allCb) allCb.indeterminate = count > 0 && count < document.querySelectorAll('.job-checkbox').length;
}

async function deleteSelectedJobs() {
  const ids = [...document.querySelectorAll('.job-checkbox:checked')].map(c => parseInt(c.value));
  if (!ids.length) return;
  if (!confirm(`Delete ${ids.length} search job(s) and their imported leads? This cannot be undone.`)) return;
  let done = 0;
  for (const id of ids) {
    try { await apiFetch(`/scraper/jobs/${id}`, { method: 'DELETE' }); done++; } catch (e) {}
  }
  showToast(`${done} job(s) deleted.`, 'success');
  loadScraperJobs();
  loadLeads();
}

async function deleteJob(jobId) {
  if (!confirm('Delete this search job and remove the leads it imported? This cannot be undone.')) return;
  try {
    const r = await apiFetch(`/scraper/jobs/${jobId}`, { method: 'DELETE' });
    showToast(`Job removed. ${r.leads_deleted} leads deleted.`, 'success');
    loadScraperJobs();
    loadLeads();
  } catch (e) { /* handled */ }
}

async function deleteAllLeads() {
  if (!confirm('Delete ALL leads in your account? This cannot be undone.')) return;
  try {
    const r = await apiFetch('/leads', { method: 'DELETE' });
    showToast(`${r.deleted} leads deleted.`, 'success');
    loadLeads();
  } catch (e) { /* handled */ }
}

// ── Quick Actions ─────────────────────────────────────────────────────────────

async function quickDial(leadId) {
  if (!confirm('Initiate AI cold call to this lead?')) return;
  try {
    const result = await apiFetch(`/calls/dial/${leadId}`, { method: 'POST' });
    showToast(`Call initiated! ${result.call_sid}`, 'success');
  } catch (e) { /* handled */ }
}

async function quickSMS(leadId) {
  try {
    const result = await apiFetch(`/calls/sms/${leadId}`, { method: 'POST' });
    showToast('SMS sent: ' + result.content?.substring(0, 50) + '...', 'success');
  } catch (e) { /* handled */ }
}

async function quickEmail(leadId) {
  try {
    await apiFetch(`/calls/email/${leadId}`, { method: 'POST' });
    showToast('Email sent!', 'success');
  } catch (e) { /* handled */ }
}

async function rescoreLead(leadId) {
  try {
    const result = await apiFetch(`/leads/${leadId}/score`, { method: 'POST' });
    showToast(`Lead score: ${result.score}/100 (${result.tier})`, 'info');
  } catch (e) { /* handled */ }
}

// ── Settings ──────────────────────────────────────────────────────────────────

async function checkSettings() {
  if (!currentUser) return;

  // Pre-fill branding fields
  document.getElementById('cred-company').value = currentUser.company_name || '';
  document.getElementById('cred-agent').value = currentUser.agent_name || '';
  document.getElementById('cred-shop').value = currentUser.shop_url || '';
  document.getElementById('cred-from-email').value = currentUser.from_email || '';
  document.getElementById('cred-from-name').value = currentUser.from_name || '';

  // Status badges
  function setBadge(id, isSet) {
    const el = document.getElementById(id);
    if (!el) return;
    el.className = isSet ? 'badge bg-success' : 'badge bg-secondary';
    el.textContent = isSet ? '✓ connected' : 'not set';
  }
  setBadge('badge-anthropic', currentUser.has_anthropic);
  setBadge('badge-twilio', currentUser.has_twilio);
  setBadge('badge-sendgrid', currentUser.has_sendgrid);
  setBadge('badge-gmaps', currentUser.has_google_maps);
  setBadge('badge-elevenlabs', currentUser.has_elevenlabs);
  setBadge('badge-yelp', currentUser.has_yelp);

  // Show subscription info
  const planNames = { starter: 'Starter — $49/mo', pro: 'Pro — $99/mo', agency: 'Agency — $199/mo' };
  const sub = document.getElementById('subscriptionInfo');
  sub.innerHTML = `
    <div class="mb-1"><strong>Plan:</strong> ${planNames[currentUser.plan] || currentUser.plan}</div>
    <div class="mb-1"><strong>Status:</strong> <span class="badge bg-${currentUser.is_active ? 'success' : 'warning'}">${currentUser.status}</span></div>
    <div class="mb-1"><strong>Leads:</strong> ${currentUser.leads_limit === -1 ? 'Unlimited' : currentUser.leads_limit}</div>
    <div><strong>Calls/mo:</strong> ${currentUser.calls_limit === -1 ? 'Unlimited' : currentUser.calls_limit}</div>
    ${currentUser.trial_ends_at ? `<div class="mt-1 text-muted small">Trial ends: ${currentUser.trial_ends_at}</div>` : ''}
  `;
}

async function saveCredentials() {
  const data = {};
  const fields = {
    'cred-anthropic': 'anthropic_api_key',
    'cred-twilio-sid': 'twilio_account_sid',
    'cred-twilio-token': 'twilio_auth_token',
    'cred-twilio-phone': 'twilio_phone_number',
    'cred-sendgrid': 'sendgrid_api_key',
    'cred-gmaps': 'google_maps_api_key',
    'cred-yelp': 'yelp_api_key',
    'cred-elevenlabs': 'elevenlabs_api_key',
    'cred-company': 'company_name',
    'cred-agent': 'agent_name',
    'cred-shop': 'shop_url',
    'cred-from-email': 'from_email',
    'cred-from-name': 'from_name',
  };
  Object.entries(fields).forEach(([id, key]) => {
    const val = document.getElementById(id)?.value?.trim();
    if (val) data[key] = val;
  });
  try {
    await apiFetch('/auth/credentials', { method: 'PATCH', body: JSON.stringify(data) });
    showToast('Settings saved!', 'success');
    await initAuth();
    checkSettings();
  } catch(e) { /* handled */ }
}

async function manageSubscription() {
  try {
    const result = await apiFetch('/billing/portal', { method: 'GET' });
    if (result?.portal_url) window.location.href = result.portal_url;
    else showToast('No active subscription. Subscribe first.', 'warning');
  } catch(e) { /* handled */ }
}

async function upgradePlan() {
  const plan = prompt('Enter plan to upgrade to: starter, pro, or agency');
  if (!plan) return;
  try {
    const result = await apiFetch('/billing/checkout', { method: 'POST', body: JSON.stringify({ plan }) });
    if (result?.checkout_url) window.location.href = result.checkout_url;
  } catch(e) { /* handled */ }
}

// ── Bulk Search ───────────────────────────────────────────────────────────────

function updateBulkJobCount() {
  const cities = (document.getElementById('bulkCities')?.value || '')
    .split('\n').map(s => s.trim()).filter(Boolean);
  const queries = [...document.querySelectorAll('.bulk-query:checked')].map(c => c.value);
  const total = cities.length * queries.length;
  const el = document.getElementById('bulkJobCount');
  if (el) el.textContent = `${total} search${total !== 1 ? 'es' : ''} queued (${cities.length} cities × ${queries.length} types)`;
}

async function startBulkSearch() {
  const cities = (document.getElementById('bulkCities')?.value || '')
    .split('\n').map(s => s.trim()).filter(Boolean);
  const queries = [...document.querySelectorAll('.bulk-query:checked')].map(c => c.value);
  const maxResults = parseInt(document.getElementById('bulkMax')?.value) || 30;
  const campaignId = document.getElementById('bulkCampaign')?.value || null;

  if (!cities.length) { showToast('Enter at least one city', 'warning'); return; }
  if (!queries.length) { showToast('Tick at least one business type', 'warning'); return; }

  const total = cities.length * queries.length;
  if (!confirm(`This will start ${total} searches across ${cities.length} cities and ${queries.length} business types.\n\nEach search finds up to ${maxResults} leads. Continue?`)) return;

  const btn = document.querySelector('[onclick="startBulkSearch()"]');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Queueing searches...';

  let queued = 0, limitHit = false;
  outer:
  for (const city of cities) {
    for (const query of queries) {
      try {
        await apiFetch('/scraper/start', {
          method: 'POST',
          body: JSON.stringify({ source: 'google_maps', query, location: city, max_results: maxResults, campaign_id: campaignId || null }),
        });
        queued++;
      } catch (e) {
        if (e.message && e.message.toLowerCase().includes('limit')) {
          limitHit = true;
          break outer;
        }
      }
      await new Promise(r => setTimeout(r, 400));
    }
  }

  btn.disabled = false;
  btn.innerHTML = '<i class="bi bi-lightning-fill me-2"></i>Start All Searches';

  if (limitHit) {
    showToast(`${queued} searches started, then stopped — lead limit reached. Upgrade your plan for more leads.`, 'warning');
  } else {
    showToast(`${queued} searches started. Watch the Search History below.`, 'success');
  }
  loadScraperJobs();
  setTimeout(loadScraperJobs, 5000);
  setTimeout(loadScraperJobs, 15000);
}

// ── Shared Helpers ────────────────────────────────────────────────────────────

async function loadCampaignDropdowns() {
  try {
    campaigns = await apiFetch('/campaigns');
    const opts = '<option value="">None</option>' + campaigns.map(c => `<option value="${c.id}">${c.name}</option>`).join('');
    ['ln-campaign','import-campaign','scraperCampaign'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = opts;
    });
  } catch (e) { /* handled */ }
}

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  const ok = await initAuth();
  if (!ok) return;
  loadDashboard();
  loadCampaignDropdowns();
});
