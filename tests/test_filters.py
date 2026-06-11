"""Unit tests for TextCleaner and NLULabeller._is_imperative."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT / "workers", ROOT / "workers" / "candidate-extractor-stub"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pytest
import spacy

from cleaner import TextCleaner
from labeller import NLULabeller


# ---------------------------------------------------------------------------
# Shared fixture: spaCy model (loaded once per test session)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def nlp():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        pytest.skip("en_core_web_sm not installed — skipping imperative filter tests")


def _first_sent(nlp_model, text: str):
    """Parse text and return the first sentence Span."""
    doc = nlp_model(text)
    sents = list(doc.sents)
    assert sents, f"No sentences parsed from: {text!r}"
    return sents[0]


# ===========================================================================
# TextCleaner
# ===========================================================================

class TestTextCleaner:

    def setup_method(self):
        self.cleaner = TextCleaner()

    # --- boilerplate removal ---

    def test_strips_grade_header(self):
        result = self.cleaner.clean("Grade 5 English Language Arts\nLesson content here.")
        assert "Grade 5" not in result
        assert "Lesson content here." in result

    def test_strips_grade_level_variant(self):
        result = self.cleaner.clean("Grade level: intermediate\nContent follows.")
        assert "Grade level" not in result
        assert "Content follows." in result

    def test_strips_learning_objectives(self):
        result = self.cleaner.clean(
            "Learning Objectives:\nUnderstand vocabulary.\nRead the passage."
        )
        assert "Learning Objectives" not in result
        assert "Understand vocabulary." in result
        assert "Read the passage." in result

    def test_strips_learning_objective_singular(self):
        result = self.cleaner.clean("Learning Objective\nContent line.")
        assert "Learning Objective" not in result
        assert "Content line." in result

    def test_strips_aims_line(self):
        result = self.cleaner.clean("Aims / Achievement goals\nStudents will learn vocabulary.")
        assert "Aims" not in result
        assert "Students will learn vocabulary." in result

    def test_strips_achievement_line(self):
        result = self.cleaner.clean("Achievement goals for this unit\nContent here.")
        assert "Achievement goals" not in result
        assert "Content here." in result

    def test_strips_lesson_period(self):
        result = self.cleaner.clean("Lesson period 1~2\nContent follows.")
        assert "Lesson period" not in result
        assert "Content follows." in result

    def test_strips_digital_multimedia_resources(self):
        result = self.cleaner.clean("Digital Multimedia Resources, p.41\nNext line.")
        assert "Digital Multimedia Resources" not in result
        assert "Next line." in result

    def test_strips_number_prefixed_boilerplate(self):
        result = self.cleaner.clean("41 Aims / Achievement goals\nContent.")
        assert "Aims" not in result
        assert "Content." in result

    # --- standalone number / punctuation removal ---

    def test_strips_standalone_integer(self):
        result = self.cleaner.clean("42\nSome lesson content.")
        assert "42" not in result
        assert "Some lesson content." in result

    def test_strips_bullet_separator(self):
        result = self.cleaner.clean("•\nContent line.")
        assert "•" not in result
        assert "Content line." in result

    def test_strips_page_slash_total(self):
        # "12 / 24" — typical slide progress indicator
        result = self.cleaner.clean("12 / 24\nContent.")
        assert "12 / 24" not in result
        assert "Content." in result

    # --- newline / paragraph structure preservation ---

    def test_preserves_double_newline_paragraph_break(self):
        text = "Paragraph one.\n\nParagraph two."
        result = self.cleaner.clean(text)
        assert "\n\n" in result
        assert "Paragraph one." in result
        assert "Paragraph two." in result

    def test_number_removal_does_not_inject_extra_blank_line(self):
        result = self.cleaner.clean("Line one.\n42\nLine two.")
        assert "42" not in result
        content_lines = [l for l in result.splitlines() if l.strip()]
        assert content_lines == ["Line one.", "Line two."]

    def test_collapses_triple_blank_lines_to_double(self):
        result = self.cleaner.clean("Para one.\n\n\n\nPara two.")
        assert "\n\n\n" not in result
        assert "Para one." in result
        assert "Para two." in result

    def test_empty_lines_between_content_preserved(self):
        text = "Sentence A.\n\nSentence B.\n\nSentence C."
        result = self.cleaner.clean(text)
        assert result.count("\n\n") == 2

    # --- content lines must NOT be dropped ---

    def test_narrative_prose_unchanged(self):
        text = (
            "Captain Grace stood on the quarterdeck.\n"
            "The wind was shifting rapidly toward the reefs."
        )
        result = self.cleaner.clean(text)
        assert "Captain Grace stood on the quarterdeck." in result
        assert "The wind was shifting rapidly toward the reefs." in result

    def test_word_grade_mid_sentence_not_stripped(self):
        # "grade" alone mid-sentence should NOT be removed (only "Grade N" / "Grade level")
        result = self.cleaner.clean("The student received a high grade on the test.")
        assert "The student received a high grade on the test." in result


# ===========================================================================
# Imperative filter  (NLULabeller._is_imperative)
# ===========================================================================

class TestImperativeFilter:

    # --- True: teacher instructions / imperative mood ---

    def test_read_command(self, nlp):
        assert NLULabeller._is_imperative(_first_sent(nlp, "Read the passage aloud.")) is True

    def test_underline_command(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "Underline the nouns in each sentence.")
        ) is True

    def test_write_command(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "Write the answer in your notebook.")
        ) is True

    def test_ask_command(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "Ask your partner the question.")
        ) is True

    def test_check_command(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "Check the answers with a classmate.")
        ) is True

    def test_circle_command(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "Circle the correct word in each sentence.")
        ) is True

    def test_match_command(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "Match each word to its definition.")
        ) is True

    # --- False: declarative sentences ---

    def test_declarative_present_continuous(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "The dog is running in the park.")
        ) is False

    def test_declarative_subject_verb(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "Students read the passage carefully.")
        ) is False

    def test_declarative_she_subject(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "She completed the exercise.")
        ) is False

    def test_declarative_comparative(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "An apple is bigger than a grape.")
        ) is False

    def test_declarative_robot(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "The robot is exploring the cave.")
        ) is False

    # --- False: interrogative sentences ---

    def test_wh_question(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "What is the capital of France?")
        ) is False

    def test_how_question(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "How does the character solve the problem?")
        ) is False

    def test_why_question(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "Why did the Gingerbread Man run away?")
        ) is False

    # --- False: dialogue / quoted speech guard ---

    def test_straight_quotes_protect_from_imperative(self, nlp):
        # Narrative dialogue must not be flagged even if the quoted content is imperative
        assert NLULabeller._is_imperative(
            _first_sent(nlp, 'Grace yelled, "Hold fast!"')
        ) is False

    def test_curly_left_quote_protects(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "“Read the book,” she said.")
        ) is False

    def test_curly_right_quote_protects(self, nlp):
        # Right curly quote alone (closing quote) also triggers the guard
        assert NLULabeller._is_imperative(
            _first_sent(nlp, "She whispered, “Listen carefully.”")
        ) is False

    def test_quoted_student_answer_not_imperative(self, nlp):
        assert NLULabeller._is_imperative(
            _first_sent(nlp, 'The student answered, "It’s a robot."')
        ) is False


# ===========================================================================
# TextCleaner — newline stitching
# ===========================================================================

class TestNewlineStitching:

    def setup_method(self):
        self.cleaner = TextCleaner()

    def test_stitches_lowercase_before_newline(self):
        # Core verification: "jagged\ncoastline" → "jagged coastline"
        result = self.cleaner.clean("The jagged\ncoastline stretched for miles.")
        assert "jagged coastline" in result

    def test_stitches_comma_before_newline(self):
        result = self.cleaner.clean("Rain, wind,\nand storm battered the ship.")
        assert "wind, and storm" in result

    def test_stitches_hyphen_continuation(self):
        result = self.cleaner.clean("The sea-\nfaring captain navigated carefully.")
        assert "sea-" in result and "faring" in result  # hyphen kept; space added

    def test_does_not_stitch_sentence_ending_period(self):
        # Period ends a sentence — the line break is intentional
        result = self.cleaner.clean("Sentence one.\nSentence two.")
        lines = [l for l in result.splitlines() if l.strip()]
        assert len(lines) == 2

    def test_does_not_stitch_uppercase_start(self):
        # Uppercase after newline signals a new sentence — keep separate
        result = self.cleaner.clean("End of sentence.\nNew sentence begins here.")
        assert "\n" in result

    def test_preserves_double_newline_paragraph_break_after_lowercase(self):
        # Even when a paragraph ends with a lowercase word, \n\n must stay intact
        result = self.cleaner.clean("The ship moved on\n\nThe next morning came.")
        assert "\n\n" in result
        assert "moved on" in result
        assert "The next morning" in result

    def test_stitching_does_not_destroy_existing_tests(self):
        # Narrative prose across two lines, period-ended — must stay as two lines
        text = (
            "Captain Grace stood on the quarterdeck.\n"
            "The wind was shifting rapidly toward the reefs."
        )
        result = self.cleaner.clean(text)
        assert "Captain Grace stood on the quarterdeck." in result
        assert "The wind was shifting rapidly" in result


# ===========================================================================
# TextCleaner — dialogue marker stripping
# ===========================================================================

class TestDialogueMarkerStripping:

    def setup_method(self):
        self.cleaner = TextCleaner()

    def test_strips_teacher_tab_marker(self):
        result = self.cleaner.clean("T\tListen and repeat after me.")
        assert not result.strip().startswith("T\t")
        assert "Listen and repeat" in result

    def test_strips_student_tab_marker(self):
        result = self.cleaner.clean('S\t"What\'s this?"')
        assert not result.strip().startswith("S\t")
        assert "What's this?" in result

    def test_strips_teacher_space_marker(self):
        result = self.cleaner.clean("T  How are you today?")
        assert not result.strip().startswith("T ")
        assert "How are you today?" in result

    def test_strips_student_space_tab_marker(self):
        result = self.cleaner.clean("S \t It's a robot.")
        assert "It's a robot." in result
        assert not result.strip().startswith("S")

    def test_does_not_strip_the_word(self):
        # "The" starts with T but is followed by 'h', not whitespace — must be kept
        result = self.cleaner.clean("The ocean was tumultuous.")
        assert "The ocean was tumultuous." in result

    def test_does_not_strip_students_word(self):
        # "Students" starts with S but second char is 't', not whitespace
        result = self.cleaner.clean("Students completed the worksheet.")
        assert "Students completed the worksheet." in result
