"""
Tests for the CV Parser service.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.cv_parser import CVParser, extract_email, extract_name, extract_phone, extract_skills


class TestRegexExtractors:
    """Unit tests for the core text extraction helpers."""

    def test_extract_name(self):
        """Name extraction from top-of-CV patterns."""
        assert extract_name("John Doe\nemail@test.com") == "John Doe"
        assert extract_name("Jane Marie Smith\n555-1234") == "Jane Marie Smith"
        assert extract_name("Dr. Alex Chen\nlinkedin.com/in/alex") == "Dr. Alex Chen"
        # Should skip job titles, section headers, and contact lines
        assert extract_name("Software Engineer\nemail@test.com") == ""
        assert extract_name("email@test.com\nJohn Doe") == "John Doe"  # name after email still found
        assert extract_name("a b") == ""  # too short, unlikely as name
        assert extract_name("") == ""

    def test_extract_email(self):
        assert extract_email("Contact: john@example.com") == "john@example.com"
        assert extract_email("No email here") == ""
        assert extract_email("a.b@c.co.uk") == "a.b@c.co.uk"

    def test_extract_phone(self):
        assert extract_phone("Call +1-555-123-4567") == "+1-555-123-4567"
        assert extract_phone("(123) 456-7890") == "(123) 456-7890"
        assert extract_phone("No phone") == ""


class TestSkillExtraction:
    """Tests for the skill taxonomy matcher."""

    def test_extract_python(self):
        skills = extract_skills("I know Python and javascript")
        names = [s.name for s in skills]
        assert "Python" in names
        assert "Javascript" in names

    def test_extract_frameworks(self):
        skills = extract_skills("Experience with React, Django, and FastAPI")
        names = [s.name for s in skills]
        assert "React" in names
        assert "Django" in names
        assert "Fastapi" in names

    def test_no_false_positives(self):
        skills = extract_skills("I like pizza and dogs")
        assert len(skills) == 0


class TestCVParser:
    """Integration tests for the full CVParser."""

    @pytest.fixture
    def parser(self):
        return CVParser()

    @pytest.fixture
    def sample_txt(self, tmp_path: Path) -> Path:
        """Create a sample plain-text CV for testing."""
        content = """John Doe
john@example.com
+1-555-123-4567
linkedin.com/in/johndoe

Software Engineer

Acme Corp - Senior Software Engineer
Led development of microservices architecture using Python and FastAPI.
Managed team of 5 engineers.

Relevant skills: React, TypeScript, PostgreSQL, Docker, Kubernetes, AWS.

Education:
Bachelor of Science in Computer Science, MIT
"""
        path = tmp_path / "cv.txt"
        path.write_text(content)
        return path

    def test_parse_txt(self, parser, sample_txt: Path):
        profile = parser.parse(sample_txt)
        assert profile.full_name == "John Doe", f"Expected 'John Doe', got '{profile.full_name}'"
        assert profile.email == "john@example.com"
        assert profile.phone == "+1-555-123-4567"
        assert "Python" in [s.name for s in profile.skills]
        assert "React" in [s.name for s in profile.skills]
        assert profile.seniority.value == "senior"
        assert profile.target_roles

    def test_parse_invalid_path(self, parser):
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/path.pdf")

    def test_parse_unsupported_format(self, parser, tmp_path: Path):
        path = tmp_path / "cv.xyz"
        path.write_text("test")
        with pytest.raises(ValueError, match="Unsupported file type"):
            parser.parse(path)

    def test_empty_text(self, parser, tmp_path: Path):
        path = tmp_path / "empty.txt"
        path.write_text("")
        with pytest.raises(ValueError, match="No text could be extracted"):
            parser.parse(path)
