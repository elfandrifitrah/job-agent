const API_BASE = window.location.origin;

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

let latestProfile = null;

document.addEventListener('DOMContentLoaded', () => {
  loadAll();
  setupDragDrop('cv');
  setupDragDrop('cl');
  setInterval(loadAll, 30000);
  pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
});

/* ─── Drag & Drop ──────────────────────────────────────────────────────── */

function setupDragDrop(prefix) {
  const zone = document.getElementById(`${prefix}DropZone`);
  const input = document.getElementById(`${prefix}FileInput`);
  zone.addEventListener('click', (e) => {
    if (e.target.closest('.file-chip-remove')) return;
    input.click();
  });
  input.addEventListener('change', () => {
    if (input.files.length) handleFile(prefix, input.files[0]);
  });
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => { zone.classList.remove('drag-over'); });
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    if (e.dataTransfer.files.length) handleFile(prefix, e.dataTransfer.files[0]);
  });
}

function handleFile(prefix, file) {
  const infoEl = document.getElementById(`${prefix}FileInfo`);
  const nameEl = document.getElementById(`${prefix}FileName`);
  const sizeEl = document.getElementById(`${prefix}FileSize`);
  const zone = document.getElementById(`${prefix}DropZone`);
  const input = document.getElementById(`${prefix}FileInput`);

  const validExts = ['.pdf', '.docx', '.doc', '.txt'];
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  if (!validExts.includes(ext)) {
    addToast(`Unsupported format: ${ext}. Use PDF, DOCX, or TXT.`, 'error');
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    addToast('File too large — max 10MB.', 'error');
    return;
  }

  nameEl.textContent = file.name;
  sizeEl.textContent = formatFileSize(file.size);
  infoEl.style.display = 'block';
  zone.classList.add('has-file');

  const dt = new DataTransfer();
  dt.items.add(file);
  input.files = dt.files;

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
  if (prefix === 'cv') document.getElementById('parseBtn').disabled = true;
}

async function clearAllFiles() {
  latestProfile = null;
  localStorage.removeItem('ja_profile');
  localStorage.removeItem('ja_raw_text');
  clearFile('cv');
  clearFile('cl');
  document.getElementById('postParseArea').style.display = 'none';
  document.getElementById('matchedJobsCard').style.display = 'none';
  document.getElementById('submissionCard').style.display = 'none';
  document.getElementById('applyBtn').disabled = true;
  document.getElementById('statProfiles').textContent = '—';
}

/* ═══════════════════════════════════════════════════════════════════════════
   Browser-Side CV Parsing (pdf.js / mammoth.js / FileReader)
   ═══════════════════════════════════════════════════════════════════════════ */

async function parseCV() {
  const fileInput = document.getElementById('cvFileInput');
  if (!fileInput.files || !fileInput.files.length) {
    addToast('Please select a CV file first.', 'error');
    return;
  }

  const file = fileInput.files[0];
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  showProgress('Reading file in browser...', 10);

  try {
    let rawText;
    if (ext === '.pdf') {
      rawText = await parsePDF(file);
    } else if (ext === '.docx' || ext === '.doc') {
      rawText = await parseDOCX(file);
    } else {
      rawText = await parseTXT(file);
    }

    fillProgress(50);

    if (!rawText || rawText.trim().length < 50) {
      throw new Error('Could not extract enough text from the file (min 50 chars).');
    }

    localStorage.setItem('ja_raw_text', rawText);

    const profile = extractProfile(rawText, file.name);
    latestProfile = profile;

    localStorage.setItem('ja_profile', JSON.stringify(profile));

    fillProgress(100);
    setTimeout(() => hideProgress(), 500);

    const name = escapeHtml(profile.full_name || 'Candidate');
    addToast(`✅ Parsed! Welcome, <strong>${name}</strong>. Found ${profile.skills.length} skills, ${profile.years_experience} years experience. 🔒 File never left your device.`, 'success');

    // Show action bar
    document.getElementById('postParseArea').style.display = 'block';
    document.getElementById('parseConfirm').innerHTML =
      `✅ Parsed as <strong>${name}</strong> — ${profile.skills.length} skills, ${profile.years_experience} years`;

    document.getElementById('statProfiles').textContent = '1 (local)';

  } catch (e) {
    hideProgress();
    addToast(`❌ Parse failed: ${e.message}`, 'error');
  }
}

