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
    showUploadResult(`Unsupported format: ${ext}. Use PDF, DOCX, or TXT.`, 'error');
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    showUploadResult('File too large — max 10MB.', 'error');
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
  hideUploadResult();
  document.getElementById('profileCard').style.display = 'none';
  document.getElementById('statProfiles').textContent = '—';
}

/* ═══════════════════════════════════════════════════════════════════════════
   Browser-Side CV Parsing (pdf.js / mammoth.js / FileReader)
   ═══════════════════════════════════════════════════════════════════════════ */

async function parseCV() {
  const fileInput = document.getElementById('cvFileInput');
  if (!fileInput.files || !fileInput.files.length) {
    showUploadResult('Please select a CV file first.', 'error');
    return;
  }

  const file = fileInput.files[0];
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  showProgress('Reading file in browser...', 10);
  hideUploadResult();

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

    showUploadResult(
      `✅ Parsed in browser! Welcome, <strong>${escapeHtml(profile.full_name || 'Candidate')}</strong>. ` +
      `Found ${profile.skills.length} skills, ${profile.years_experience} years experience. ` +
      `<br><small>🔒 File never left your device. Profile stored in browser only.</small>`,
      'success'
    );

    renderProfilePreview(profile);
    document.getElementById('statProfiles').textContent = '1 (local)';

  } catch (e) {
    hideProgress();
    showUploadResult(`❌ Parse failed: ${e.message}`, 'error');
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
   Profile Preview
   ═══════════════════════════════════════════════════════════════════════════ */

function renderProfilePreview(data) {
  const card = document.getElementById('profileCard');
  const body = document.getElementById('profileBody');

  const skillsHtml = (data.skills || []).map(s => {
    const cat = (s.category || 'general').toLowerCase().replace(/\s+/g, '');
    return `<span class="skill-tag ${cat}">${escapeHtml(s.name)} <span class="skill-tag-count">×${s.mentions || 1}</span></span>`;
  }).join('');

  const expHtml = (data.experiences || []).slice(0, 5).map(e => `
    <div class="experience-item">
      <div class="exp-header">
        <span class="exp-title">${escapeHtml(e.title || 'Role')}</span>
        <span class="exp-company">${escapeHtml(e.company || '')}</span>
        ${e.start_date ? `<span class="exp-dates">${escapeHtml(e.start_date)} — ${escapeHtml(e.end_date || 'Present')}</span>` : ''}
      </div>
      ${e.description ? `<div class="exp-desc">${escapeHtml(e.description.slice(0, 200))}</div>` : ''}
    </div>
  `).join('');

  const eduHtml = (data.education || []).map(e => `
    <div class="experience-item">
      <div class="exp-header">
        <span class="exp-title">${escapeHtml(e.institution || '')}</span>
        <span class="exp-company">${escapeHtml(e.degree || '')}</span>
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
        <span style="font-size:11px;color:var(--text-muted);margin-top:4px;">🔒 Stored locally in browser only</span>
      </div>
    </div>
    <div class="profile-details">
      ${skillsHtml ? `<div class="profile-section"><div class="profile-section-title">🛠️ Skills</div><div class="skills-tags">${skillsHtml}</div></div>` : ''}
      ${expHtml ? `<div class="profile-section"><div class="profile-section-title">💼 Experience</div><div class="experience-list">${expHtml}</div></div>` : ''}
      ${eduHtml ? `<div class="profile-section"><div class="profile-section-title">🎓 Education</div><div class="experience-list">${eduHtml}</div></div>` : ''}
    </div>
  `;

  card.style.display = 'block';
  card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ═══════════════════════════════════════════════════════════════════════════
   Cover Letter Generation (stateless — sends raw_text, no profile_id)
   ═══════════════════════════════════════════════════════════════════════════ */

async function generateCoverLetter() {
  if (!latestProfile) {
    showUploadResult('Please parse a CV first.', 'error');
    return;
  }

  const btn = document.getElementById('genClBtn');
  btn.disabled = true;
  btn.innerHTML = '⏳ Finding best job match...';
  showUploadResult('⏳ Generating tailored cover letter...', 'info');

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
      showUploadResult('No matching jobs found. Discover jobs first via Quick Actions.', 'info');
      btn.disabled = false; btn.innerHTML = '✍️ Generate Cover Letter'; return;
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

    showUploadResult(
      `✅ Cover letter generated for <strong>${escapeHtml(topResult.job_title)}</strong> @ <strong>${escapeHtml(topResult.company)}</strong>! ` +
      `(${genData.word_count} words) <br><small>🔒 No data stored on server.</small>`,
      'success'
    );

    const resultArea = document.getElementById('uploadResult');
    const previewDiv = document.createElement('div');
    previewDiv.className = 'cover-letter-preview';
    previewDiv.id = 'coverLetterPreview';
    const previewText = genData.letter_text.slice(0, 1200);
    const isTruncated = genData.letter_text.length > 1200;
    previewDiv.innerHTML = `
      <div class="cl-preview-header">
        <span>📝 Cover Letter Preview</span>
        <button class="btn btn-sm btn-secondary cl-copy-btn">📋 Copy to Clipboard</button>
      </div>
      <pre class="cl-preview-text">${escapeHtml(previewText)}</pre>
      ${isTruncated ? '<div class="cl-preview-truncated">… Preview truncated (' + genData.letter_text.length + ' total chars)</div>' : ''}`;
    resultArea.appendChild(previewDiv);
    previewDiv.querySelector('.cl-copy-btn').addEventListener('click', function () {
      navigator.clipboard.writeText(genData.letter_text).then(() => {
        showUploadResult('✅ Copied!', 'success');
        document.getElementById('uploadResult').appendChild(previewDiv);
      }).catch(() => { document.getElementById('uploadResult').appendChild(previewDiv); });
    });
    loadAll();
  } catch (e) {
    showUploadResult(`⚠️ ${e.message}`, 'info');
  } finally {
    btn.disabled = false; btn.innerHTML = '✍️ Generate Cover Letter';
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   Match Profile (stateless)
   ═══════════════════════════════════════════════════════════════════════════ */

async function matchProfile() {
  if (!latestProfile) { showUploadResult('Please parse a CV first.', 'error'); return; }
  const btn = document.getElementById('matchBtn');
  btn.disabled = true; btn.innerHTML = '⏳ Matching...';
  showUploadResult('⏳ Matching profile against jobs...', 'info');
  try {
    const res = await fetch(`${API_BASE}/api/automation/match`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: 'local', raw_text: latestProfile.raw_text || '', threshold: 0.5, top_k: 10 }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showUploadResult(`✅ Matched! ${data.matched} jobs scored. Check the Applications table below.`, 'success');
    loadAll();
  } catch (e) {
    showUploadResult(`⚠️ ${e.message}`, 'info');
  } finally {
    btn.disabled = false; btn.innerHTML = '⚖️ Match Jobs';
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   Analyze & Apply (stateless)
   ═══════════════════════════════════════════════════════════════════════════ */

async function analyzeAndApply() {
  if (!latestProfile) { showUploadResult('Please parse a CV first.', 'error'); return; }
  const btn = document.getElementById('analyzeBtn');
  const origText = btn.innerHTML;
  btn.disabled = true; btn.innerHTML = '⏳ Analyzing...';
  showUploadResult('⏳ Analyzing skills vs job requirements...', 'info');
  try {
    const analyzeRes = await fetch(`${API_BASE}/api/automation/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: 'local', raw_text: latestProfile.raw_text || '', threshold: 0.60, auto_apply: false, top_k: 50 }),
    });
    if (!analyzeRes.ok) throw new Error(await analyzeRes.text());
    const analysis = await analyzeRes.json();
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
        <span class="analyze-pill">📊 Scored: <strong>${totalJobs}</strong></span>
      </div>`;
    if (eligibleJobs.length > 0) {
      html += '<div class="analyze-table-wrap"><table class="analyze-table"><thead><tr><th>Score</th><th>Role</th><th>Company</th><th>Skills ✓</th><th>Skills ✗</th></tr></thead><tbody>';
      eligibleJobs.slice(0, 10).forEach(j => {
        html += `<tr><td class="score-cell">${(j.score * 100).toFixed(0)}%</td><td>${escapeHtml(j.job_title)}</td><td>${escapeHtml(j.company)}</td><td class="overlap-cell">${(j.skill_overlap || []).slice(0, 4).join(', ')}</td><td class="gap-cell">${(j.skill_gaps || []).slice(0, 4).join(', ')}</td></tr>`;
      });
      html += '</tbody></table></div>';
    } else {
      html += '<div class="analyze-empty">No jobs meet the 60% threshold.</div>';
    }
    showUploadResult(html, 'success');
    window._analysisData = analysis;
    window._eligibleJobIds = eligibleJobs.map(j => j.job_id);
    loadAll();
  } catch (e) {
    showUploadResult(`⚠️ ${e.message}`, 'info');
  } finally {
    btn.disabled = false; btn.innerHTML = origText;
  }
}

async function applyEligibleJobs() {
  if (!window._eligibleJobIds || !window._eligibleJobIds.length) {
    showUploadResult('No eligible jobs. Run analysis first.', 'error');
    return;
  }
  const btn = document.getElementById('applyEligibleBtn');
  if (btn) { btn.disabled = true; btn.innerHTML = '⏳ Applying...'; }
  showUploadResult(`⏳ Processing ${window._eligibleJobIds.length} jobs...`, 'info');
  let submitted = 0, failed = 0;
  for (const jobId of window._eligibleJobIds) {
    try {
      const matchRes = await fetch(`${API_BASE}/api/automation/match`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile_id: 'local', raw_text: latestProfile?.raw_text || '', job_ids: [jobId], threshold: 0.3, top_k: 1 }),
      });
      if (!matchRes.ok) { failed++; continue; }
      const matchData = await matchRes.json();
      if (matchData.results?.[0]?.application_id) submitted++;
    } catch (e) { failed++; }
  }
  showUploadResult(`✅ Done! ${submitted} matched, ${failed} failed.`, 'success');
  if (btn) { btn.disabled = false; btn.innerHTML = '🤖 Auto-Apply'; }
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
    if (!apps.length) { tbody.innerHTML = '<tr><td colspan="7" class="loading">No applications</td></tr>'; return; }
    tbody.innerHTML = apps.map(app => `
      <tr>
        <td><span class="status-badge-cell status-${app.status}">● ${app.status}</span></td>
        <td>${escapeHtml(app.job_title)}</td>
        <td>${escapeHtml(app.company)}</td>
        <td>${(app.match_score * 100).toFixed(0)}%</td>
        <td>${app.ats_name || '—'}</td>
        <td>${app.fields_filled}/${app.total_fields}</td>
        <td>${formatDate(app.created_at)}</td>
      </tr>`).join('');
  } catch (e) {
    document.getElementById('applicationsBody').innerHTML = '<tr><td colspan="7" class="loading">⚠ Connection error</td></tr>';
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

/* ─── Upload Result ────────────────────────────────────────────────────── */

function showUploadResult(message, type) {
  const el = document.getElementById('uploadResult');
  el.style.display = 'block';
  el.className = 'upload-result ' + (type || 'info');
  el.innerHTML = message;
}

function hideUploadResult() {
  document.getElementById('uploadResult').style.display = 'none';
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
