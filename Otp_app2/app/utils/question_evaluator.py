from typing import Any, Dict, List, Optional, Tuple


def normalize_question_options(question: dict) -> Tuple[str, List[Any]]:
    """
    Extract normalized question type and options list.
    Preserves index positions so that options[index] aligns with 0-based option numbers.
    """
    q_type = str(question.get("type") or "text").strip().lower()
    if q_type == "image":
        raw_options = question.get("image_options")
        if not raw_options:
            raw_options = question.get("options")
    else:
        raw_options = question.get("options")
        if not raw_options:
            raw_options = question.get("image_options")

    if not isinstance(raw_options, list):
        options = []
    else:
        options = list(raw_options)

    return q_type, options


def resolve_verified_correct_index_and_answer(
    question: dict,
    q_type: str,
    options: List[Any]
) -> Tuple[Optional[int], Optional[str]]:
    """
    Determine the verified 0-based correct option index and the verified correct answer value.
    Disambiguates whether correct_answer is an option string, a 1-based index string,
    or an option filename/URL.
    """
    raw_ci = question.get("correct_index")
    raw_ca = question.get("correct_answer")

    verified_ci: Optional[int] = None

    # 1. First, check if correct_index is a valid 0-based integer
    if raw_ci is not None and not isinstance(raw_ci, bool):
        try:
            ci_int = int(raw_ci)
            if options and 0 <= ci_int < len(options) and options[ci_int] is not None:
                verified_ci = ci_int
        except (ValueError, TypeError):
            pass

    # 2. If verified_ci is not resolved, inspect correct_answer
    if verified_ci is None and raw_ca is not None and not isinstance(raw_ca, bool):
        ca_str = str(raw_ca).strip()

        # Check if ca_str matches an option directly (text or URL)
        matched_idx = None
        for idx, opt in enumerate(options):
            if opt is not None and str(opt).strip() == ca_str:
                matched_idx = idx
                break

        if matched_idx is None and q_type != "image":
            # Case-insensitive match for text options
            for idx, opt in enumerate(options):
                if opt is not None and str(opt).strip().lower() == ca_str.lower():
                    matched_idx = idx
                    break

        if matched_idx is not None:
            # It was the actual option text or URL
            verified_ci = matched_idx
        elif ca_str.isdigit():
            # Determine actual meaning:
            # ca_str is a digit string (e.g. "1") that does not match any option text.
            # In the data model, admin forms use 1-based index (Options 1..4).
            digit_val = int(ca_str)
            if options and 1 <= digit_val <= len(options) and options[digit_val - 1] is not None:
                # 1-based index converted to 0-based index
                verified_ci = digit_val - 1
            elif options and 0 <= digit_val < len(options) and options[digit_val] is not None:
                # 0-based fallback
                verified_ci = digit_val

    # 3. Determine verified correct answer string for display/serialization
    verified_ca: Optional[str] = None
    if verified_ci is not None and options and 0 <= verified_ci < len(options) and options[verified_ci] is not None:
        verified_ca = str(options[verified_ci])
    elif raw_ca is not None and str(raw_ca).strip() != "":
        verified_ca = str(raw_ca).strip()
    elif verified_ci is not None:
        verified_ca = str(verified_ci)

    return verified_ci, verified_ca


def normalize_student_answer_index(
    student_answer: Any,
    q_type: str,
    options: List[Any]
) -> Optional[int]:
    """
    Safely extract the student's selected 0-based option index.
    Returns None if the answer is missing, invalid, non-numeric (for image MCQs),
    or out-of-range.
    """
    if student_answer is None or isinstance(student_answer, bool):
        return None

    # If it is an integer
    if isinstance(student_answer, int):
        idx = student_answer
        if options and 0 <= idx < len(options) and options[idx] is not None:
            return idx
        return None

    # If it is a string
    if isinstance(student_answer, str):
        cleaned = student_answer.strip()
        if not cleaned:
            return None

        # Check if it's an integer string representing a 0-based index
        if cleaned.lstrip('-').isdigit():
            idx = int(cleaned)
            if options and 0 <= idx < len(options) and options[idx] is not None:
                return idx
            return None

        # If it's a text-based question, the student might have submitted the option text directly
        if q_type != "image" and options:
            for opt_idx, opt in enumerate(options):
                if opt is not None and str(opt).strip().lower() == cleaned.lower():
                    return opt_idx

    return None


def evaluate_question_answer(question: dict, student_answer: Any) -> Dict[str, Any]:
    """
    Fully evaluates a student's answer for a given question document.
    Returns a dictionary containing:
        - is_correct: bool
        - verified_correct_index: Optional[int]
        - verified_correct_answer: Optional[str]
        - student_selected_index: Optional[int]
        - options: List[Any]
        - q_type: str
    """
    q_type, options = normalize_question_options(question)
    verified_ci, verified_ca = resolve_verified_correct_index_and_answer(question, q_type, options)

    if q_type == "rating":
        # Rating questions: valid as long as student submitted a non-empty rating
        is_answered = (
            student_answer is not None
            and not isinstance(student_answer, bool)
            and str(student_answer).strip() != ""
        )
        return {
            "is_correct": is_answered,
            "verified_correct_index": verified_ci,
            "verified_correct_answer": verified_ca,
            "student_selected_index": None,
            "options": options,
            "q_type": q_type,
        }

    # For image-based and text-based multiple-choice questions:
    student_idx = normalize_student_answer_index(student_answer, q_type, options)

    if (
        student_idx is not None
        and verified_ci is not None
        and options
        and 0 <= student_idx < len(options)
        and student_idx == verified_ci
    ):
        is_correct = True
    else:
        is_correct = False

    return {
        "is_correct": is_correct,
        "verified_correct_index": verified_ci,
        "verified_correct_answer": verified_ca,
        "student_selected_index": student_idx,
        "options": options,
        "q_type": q_type,
    }