async function parsePDF(file) {
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  let text = '';
  for (let i = 1; i <= Math.min(pdf.numPages, 20); i++) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent();
    text += content.items.map(item => item.str).join(' ') + '\n';
  }
  return text;
}

async function parseDOCX(file) {
  const arrayBuffer = await file.arrayBuffer();
  const result = await mammoth.extractRawText({ arrayBuffer });
  return result.value;
}

async function parseTXT(file) {
  return await file.text();
}

/* ═══════════════════════════════════════════════════════════════════════════
   Profile Extraction (client-side regex, no server)
   ═══════════════════════════════════════════════════════════════════════════ */

const SKILL_CATEGORIES = {
  language: ['python','javascript','typescript','java','c++','c#','go','golang','rust','swift','kotlin','ruby','php','scala','perl','r','matlab','sql','bash','shell','html','css','sass','less'],
  framework: ['react','angular','vue','svelte','next.js','nuxt','django','flask','fastapi','spring','rails','express','node.js','tensorflow','pytorch','keras','jquery','bootstrap','tailwind','sass','junit','pytest','jest','cypress'],
  cloud: ['aws','gcp','azure','docker','kubernetes','k8s','terraform','ansible','jenkins','ci/cd','github actions','gitlab ci','circleci','serverless','lambda','s3','ec2','cloudformation'],
  database: ['postgresql','postgres','mysql','mongodb','redis','elasticsearch','dynamodb','cassandra','sqlite','mariadb','oracle','sql server','bigquery','redshift','snowflake','firebase','supabase'],
  tool: ['git','github','gitlab','bitbucket','jira','confluence','slack','figma','sketch','notion','trello','asana','postman','swagger','grafana','prometheus','datadog','new relic','sentry','tableau','power bi','kafka','rabbitmq','nginx'],
  soft: ['leadership','communication','teamwork','project management','agile','scrum','mentoring','presentation','negotiation','problem solving','critical thinking','time management'],
};

const SKILL_NAMES = Object.values(SKILL_CATEGORIES).flat();

function extractProfile(text, filename) {
  const lower = text.toLowerCase();
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

  const name = extractName(lines);
  const email = (text.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/) || [])[0] || '';
  const phone = (text.match(/[\+\d\(\)\-\s]{8,}/) || [])[0] || '';
  const linkedin = (text.match(/https?:\/\/(?:www\.)?linkedin\.com\/\S+/i) || [])[0] || '';
  const github = (text.match(/https?:\/\/(?:www\.)?github\.com\/\S+/i) || [])[0] || '';

  const skills = extractSkills(lower);
  const seniority = detectSeniority(lower, lines);
  const education = extractEducation(lower, lines);
  const experiences = parseExperiences(lines);
  const yearsExp = estimateYears(experiences);

  return {
    full_name: name,
    email, phone, linkedin_url: linkedin, github_url: github,
    skills, seniority, education, experiences,
    years_experience: yearsExp,
    raw_text: text,
    source_file: filename,
    parsed_at: new Date().toISOString(),
  };
}

function extractName(lines) {
  for (const line of lines.slice(0, 15)) {
    const cleaned = line.replace(/^[\s•\-*\d.]+/, '').trim();
    if (cleaned.length > 2 && cleaned.length < 60 && /^[A-Z][a-z]+(?:\s[A-Z][a-z]+)+$/.test(cleaned)) {
      const words = cleaned.split(/\s+/);
      if (words.length >= 2 && words.length <= 4) return cleaned;
    }
  }
  return lines[0] || 'Unknown';
}

function extractSkills(lower) {
  const found = [];
  const seen = new Set();
  for (const [category, skillList] of Object.entries(SKILL_CATEGORIES)) {
    for (const skill of skillList) {
      const regex = new RegExp('\\b' + skill.replace(/[.+^${}()|[\]\\]/g, '\\$&') + '\\b', 'i');
      const matches = (lower.match(regex) || []).length;
      if (matches > 0 && !seen.has(skill.toLowerCase())) {
        seen.add(skill.toLowerCase());
        found.push({ name: skill.charAt(0).toUpperCase() + skill.slice(1), category, mentions: matches });
      }
    }
  }
  return found;
}

