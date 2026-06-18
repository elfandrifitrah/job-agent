/* ─── Client-Side ATS Resume Checker ─────────────────────────────────────── */
/* Pure JS logic, zero network calls. Ported from backend/services/ats_checker.py */

const ACTION_VERBS = [
  "achieved","accelerated","acquired","built","chaired","compiled",
  "completed","conceived","conducted","consolidated","created","cut",
  "decreased","defined","delivered","designed","developed","devised",
  "directed","drove","earned","eliminated","enabled","established",
  "evaluated","executed","expanded","expedited","formulated","founded",
  "generated","grew","headed","identified","implemented","improved",
  "increased","initiated","instituted","integrated","introduced","invented",
  "launched","led","managed","mentored","negotiated","optimized",
  "orchestrated","organized","overhauled","pioneered","planned","prepared",
  "presented","produced","programmed","proposed","raised","recommended",
  "reduced","reengineered","reorganized","replaced","resolved","restructured",
  "revamped","revitalized","saved","shaped","simplified","slashed",
  "spearheaded","standardized","steered","streamlined","strengthened",
  "structured","succeeded","transformed","upgraded","won",
];

const SECTION_HEADERS = [
  "experience","work experience","employment","professional experience",
  "education","academic","qualifications",
  "skills","technical skills","core competencies",
  "summary","professional summary","profile","objective",
  "projects","certifications","publications","awards",
  "languages","volunteer","interests",
];

const ATS_FORMATS = { ".pdf": 100, ".docx": 90, ".doc": 70, ".txt": 50, ".rtf": 60 };

