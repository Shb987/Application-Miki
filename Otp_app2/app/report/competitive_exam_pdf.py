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
    if text is None: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def save_competitive_exam_paper(paper_json: dict, filename: str):
    """
    Generates a professional Competitive Examination Question Paper PDF from paper_json
    using PyMuPDF (fitz.Story) with fallback to ReportLab.
    """
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

    exam_name = _escape_html(paper_json.get("exam_name", "COMPETITIVE EXAMINATION"))
    category_name = _escape_html(paper_json.get("exam_category", "NATIONAL / STATE COMPETITIVE EXAMS"))
    subject = _escape_html(paper_json.get("subject", "GENERAL STUDIES"))
    total_marks = _escape_html(str(paper_json.get("total_marks", 100)))
    time_limit = _escape_html(str(paper_json.get("time_limit", "120 MINUTES")))
    negative_marking = _escape_html(str(paper_json.get("negative_marking_rule", "0.33 Mark penalty per incorrect response")))
    paper_title = _escape_html(paper_json.get("paper_title", f"{exam_name} - PRACTICE QUESTION PAPER"))

    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: 'Helvetica', 'Arial', sans-serif;
    font-size: 11px;
    line-height: 1.45;
    color: #111111;
    margin: 0;
    padding: 0;
  }}
  .exam-header {{
    text-align: center;
    border-bottom: 2px solid #002B49;
    padding-bottom: 8px;
    margin-bottom: 12px;
  }}
  .agency-name {{
    font-size: 15px;
    font-weight: bold;
    color: #002B49;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    margin-bottom: 3px;
  }}
  .exam-title {{
    font-size: 13px;
    font-weight: bold;
    color: #222222;
    text-transform: uppercase;
    margin-bottom: 4px;
  }}
  .sub-title {{
    font-size: 11px;
    font-weight: 600;
    color: #444444;
  }}
  table.meta-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 10px;
    border-bottom: 1px solid #777777;
    font-size: 10px;
    font-weight: bold;
  }}
  table.meta-table td {{
    padding: 4px 0;
  }}
  .instructions-box {{
    background-color: #f8f9fa;
    border: 1px solid #d1d5db;
    border-left: 3px solid #002B49;
    padding: 6px 10px;
    margin-bottom: 14px;
    font-size: 9.5px;
    color: #333333;
  }}
  .instructions-title {{
    font-weight: bold;
    margin-bottom: 3px;
    text-transform: uppercase;
    color: #002B49;
  }}
  .section-header {{
    background-color: #002B49;
    color: #ffffff;
    font-weight: bold;
    font-size: 11px;
    padding: 4px 8px;
    margin-top: 12px;
    margin-bottom: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .question-item {{
    margin-bottom: 11px;
    page-break-inside: avoid;
  }}
  .q-head {{
    font-weight: bold;
    margin-bottom: 4px;
  }}
  .q-marks {{
    float: right;
    font-size: 9px;
    color: #555555;
    font-weight: normal;
  }}
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
    font-size: 10.5px;
  }}
  .opt-badge {{
    font-weight: bold;
    color: #002B49;
  }}
  .page-break {{
    page-break-before: always;
  }}
  .key-section {{
    margin-top: 25px;
    border-top: 2px dashed #002B49;
    padding-top: 15px;
  }}
  .explanation-box {{
    background-color: #f0fdf4;
    border: 1px solid #bbf7d0;
    padding: 4px 8px;
    margin-top: 4px;
    margin-left: 12px;
    font-size: 9.5px;
    color: #166534;
  }}
</style>
</head>
<body>
  <div class="exam-header">
    <div class="agency-name">{category_name}</div>
    <div class="exam-title">{paper_title}</div>
    <div class="sub-title">Subject: {subject}</div>
  </div>

  <table class="meta-table">
    <tr>
      <td style="text-align: left;">TIME ALLOWED: {time_limit}</td>
      <td style="text-align: right;">MAXIMUM MARKS: {total_marks}</td>
    </tr>
  </table>

  <div class="instructions-box">
    <div class="instructions-title">IMPORTANT CANDIDATE INSTRUCTIONS:</div>
    <div>1. This question paper contains objective type Multiple Choice Questions (MCQs) grounded in standard curriculum topics.</div>
    <div>2. Each question has four alternative choices (A), (B), (C), and (D). Select only ONE correct alternative.</div>
    <div>3. <b>Negative Marking Rule:</b> {negative_marking}. Avoid random guessing.</div>
    <div>4. All questions carry marks as indicated. No marks are deducted for unattempted questions.</div>
  </div>
