/**
 * Job Agent Dashboard — frontend application logic.
 * Fetches data from the FastAPI backend and renders stats, tables, and charts.
 */

const API_BASE = window.location.origin;

// ─── Colour palette ────────────────────────────────────────────────────────

const COLORS = {
  adzuna: '#6366f1',
  linkedin: '#0a66c2',
  indeed: '#2164f3',
  greenhouse: '#00b294',
  lever: '#ff5722',
  workday: '#f15b2e',
  submitted: '#22c55e',
  matched: '#3b82f6',
  error: '#ef4444',
  captcha_blocked: '#f59e0b',
  pending: '#8b8fa0',
};

// ─── State ─────────────────────────────────────────────────────────────────

let latestProfile = null;   // Last parsed profile from /api/profiles/parse
let latestProfileId = null; // DB profile ID


// ─── Initialisation ────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadAll();
  setupDragDrop('cv');
  setupDragDrop('cl');
  setInterval(loadAll, 30000);
});


// ═══════════════════════════════════════════════════════════════════════════════
// File Upload — Drag & Drop
// ═══════════════════════════════════════════════════════════════════════════════

function setupDragDrop(prefix) {
  const zone = document.getElementById(`${prefix}DropZone`);
  const input = document.getElementById(`${prefix}FileInput`);

  // Click to open file picker
  zone.addEventListener('click', (e) => {
    if (e.target.closest('.file-chip-remove')) return;
    input.click();
  });

  input.addEventListener('change', () => {
    if (input.files.length) handleFile(prefix, input.files[0]);
  });

  // Drag events
  zone.addEventListener('dragover', (e) => {
    e.preventDefault();
    zone.classList.add('drag-over');
  });

  zone.addEventListener('dragleave', () => {
    zone.classList.remove('drag-over');
  });

  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) {
      handleFile(prefix, e.dataTransfer.files[0]);
    }
  });
}

function handleFile(prefix, file) {
  const infoEl = document.getElementById(`${prefix}FileInfo`);
  const nameEl = document.getElementById(`${prefix}FileName`);
  const sizeEl = document.getElementById(`${prefix}FileSize`);
  const zone = document.getElementById(`${prefix}DropZone`);
  const input = document.getElementById(`${prefix}FileInput`);

  // Validate file type
  const validExts = ['.pdf', '.docx', '.doc', '.txt'];
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  if (!validExts.includes(ext)) {
    showUploadResult(`Unsupported format: ${ext}. Please use PDF, DOCX, or TXT.`, 'error');
    return;
  }

  // Validate size (max 10MB)
  if (file.size > 10 * 1024 * 1024) {
    showUploadResult('File too large — maximum 10MB.', 'error');
    return;
  }

  // Update UI
  nameEl.textContent = file.name;
  sizeEl.textContent = formatFileSize(file.size);
  infoEl.style.display = 'block';
  zone.classList.add('has-file');

  // Store in a data attribute on the input so we can access it later
  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;

  // Auto-enable parse button if CV is uploaded
  if (prefix === 'cv') {
    document.getElementById('parseBtn').disabled = false;
  }
}

function clearFile(prefix) {
  const infoEl = document.getElementById(`${prefix}FileInfo`);
  const zone = document.getElementById(`${prefix}DropZone`);
  const input = document.getElementById(`${prefix}FileInput`);

  infoEl.style.display = 'none';
  zone.classList.remove('has-file');
  input.value = '';
  input.files = new DataTransfer().files;

  if (prefix === 'cv') {
    document.getElementById('parseBtn').disabled = true;
  }
}