export function runAtsCheck(cvText, jobSkills, fileExtension) {
  const ext = (fileExtension || '.pdf').toLowerCase().trim();
  const lowerText = cvText.toLowerCase();
  const lines = cvText.split('\n');
  const words = cvText.split(/\s+/).filter(Boolean);

  const criteria = [];
  const suggestions = [];

  // ── Keyword Match (35%) ──────────────────────────────────────────────────
  let kwScore = 0;
  if (!jobSkills || jobSkills.length === 0) {
    kwScore = 50;
    criteria.push({ name: "keyword_density", passed: true, score: 50, detail: "No job skills provided" });
  } else {
    let foundCount = 0;
    for (const skill of jobSkills) {
      const sl = skill.toLowerCase();
      const found = lowerText.includes(sl);
      if (found) foundCount++;
      criteria.push({
        name: "skill_" + skill.replace(/\s+/g, '_').toLowerCase().slice(0, 20),
        passed: found, score: found ? 100 : 0,
        detail: `Skill '${skill}' ${found ? 'found' : 'not found'} in CV`,
      });
    }
    const matchPct = (foundCount / jobSkills.length) * 100;
    kwScore = matchPct;
    criteria.push({
      name: "keyword_match_overall", passed: matchPct >= 50, score: matchPct,
      detail: `${foundCount}/${jobSkills.length} required skills found (${Math.round(matchPct)}%)`,
    });
    if (matchPct < 50) suggestions.push("Add more keywords from the job description to your CV");
  }

  // ── Format (25%) ─────────────────────────────────────────────────────────
  let fmtScore = 0;
  let fmtChecks = 0;

  // Section headers
  const foundSections = SECTION_HEADERS.filter(h => lowerText.includes(h));
  const sectionPct = Math.min(100, (foundSections.length / 5) * 100);
  fmtScore += sectionPct; fmtChecks++;
  criteria.push({
    name: "section_headers", passed: sectionPct >= 60, score: sectionPct,
    detail: `Found ${foundSections.length} sections: ${foundSections.slice(0, 6).join(', ')}`,
  });
  if (foundSections.length < 4) suggestions.push("Add Experience, Education, Skills, Summary headers");

  // Bullet usage
  const bulletCount = (cvText.match(/^[\s]*[•\-\*\d+\.]\s/gm) || []).length;
  const contentLines = lines.filter(l => l.trim()).length;
  const bulletRatio = contentLines > 0 ? bulletCount / contentLines : 0;
  const bulletScore = Math.min(100, (bulletRatio / 0.5) * 100);
  fmtScore += bulletScore; fmtChecks++;
  criteria.push({
    name: "bullet_points", passed: bulletScore >= 50, score: bulletScore,
    detail: `${bulletCount} bullets in ${contentLines} lines (${Math.round(bulletRatio * 100)}%)`,
  });
  if (bulletCount < 15) suggestions.push("Use more bullet points (ATS prefers bullets)");

  // Length
  const wordCount = words.length;
  let lengthScore;
  if (wordCount >= 400 && wordCount <= 1200) lengthScore = 100;
  else if (wordCount < 300) lengthScore = 40;
  else if (wordCount < 400) lengthScore = 70;
  else if (wordCount > 1500) lengthScore = 60;
  else lengthScore = 80;
  fmtScore += lengthScore; fmtChecks++;
  criteria.push({
    name: "cv_length", passed: wordCount >= 400 && wordCount <= 1200,
    score: lengthScore,
    detail: `${wordCount} words (ideal: 400-1200)`,
  });
  if (wordCount > 1200) suggestions.push("Trim CV to 1-2 pages");
  else if (wordCount < 300) suggestions.push("Add more detail (~500 words minimum)");

  // File format
  const formatScore = ATS_FORMATS[ext] || 30;
  fmtScore += formatScore; fmtChecks++;
  criteria.push({
    name: "file_format", passed: formatScore >= 70, score: formatScore,
    detail: `Format: ${ext.toUpperCase()} (PDF best for ATS)`,
  });
  if (ext !== '.pdf') suggestions.push("Upload as PDF for best ATS compatibility");

  // Chronological order (date ranges found)
  const dateRanges = lowerText.match(/(?:19|20)\d{2}\s*[-–to]+\s*(?:\w+|(?:19|20)\d{2})/g) || [];
  const chronoScore = dateRanges.length > 0 ? 70 : 50;
  fmtScore += chronoScore; fmtChecks++;
  criteria.push({
    name: "chronological_order", passed: chronoScore >= 70, score: chronoScore,
    detail: `Found ${dateRanges.length} date ranges`,
  });

  // Consistent formatting
  const markers = new Set((cvText.match(/^[\s]*([•\-\*\d+\.])\s/gm) || []).map(m => m.trim()[0]));
  const consistent = markers.size <= 2;
  const consistencyScore = consistent ? 100 : 60;
  fmtScore += consistencyScore; fmtChecks++;
  criteria.push({
    name: "consistent_formatting", passed: consistent, score: consistencyScore,
    detail: consistent ? "Bullet styles consistent" : `Mixed markers: ${[...markers].join(', ')}`,
  });
  if (!consistent) suggestions.push("Use one bullet style throughout");

  fmtScore = fmtScore / Math.max(fmtChecks, 1);

  // ── Impact (25%) ────────────────────────────────────────────────────────
  let impScore = 0;
  let impChecks = 0;

  const verbCount = ACTION_VERBS.filter(v => lowerText.includes(v)).length;
  const verbDensity = wordCount > 0 ? (verbCount / wordCount) * 1000 : 0;
  const verbScore = Math.min(100, (verbDensity / 15) * 100);
  impScore += verbScore; impChecks++;
  criteria.push({
    name: "action_verbs", passed: verbScore >= 50, score: verbScore,
    detail: `${verbCount} action verbs (${verbDensity.toFixed(1)}/1000 words)`,
  });
  if (verbCount < 10) suggestions.push("Start bullets with strong action verbs");

  // Quantified results
  const numberCount = (lowerText.match(/\b\d+%|\$\s*\d+[kKmMbB]?|\b\d+x\b|\b\d+(?:\.\d+)?\s*(?:million|billion|users|customers|revenue|cost)\b/g) || []).length;
  const quantScore = Math.min(100, (numberCount / 5) * 100);
  impScore += quantScore; impChecks++;
  criteria.push({
    name: "quantified_results", passed: quantScore >= 40, score: quantScore,
    detail: `${numberCount} quantified metrics (aim for 5+)`,
  });
  if (numberCount < 3) suggestions.push("Add quantified results (%, $, users impacted)");

  // Bullet starts with action verbs
  const bulletStarts = [...cvText.matchAll(/^[\s]*[•\-\*]\s+(\w+)/gm)].map(m => m[1].toLowerCase());
  const strongStarts = bulletStarts.filter(w => ACTION_VERBS.includes(w)).length;
  const startRatio = bulletStarts.length > 0 ? strongStarts / bulletStarts.length : 0;
  const startScore = startRatio * 100;
  impScore += startScore; impChecks++;
  criteria.push({
    name: "bullet_starts", passed: startRatio >= 0.5, score: startScore,
    detail: `${strongStarts}/${bulletStarts.length} bullets start with action verbs (${Math.round(startRatio * 100)}%)`,
  });
  if (startRatio < 0.3) suggestions.push("Start every bullet with a strong action verb");

  impScore = impScore / Math.max(impChecks, 1);

  // ── Completeness (15%) ──────────────────────────────────────────────────
  let compScore = 0;
  let compChecks = 0;

  const hasEmail = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/.test(cvText);
  compScore += hasEmail ? 100 : 0; compChecks++;
  criteria.push({
    name: "email_present", passed: hasEmail, score: hasEmail ? 100 : 0,
    detail: hasEmail ? "Email found" : "No email found",
  });
  if (!hasEmail) suggestions.push("Add your email at the top");

  const hasPhone = /[\+\d\(\)\-\s]{8,}/.test(cvText);
  compScore += hasPhone ? 100 : 0; compChecks++;
  criteria.push({
    name: "phone_present", passed: hasPhone, score: hasPhone ? 100 : 0,
    detail: hasPhone ? "Phone found" : "No phone found",
  });
  if (!hasPhone) suggestions.push("Add your phone number");

  const hasLinkedin = lowerText.includes("linkedin.com") || lowerText.includes("linkedin");
  compScore += hasLinkedin ? 100 : 0; compChecks++;
  criteria.push({
    name: "linkedin_present", passed: hasLinkedin, score: hasLinkedin ? 100 : 0,
    detail: hasLinkedin ? "LinkedIn found" : "No LinkedIn URL",
  });

  const eduKeywords = ["education","bachelor","master","phd","b.s.","m.s.","b.a.","m.a."];
  const hasEducation = eduKeywords.some(k => lowerText.includes(k));
  compScore += hasEducation ? 100 : 0; compChecks++;
  criteria.push({
    name: "education_section", passed: hasEducation, score: hasEducation ? 100 : 0,
    detail: hasEducation ? "Education found" : "No education section",
  });

  const hasExperience = lowerText.includes("experience") || lowerText.includes("employment") || lowerText.includes("work history");
  compScore += hasExperience ? 100 : 0; compChecks++;
  criteria.push({
    name: "experience_section", passed: hasExperience, score: hasExperience ? 100 : 0,
    detail: hasExperience ? "Experience found" : "No experience section",
  });
  if (!hasExperience) suggestions.push("Add a Work Experience section");

  const hasSkills = lowerText.includes("skills") || lowerText.includes("competencies");
  compScore += hasSkills ? 100 : 0; compChecks++;
  criteria.push({
    name: "skills_section", passed: hasSkills, score: hasSkills ? 100 : 0,
    detail: hasSkills ? "Skills found" : "No skills section",
  });
  if (!hasSkills) suggestions.push("Add a Skills section");

  const hasDateRanges = (lowerText.match(/(?:19|20)\d{2}\s*[-–to]+\s*(?:\w+|(?:19|20)\d{2})/g) || []).length > 0;
  compScore += hasDateRanges ? 100 : 0; compChecks++;
  criteria.push({
    name: "date_ranges", passed: hasDateRanges, score: hasDateRanges ? 100 : 0,
    detail: hasDateRanges ? "Date ranges found" : "No date ranges found",
  });
  if (!hasDateRanges) suggestions.push("Add start/end dates to experience entries");

  compScore = compScore / Math.max(compChecks, 1);

  // ── Composite ───────────────────────────────────────────────────────────
  const composite = Math.round(kwScore * 0.35 + fmtScore * 0.25 + impScore * 0.25 + compScore * 0.15);

  return {
    keyword_match: Math.round(kwScore),
    format_score: Math.round(fmtScore),
    impact_score: Math.round(impScore),
    completeness_score: Math.round(compScore),
    composite,
    criteria,
    suggestions: suggestions.slice(0, 10),
  };
}
