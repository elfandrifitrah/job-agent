"""
Seed script — populates the database with 75 jobs and 100+ application records.

Run: python -m backend.seed_data
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession

from backend.models.db_models import (
    ApplicationModel,
    Base,
    JobModel,
    ProfileModel,
    _utcnow,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")


# ═══════════════════════════════════════════════════════════════════════════════
# PROFILES — 3 candidates
# ═══════════════════════════════════════════════════════════════════════════════

PROFILES = [
    {
        "full_name": "Alex Chen",
        "email": "alex.chen@email.com",
        "phone": "+1-555-0101",
        "location": "San Francisco, CA",
        "linkedin_url": "https://linkedin.com/in/alexchen",
        "github_url": "https://github.com/alexchen",
        "years_of_experience": 6.0,
        "seniority": "senior",
        "remote_preferred": True,
        "target_roles": ["Senior Software Engineer", "Staff Engineer", "Tech Lead"],
        "preferred_locations": ["San Francisco", "Remote"],
        "skills": [
            {"name": "Python", "category": "language", "confidence": 0.95, "mentions": 8},
            {"name": "TypeScript", "category": "language", "confidence": 0.85, "mentions": 5},
            {"name": "React", "category": "framework", "confidence": 0.8, "mentions": 4},
            {"name": "FastAPI", "category": "framework", "confidence": 0.9, "mentions": 6},
            {"name": "PostgreSQL", "category": "database", "confidence": 0.85, "mentions": 5},
            {"name": "Docker", "category": "cloud", "confidence": 0.8, "mentions": 4},
            {"name": "AWS", "category": "cloud", "confidence": 0.75, "mentions": 3},
            {"name": "Kubernetes", "category": "cloud", "confidence": 0.7, "mentions": 3},
        ],
        "experiences": [
            {"company": "TechCorp", "title": "Senior Software Engineer", "start_date": "2022-03", "end_date": "Present",
             "description": "Led migration of monolith to microservices. Built real-time data pipeline processing 1M+ events/day."},
            {"company": "StartupXYZ", "title": "Software Engineer", "start_date": "2019-01", "end_date": "2022-02",
             "description": "Built REST APIs and frontend features. Hired and mentored 3 junior engineers."},
            {"company": "BigCo", "title": "Junior Developer", "start_date": "2017-06", "end_date": "2018-12",
             "description": "Maintained internal tooling and automated CI/CD pipelines."},
        ],
        "education": [
            {"institution": "UC Berkeley", "degree": "B.S.", "field": "Computer Science"},
        ],
    },
    {
        "full_name": "Sarah Williams",
        "email": "sarah.w@email.com",
        "phone": "+1-555-0202",
        "location": "New York, NY",
        "linkedin_url": "https://linkedin.com/in/sarahw",
        "github_url": "https://github.com/sarahw",
        "years_of_experience": 4.0,
        "seniority": "mid",
        "remote_preferred": False,
        "target_roles": ["Data Scientist", "ML Engineer", "Data Engineer"],
        "preferred_locations": ["New York", "Boston"],
        "skills": [
            {"name": "Python", "category": "language", "confidence": 0.9, "mentions": 7},
            {"name": "TensorFlow", "category": "framework", "confidence": 0.85, "mentions": 5},
            {"name": "PyTorch", "category": "framework", "confidence": 0.8, "mentions": 4},
            {"name": "SQL", "category": "language", "confidence": 0.85, "mentions": 5},
            {"name": "Pandas", "category": "framework", "confidence": 0.9, "mentions": 6},
            {"name": "Spark", "category": "tool", "confidence": 0.75, "mentions": 3},
            {"name": "Airflow", "category": "tool", "confidence": 0.7, "mentions": 3},
        ],
        "experiences": [
            {"company": "DataFlow Inc", "title": "Data Scientist", "start_date": "2021-06", "end_date": "Present",
             "description": "Built ML models for fraud detection. Reduced false positives by 40%."},
            {"company": "AnalyticsCo", "title": "Junior Data Analyst", "start_date": "2019-08", "end_date": "2021-05",
             "description": "Created dashboards and ETL pipelines using SQL and Python."},
        ],
        "education": [
            {"institution": "MIT", "degree": "M.S.", "field": "Data Science"},
            {"institution": "Cornell", "degree": "B.S.", "field": "Statistics"},
        ],
    },
    {
        "full_name": "Maria Garcia",
        "email": "maria.g@email.com",
        "phone": "+1-555-0303",
        "location": "Austin, TX",
        "linkedin_url": "https://linkedin.com/in/mariag",
        "years_of_experience": 8.0,
        "seniority": "principal",
        "remote_preferred": True,
        "target_roles": ["Principal Engineer", "Engineering Manager", "Director of Engineering"],
        "preferred_locations": ["Austin", "Remote", "San Francisco"],
        "skills": [
            {"name": "Go", "category": "language", "confidence": 0.9, "mentions": 6},
            {"name": "Python", "category": "language", "confidence": 0.85, "mentions": 5},
            {"name": "Kubernetes", "category": "cloud", "confidence": 0.95, "mentions": 8},
            {"name": "Terraform", "category": "cloud", "confidence": 0.9, "mentions": 6},
            {"name": "AWS", "category": "cloud", "confidence": 0.95, "mentions": 8},
            {"name": "Distributed Systems", "category": "tool", "confidence": 0.9, "mentions": 7},
            {"name": "Leadership", "category": "soft", "confidence": 0.85, "mentions": 5},
        ],
        "experiences": [
            {"company": "CloudScale", "title": "Principal Engineer", "start_date": "2020-01", "end_date": "Present",
             "description": "Architected multi-region Kubernetes platform serving 10M+ users."},
            {"company": "WebServices Co", "title": "Senior Backend Engineer", "start_date": "2017-03", "end_date": "2019-12",
             "description": "Led team of 5 building microservices on AWS EKS."},
            {"company": "Startup Inc", "title": "Software Engineer", "start_date": "2014-09", "end_date": "2017-02",
             "description": "Early employee — built MVP that led to Series A funding."},
        ],
        "education": [
            {"institution": "Stanford", "degree": "M.S.", "field": "Computer Science"},
            {"institution": "UT Austin", "degree": "B.S.", "field": "Computer Engineering"},
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════════
# JOBS — 75 postings (25 original + 50 new)
# ═══════════════════════════════════════════════════════════════════════════════

JOBS = [
    # ─── 0-9: Software Engineering ───
    {"title": "Senior Software Engineer", "company": "Google", "location": "Mountain View, CA", "source": "linkedin", "remote": False, "seniority": "senior",
     "description": "Build and maintain large-scale distributed systems powering Google Search. 5+ years experience in C++, Java, or Python required.",
     "skills_required": ["Python", "C++", "Java", "Distributed Systems", "Kubernetes"], "salary_range": "$180K – $260K"},
    {"title": "Staff Software Engineer", "company": "Stripe", "location": "San Francisco, CA", "source": "greenhouse", "remote": True, "seniority": "staff",
     "description": "Design and build the next generation of payment infrastructure. Lead technical strategy for core payments team.",
     "skills_required": ["Python", "Go", "PostgreSQL", "Distributed Systems", "API Design"], "salary_range": "$220K – $320K"},
    {"title": "Backend Engineer — Platform", "company": "GitHub", "location": "Remote", "source": "lever", "remote": True, "seniority": "senior",
     "description": "Build the platform that powers millions of developers. Focus on performance, reliability, and developer experience.",
     "skills_required": ["Ruby", "Go", "PostgreSQL", "Redis", "Kubernetes"], "salary_range": "$170K – $250K"},
    {"title": "Software Engineer — Infrastructure", "company": "Netflix", "location": "Los Gatos, CA", "source": "linkedin", "remote": False, "seniority": "senior",
     "description": "Build and operate the infrastructure that delivers streaming to 200M+ subscribers worldwide.",
     "skills_required": ["Java", "Python", "AWS", "Kubernetes", "Terraform"], "salary_range": "$200K – $350K"},
    {"title": "Full Stack Engineer", "company": "Notion", "location": "San Francisco, CA", "source": "greenhouse", "remote": True, "seniority": "mid",
     "description": "Build features that make knowledge management delightful. Work across the stack from React to PostgreSQL.",
     "skills_required": ["TypeScript", "React", "Node.js", "PostgreSQL", "CSS"], "salary_range": "$150K – $220K"},
    {"title": "Lead Engineer — AI Platform", "company": "Anthropic", "location": "San Francisco, CA", "source": "greenhouse", "remote": False, "seniority": "principal",
     "description": "Lead development of the platform that powers Claude. Shape the architecture of cutting-edge AI infrastructure.",
     "skills_required": ["Python", "PyTorch", "Kubernetes", "Distributed Systems", "CUDA"], "salary_range": "$250K – $400K"},
    {"title": "Senior Backend Engineer", "company": "Shopify", "location": "Remote", "source": "lever", "remote": True, "seniority": "senior",
     "description": "Build the commerce platform for millions of merchants. Scale systems to handle Black Friday traffic spikes.",
     "skills_required": ["Ruby", "Python", "PostgreSQL", "Redis", "Kafka"], "salary_range": "$160K – $240K"},
    {"title": "Engineering Manager — Core Services", "company": "Datadog", "location": "New York, NY", "source": "linkedin", "remote": True, "seniority": "senior",
     "description": "Lead a team of 6-8 engineers building observability products. Drive technical strategy and career growth.",
     "skills_required": ["Go", "Python", "Kubernetes", "Leadership", "Distributed Systems"], "salary_range": "$210K – $300K"},
    {"title": "Junior Software Engineer", "company": "Coda", "location": "San Francisco, CA", "source": "indeed", "remote": False, "seniority": "junior",
     "description": "Join a small team building the next generation of collaborative documents. Great mentorship and growth opportunities.",
     "skills_required": ["TypeScript", "React", "Node.js"], "salary_range": "$110K – $140K"},
    {"title": "Software Engineer — Growth", "company": "Figma", "location": "San Francisco, CA", "source": "greenhouse", "remote": False, "seniority": "mid",
     "description": "Build features that drive user acquisition and retention. A/B test and iterate rapidly.",
     "skills_required": ["TypeScript", "React", "Python", "SQL", "A/B Testing"], "salary_range": "$140K – $200K"},

    # ─── 10-19: Data / ML ───
    {"title": "Senior Data Scientist", "company": "Spotify", "location": "New York, NY", "source": "linkedin", "remote": False, "seniority": "senior",
     "description": "Use data to personalize the listening experience for 400M+ users. Build recommendation models and experimentation platforms.",
     "skills_required": ["Python", "SQL", "TensorFlow", "Spark", "A/B Testing"], "salary_range": "$180K – $260K"},
    {"title": "ML Engineer — Search", "company": "Pinecone", "location": "Remote", "source": "adzuna", "remote": True, "seniority": "mid",
     "description": "Build vector search infrastructure for AI applications. Work on cutting-edge embedding and retrieval systems.",
     "skills_required": ["Python", "PyTorch", "Rust", "Vector Databases", "NLP"], "salary_range": "$160K – $230K"},
    {"title": "Data Engineer", "company": "Airbnb", "location": "San Francisco, CA", "source": "linkedin", "remote": True, "seniority": "mid",
     "description": "Build and maintain data pipelines powering business intelligence and ML models across the company.",
     "skills_required": ["Python", "SQL", "Spark", "Airflow", "Snowflake"], "salary_range": "$150K – $220K"},
    {"title": "Research Scientist — NLP", "company": "OpenAI", "location": "San Francisco, CA", "source": "greenhouse", "remote": False, "seniority": "senior",
     "description": "Push the boundaries of language models. Conduct research and ship production systems.",
     "skills_required": ["Python", "PyTorch", "NLP", "Transformers", "Distributed Training"], "salary_range": "$250K – $400K"},
    {"title": "Analytics Engineer", "company": "dbt Labs", "location": "Remote", "source": "lever", "remote": True, "seniority": "mid",
     "description": "Build tools that empower data teams. Work on the analytics engineering workflow and community.",
     "skills_required": ["SQL", "Python", "dbt", "Snowflake", "Data Modeling"], "salary_range": "$130K – $190K"},
    {"title": "Machine Learning Engineer", "company": "Scale AI", "location": "San Francisco, CA", "source": "greenhouse", "remote": True, "seniority": "mid",
     "description": "Build ML systems that power the world's most advanced AI models. Work on data quality, model evaluation, and RLHF pipelines.",
     "skills_required": ["Python", "PyTorch", "NLP", "Kubernetes", "Ray"], "salary_range": "$170K – $250K"},
    {"title": "Data Scientist — Recommendations", "company": "Pinterest", "location": "San Francisco, CA", "source": "linkedin", "remote": False, "seniority": "senior",
     "description": "Build recommendation systems connecting 450M+ users with ideas they love. Deep focus on personalization.",
     "skills_required": ["Python", "SQL", "TensorFlow", "Spark", "Recommendation Systems"], "salary_range": "$190K – $280K"},
    {"title": "BI Engineer", "company": "Snowflake", "location": "San Mateo, CA", "source": "adzuna", "remote": True, "seniority": "mid",
     "description": "Build the analytics infrastructure powering Snowflake's data cloud. Work with the teams that manage petabytes of data.",
     "skills_required": ["SQL", "Python", "dbt", "Snowflake", "Looker"], "salary_range": "$150K – $220K"},
    {"title": "Applied Scientist", "company": "Amazon", "location": "Seattle, WA", "source": "linkedin", "remote": False, "seniority": "senior",
     "description": "Apply cutting-edge ML research to Amazon's supply chain optimization problems. Publish papers and file patents.",
     "skills_required": ["Python", "TensorFlow", "PyTorch", "NLP", "Computer Vision"], "salary_range": "$200K – $300K"},
    {"title": "Data Engineer II", "company": "Meta", "location": "Menlo Park, CA", "source": "indeed", "remote": False, "seniority": "mid",
     "description": "Build data pipelines that power Facebook, Instagram, and WhatsApp. Work at petabyte scale on real-time data.",
     "skills_required": ["Python", "SQL", "Spark", "Hive", "Airflow"], "salary_range": "$170K – $250K"},

    # ─── 20-29: DevOps / Platform / Security ───
    {"title": "Senior DevOps Engineer", "company": "Cloudflare", "location": "Austin, TX", "source": "adzuna", "remote": True, "seniority": "senior",
     "description": "Operate one of the world's largest networks. Automate everything and improve reliability at scale.",
     "skills_required": ["Go", "Kubernetes", "Terraform", "Linux", "Networking"], "salary_range": "$180K – $260K"},
    {"title": "Platform Engineer", "company": "Vercel", "location": "San Francisco, CA", "source": "greenhouse", "remote": True, "seniority": "mid",
     "description": "Build the platform that powers the frontend web. Work on Edge Functions, ISR, and build infrastructure.",
     "skills_required": ["TypeScript", "Go", "Kubernetes", "AWS", "Terraform"], "salary_range": "$150K – $220K"},
    {"title": "SRE — Compute Platform", "company": "Lyft", "location": "San Francisco, CA", "source": "linkedin", "remote": False, "seniority": "senior",
     "description": "Ensure the reliability of ride-sharing infrastructure. Incident response, capacity planning, and automation.",
     "skills_required": ["Go", "Kubernetes", "AWS", "Monitoring", "Incident Response"], "salary_range": "$180K – $260K"},
    {"title": "Cloud Infrastructure Engineer", "company": "DigitalOcean", "location": "New York, NY", "source": "lever", "remote": True, "seniority": "mid",
     "description": "Build and maintain the cloud platform that powers over a million developers. Focus on simplicity and performance.",
     "skills_required": ["Go", "Kubernetes", "Terraform", "Linux", "CFSSL"], "salary_range": "$140K – $200K"},
    {"title": "Security Engineer", "company": "CrowdStrike", "location": "Austin, TX", "source": "greenhouse", "remote": True, "seniority": "senior",
     "description": "Protect the world's most sensitive networks. Build endpoint detection and response systems at global scale.",
     "skills_required": ["Go", "Python", "Kubernetes", "Security", "Linux"], "salary_range": "$190K – $280K"},
    {"title": "Platform Architect", "company": "Twilio", "location": "San Francisco, CA", "source": "linkedin", "remote": True, "seniority": "principal",
     "description": "Design the next-generation communications platform. Define technical strategy across 50+ microservices.",
     "skills_required": ["Go", "Kubernetes", "Terraform", "AWS", "API Design"], "salary_range": "$240K – $350K"},
    {"title": "Site Reliability Engineer", "company": "Uber", "location": "San Francisco, CA", "source": "indeed", "remote": False, "seniority": "senior",
     "description": "Keep Uber's marketplace running at global scale. Build self-healing systems and drive incident response.",
     "skills_required": ["Go", "Kubernetes", "AWS", "Terraform", "Kafka"], "salary_range": "$190K – $280K"},
    {"title": "DevOps Engineer", "company": "GitLab", "location": "Remote", "source": "lever", "remote": True, "seniority": "mid",
     "description": "Help operate the world's largest single-codebase DevOps platform. Dogfood GitLab CI/CD daily.",
     "skills_required": ["Go", "Kubernetes", "Terraform", "GCP", "Prometheus"], "salary_range": "$140K – $200K"},
    {"title": "Network Engineer", "company": "Cisco", "location": "San Jose, CA", "source": "adzuna", "remote": False, "seniority": "mid",
     "description": "Design and maintain global network infrastructure. Work on SDN, automation, and next-gen routing.",
     "skills_required": ["Go", "Linux", "Networking", "SDN", "Automation"], "salary_range": "$140K – $210K"},
    {"title": "Infrastructure Engineer", "company": "Fastly", "location": "San Francisco, CA", "source": "greenhouse", "remote": True, "seniority": "senior",
     "description": "Run the edge cloud platform. Optimize CDN performance and build tools for global traffic management.",
     "skills_required": ["Go", "Kubernetes", "Terraform", "Varnish", "Networking"], "salary_range": "$180K – $260K"},

    # ─── 30-39: Frontend / Mobile ───
    {"title": "Senior Frontend Engineer", "company": "Linear", "location": "Remote", "source": "lever", "remote": True, "seniority": "senior",
     "description": "Build the most polished issue tracking experience. Obsess over performance and developer experience.",
     "skills_required": ["TypeScript", "React", "GraphQL", "CSS", "Performance"], "salary_range": "$160K – $230K"},
    {"title": "Mobile Engineer — iOS", "company": "Duolingo", "location": "Pittsburgh, PA", "source": "greenhouse", "remote": False, "seniority": "mid",
     "description": "Build engaging language learning experiences. Work on gamification, animations, and learning science.",
     "skills_required": ["Swift", "iOS", "UIKit", "SwiftUI", "Core Data"], "salary_range": "$140K – $200K"},
    {"title": "Senior React Engineer", "company": "Vercel", "location": "Remote", "source": "linkedin", "remote": True, "seniority": "senior",
     "description": "Push the boundaries of what's possible with React. Work on Next.js and the modern frontend pipeline.",
     "skills_required": ["TypeScript", "React", "Next.js", "Webpack", "CSS"], "salary_range": "$160K – $240K"},
    {"title": "UI Engineer — Design Systems", "company": "Apple", "location": "Cupertino, CA", "source": "greenhouse", "remote": False, "seniority": "senior",
     "description": "Build and maintain Apple's design system used by millions of users across iOS, macOS, and visionOS.",
     "skills_required": ["Swift", "SwiftUI", "UIKit", "Objective-C", "Design Systems"], "salary_range": "$200K – $300K"},
    {"title": "Frontend Engineer — Web", "company": "Coinbase", "location": "Remote", "source": "adzuna", "remote": True, "seniority": "mid",
     "description": "Build the web interface for the world's largest crypto exchange. Focus on security and real-time data.",
     "skills_required": ["TypeScript", "React", "Node.js", "GraphQL", "Web3"], "salary_range": "$150K – $220K"},
    {"title": "Mobile Engineer — Android", "company": "Spotify", "location": "New York, NY", "source": "linkedin", "remote": True, "seniority": "mid",
     "description": "Build the Android experience for 200M+ active users. Focus on performance and offline playback.",
     "skills_required": ["Kotlin", "Android", "Jetpack Compose", "Coroutines", "ExoPlayer"], "salary_range": "$150K – $220K"},
    {"title": "Web Performance Engineer", "company": "Shopify", "location": "Remote", "source": "lever", "remote": True, "seniority": "senior",
     "description": "Make the web faster for millions of merchants. Optimize Core Web Vitals, build performance tooling.",
     "skills_required": ["TypeScript", "React", "Webpack", "Lighthouse", "CDN"], "salary_range": "$160K – $230K"},
    {"title": "React Native Engineer", "company": "Discord", "location": "San Francisco, CA", "source": "greenhouse", "remote": True, "seniority": "mid",
     "description": "Build the Discord mobile app used by 150M+ monthly active users. Own features from conception to shipping.",
     "skills_required": ["TypeScript", "React Native", "React", "GraphQL", "Performance"], "salary_range": "$150K – $220K"},
    {"title": "Junior Frontend Engineer", "company": "Webflow", "location": "San Francisco, CA", "source": "indeed", "remote": True, "seniority": "junior",
     "description": "Join a team building the visual web development platform. Grow your skills with mentorship from senior engineers.",
     "skills_required": ["TypeScript", "React", "CSS", "HTML"], "salary_range": "$100K – $130K"},
    {"title": "Creative Developer", "company": "Stripe", "location": "San Francisco, CA", "source": "greenhouse", "remote": True, "seniority": "mid",
     "description": "Build Stripe's brand and marketing experiences. Work on animations, interactive docs, and developer relations.",
     "skills_required": ["TypeScript", "React", "CSS", "Three.js", "Animation"], "salary_range": "$160K – $230K"},

    # ─── 40-49: Product / Design / Management ───
    {"title": "Product Designer", "company": "Figma", "location": "San Francisco, CA", "source": "adzuna", "remote": True, "seniority": "mid",
     "description": "Design the future of collaborative design tools. Work closely with engineers and product managers.",
     "skills_required": ["Figma", "UI Design", "UX Research", "Prototyping", "Design Systems"], "salary_range": "$140K – $210K"},
    {"title": "Director of Engineering", "company": "Hashicorp", "location": "Remote", "source": "linkedin", "remote": True, "seniority": "executive",
     "description": "Lead multiple engineering teams building infrastructure tools. Drive technical vision and organizational growth.",
     "skills_required": ["Leadership", "Kubernetes", "Terraform", "Distributed Systems", "Strategic Planning"], "salary_range": "$280K – $400K"},
    {"title": "Engineering Lead — Developer Tools", "company": "Replit", "location": "San Francisco, CA", "source": "greenhouse", "remote": True, "seniority": "staff",
     "description": "Lead the team building AI-powered development environments. Shape how millions of developers write code.",
     "skills_required": ["TypeScript", "Go", "React", "Kubernetes", "AI/ML"], "salary_range": "$200K – $300K"},
    {"title": "Product Manager — API Platform", "company": "Twilio", "location": "San Francisco, CA", "source": "linkedin", "remote": True, "seniority": "senior",
     "description": "Define the roadmap for Twilio's communication APIs. Work with developers to build the future of customer engagement.",
     "skills_required": ["Product Strategy", "API Design", "Developer Relations", "Analytics"], "salary_range": "$180K – $260K"},
    {"title": "Design Lead — Core App", "company": "Notion", "location": "New York, NY", "source": "greenhouse", "remote": True, "seniority": "senior",
     "description": "Lead design for Notion's core editing experience. Define visual language and interaction patterns.",
     "skills_required": ["Figma", "UI Design", "Design Systems", "User Research", "Prototyping"], "salary_range": "$180K – $260K"},
    {"title": "VP of Platform Engineering", "company": "GitHub", "location": "Remote", "source": "linkedin", "remote": True, "seniority": "executive",
     "description": "Lead the platform organization that powers GitHub's developer tools. Drive engineering excellence across the company.",
     "skills_required": ["Leadership", "Strategy", "Distributed Systems", "Developer Experience"], "salary_range": "$350K – $500K"},
    {"title": "Technical Product Manager — AI", "company": "Microsoft", "location": "Redmond, WA", "source": "greenhouse", "remote": False, "seniority": "senior",
     "description": "Define the product strategy for Azure AI services. Work with research teams to bring cutting-edge AI to market.",
     "skills_required": ["Product Strategy", "AI/ML", "Azure", "Technical Communication", "NLP"], "salary_range": "$200K – $300K"},
    {"title": "UX Researcher", "company": "Meta", "location": "Menlo Park, CA", "source": "adzuna", "remote": False, "seniority": "mid",
     "description": "Conduct research that shapes the future of social media. Use qualitative and quantitative methods.",
     "skills_required": ["User Research", "Usability Testing", "Statistics", "Survey Design", "Qualitative Analysis"], "salary_range": "$150K – $220K"},
    {"title": "Engineering Director — ML Platform", "company": "Netflix", "location": "Los Gatos, CA", "source": "linkedin", "remote": False, "seniority": "executive",
     "description": "Lead the ML platform team that powers Netflix's personalization, recommendations, and content understanding.",
     "skills_required": ["Leadership", "ML Infrastructure", "Kubernetes", "PyTorch", "Strategic Planning"], "salary_range": "$350K – $500K"},
    {"title": "Staff Product Designer", "company": "Linear", "location": "Remote", "source": "greenhouse", "remote": True, "seniority": "staff",
     "description": "Define the design vision for Linear. Create pixel-perfect interfaces that make project management a joy.",
     "skills_required": ["Figma", "UI Design", "Interaction Design", "Design Systems", "Typography"], "salary_range": "$190K – $280K"},

    # ─── 50-59: Emerging Tech / AI ───
    {"title": "AI Engineer — Agentic Systems", "company": "Anthropic", "location": "San Francisco, CA", "source": "greenhouse", "remote": False, "seniority": "senior",
     "description": "Build autonomous AI systems that can execute complex, multi-step tasks. Push the boundaries of what LLMs can do.",
     "skills_required": ["Python", "PyTorch", "NLP", "LangChain", "Kubernetes"], "salary_range": "$220K – $350K"},
    {"title": "Prompt Engineer", "company": "OpenAI", "location": "San Francisco, CA", "source": "linkedin", "remote": False, "seniority": "mid",
     "description": "Design and optimize prompts for GPT models. Build evaluation pipelines and contribute to safety research.",
     "skills_required": ["Python", "NLP", "Prompt Engineering", "Evaluation", "Statistics"], "salary_range": "$160K – $240K"},
    {"title": "Computer Vision Engineer", "company": "Tesla", "location": "Palo Alto, CA", "source": "adzuna", "remote": False, "seniority": "senior",
     "description": "Build the vision system that powers Tesla's autonomous driving. Work on real-time object detection and tracking.",
     "skills_required": ["Python", "PyTorch", "Computer Vision", "CUDA", "C++"], "salary_range": "$200K – $320K"},
    {"title": "Blockchain Engineer", "company": "Coinbase", "location": "Remote", "source": "lever", "remote": True, "seniority": "mid",
     "description": "Build the next generation of on-chain applications. Work on DeFi, NFTs, and Layer 2 scaling solutions.",
     "skills_required": ["Go", "Solidity", "Ethereum", "TypeScript", "Web3.js"], "salary_range": "$160K – $240K"},
    {"title": "AI Platform Engineer", "company": "Nvidia", "location": "Santa Clara, CA", "source": "greenhouse", "remote": False, "seniority": "senior",
     "description": "Build the platform that trains the world's largest AI models. Work on GPU clusters, distributed training, and CUDA optimization.",
     "skills_required": ["Python", "CUDA", "Kubernetes", "PyTorch", "Distributed Systems"], "salary_range": "$220K – $350K"},
    {"title": "Robotics Software Engineer", "company": "Boston Dynamics", "location": "Waltham, MA", "source": "linkedin", "remote": False, "seniority": "senior",
     "description": "Write software that makes robots dance, run, and climb. Work on perception, planning, and control systems.",
     "skills_required": ["C++", "Python", "ROS", "Computer Vision", "Control Systems"], "salary_range": "$180K – $280K"},
    {"title": "AR/VR Engineer", "company": "Meta (Reality Labs)", "location": "Redmond, WA", "source": "greenhouse", "remote": False, "seniority": "senior",
     "description": "Build the next generation of mixed reality experiences. Work on Quest headsets and AR glasses.",
     "skills_required": ["C++", "Unity", "Unreal", "Computer Vision", "3D Graphics"], "salary_range": "$200K – $320K"},
    {"title": "Speech Recognition Engineer", "company": "Deepgram", "location": "Remote", "source": "adzuna", "remote": True, "seniority": "mid",
     "description": "Build state-of-the-art speech recognition models. Work on end-to-end deep learning for audio understanding.",
     "skills_required": ["Python", "PyTorch", "NLP", "Audio Processing", "Kubernetes"], "salary_range": "$150K – $230K"},
    {"title": "AI Safety Researcher", "company": "DeepMind", "location": "Remote", "source": "linkedin", "remote": True, "seniority": "senior",
     "description": "Conduct research on AI alignment and safety. Work on interpretability, robustness, and value learning.",
     "skills_required": ["Python", "PyTorch", "NLP", "Reinforcement Learning", "ML Theory"], "salary_range": "$200K – $350K"},
    {"title": "Quantitative Developer", "company": "Jane Street", "location": "New York, NY", "source": "greenhouse", "remote": False, "seniority": "mid",
     "description": "Build trading systems that process billions of dollars daily. Work on low-latency systems and ML models.",
     "skills_required": ["OCaml", "Python", "C++", "Distributed Systems", "Statistics"], "salary_range": "$250K – $400K"},

    # ─── 60-69: Database / Infra / Specialized ───
    {"title": "Database Reliability Engineer", "company": "MongoDB", "location": "New York, NY", "source": "greenhouse", "remote": True, "seniority": "senior",
     "description": "Keep the world's data running. Build tools to manage thousands of database clusters across global regions.",
     "skills_required": ["Go", "Kubernetes", "MongoDB", "Linux", "Distributed Systems"], "salary_range": "$190K – $280K"},
    {"title": "Search Engineer", "company": "Elastic", "location": "Mountain View, CA", "source": "lever", "remote": True, "seniority": "mid",
     "description": "Build the search engine that powers observability, security, and search use cases worldwide.",
     "skills_required": ["Java", "Elasticsearch", "Kubernetes", "Go", "Search Relevance"], "salary_range": "$150K – $230K"},
    {"title": "Streaming Data Engineer", "company": "Confluent", "location": "Remote", "source": "adzuna", "remote": True, "seniority": "senior",
     "description": "Build and scale Apache Kafka platforms for the world's largest companies. Real-time data at petabyte scale.",
     "skills_required": ["Java", "Kafka", "Kubernetes", "Go", "Stream Processing"], "salary_range": "$180K – $260K"},
    {"title": "Graph Database Engineer", "company": "Neo4j", "location": "San Mateo, CA", "source": "greenhouse", "remote": True, "seniority": "mid",
     "description": "Build the world's leading graph database. Work on Cypher query processing and graph algorithms.",
     "skills_required": ["Java", "Python", "Graph Theory", "Distributed Systems", "Cypher"], "salary_range": "$140K – $210K"},
    {"title": "Observability Engineer", "company": "Datadog", "location": "New York, NY", "source": "linkedin", "remote": True, "seniority": "senior",
     "description": "Build the monitoring platform that keeps the internet running. Work on metrics, traces, and logs at massive scale.",
     "skills_required": ["Go", "Kubernetes", "Distributed Systems", "Prometheus", "Grafana"], "salary_range": "$190K – $280K"},

    # ─── 70-74: Interns & Entry Level ───
    {"title": "Software Engineering Intern", "company": "Stripe", "location": "San Francisco, CA", "source": "indeed", "remote": False, "seniority": "entry",
     "description": "Join Stripe for a 12-week internship. Work on real projects with mentorship from senior engineers.",
     "skills_required": ["Python", "Java", "SQL"], "salary_range": "$8,000 – $10,000/month"},
    {"title": "Data Science Intern", "company": "Netflix", "location": "Los Gatos, CA", "source": "linkedin", "remote": False, "seniority": "entry",
     "description": "Summer internship on the data science team. Analyze viewer behavior and build recommendation experiments.",
     "skills_required": ["Python", "SQL", "Statistics", "R"], "salary_range": "$7,000 – $9,000/month"},
    {"title": "Engineering Apprentice", "company": "Apple", "location": "Cupertino, CA", "source": "greenhouse", "remote": False, "seniority": "entry",
     "description": "Apple's apprenticeship program for early-career engineers. Rotate through teams and find your passion.",
     "skills_required": ["Swift", "Python", "Problem Solving"], "salary_range": "$90K – $120K"},
    {"title": "Graduate ML Engineer", "company": "DeepMind", "location": "London, UK", "source": "linkedin", "remote": False, "seniority": "entry",
     "description": "Join DeepMind's graduate program. Work alongside world-class researchers on fundamental AI challenges.",
     "skills_required": ["Python", "PyTorch", "Mathematics", "Statistics"], "salary_range": "$100K – $150K"},
    {"title": "New Grad Software Engineer", "company": "Google", "location": "Mountain View, CA", "source": "indeed", "remote": False, "seniority": "entry",
     "description": "Google's new grad program. Work on products used by billions of people. Build your career with world-class mentorship.",
     "skills_required": ["Python", "Java", "C++", "Data Structures", "Algorithms"], "salary_range": "$130K – $180K"},
]


# ═══════════════════════════════════════════════════════════════════════════════
# APPLICATION GENERATION — weighted random distribution
# ═══════════════════════════════════════════════════════════════════════════════

STATUS_WEIGHTS = {
    "submitted": 0.30,
    "matched": 0.12,
    "pending": 0.20,
    "error": 0.08,
    "captcha_blocked": 0.05,
    "under_review": 0.08,
    "interview": 0.07,
    "rejected": 0.07,
    "skipped": 0.03,
}

STATUSES = list(STATUS_WEIGHTS.keys())
STATUS_PROBS = list(STATUS_WEIGHTS.values())

ALL_SKILLS = [
    "Python", "Go", "TypeScript", "Java", "C++", "Ruby", "Rust", "Swift", "Kotlin",
    "React", "Kubernetes", "Terraform", "AWS", "Docker", "PostgreSQL", "Redis", "Kafka",
    "PyTorch", "TensorFlow", "SQL", "Spark", "NLP", "Leadership", "CSS", "GraphQL",
    "Linux", "Monitoring", "API Design", "Distributed Systems", "JavaScript",
]

COVER_LETTERS = [
    "./data/cover_letters/google_senior_software_engineer.txt",
    "./data/cover_letters/stripe_staff_software_engineer.txt",
    "./data/cover_letters/github_backend_engineer.txt",
    "./data/cover_letters/netflix_infrastructure_engineer.txt",
    "./data/cover_letters/notion_full_stack_engineer.txt",
]


def generate_application(profile_id: str, job_id: str, job_data: dict) -> ApplicationModel:
    """Generate a single random application record."""
    status = random.choices(STATUSES, weights=STATUS_PROBS)[0]

    # Match score varies by status
    if status in ("submitted", "interview", "under_review"):
        score = round(random.uniform(0.65, 0.98), 3)
    elif status == "matched":
        score = round(random.uniform(0.50, 0.75), 3)
    elif status == "captcha_blocked":
        score = round(random.uniform(0.70, 0.95), 3)
    elif status == "error":
        score = round(random.uniform(0.45, 0.85), 3)
    else:
        score = round(random.uniform(0.35, 0.80), 3)

    # Skills overlap and gaps
    n_overlap = random.randint(1, min(4, len(job_data.get("skills_required", []))))
    overlap = random.sample(job_data.get("skills_required", ALL_SKILLS), n_overlap)
    remaining = [s for s in ALL_SKILLS if s not in overlap]
    n_gaps = random.randint(0, min(3, len(remaining)))
    gaps = random.sample(remaining, n_gaps) if n_gaps else []

    # Days ago — spread across 1-60 days
    days_ago = random.randint(1, 60)
    submitted_at = _utcnow() - timedelta(days=days_ago)

    # Fields filled varies by complexity
    fields_filled = random.randint(4, 14)
    total_fields = fields_filled + random.randint(0, 3)

    cover_letter = random.choice(COVER_LETTERS) if random.random() > 0.5 else None

    error_log = ""
    if status == "error":
        error_logs = [
            "Connection timeout during form submission",
            "CAPTCHA verification required after 3 attempts",
            "Form field 'education_level' not found on page",
            "ATS adapter failed: Greenhouse field mapping error",
            "Page navigation timeout — job board requires sign-in",
            "File upload failed — resume exceeds 5MB limit",
        ]
        error_log = random.choice(error_logs)
    elif status == "captcha_blocked":
        error_logs = [
            "reCAPTCHA v2 detected — human review requested",
            "hCaptcha challenge not passed automatically",
            "Custom CAPTCHA detected on Workday form",
        ]
        error_log = random.choice(error_logs)

    return ApplicationModel(
        profile_id=profile_id,
        job_id=job_id,
        match_score=score,
        status=status,
        skill_overlap=overlap,
        skill_gaps=gaps,
        ats_name=job_data.get("source", ""),
        fields_filled=fields_filled,
        total_fields=total_fields,
        submitted_at=submitted_at,
        cover_letter_path=cover_letter,
        error_log=error_log,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SEEDING LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

def seed(drop_existing: bool = True):
    """Run the seed script — creates 3 profiles, 75 jobs, and 100+ applications."""
    from backend.config import settings

    sync_url = settings.database_url.replace("+asyncpg", "+psycopg2").replace("postgresql+psycopg2", "postgresql")
    engine = create_engine(sync_url)

    if drop_existing:
        Base.metadata.drop_all(engine)
        logger.info("Dropped existing tables")

    Base.metadata.create_all(engine)
    logger.info("Created tables")

    with SASession(engine) as db:
        # ─── Profiles ─────────────────────────────────────────────────────
        profile_ids = []
        for p_data in PROFILES:
            profile = ProfileModel(**p_data)
            db.add(profile)
            db.flush()
            profile_ids.append(profile.id)
            logger.info("Added profile: %s", profile.full_name)

        # ─── Jobs ─────────────────────────────────────────────────────────
        job_ids = []
        for i, j_data in enumerate(JOBS):
            job = JobModel(external_id=f"job_{i:03d}", **j_data)
            db.add(job)
            db.flush()
            job_ids.append(job.id)
        logger.info("Added %d jobs", len(JOBS))

        # ─── Applications ─────────────────────────────────────────────────
        random.seed(42)
        app_ids = []

        # Each profile applies to 35-55 jobs each for 100+ total
        # Profile 0 (Alex — Senior SWE): backend, infra, platform, frontend, specialized
        alex_indices = (list(range(0, 10)) + list(range(20, 35)) + list(range(60, 70)) + [72, 74, 46, 54, 55])
        # Profile 1 (Sarah — Data Scientist): data, ML, research, some general SWE
        sarah_indices = (list(range(10, 20)) + list(range(50, 60)) + [0, 4, 7, 15, 16, 18, 40, 47, 68, 70, 71, 73, 74])
        # Profile 2 (Maria — Principal): platform, infra, leadership, security, AI infra
        maria_indices = (list(range(20, 30)) + list(range(40, 50)) + [2, 5, 6, 3, 24, 26, 41, 49, 54, 57, 59, 60, 62, 64])

        profile_job_map = [
            (profile_ids[0], alex_indices),
            (profile_ids[1], sarah_indices),
            (profile_ids[2], maria_indices),
        ]

        for pid, indices in profile_job_map:
            for idx in indices:
                if idx >= len(job_ids):
                    continue
                app = generate_application(pid, job_ids[idx], JOBS[idx])
                db.add(app)
                app_ids.append(app.id)

        db.commit()
        total_apps = len(app_ids)

    logger.info("=" * 50)
    logger.info("Seed complete!")
    logger.info("  Profiles: %d", len(profile_ids))
    logger.info("  Jobs: %d", len(job_ids))
    logger.info("  Applications: %d", total_apps)
    logger.info("=" * 50)

    return {
        "profiles": len(profile_ids),
        "jobs": len(job_ids),
        "applications": total_apps,
    }


if __name__ == "__main__":
    seed()