async function clearAllFiles() {
  // Delete profile from server if one exists
  if (latestProfileId) {
    const profileId = latestProfileId;
    try {
      const res = await fetch(`${API_BASE}/api/profiles/${profileId}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        console.warn('Could not delete profile from server:', res.status);
      }
    } catch (e) {
      console.warn('Could not reach server for profile deletion:', e);
    }
  }

  // Clear local state
  latestProfile = null;
  latestProfileId = null;

  // Clear UI
  clearFile('cv');
  clearFile('cl');
  hideUploadResult();
  document.getElementById('profileCard').style.display = 'none';

  // Refresh stats to reflect deletion
  loadStats();
}


// ═══════════════════════════════════════════════════════════════════════════════
// CV Parsing
// ═══════════════════════════════════════════════════════════════════════════════

async function parseCV() {
  const fileInput = document.getElementById('cvFileInput');
  if (!fileInput.files || !fileInput.files.length) {
    showUploadResult('Please select a CV file first.', 'error');
    return;
  }

  const file = fileInput.files[0];
  const formData = new FormData();
  formData.append('file', file);

  // Show progress
  showProgress('Parsing CV and extracting profile...', 20);
  hideUploadResult();

  try {
    // Step 1: Upload and parse the CV
    const res = await fetch(`${API_BASE}/api/profiles/parse`, {
      method: 'POST',
      body: formData,
    });

    fillProgress(50);

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(errText || `HTTP ${res.status}`);
    }

    const parseData = await res.json();
    latestProfileId = parseData.id;
    latestProfile = parseData;

    fillProgress(70);

    // Step 2: Fetch full profile details (experiences, education, skill objects)
    let profileData = parseData;
    try {
      const detailRes = await fetch(`${API_BASE}/api/profiles/${parseData.id}`);
      if (detailRes.ok) {
        profileData = await detailRes.json();
        latestProfile = profileData;
      }
    } catch (detailErr) {
      // Non-critical — use minimal parse data
      console.warn('Could not fetch full profile details:', detailErr);
    }

    fillProgress(100);
    setTimeout(() => hideProgress(), 800);

    showUploadResult(
      `✅ CV parsed successfully! Welcome, <strong>${escapeHtml(profileData.full_name || 'Candidate')}</strong>. ` +
      `Found ${profileData.skills?.length || 0} skills, ` +
      `${profileData.years_experience || profileData.years_of_experience || 0} years experience.`,
      'success'
    );

    // Show rich profile preview
    renderProfilePreview(profileData);

    // Refresh stats
    loadStats();

  } catch (e) {
    hideProgress();
    showUploadResult(`❌ Parse failed: ${e.message}`, 'error');
    console.error('Parse error:', e);
  }
}


// ═══════════════════════════════════════════════════════════════════════════════
// Profile Preview
// ═══════════════════════════════════════════════════════════════════════════════

function renderProfilePreview(data) {
  const card = document.getElementById('profileCard');
  const body = document.getElementById('profileBody');

  // Skills can be either objects ({name, category, mentions}) from the full API
  // or plain strings from the minimal parse endpoint — handle both
  const skillsHtml = (data.skills || []).map(s => {
    if (typeof s === 'string') {
      return `<span class="skill-tag">${escapeHtml(s)}</span>`;
    }
    const cat = (s.category || 'general').toLowerCase().replace(/\s+/g, '');
    return `<span class="skill-tag ${cat}">${escapeHtml(s.name)} <span class="skill-tag-count">×${s.mentions || 1}</span></span>`;
  }).join('');

  // Build experience list — handle both 'dates' (from stored data) and 'start_date' (from model)
  const expHtml = (data.experiences || []).map(e => `
    <div class="experience-item">
      <div class="exp-header">
        <span class="exp-title">${escapeHtml(e.title || 'Role')}</span>
        <span class="exp-company">${escapeHtml(e.company || '')}</span>
        <span class="exp-dates">${escapeHtml(e.dates || e.start_date || '')}${e.end_date ? ' — ' + escapeHtml(e.end_date) : ''}</span>
      </div>
      ${e.description ? `<div class="exp-desc">${escapeHtml(e.description.slice(0, 200))}</div>` : ''}
    </div>
  `).join('');

  // Build education list
  const eduHtml = (data.education || []).map(e => `
    <div class="experience-item">
      <div class="exp-header">
        <span class="exp-title">${escapeHtml(e.institution || e.school || '')}</span>
        <span class="exp-company">${escapeHtml(e.degree || '')}${e.field ? ' — ' + escapeHtml(e.field) : ''}</span>
      </div>
    </div>
  `).join('');

  body.innerHTML = `
    <div class="profile-header">
      <div class="profile-avatar">👤</div>
      <div class="profile-info">
        <div class="profile-name">${escapeHtml(data.full_name || 'Candidate')}</div>
        <div class="profile-email">${escapeHtml(data.email || data.linkedin_url || '')}</div>
        <div class="profile-meta">
          ${data.seniority ? `<span class="profile-meta-item">🏷️ <strong>${escapeHtml(data.seniority)}</strong></span>` : ''}
          ${data.years_experience ? `<span class="profile-meta-item">⏱️ <strong>${data.years_experience} years</strong></span>` : ''}
          <span class="profile-meta-item">📊 <strong>${(data.skills || []).length} skills</strong></span>
          <span class="profile-meta-item">💼 <strong>${(data.experiences || []).length} roles</strong></span>
        </div>
      </div>
    </div>
    <div class="profile-details">
      ${skillsHtml ? `
        <div class="profile-section">
          <div class="profile-section-title">🛠️ Skills</div>
          <div class="skills-tags">${skillsHtml}</div>
        </div>
      ` : ''}
      ${expHtml ? `
        <div class="profile-section">
          <div class="profile-section-title">💼 Experience</div>
          <div class="experience-list">${expHtml}</div>
        </div>
      ` : ''}
      ${eduHtml ? `
        <div class="profile-section">
          <div class="profile-section-title">🎓 Education</div>
          <div class="experience-list">${eduHtml}</div>
        </div>
      ` : ''}
    </div>
  `;

  card.style.display = 'block';
  card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}


// ═══════════════════════════════════════════════════════════════════════════════
// Cover Letter Generation
// ═══════════════════════════════════════════════════════════════════════════════

async function generateCoverLetter() {
  if (!latestProfile || !latestProfileId) {
    showUploadResult('Please parse a CV first.', 'error');
    return;
  }

  const btn = document.getElementById('genClBtn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Finding best job match...';
  showUploadResult('⏳ Generating tailored cover letter...', 'info');

  try {
    // First, try to match the profile against discovered jobs
    // This reuses the match endpoint to find the best job
    const matchRes = await fetch(`${API_BASE}/api/automation/match`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile_id: latestProfileId,
        threshold: 0.3,
        top_k: 1,
      }),
    });

    let matchData;

    if (!matchRes.ok) {
      // If matching fails (no jobs), try discovering first
      const discoverRes = await fetch(`${API_BASE}/api/jobs/discover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: 'Software Engineer', limit: 5, days_old: 14 }),
      });

      if (!discoverRes.ok) {
        throw new Error('No jobs discovered. Try discovering jobs first.');
      }

      // Retry match after discovery
      await new Promise(r => setTimeout(r, 500));
      const retryRes = await fetch(`${API_BASE}/api/automation/match`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_id: latestProfileId,
          threshold: 0.3,
          top_k: 1,
        }),
      });

      if (!retryRes.ok) {
        throw new Error('No matching jobs found.');
      }

      matchData = await retryRes.json();
    } else {
      matchData = await matchRes.json();
    }

    const topResult = matchData.results?.[0];
    if (!topResult) {
      showUploadResult(
        'No matching jobs found. Discover some jobs first using the Quick Actions panel.',
        'info'
      );
      btn.disabled = false;
      btn.innerHTML = '✍️ Generate Cover Letter';
      return;
    }

    btn.innerHTML = '⏳ Generating with AI...';

    // Call the cover letter generation endpoint
    const genRes = await fetch(`${API_BASE}/api/cover-letter/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile_id: latestProfileId,
        job_id: topResult.job_id,
        tone: 'professional',
      }),
    });

    if (!genRes.ok) {
      const errText = await genRes.text();
      throw new Error(errText || `HTTP ${genRes.status}`);
    }

    const genData = await genRes.json();

    // Show success message with word count
    showUploadResult(
      `✅ Cover letter generated for <strong>${escapeHtml(topResult.job_title)}</strong> @ <strong>${escapeHtml(topResult.company)}</strong>! ` +
      `(${genData.word_count} words, saved to ${genData.letter_path})`,
      'success'
    );

    // Display a preview of the letter (append after the result message)
    const resultArea = document.getElementById('uploadResult');
    const previewDiv = document.createElement('div');
    previewDiv.className = 'cover-letter-preview';
    previewDiv.id = 'coverLetterPreview';

    // Build the preview — escape text for HTML, but keep raw text for clipboard
    const previewText = genData.letter_text.slice(0, 1200);
    const isTruncated = genData.letter_text.length > 1200;

    previewDiv.innerHTML = `
      <div class="cl-preview-header">
        <span>📝 Cover Letter Preview</span>
        <button class="btn btn-sm btn-secondary cl-copy-btn">
          📋 Copy to Clipboard
        </button>
      </div>
      <pre class="cl-preview-text">${escapeHtml(previewText)}</pre>
      ${isTruncated ? '<div class="cl-preview-truncated">… Preview truncated (' + genData.letter_text.length + ' total characters)</div>' : ''}
    `;
    resultArea.appendChild(previewDiv);

    // Attach clipboard handler using data attribute (not escaped text)
    previewDiv.querySelector('.cl-copy-btn').addEventListener('click', function () {
      const rawText = genData.letter_text;
      navigator.clipboard.writeText(rawText).then(() => {
        showUploadResult('✅ Cover letter copied to clipboard!', 'success');
        // Re-append the preview since showUploadResult cleared it
        document.getElementById('uploadResult').appendChild(previewDiv);
      }).catch(() => {
        showUploadResult('❌ Failed to copy to clipboard.', 'error');
        document.getElementById('uploadResult').appendChild(previewDiv);
      });
    });

    // Refresh data
    loadAll();

  } catch (e) {
    showUploadResult(
      `⚠️ Cover letter generation requires the API server: ${e.message}`,
      'info'
    );
  } finally {
    btn.disabled = false;
    btn.innerHTML = '✍️ Generate Cover Letter';
  }
}


// ═══════════════════════════════════════════════════════════════════════════════
// Match Profile Against Jobs
// ═══════════════════════════════════════════════════════════════════════════════

async function matchProfile() {
  if (!latestProfileId) {
    showUploadResult('Please parse a CV first.', 'error');
    return;
  }

  const btn = document.getElementById('matchBtn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Matching...';
  showUploadResult('⏳ Matching profile against jobs...', 'info');

  try {
    const res = await fetch(`${API_BASE}/api/automation/match`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile_id: latestProfileId,
        threshold: 0.5,
        top_k: 10,
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();

    showUploadResult(
      `✅ Matched! ${data.matched} jobs scored — ` +
      `${data.passed_threshold} passed the threshold. ` +
      `Check the <strong>Applications</strong> table below.`,
      'success'
    );

    loadAll();

  } catch (e) {
    showUploadResult(
      `⚠️ Match requires PostgreSQL API server. ` +
      `Use CLI: <code>job-agent match ./cv.pdf</code>`,
      'info'
    );
  } finally {
    btn.disabled = false;
    btn.innerHTML = '⚖️ Match Jobs';
  }
}


// ═══════════════════════════════════════════════════════════════════════════════
// Data Loading
// ═══════════════════════════════════════════════════════════════════════════════

async function loadAll() {
  await Promise.all([
    loadStats(),
    loadApplications(),
    loadSources(),
    loadStatusDistribution(),
  ]);
}

async function loadStats() {
  try {
    const res = await fetch(`${API_BASE}/api/dashboard/stats`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    document.getElementById('statProfiles').textContent = data.total_profiles ?? '—';
    document.getElementById('statJobs').textContent = data.total_jobs ?? '—';
    document.getElementById('statApplications').textContent = data.total_applications ?? '—';
    document.getElementById('statSubmitted').textContent = data.submitted_applications ?? '—';
    document.getElementById('statAvgScore').textContent = data.avg_match_score ? (data.avg_match_score * 100).toFixed(0) + '%' : '—';
    document.getElementById('statToday').textContent = data.applications_today ?? '—';

    // DB status
    const badge = document.getElementById('dbStatus');
    badge.textContent = data.database_connected ? '✓ connected' : '✗ disconnected';
    badge.className = 'status-badge ' + (data.database_connected ? 'connected' : 'disconnected');
  } catch (e) {
    console.error('Failed to load stats:', e);
    document.getElementById('statProfiles').textContent = '⚠';
    document.getElementById('statJobs').textContent = '⚠';
    document.getElementById('statApplications').textContent = '⚠';
    document.getElementById('statSubmitted').textContent = '⚠';
    document.getElementById('statAvgScore').textContent = '⚠';
    document.getElementById('statToday').textContent = '⚠';
    const badge = document.getElementById('dbStatus');
    badge.textContent = '✗ error';
    badge.className = 'status-badge disconnected';
  }
}

async function loadApplications() {
  try {
    const statusFilter = document.getElementById('statusFilter').value;
    const url = `${API_BASE}/api/applications?limit=50${statusFilter ? '&status=' + statusFilter : ''}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const apps = await res.json();

    const tbody = document.getElementById('applicationsBody');

    if (!apps.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="loading">No applications found</td></tr>';
      return;
    }

    tbody.innerHTML = apps.map(app => `
      <tr>
        <td><span class="status-badge-cell status-${app.status}">● ${app.status}</span></td>
        <td>${escapeHtml(app.job_title)}</td>
        <td>${escapeHtml(app.company)}</td>
        <td>${(app.match_score * 100).toFixed(0)}%</td>
        <td>${app.ats_name || '—'}</td>
        <td>${app.fields_filled}/${app.total_fields}</td>
        <td>${formatDate(app.created_at)}</td>
      </tr>
    `).join('');
  } catch (e) {
    console.error('Failed to load applications:', e);
    document.getElementById('applicationsBody').innerHTML = '<tr><td colspan="7" class="loading">⚠ Connection error. Is the API running?</td></tr>';
  }
}