""")

    sections = paper_json.get("sections", [])
    q_counter = 1
    answer_explanations = []

    for s_idx, sec in enumerate(sections):
        s_title = _escape_html(sec.get("section_title") or sec.get("name") or f"SECTION {chr(65 + s_idx)}")
        s_desc = _escape_html(sec.get("description", ""))
        html_parts.append(f'<div class="section-header">{s_title}</div>')
        if s_desc:
            html_parts.append(f'<div style="font-size:9.5px; color:#555; margin-bottom:8px;">{s_desc}</div>')

        questions = sec.get("questions", [])
        for q in questions:
            q_text = _escape_html(q.get("question", ""))
            q_num = q.get("question_number", q_counter)
            q_marks = q.get("marks", 1)
            q_diff = _escape_html(q.get("difficulty", "Medium"))
            correct_ans = _escape_html(q.get("correct_answer", ""))
            explanation = _escape_html(q.get("explanation", ""))
            source_ref = _escape_html(q.get("chapter_reference", ""))

            html_parts.append(f"""
            <div class="question-item">
              <div class="q-head">
                <span class="q-marks">[{q_marks} Mark | Diff: {q_diff}]</span>
                <span><b>Q{q_num}.</b> {q_text}</span>
              </div>
            """)

            opts = q.get("options", {})
            if isinstance(opts, dict):
                html_parts.append('<table class="options-table">')
                keys = ["A", "B", "C", "D"]
                html_parts.append('<tr>')
                html_parts.append(f'<td><span class="opt-badge">(A)</span> {_escape_html(opts.get("A", ""))}</td>')
                html_parts.append(f'<td><span class="opt-badge">(B)</span> {_escape_html(opts.get("B", ""))}</td>')
                html_parts.append('</tr><tr>')
                html_parts.append(f'<td><span class="opt-badge">(C)</span> {_escape_html(opts.get("C", ""))}</td>')
                html_parts.append(f'<td><span class="opt-badge">(D)</span> {_escape_html(opts.get("D", ""))}</td>')
                html_parts.append('</tr></table>')
            elif isinstance(opts, list):
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

            html_parts.append('</div>')

            answer_explanations.append({
                "num": q_num,
                "answer": correct_ans,
                "explanation": explanation,
                "source": source_ref
            })
            q_counter += 1

    # Appendix: Answer Key & Detailed Explanations
    html_parts.append("""
    <div class="page-break"></div>
    <div class="key-section">
      <div class="agency-name" style="text-align: center; margin-bottom: 4px;">ANSWER KEY &amp; EXPLANATIONS</div>
      <div style="text-align: center; font-size: 10px; color: #555; margin-bottom: 12px;">Detailed pedagogical explanations and textbook references for each question</div>
      <div class="section-header">OFFICIAL SOLUTIONS</div>
    """)

    for item in answer_explanations:
        html_parts.append(f"""
        <div style="margin-bottom: 8px; page-break-inside: avoid;">
          <div><b>Q{item['num']}. Correct Answer: <span style="color:#002B49;">({item['answer']})</span></b></div>
        """)
        if item.get("explanation"):
            html_parts.append(f"""
            <div class="explanation-box">
              <b>Explanation:</b> {item['explanation']}
              {f"<br><small style='color:#555;'>Source Reference: {item['source']}</small>" if item.get('source') else ""}
            </div>
            """)
        html_parts.append('</div>')

    html_parts.append("""
    </div>
</body>
</html>
""")

    full_html = "".join(html_parts)

    # 1. Try PyMuPDF fitz.Story rendering
    if fitz is not None:
        try:
            doc = fitz.open()
            MEDIABOX = fitz.paper_rect("a4")
            MARGIN_TOP = 36
            MARGIN_BOTTOM = 36
            MARGIN_LEFT = 36
            MARGIN_RIGHT = 36
            WHERE = fitz.Rect(MARGIN_LEFT, MARGIN_TOP, MEDIABOX.width - MARGIN_RIGHT, MEDIABOX.height - MARGIN_BOTTOM)

            story = fitz.Story(html=full_html)
            more = 1
            while more:
                page = doc.new_page(width=MEDIABOX.width, height=MEDIABOX.height)
                more, _ = story.place(WHERE)
                story.draw(page)

            doc.save(filename)
            doc.close()
            print(f"[CompExamPDF] Successfully generated PDF with PyMuPDF fitz.Story: {filename}")
            return
        except Exception as e:
            print(f"[CompExamPDF] PyMuPDF fitz.Story rendering warning: {e}. Falling back to ReportLab...")

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

        story.append(Paragraph(paper_title, title_style))
        story.append(Paragraph(f"Subject: {subject} | Time: {time_limit} | Marks: {total_marks}", h2_style))
        story.append(Paragraph(f"<b>Negative Marking Rule:</b> {negative_marking}", body_style))
        story.append(Spacer(1, 10))

        for sec in sections:
            s_name = sec.get("section_title") or sec.get("name") or "SECTION"
            story.append(Paragraph(f"&nbsp;{s_name}", sec_style))
            story.append(Spacer(1, 8))
            for q in sec.get("questions", []):
                q_text = q.get("question", "")
                q_num = q.get("question_number", 1)
                story.append(Paragraph(f"<b>Q{q_num}. {q_text}</b>", body_style))
                opts = q.get("options", {})
                if isinstance(opts, dict):
                    for k in ["A", "B", "C", "D"]:
                        if k in opts:
                            story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;<b>({k})</b> {opts[k]}", body_style))
                story.append(Spacer(1, 6))

        doc.build(story)
        print(f"[CompExamPDF] Saved PDF via ReportLab fallback: {filename}")
    except Exception as ex:
        print(f"[CompExamPDF] Critical error in ReportLab generation: {ex}")