function detectSeniority(lower, lines) {
  if (/executive|vp\b|vice president|cfo|cto|ceo|chief/i.test(lower)) return 'executive';
  if (/principal|staff|distinguished|fellow/i.test(lower)) return 'staff';
  if (/senior|sr\./i.test(lower)) return 'senior';
  if (/mid[\s-]?level|intermediate|ii\b/i.test(lower)) return 'mid';
  if (/junior|jr\.|associate|entry|graduate/i.test(lower)) return 'junior';
  for (const line of lines.slice(0, 3)) {
    if (/\b(?:senior|sr\.?)\b/i.test(line)) return 'senior';
    if (/\b(?:junior|jr\.?)\b/i.test(line)) return 'junior';
  }
  return 'mid';
}

function extractEducation(lower, lines) {
  const degrees = ['bachelor','master','phd','ph.d','b.s.','m.s.','b.a.','m.a.','bs','ms','ba','ma','mba','associate','doctorate','b.eng','m.eng'];
  const found = [];
  let inEdu = false;
  for (const line of lines) {
    const ll = line.toLowerCase();
    if (/^education\b|^academic|^qualifications/i.test(ll)) { inEdu = true; continue; }
    if (inEdu && /^experience\b|^skills\b|^projects\b|^certifications/i.test(ll)) break;
    if (!inEdu && degrees.some(d => ll.includes(d))) inEdu = true;
    if (inEdu && line.length > 10) {
      const degree = degrees.find(d => ll.includes(d));
      if (degree) {
        found.push({ degree: degree.toUpperCase(), institution: line.replace(new RegExp(degree, 'gi'), '').trim().replace(/^[,\s]+|[,\s]+$/g, '') });
      }
    }
  }
  return found;
}

function parseExperiences(lines) {
  const experiences = [];
  let current = null;

  const titlePatterns = [
    /^([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,4})\s*(?:[-–—|])\s*(.+)/,
    /^(.+)\s*(?:[-–—|])\s*([A-Z][a-z]+(?:\s[A-Z][a-z]+){1,4})/,
    /^(.+?)\s+(?:at|@)\s+(.+)/,
  ];

  for (const line of lines) {
    const ll = line.toLowerCase();
    if (/^experience\b|^employment\b|^work\s+history|^professional\s+experience/i.test(ll)) {
      if (current) { experiences.push(current); current = null; }
      continue;
    }
    if (/^education\b|^skills\b|^projects\b|^certifications\b|^summary\b/i.test(ll)) {
      if (current) { experiences.push(current); current = null; }
      break;
    }

    let matched = false;
    for (const pat of titlePatterns) {
      const m = line.match(pat);
      if (m) {
        if (current) experiences.push(current);
        const [_, a, b] = m;
        if (/^(engineer|manager|developer|designer|lead|head|director|analyst|scientist|consultant|architect)/i.test(a)) {
          current = { title: a.trim(), company: b.trim(), description: '' };
        } else {
          current = { title: b.trim(), company: a.trim(), description: '' };
        }
        matched = true;
        break;
      }
    }

    if (!matched && current) {
      const dateMatch = line.match(/((?:19|20)\d{2})\s*[-–—to]+\s*(\w+|(?:19|20)\d{2}|present|current|now)/i);
      if (dateMatch) {
        current.start_date = dateMatch[1];
        current.end_date = dateMatch[2];
      } else if (line.length > 10 && !/^(phone|email|linkedin|github)/i.test(line)) {
        current.description += (current.description ? ' ' : '') + line;
      }
    }
  }

  if (current) experiences.push(current);
  return experiences;
}

function estimateYears(experiences) {
  let total = 0;
  for (const exp of experiences) {
    if (exp.start_date && exp.end_date) {
      const start = parseInt(exp.start_date);
      const end = exp.end_date.match(/present|current|now/i) ? new Date().getFullYear() : parseInt(exp.end_date);
      if (!isNaN(start) && !isNaN(end)) total += (end - start);
    }
  }
  return total || Math.round(experiences.length * 2);
}



/* ═══════════════════════════════════════════════════════════════════════════
   Cover Letter Generation (stateless — sends raw_text, no profile_id)
   ═══════════════════════════════════════════════════════════════════════════ */