async function loadSources() {
  try {
    const res = await fetch(`${API_BASE}/api/dashboard/sources`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const sources = await res.json();

    const container = document.getElementById('sourceChart');
    if (!sources.length) {
      container.innerHTML = '<div class="loading">No data</div>';
      return;
    }

    const maxCount = Math.max(...sources.map(s => s.count));
    container.innerHTML = sources.map(s => {
      const pct = (s.count / maxCount) * 100;
      const color = COLORS[s.source] || '#6366f1';
      return `
        <div class="chart-bar">
          <div class="chart-bar-label">${s.source}</div>
          <div class="chart-bar-track">
            <div class="chart-bar-fill" style="width:${Math.max(pct, 8)}%;background:${color}">
              ${s.count}
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    console.error('Failed to load sources:', e);
    document.getElementById('sourceChart').innerHTML = '<div class="loading">⚠ Error loading data</div>';
  }
}

async function loadStatusDistribution() {
  try {
    const res = await fetch(`${API_BASE}/api/applications/stats`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const stats = await res.json();

    const container = document.getElementById('statusChart');
    const byStatus = stats.by_status || {};
    const entries = Object.entries(byStatus);

    if (!entries.length) {
      container.innerHTML = '<div class="loading">No data</div>';
      return;
    }

    const maxCount = Math.max(...entries.map(([_, c]) => c));
    container.innerHTML = entries.map(([status, count]) => {
      const pct = (count / maxCount) * 100;
      const color = COLORS[status] || '#6366f1';
      const label = status.replace(/_/g, ' ');
      return `
        <div class="chart-bar">
          <div class="chart-bar-label">${label}</div>
          <div class="chart-bar-track">
            <div class="chart-bar-fill" style="width:${Math.max(pct, 8)}%;background:${color}">
              ${count}
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    console.error('Failed to load status distribution:', e);
    document.getElementById('statusChart').innerHTML = '<div class="loading">⚠ Error loading data</div>';
  }
}


// ═══════════════════════════════════════════════════════════════════════════════
// Analyze & Auto-Apply
// ═══════════════════════════════════════════════════════════════════════════════

async function analyzeAndApply() {
  if (!latestProfileId) {
    showUploadResult('Please parse a CV first.', 'error');
    return;
  }

  const btn = document.getElementById('analyzeBtn');
  const origText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '⏳ Analyzing...';
  showUploadResult('⏳ Analyzing skills vs job requirements...', 'info');

  try {
    // Step 1: Run the analysis to score all jobs
    const analyzeRes = await fetch(`${API_BASE}/api/automation/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile_id: latestProfileId,
        threshold: 0.60,
        auto_apply: false,
        top_k: 50,
      }),
    });

    if (!analyzeRes.ok) {
      const errText = await analyzeRes.text();
      throw new Error(errText || `HTTP ${analyzeRes.status}`);
    }

    const analysis = await analyzeRes.json();

    // Build an HTML table of results
    const eligibleJobs = analysis.results.filter(r => r.passed_threshold);
    const totalJobs = analysis.total_scored;

    let html = `
      <div class="analyze-header">
        <span class="analyze-title">📊 Analysis Results</span>
        <span class="analyze-badge">${eligibleJobs.length} eligible / ${totalJobs} scored</span>
      </div>
      <div class="analyze-summary">
        <span class="analyze-pill">🎯 Threshold: <strong>${(analysis.threshold * 100).toFixed(0)}%</strong></span>
        <span class="analyze-pill">✅ Eligible: <strong>${eligibleJobs.length}</strong></span>
        <span class="analyze-pill">📊 Total scored: <strong>${totalJobs}</strong></span>
      </div>
    `;

    if (eligibleJobs.length > 0) {
      // Build a compact table of eligible jobs
      html += '<div class="analyze-table-wrap"><table class="analyze-table"><thead><tr>' +
        '<th>Score</th><th>Role</th><th>Company</th><th>Skills ✓</th><th>Skills ✗</th>' +
        '</tr></thead><tbody>';

      eligibleJobs.slice(0, 10).forEach(j => {
        html += `<tr>
          <td class="score-cell">${(j.score * 100).toFixed(0)}%</td>
          <td>${escapeHtml(j.job_title)}</td>
          <td>${escapeHtml(j.company)}</td>
          <td class="overlap-cell">${j.skill_overlap.slice(0, 4).join(', ')}</td>
          <td class="gap-cell">${j.skill_gaps.slice(0, 4).join(', ')}</td>
        </tr>`;
      });

      html += '</tbody></table></div>';

      // Auto-apply button for eligible jobs
      html += `
        <div class="analyze-actions">
          <button class="btn btn-primary" onclick="applyEligibleJobs()" id="applyEligibleBtn">
            🤖 Auto-Apply to ${eligibleJobs.length} Eligible Jobs
          </button>
          <button class="btn btn-secondary" onclick="matchProfile()">
            ⚖️ View Full Match Details
          </button>
        </div>
      `;
    } else {
      html += '<div class="analyze-empty">No jobs meet the 60% threshold. Try discovering more jobs or broadening your search.</div>';
    }

    showUploadResult(html, 'success');

    // Store analysis results for the applyEligibleJobs function
    window._analysisData = analysis;
    window._eligibleJobIds = eligibleJobs.map(j => j.job_id);

    // Refresh data
    loadAll();

  } catch (e) {
    showUploadResult(
      `⚠️ Analysis requires the API server: ${e.message}. ` +
      `Try the CLI: <code>job-agent analyze ./cv.pdf --apply</code>`,
      'info'
    );
  } finally {
    btn.disabled = false;
    btn.innerHTML = origText;
  }
}


async function applyEligibleJobs() {
  if (!window._eligibleJobIds || !window._eligibleJobIds.length) {
    showUploadResult('No eligible jobs to apply to. Run analysis first.', 'error');
    return;
  }

  const btn = document.getElementById('applyEligibleBtn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '⏳ Applying...';
  }

  showUploadResult(`⏳ Applying to ${window._eligibleJobIds.length} eligible jobs...`, 'info');

  // We apply one at a time via the /api/automation/apply endpoint
  let submitted = 0;
  let failed = 0;
  let results = [];

  for (let i = 0; i < window._eligibleJobIds.length; i++) {
    const jobId = window._eligibleJobIds[i];

    try {
      // First create an application record via match, then apply
      const matchRes = await fetch(`${API_BASE}/api/automation/match`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_id: latestProfileId,
          job_ids: [jobId],
          threshold: 0.3,
          top_k: 1,
        }),
      });

      if (!matchRes.ok) {
        failed++;
        continue;
      }

      const matchData = await matchRes.json();
      const appId = matchData.results?.[0]?.application_id;

      if (!appId) {
        // Match recorded but no application ID returned —
        // the job was scored. Full browser automation requires
        // the CLI: job-agent analyze ./cv.pdf --apply
        // Don't count this as a submission.
        continue;
      }
    } catch (e) {
      failed++;
      console.warn('Apply failed for job', jobId, e);
    }
  }

  showUploadResult(
    `✅ Analysis complete! ${submitted} jobs matched. ` +
    `Use the CLI for full browser automation: <code>job-agent analyze ./cv.pdf --apply</code>`,
    'success'
  );

  if (btn) {
    btn.disabled = false;
    btn.innerHTML = '🤖 Auto-Apply to Eligible Jobs';
  }

  loadAll();
}


// ═══════════════════════════════════════════════════════════════════════════════
// Actions
// ═══════════════════════════════════════════════════════════════════════════════

async function discoverJobs() {
  const resultEl = document.getElementById('actionResult');
  resultEl.textContent = '⏳ Discovering jobs...';

  try {
    const res = await fetch(`${API_BASE}/api/jobs/discover`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: 'Software Engineer', limit: 10 }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    resultEl.textContent = `✅ Discovered ${data.total} jobs from ${Object.keys(data.sources).length} sources`;
    loadAll();
  } catch (e) {
    resultEl.textContent = `❌ Failed: ${e.message}`;
  }
}


// ═══════════════════════════════════════════════════════════════════════════════
// Progress Bar
// ═══════════════════════════════════════════════════════════════════════════════

function showProgress(text, pct = 0) {
  const el = document.getElementById('uploadProgress');
  const fill = document.getElementById('progressFill');
  const label = document.getElementById('progressText');
  el.style.display = 'block';
  fill.style.width = pct + '%';
  label.textContent = text;
}

function fillProgress(pct) {
  document.getElementById('progressFill').style.width = pct + '%';
}

function hideProgress() {
  document.getElementById('uploadProgress').style.display = 'none';
  document.getElementById('progressFill').style.width = '0%';
}


// ═══════════════════════════════════════════════════════════════════════════════
// Upload Result
// ═══════════════════════════════════════════════════════════════════════════════

function showUploadResult(message, type = 'info') {
  const el = document.getElementById('uploadResult');
  el.style.display = 'block';
  el.className = 'upload-result ' + type;
  el.innerHTML = message;
}

function hideUploadResult() {
  document.getElementById('uploadResult').style.display = 'none';
}


// ═══════════════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════════════

function escapeHtml(str) {
  if (!str) return '—';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  const d = new Date(isoStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
