import os
import json
import re
import sys

try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        fitz = None


def _escape_html(text):
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def save_competitive_question_bank_pdf(question_bank_json: dict, filename: str):
    """
    Renders an official, beautifully structured Question Bank PDF from question_bank_json
    using PyMuPDF (fitz.Story / DocumentWriter) with fallback to ReportLab.

    Includes:
    - Textbook title, Exam Category, Exam Name, Subject, and Publication metadata
    - Table of Contents / Chapter Syllabus Overview
    - Candidate Instructions & Question Bank Guidance
    - Chapter-wise MCQ Sections with 4 options, difficulty tags, and textbook page citations
    - Answer Key Quick-Reference Matrix
    - Comprehensive In-depth Pedagogical Explanations
    """
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

    textbook_title = _escape_html(question_bank_json.get("textbook_title") or question_bank_json.get("title") or "COMPETITIVE EXAM TEXTBOOK")
    exam_name = _escape_html(question_bank_json.get("exam_name", "COMPETITIVE EXAMINATION"))
    category_name = _escape_html(question_bank_json.get("exam_category") or question_bank_json.get("category", "NATIONAL & STATE COMPETITIVE EXAMS"))
    subject = _escape_html(question_bank_json.get("subject", "GENERAL STUDIES"))
    language = _escape_html(str(question_bank_json.get("language", "English")).upper())
    total_questions = _escape_html(str(question_bank_json.get("total_questions", len(question_bank_json.get("questions", [])))))
    sections = question_bank_json.get("sections", [])
    total_chapters = len(sections)

    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: 'Helvetica', 'Arial', sans-serif;
    font-size: 10.5px;
    line-height: 1.45;
    color: #0f172a;
    margin: 0;
    padding: 0;
  }}
  .bank-header {{
    text-align: center;
    border-bottom: 2.5px solid #002B49;
    padding-bottom: 8px;
    margin-bottom: 12px;
  }}
  .bank-agency {{
    font-size: 13px;
    font-weight: bold;
    color: #002B49;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 2px;
  }}
  .bank-main-title {{
    font-size: 15px;
    font-weight: 800;
    color: #1e293b;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 3px;
  }}
  .bank-subtitle {{
    font-size: 11px;
    font-weight: 600;
    color: #475569;
  }}
  table.meta-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 12px;
    border-bottom: 1.5px solid #cbd5e1;
    font-size: 9.5px;
  }}
  table.meta-table td {{
    padding: 4px 6px;
    vertical-align: middle;
  }}
  .toc-box {{
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #0284c7;
    padding: 8px 12px;
    margin-bottom: 14px;
    font-size: 9px;
  }}
  .toc-title {{
    font-weight: bold;
    text-transform: uppercase;
    color: #002B49;
    font-size: 10px;
    margin-bottom: 4px;
  }}
  .toc-grid {{
    width: 100%;
    border-collapse: collapse;
  }}
  .toc-grid th {{
    text-align: left;
    border-bottom: 1px solid #cbd5e1;
    padding: 2px 4px;
    color: #475569;
  }}
  .toc-grid td {{
    padding: 2.5px 4px;
    border-bottom: 1px dotted #e2e8f0;
  }}
  .section-header {{
    background-color: #002B49;
    color: #ffffff;
    font-weight: bold;
    font-size: 11px;
    padding: 4px 8px;
    margin-top: 14px;
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    page-break-after: avoid;
    break-after: avoid;
  }}
  .chapter-subtext {{
    font-size: 9px;
    color: #475569;
    margin-top: -6px;
    margin-bottom: 8px;
    font-style: italic;
  }}
  .question-item {{
    margin-bottom: 11px;
    page-break-inside: avoid;
    break-inside: avoid;
  }}
  .q-head {{
    font-weight: 600;
    margin-bottom: 3px;
    color: #0f172a;
  }}
  .q-badge {{
    float: right;
    font-size: 8.5px;
    color: #64748b;
    font-weight: normal;
  }}
  .diff-easy {{ color: #16a34a; font-weight: bold; }}
  .diff-med {{ color: #d97706; font-weight: bold; }}
  .diff-hard {{ color: #dc2626; font-weight: bold; }}
  table.options-table {{
    width: 100%;
    border-collapse: collapse;
    margin-left: 12px;
    margin-top: 2px;
  }}
  table.options-table td {{
    width: 50%;
    padding: 2px 4px;
    vertical-align: top;
    font-size: 10px;
  }}
  .opt-badge {{
    font-weight: bold;
    color: #002B49;
  }}
  .page-break {{
    page-break-before: always;
  }}
  .key-section {{
    margin-top: 20px;
    border-top: 2.5px solid #002B49;
    padding-top: 12px;
  }}
  .answer-grid {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 14px;
    font-size: 9px;
  }}
  .answer-grid th {{
    background-color: #0f172a;
    color: #ffffff;
    padding: 3px 6px;
    text-align: center;
    border: 1px solid #334155;
  }}
  .answer-grid td {{
    padding: 3px 6px;
    text-align: center;
    border: 1px solid #cbd5e1;
  }}
  .answer-line {{
    margin-left: 12px;
    margin-top: 4px;
    font-size: 9.5px;
    color: #002B49;
  }}
  .explanation-box {{
    background-color: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-left: 3px solid #16a34a;
    padding: 4px 8px;
    margin-top: 3px;
    margin-left: 12px;
    font-size: 9.5px;
    color: #14532d;
    margin-bottom: 6px;
    page-break-inside: avoid;
    break-inside: avoid;
  }}
</style>
</head>
<body>
  <div class="bank-header">
    <div class="bank-agency">{category_name} &bull; {exam_name}</div>
    <div class="bank-main-title">{textbook_title}</div>
    <div class="bank-subtitle">Comprehensive Textbook Question Bank &bull; Answers &amp; Explanations</div>
  </div>

  <table class="meta-table">
    <tr>
      <td><b>Subject:</b> {subject}</td>
      <td><b>Language:</b> {language}</td>
      <td style="text-align: right;"><b>Total Questions:</b> {total_questions}</td>
    </tr>
  </table>
""")

    q_counter = 1

    # Render Questions sequentially with Correct Answer and Explanation directly below each question
    for sec in sections:
        questions = sec.get("questions", [])

        for q in questions:
            q_text = _escape_html(q.get("question", ""))
            q_num = q_counter
            correct_ans = _escape_html(q.get("correct_answer", ""))
            explanation = _escape_html(q.get("explanation", ""))

            html_parts.append(f"""
            <div class="question-item">
              <div class="q-head">
                <span><b>Q{q_num}.</b> {q_text}</span>
              </div>
            """)

            opts = q.get("options", {})
            correct_opt_text = ""
            if isinstance(opts, dict):
                correct_opt_text = _escape_html(opts.get(correct_ans, ""))
                html_parts.append('<table class="options-table">')
                html_parts.append('<tr>')
                html_parts.append(f'<td><span class="opt-badge">(A)</span> {_escape_html(opts.get("A", ""))}</td>')
                html_parts.append(f'<td><span class="opt-badge">(B)</span> {_escape_html(opts.get("B", ""))}</td>')
                html_parts.append('</tr><tr>')
                html_parts.append(f'<td><span class="opt-badge">(C)</span> {_escape_html(opts.get("C", ""))}</td>')
                html_parts.append(f'<td><span class="opt-badge">(D)</span> {_escape_html(opts.get("D", ""))}</td>')
                html_parts.append('</tr></table>')
            elif isinstance(opts, list):
                idx_map = {"A": 0, "B": 1, "C": 2, "D": 3}
                if correct_ans in idx_map and idx_map[correct_ans] < len(opts):
                    correct_opt_text = _escape_html(opts[idx_map[correct_ans]])
                html_parts.append('<table class="options-table">')
                for i in range(0, len(opts), 2):
                    html_parts.append('<tr>')
                    opt_a = _escape_html(opts[i]) if i < len(opts) else ""
                    html_parts.append(f'<td><span class="opt-badge">({chr(65+i)})</span> {opt_a}</td>')
                    if i + 1 < len(opts):
                        opt_b = _escape_html(opts[i+1])
                        html_parts.append(f'<td><span class="opt-badge">({chr(65+i+1)})</span> {opt_b}</td>')
                    else:
                        html_parts.append('<td></td>')
                    html_parts.append('</tr>')
                html_parts.append('</table>')

            ans_display = f"({correct_ans}) {correct_opt_text}".strip() if correct_opt_text else f"({correct_ans})"
            html_parts.append(f'<div class="answer-line"><b>Correct Answer:</b> {ans_display}</div>')
            if explanation:
                html_parts.append(f'<div class="explanation-box"><b>Explanation:</b> {explanation}</div>')

            html_parts.append('</div>')
            q_counter += 1

    html_parts.append("""
</body>
</html>
""")

    full_html = "".join(html_parts)

    # 1. Try PyMuPDF fitz.Story rendering
    if fitz is not None and hasattr(fitz, "Story") and hasattr(fitz, "DocumentWriter"):
        try:
            page_rect = fitz.paper_rect("a4")
            MARGIN = 36
            content_rect = fitz.Rect(MARGIN, MARGIN, page_rect.width - MARGIN, page_rect.height - MARGIN)

            story = fitz.Story(html=full_html)
            writer = fitz.DocumentWriter(filename)

            def rectfn(rect_num, filled):
                return page_rect, content_rect, fitz.Identity

            story.write(writer, rectfn)
            writer.close()

            chk = fitz.open(filename)
            p_cnt = len(chk)
            chk.close()
            print(f"[CompQB-PDF] Successfully generated Question Bank PDF with PyMuPDF story.write: {filename} ({p_cnt} pages)")
            return filename
        except Exception as e:
            print(f"[CompQB-PDF] PyMuPDF fitz.Story rendering warning: {e}. Falling back to ReportLab...")

    # 2. Fallback to ReportLab SimpleDocTemplate
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors

        doc = SimpleDocTemplate(filename, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=14, alignment=1, textColor=colors.HexColor("#002B49"))
        h2_style = ParagraphStyle('H2Style', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11, alignment=1, textColor=colors.HexColor("#333333"))
        body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14)
        sec_style = ParagraphStyle('SecStyle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, textColor=colors.white, backColor=colors.HexColor("#002B49"))

        story.append(Paragraph(f"{textbook_title} - QUESTION BANK", title_style))
        story.append(Paragraph(f"Subject: {subject} | Category: {category_name} | Exam: {exam_name}", h2_style))
        story.append(Spacer(1, 10))

        q_idx = 1
        for sec in sections:
            for q in sec.get("questions", []):
                q_text = _escape_html(q.get("question", ""))
                story.append(Paragraph(f"<b>Q{q_idx}. {q_text}</b>", body_style))
                opts = q.get("options", {})
                c_ans = _escape_html(q.get("correct_answer", ""))
                c_opt = _escape_html(opts.get(c_ans, "")) if isinstance(opts, dict) else ""
                if isinstance(opts, dict):
                    for k in ["A", "B", "C", "D"]:
                        if k in opts:
                            story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;<b>({k})</b> {_escape_html(opts[k])}", body_style))
                ans_str = f"({c_ans}) {c_opt}".strip() if c_opt else f"({c_ans})"
                story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;<b>Correct Answer:</b> {ans_str}", body_style))
                expl = _escape_html(q.get("explanation", ""))
                if expl:
                    story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;<b>Explanation:</b> {expl}", body_style))
                story.append(Spacer(1, 8))
                q_idx += 1

        doc.build(story)
        print(f"[CompQB-PDF] Saved Question Bank PDF via ReportLab fallback: {filename}")
        return filename
    except Exception as ex:
        print(f"[CompQB-PDF] Critical error in ReportLab generation: {ex}")
        return filename