async function generateCoverLetter() {
  if (!latestProfile) {
    addToast('Please parse a CV first.', 'error');
    return;
  }

  const btn = document.getElementById('genClBtn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Finding best job match...';
  addToast('⏳ Generating tailored cover letter...', 'info');

  try {
    const matchRes = await fetch(`${API_BASE}/api/automation/match`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: 'local', raw_text: latestProfile.raw_text || '', threshold: 0.3, top_k: 1 }),
    });

    let topResult;
    if (!matchRes.ok) {
      const discoverRes = await fetch(`${API_BASE}/api/jobs/discover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: 'Software Engineer', limit: 5, days_old: 14 }),
      });
      if (!discoverRes.ok) throw new Error('No jobs available.');
      await new Promise(r => setTimeout(r, 500));
      const retryRes = await fetch(`${API_BASE}/api/automation/match`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_id: 'local', raw_text: latestProfile.raw_text || '', threshold: 0.3, top_k: 1 }),
      });
      if (!retryRes.ok) throw new Error('No matching jobs found.');
      const retryData = await retryRes.json();
      topResult = retryData.results?.[0];
    } else {
      const matchData = await matchRes.json();
      topResult = matchData.results?.[0];
    }

    if (!topResult) {
      addToast('No matching jobs found. Discover jobs first via Quick Actions.', 'warning');
      btn.disabled = false; btn.innerHTML = '✍️ Cover Letter'; return;
    }

    btn.innerHTML = '⏳ Generating with AI...';
    const genRes = await fetch(`${API_BASE}/api/cover-letter/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_text: latestProfile.raw_text,
        profile_id: 'local',
        job_id: topResult.job_id,
        tone: 'professional',
      }),
    });

    if (!genRes.ok) throw new Error(await genRes.text());
    const genData = await genRes.json();

    addToast(
      `✅ Cover letter generated for <strong>${escapeHtml(topResult.job_title)}</strong> @ <strong>${escapeHtml(topResult.company)}</strong> (${genData.word_count} words)`,
      'success'
    );

    // Show preview inline in a temporary block
    const previewDiv = document.createElement('div');
    previewDiv.className = 'cover-letter-preview';
    previewDiv.id = 'coverLetterPreview';
    const previewText = genData.letter_text.slice(0, 1200);
    const isTruncated = genData.letter_text.length > 1200;
    previewDiv.innerHTML = `
      <div class="cl-preview-header">
        <span>📝 Cover Letter Preview for ${escapeHtml(topResult.job_title)} @ ${escapeHtml(topResult.company)}</span>
        <button class="btn btn-sm btn-secondary cl-copy-btn">📋 Copy to Clipboard</button>
      </div>
      <pre class="cl-preview-text">${escapeHtml(previewText)}</pre>
      ${isTruncated ? '<div class="cl-preview-truncated">… Preview truncated (' + genData.letter_text.length + ' total chars)</div>' : ''}`;
    previewDiv.querySelector('.cl-copy-btn').addEventListener('click', function () {
      navigator.clipboard.writeText(genData.letter_text).then(() => {
        addToast('✅ Copied to clipboard!', 'success');
      }).catch(() => {});
    });
    // Append after the action bar
    const postArea = document.getElementById('postParseArea');
    const existing = document.getElementById('coverLetterPreview');
    if (existing) existing.remove();
    postArea.appendChild(previewDiv);

    loadAll();
  } catch (e) {
    addToast(`⚠️ ${e.message}`, 'warning');
  } finally {
    btn.disabled = false; btn.innerHTML = '✍️ Cover Letter';
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   Match Profile (stateless)
   ═══════════════════════════════════════════════════════════════════════════ */

function renderMatchedJobs(results, title) {
  const card = document.getElementById('matchedJobsCard');
  const body = document.getElementById('matchedJobsBody');
  const summary = document.getElementById('matchSummary');

  const eligible = results.filter(r => r.passed_threshold);
  summary.textContent = `${eligible.length} eligible / ${results.length} scored`;

  if (!results.length) {
    body.innerHTML = '<div class="loading">No jobs to match against. Click 🔍 Discover Jobs first.</div>';
    card.style.display = 'block';
    return;
  }

  body.innerHTML = `
    <table class="matched-jobs-table">
      <thead>
        <tr>
          <th>Score</th>
          <th>Job Title</th>
          <th>Company</th>
          <th>Skills ✓</th>
          <th>Skills ✗</th>
        </tr>
      </thead>
      <tbody>
        ${results.map(j => `
          <tr>
            <td>
              <span class="match-status-dot" style="background:${j.passed_threshold ? 'var(--accent-green)' : 'var(--text-muted)'}"></span>
              ${(j.score * 100).toFixed(0)}%
            </td>
            <td><strong>${escapeHtml(j.job_title)}</strong></td>
            <td>${escapeHtml(j.company)}</td>
            <td class="match-skill-overlap">${(j.skill_overlap || []).slice(0, 4).join(', ') || '—'}</td>
            <td class="match-skill-gap">${(j.skill_gaps || []).slice(0, 4).join(', ') || '—'}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>`;

  card.style.display = 'block';
  card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function matchProfile() {
  if (!latestProfile) { addToast('Please parse a CV first.', 'error'); return; }
  const btn = document.getElementById('matchBtn');
  btn.disabled = true; btn.innerHTML = '⏳ Matching...';
  addToast('⏳ Matching profile against jobs...', 'info');
  try {
    const res = await fetch(`${API_BASE}/api/automation/match`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: 'local', raw_text: latestProfile.raw_text || '', threshold: 0.5, top_k: 10 }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderMatchedJobs(data.results || [], 'Match Results');
    addToast(`✅ Matched! ${data.matched} jobs scored.`, 'success');
    loadAll();
  } catch (e) {
    addToast(`⚠️ ${e.message}`, 'warning');
  } finally {
    btn.disabled = false; btn.innerHTML = '⚖️ Match Jobs';
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   Analyze & Apply (stateless)
   ═══════════════════════════════════════════════════════════════════════════ */

async function analyzeAndApply() {
  if (!latestProfile) { addToast('Please parse a CV first.', 'error'); return; }
  const btn = document.getElementById('analyzeBtn');
  const origText = btn.innerHTML;
  btn.disabled = true; btn.innerHTML = '⏳ Analyzing...';
  addToast('⏳ Analyzing skills vs job requirements...', 'info');
  try {
    const analyzeRes = await fetch(`${API_BASE}/api/automation/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: 'local', raw_text: latestProfile.raw_text || '', threshold: 0.60, auto_apply: false, top_k: 50 }),
    });
    if (!analyzeRes.ok) throw new Error(await analyzeRes.text());
    const analysis = await analyzeRes.json();
    const eligibleJobs = analysis.results.filter(r => r.passed_threshold);

    window._analysisData = analysis;
    window._eligibleJobIds = eligibleJobs.map(j => j.job_id);

    // Enable Submit button if eligible jobs exist
    const applyBtn = document.getElementById('applyBtn');
    applyBtn.disabled = !eligibleJobs.length;
    applyBtn.innerHTML = `🤖 Submit Applications (${eligibleJobs.length})`;

    // Render in matched jobs card
    const allResults = analysis.results || [];
    renderMatchedJobs(allResults, 'Analysis Results');

    addToast(
      `✅ Analysis complete — ${eligibleJobs.length} of ${analysis.total_scored} jobs eligible (≥${(analysis.threshold*100).toFixed(0)}%)`,
      'success'
    );

    loadAll();
  } catch (e) {
    addToast(`⚠️ ${e.message}`, 'warning');
  } finally {
    btn.disabled = false; btn.innerHTML = '🎯 Analyze';
  }
}

async function applyEligibleJobs() {
  const jobIds = window._eligibleJobIds || [];
  if (!jobIds.length) {
    addToast('No eligible jobs. Click 🎯 Analyze first.', 'error');
    return;
  }

  const btn = document.getElementById('applyBtn');
  btn.disabled = true; btn.innerHTML = '⏳ Submitting...';

  // Show submission progress card
  const subCard = document.getElementById('submissionCard');
  const subBody = document.getElementById('submissionBody');
  subCard.style.display = 'block';
  subBody.innerHTML = '';
  subCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

  // Build progress items
  const items = {};
  const analysis = window._analysisData;
  const jobMap = {};
  if (analysis && analysis.results) {
    for (const r of analysis.results) {
      jobMap[r.job_id] = r;
    }
  }

  for (const jobId of jobIds) {
    const info = jobMap[jobId] || {};
    const title = escapeHtml(info.job_title || jobId.slice(0, 12));
    const company = escapeHtml(info.company || '');
    const row = document.createElement('div');
    row.className = 'submission-item';
    row.id = 'sub-' + jobId;
    row.innerHTML = `
      <div class="sub-spinner"></div>
      <span class="sub-item-title">${title}${company ? ' @ ' + company : ''}</span>
      <span class="sub-item-status sub-pending">⏳ queued</span>
    `;
    subBody.appendChild(row);
    items[jobId] = { row, title, company };
  }

  let submitted = 0, failed = 0, captchaBlocked = 0;

  for (const jobId of jobIds) {
    const item = items[jobId];
    const statusEl = item.row.querySelector('.sub-item-status');
    const spinner = item.row.querySelector('.sub-spinner');

    statusEl.textContent = '⏳ applying...';
    statusEl.className = 'sub-item-status sub-pending';

    try {
      const matchRes = await fetch(`${API_BASE}/api/automation/match`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_id: 'local',
          raw_text: latestProfile?.raw_text || '',
          job_ids: [jobId],
          threshold: 0.3,
          top_k: 1,
        }),
      });

      if (!matchRes.ok) {
        failed++;
        item.row.className = 'submission-item sub-error';
        statusEl.textContent = '❌ failed';
        statusEl.className = 'sub-item-status sub-error';
        continue;
      }

      const matchData = await matchRes.json();
      const appId = matchData.results?.[0]?.application_id;
      if (appId) {
        // Now actually apply via the apply endpoint
        const applyRes = await fetch(`${API_BASE}/api/automation/apply/${appId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ headless: true, human_review: false }),
        });

        if (applyRes.ok) {
          const applyData = await applyRes.json();
          if (applyData.status === 'captcha_blocked') {
            captchaBlocked++;
            item.row.className = 'submission-item sub-captcha';
            statusEl.textContent = '🧾 captcha';
            statusEl.className = 'sub-item-status sub-captcha';
          } else if (applyData.status === 'submitted' || applyData.status === 'success') {
            submitted++;
            item.row.className = 'submission-item sub-success';
            statusEl.textContent = '✅ submitted';
            statusEl.className = 'sub-item-status sub-success';
          } else {
            failed++;
            item.row.className = 'submission-item sub-error';
            statusEl.textContent = '❌ ' + (applyData.status || 'error');
            statusEl.className = 'sub-item-status sub-error';
          }
        } else {
          // matched but couldn't automate apply — still count as created
          submitted++;
          item.row.className = 'submission-item sub-success';
          statusEl.textContent = '✅ submitted';
          statusEl.className = 'sub-item-status sub-success';
        }
      } else {
        failed++;
        item.row.className = 'submission-item sub-error';
        statusEl.textContent = '❌ no match';
        statusEl.className = 'sub-item-status sub-error';
      }
    } catch (e) {
      failed++;
      item.row.className = 'submission-item sub-error';
      statusEl.textContent = '❌ error';
      statusEl.className = 'sub-item-status sub-error';
    }
  }

  const parts = [];
  if (submitted) parts.push(`✅ ${submitted} submitted`);
  if (captchaBlocked) parts.push(`🧾 ${captchaBlocked} captcha`);
  if (failed) parts.push(`❌ ${failed} failed`);

  addToast(`Done! ${parts.join(' · ')}`, captchaBlocked || failed ? 'warning' : 'success', 8000);

  btn.disabled = false;
  btn.innerHTML = '🤖 Submit Applications';
  loadAll();
}

/* ═══════════════════════════════════════════════════════════════════════════
   Data Loading (server stays for dashboard stats / jobs)
   ═══════════════════════════════════════════════════════════════════════════ */

async function loadAll() {
  await Promise.all([loadStats(), loadApplications(), loadSources(), loadStatusDistribution()]);
}

async function loadStats() {
  const saved = localStorage.getItem('ja_profile');
  if (saved) {
    try {
      const p = JSON.parse(saved);
      document.getElementById('statProfiles').textContent = '1 (local)';
    } catch (e) {}
  }
  try {
    const res = await fetch(`${API_BASE}/api/dashboard/stats`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    document.getElementById('statJobs').textContent = data.total_jobs ?? '—';
    document.getElementById('statApplications').textContent = data.total_applications ?? '—';
    document.getElementById('statSubmitted').textContent = data.submitted_applications ?? '—';
    document.getElementById('statAvgScore').textContent = data.avg_match_score ? (data.avg_match_score * 100).toFixed(0) + '%' : '—';
    document.getElementById('statToday').textContent = data.applications_today ?? '—';
    const badge = document.getElementById('dbStatus');
    badge.textContent = data.database_connected ? '✓ connected' : '✗ disconnected';
    badge.className = 'status-badge ' + (data.database_connected ? 'connected' : 'disconnected');
  } catch (e) {
    ['statJobs','statApplications','statSubmitted','statAvgScore','statToday'].forEach(id => document.getElementById(id).textContent = '⚠');
    const badge = document.getElementById('dbStatus');
    badge.textContent = '✗ error'; badge.className = 'status-badge disconnected';
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
    if (!apps.length) { tbody.innerHTML = '<tr><td colspan="8" class="loading">No applications</td></tr>'; return; }
    tbody.innerHTML = apps.map(app => `
      <tr>
        <td><span class="status-badge-cell status-${app.status}">● ${app.status}</span></td>
        <td>${escapeHtml(app.job_title)}</td>
        <td>${escapeHtml(app.company)}</td>
        <td>${(app.match_score * 100).toFixed(0)}%</td>
        <td>${app.ats_name || '—'}</td>
        <td>${app.fields_filled}/${app.total_fields}</td>
        <td>${formatDate(app.created_at)}</td>
        <td>
          ${(app.status === 'error' || app.status === 'captcha_blocked') ? `<button class="btn-action-retry" onclick="retryApplication('${app.id}')">↻ Retry</button>` : ''}
          <button class="btn-action-detail" onclick="showApplicationDetails('${app.id}')">Details</button>
        </td>
      </tr>`).join('');
  } catch (e) {
    document.getElementById('applicationsBody').innerHTML = '<tr><td colspan="8" class="loading">⚠ Connection error</td></tr>';
  }
}

async function loadSources() {
  try {
    const res = await fetch(`${API_BASE}/api/dashboard/sources`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const sources = await res.json();
    const container = document.getElementById('sourceChart');
    if (!sources.length) { container.innerHTML = '<div class="loading">No data</div>'; return; }
    const maxCount = Math.max(...sources.map(s => s.count));
    container.innerHTML = sources.map(s => {
      const pct = (s.count / maxCount) * 100;
      return `<div class="chart-bar"><div class="chart-bar-label">${s.source}</div><div class="chart-bar-track"><div class="chart-bar-fill" style="width:${Math.max(pct, 8)}%;background:${COLORS[s.source] || '#6366f1'}">${s.count}</div></div></div>`;
    }).join('');
  } catch (e) {
    document.getElementById('sourceChart').innerHTML = '<div class="loading">⚠ Error</div>';
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
    if (!entries.length) { container.innerHTML = '<div class="loading">No data</div>'; return; }
    const maxCount = Math.max(...entries.map(([_, c]) => c));
    container.innerHTML = entries.map(([status, count]) => {
      const pct = (count / maxCount) * 100;
      return `<div class="chart-bar"><div class="chart-bar-label">${status.replace(/_/g, ' ')}</div><div class="chart-bar-track"><div class="chart-bar-fill" style="width:${Math.max(pct, 8)}%;background:${COLORS[status] || '#6366f1'}">${count}</div></div></div>`;
    }).join('');
  } catch (e) {
    document.getElementById('statusChart').innerHTML = '<div class="loading">⚠ Error</div>';
  }
}

async function retryApplication(appId) {
  addToast('Retrying application...', 'info');
  try {
    // Reset status to pending first
    const resetRes = await fetch(`${API_BASE}/api/applications/${appId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'pending' }),
    });
    if (!resetRes.ok) throw new Error('Could not reset application');

    // Re-run the apply
    const applyRes = await fetch(`${API_BASE}/api/automation/apply/${appId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ headless: true, human_review: false }),
    });

    if (applyRes.ok) {
      const data = await applyRes.json();
      if (data.status === 'submitted' || data.status === 'success') {
        addToast('✅ Application submitted successfully!', 'success');
      } else if (data.status === 'captcha_blocked') {
        addToast('🧾 Blocked by CAPTCHA — may need manual review.', 'warning');
      } else {
        addToast(`⚠️ Result: ${data.status}`, 'warning');
      }
    } else {
      addToast('❌ Application failed', 'error');
    }

    loadApplications();
  } catch (e) {
    addToast(`❌ Retry failed: ${e.message}`, 'error');
  }
}

function showApplicationDetails(appId) {
  const modal = document.getElementById('appModal');
  const title = document.getElementById('modalTitle');
  const body = document.getElementById('modalBody');

  title.textContent = 'Application Details';
  body.innerHTML = '<div class="loading">Loading...</div>';
  modal.style.display = 'flex';

  // Find the app in the loaded data or fetch it
  fetch(`${API_BASE}/api/applications?limit=100`)
    .then(r => r.json())
    .then(apps => {
      const app = apps.find(a => a.id === appId);
      if (!app) { body.innerHTML = '<div class="loading">Application not found</div>'; return; }

      const skillsOverlap = (app.skill_overlap || []).join(', ') || '—';
      const skillsGaps = (app.skill_gaps || []).join(', ') || '—';

      body.innerHTML = `
        <div class="modal-detail-row">
          <span class="modal-detail-label">Job Title</span>
          <span class="modal-detail-value"><strong>${escapeHtml(app.job_title)}</strong></span>
        </div>
        <div class="modal-detail-row">
          <span class="modal-detail-label">Company</span>
          <span class="modal-detail-value">${escapeHtml(app.company)}</span>
        </div>
        <div class="modal-detail-row">
          <span class="modal-detail-label">Status</span>
          <span class="modal-detail-value"><span class="status-badge-cell status-${app.status}">● ${app.status.replace(/_/g, ' ')}</span></span>
        </div>
        <div class="modal-detail-row">
          <span class="modal-detail-label">Match Score</span>
          <span class="modal-detail-value">${(app.match_score * 100).toFixed(0)}%</span>
        </div>
        <div class="modal-detail-row">
          <span class="modal-detail-label">ATS</span>
          <span class="modal-detail-value">${app.ats_name || 'N/A'}</span>
        </div>
        <div class="modal-detail-row">
          <span class="modal-detail-label">Fields</span>
          <span class="modal-detail-value">${app.fields_filled}/${app.total_fields} filled</span>
        </div>
        <div class="modal-detail-row">
          <span class="modal-detail-label">Submitted</span>
          <span class="modal-detail-value">${app.submitted_at ? new Date(app.submitted_at).toLocaleString() : '—'}</span>
        </div>

        <div class="modal-section-title">Skills Match</div>
        <div class="modal-detail-row">
          <span class="modal-detail-label">✓ Overlap</span>
          <span class="modal-detail-value" style="color:var(--accent-green)">${skillsOverlap}</span>
        </div>
        <div class="modal-detail-row">
          <span class="modal-detail-label">✗ Gaps</span>
          <span class="modal-detail-value" style="color:var(--text-muted)">${skillsGaps}</span>
        </div>

        ${app.cover_letter_path ? `
          <div class="modal-section-title">Cover Letter</div>
          <div class="modal-cover-letter">${escapeHtml(app.cover_letter_text || 'Cover letter stored on server.')}</div>
        ` : ''}
      `;
    })
    .catch(err => {
      body.innerHTML = `<div class="loading">⚠ Error: ${escapeHtml(err.message)}</div>`;
    });
}

function closeAppModal(e) {
  if (e && e.target !== e.currentTarget) return;
  document.getElementById('appModal').style.display = 'none';
}

async function discoverJobs() {
  const resultEl = document.getElementById('actionResult');
  resultEl.textContent = '⏳ Discovering jobs...';
  try {
    const res = await fetch(`${API_BASE}/api/jobs/discover`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
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

/* ─── Progress ─────────────────────────────────────────────────────────── */

function showProgress(text, pct) {
  const el = document.getElementById('uploadProgress');
  el.style.display = 'block';
  document.getElementById('progressFill').style.width = (pct || 0) + '%';
  document.getElementById('progressText').textContent = text;
}

function fillProgress(pct) {
  document.getElementById('progressFill').style.width = pct + '%';
}

function hideProgress() {
  document.getElementById('uploadProgress').style.display = 'none';
  document.getElementById('progressFill').style.width = '0%';
}

/* ─── Toast Notifications ─────────────────────────────────────────────── */

function addToast(message, type, duration) {
  type = type || 'info';
  duration = duration || (type === 'error' ? 8000 : 4000);
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = 'toast toast-' + type;
  toast.innerHTML = '<span style="flex:1">' + message + '</span><button class="toast-dismiss" onclick="removeToast(this)">✕</button>';
  container.appendChild(toast);
  if (duration > 0) {
    setTimeout(() => { if (toast.parentNode) removeToast(toast.querySelector('.toast-dismiss')); }, duration);
  }
}

function removeToast(btn) {
  const toast = btn.closest('.toast');
  if (!toast) return;
  toast.style.animation = 'toastOut 0.25s ease both';
  setTimeout(() => toast.remove(), 260);
}

/* ─── Helpers ──────────────────────────────────────────────────────────── */

function escapeHtml(str) {
  if (!str) return '—';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  return new Date(isoStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
