from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import json
import os
import re

# Optional: register a nicer font
# pdfmetrics.registerFont(TTFont('DejaVuSans', '/path/to/DejaVuSans.ttf'))

def _safe(obj, key, default=""):
    return obj.get(key, default) if isinstance(obj, dict) else default

def save_scert_question_paper(json_paper: dict, filename: str):
    """
    Generate a professional SCERT-style question paper PDF from JSON.
    """
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

    # -------------------
    # DOCUMENT SETUP
    # -------------------
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=36, leftMargin=36,
        topMargin=36, bottomMargin=36
    )

    # -------------------
    # STYLES
    # -------------------
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title", parent=styles["Heading1"], alignment=1, fontSize=18,
        leading=22, spaceAfter=10, fontName="Helvetica-Bold", textColor=colors.darkblue
    )
    hdr_style = ParagraphStyle(
        "Hdr", parent=styles["Normal"], alignment=1, fontSize=12,
        leading=14, spaceAfter=4, fontName="Helvetica-Bold"
    )
    instr_title = ParagraphStyle(
        "InstrTitle", parent=styles["Normal"], fontSize=12,
        fontName="Helvetica-Bold", spaceAfter=4, textColor=colors.darkgreen
    )
    instr_style = ParagraphStyle(
        "Instr", parent=styles["Normal"], fontSize=11, leftIndent=10, leading=16
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontSize=13,
        fontName="Helvetica-Bold", backColor=colors.lightgrey,
        spaceBefore=12, spaceAfter=8, leftIndent=4
    )
    q_style = ParagraphStyle(
        "Q", parent=styles["Normal"], fontSize=11, leading=16, spaceAfter=4
    )
    opt_style = ParagraphStyle(
        "Opt", parent=styles["Normal"], fontSize=10, leftIndent=18, leading=14
    )
    case_style = ParagraphStyle(
        "Case", parent=styles["Normal"], fontSize=10, backColor=colors.whitesmoke,
        leftIndent=6, rightIndent=6, spaceBefore=6, spaceAfter=6, leading=14
    )

    story = []

    # -------------------
    # HEADER
    # -------------------
    story.append(Paragraph("QUESTION PAPER", title_style))
    story.append(Paragraph(f"CLASS: { _safe(json_paper, 'standard', 'N/A') }", hdr_style))
    story.append(Paragraph(f"SUBJECT: { _safe(json_paper, 'subject', 'N/A') }", hdr_style))
    story.append(Spacer(1, 8))

    # TIME / MM row
    
    time_text = json_paper.get("time", "TIME - 90 MINUTES")
    marks_total = json_paper.get("marks", 0)
    mm_text = f"TOTAL MARKS: {marks_total}"

    title_row = Table([[time_text, "", mm_text]], colWidths=[9*cm, 2*cm, 8*cm])
    title_row.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 11),
        ("ALIGN", (0,0), (0,0), "LEFT"),
        ("ALIGN", (2,0), (2,0), "RIGHT"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(title_row)
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceBefore=6, spaceAfter=6))
    story.append(Spacer(1, 6))

    # -------------------
    # GENERAL INSTRUCTIONS
    # -------------------
    story.append(Paragraph("<b>GENERAL INSTRUCTIONS:</b>", instr_title))
    gen_instr_list = []

    sections = _safe(json_paper, "sections", [])
    num_sections = len(sections)
    gen_instr_list.append(f"The Question Paper contains {num_sections} section{'s' if num_sections > 1 else ''}.")

    for sec in sections:
        sname = sec.get("section")
        total_q = len(sec.get("questions", []))
        attempt = sec.get("attempt", f"{total_q}")
        note = sec.get("note", "")
        text = f"Section {sname} has {total_q} questions."
        if note:
            text += f" ({note})"
        gen_instr_list.append(text)

    gen_instr_list.append("Attempt all questions.")
    gen_instr_list.append("There is no negative marking.")

    for i, inst in enumerate(gen_instr_list, start=1):
        story.append(Paragraph(f"{i}. {inst}", instr_style))

    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceBefore=6, spaceAfter=6))
    story.append(Spacer(1, 10))

    # Additional instructions from JSON
    json_instructions = _safe(json_paper, "instructions", [])
    for inst in json_instructions:
        story.append(Paragraph(inst, instr_style))
    if json_instructions:
        story.append(Spacer(1, 8))

    # -------------------
    # SECTIONS & QUESTIONS
    # -------------------
    qnum = 1
    for sec in sections:
        sec_name = sec.get("section") or sec.get("title") or "Section"
        marks_per_q = sec.get("marks_per_question", None)
        sec_label = f"SECTION {sec_name}"
        if marks_per_q:
            sec_label += f"  (Each question: {marks_per_q} mark{'s' if marks_per_q>1 else ''})"
        story.append(Paragraph(sec_label, section_style))

        sec_instr = sec.get("instruction")
        if sec_instr:
            story.append(Paragraph(sec_instr, instr_style))
            story.append(Spacer(1, 6))

        if sec.get("case"):
            story.append(Paragraph(sec.get("case"), case_style))
            story.append(Spacer(1, 6))

        for q in sec.get("questions", []):
            # Defensive check: in case AI returns a string instead of a dictionary
            if not isinstance(q, dict):
                q = {"question": str(q), "type": "SHORT", "marks": marks_per_q}

            qtext = q.get("question", "").strip()
            qtype = (q.get("type") or "").upper()
            q_marks = q.get("marks", marks_per_q)
            q_marks_str = f" ({q_marks} mark{'s' if q_marks > 1 else ''})" if q_marks else ""
            story.append(Paragraph(f"{qnum}. {qtext}<b>{q_marks_str}</b>", q_style))

            # Picture-based placeholder
            if qtype == "PICTUREBASED":
                story.append(Spacer(1, 6))
                box = Table([[" [ SPACE FOR IMAGE / PICTURE ] "]], colWidths=[16*cm], rowHeights=[4*cm])
                box.setStyle(TableStyle([
                    ("BOX", (0,0), (-1,-1), 0.6, colors.black),
                    ("ALIGN", (0,0), (-1,-1), "CENTER"),
                    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                    ("FONTSIZE", (0,0), (-1,-1), 10),
                    ("TEXTCOLOR", (0,0), (-1,-1), colors.grey)
                ]))
                story.append(box)
                story.append(Spacer(1, 6))

            # MCQ Options
            if qtype == "MCQ":
                options = [str(o) for o in q.get("options", [])]
                cleaned_options = []
                for opt in options:
                    clean_opt = re.sub(r'^[A-Z0-9][\.\)\:\s-]+\s*', '', opt, flags=re.IGNORECASE)
                    clean_opt = re.sub(r'^\([A-Z0-9]\)\s*', '', clean_opt, flags=re.IGNORECASE)
                    cleaned_options.append(clean_opt)

                if len(cleaned_options) >= 4:
                    opt_table = Table([[f"A. {cleaned_options[0]}", f"B. {cleaned_options[1]}"],
                                       [f"C. {cleaned_options[2]}", f"D. {cleaned_options[3]}"]],
                                      colWidths=[9*cm, 7*cm])
                    opt_table.setStyle(TableStyle([
                        ("FONTNAME", (0,0), (-1,-1), "Helvetica"),
                        ("FONTSIZE", (0,0), (-1,-1), 10),
                        ("VALIGN", (0,0), (-1,-1), "TOP"),
                        ("LEFTPADDING", (0,0), (-1,-1), 8),
                        ("RIGHTPADDING", (0,0), (-1,-1), 8),
                    ]))
                    story.append(opt_table)
                else:
                    for idx, opt in enumerate(cleaned_options):
                        story.append(Paragraph(f"{chr(65+idx)}. {opt}", opt_style))

            # True/False
            elif qtype in ("TRUEFALSE", "TRUE/FALSE"):
                story.append(Paragraph("True &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; False", opt_style))

            # Match the following
            elif qtype == "MATCHTHEFOLLOWING":
                lefts, rights = q.get("left", []), q.get("right", [])
                rows = [[f"{i+1}. {l}", r] for i, (l, r) in enumerate(zip(lefts, rights))]
                mtable = Table(rows, colWidths=[9*cm, 7*cm])
                mtable.setStyle(TableStyle([("FONTSIZE", (0,0), (-1,-1), 10), ("VALIGN", (0,0), (-1,-1), "TOP")]))
                story.append(mtable)

            # Fill in the blanks
            elif qtype == "FILLINTHEBLANKS":
                blanks = q.get("blanks", 1)
                for _ in range(blanks):
                    story.append(Paragraph("____", opt_style))

            # Diagram/Map placeholder
            elif qtype in ("DIAGRAM", "MAP"):
                story.append(Spacer(1, 6))
                box = Table([[" "]], colWidths=[16*cm], rowHeights=[4*cm])
                box.setStyle(TableStyle([("BOX", (0,0), (-1,-1), 0.6, colors.black)]))
                story.append(box)
                story.append(Spacer(1, 6))

            # Answer space for short/essay
            if qtype in ("VERYSHORT", "SHORT"):
                story.append(Spacer(1, 10))
            elif qtype in ("ESSAY", "LONG", "ANALYZE", "APPLY"):
                story.append(Spacer(1, 20))

            story.append(Spacer(1, 6))
            qnum += 1

        story.append(Spacer(1, 12))  # space after section

    # -------------------
    # FOOTER
    # -------------------
    def _footer(canvas, doc):
        canvas.saveState()
        footer_text = f"Page {canvas.getPageNumber()}"
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(A4[0] - 36, 18, footer_text)
        canvas.restoreState()

    # -------------------
    # BUILD PDF
    # -------------------
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    print(f"Saved PDF → {filename}")

# -------------------
# EXAMPLE USAGE
# -------------------
if __name__ == "__main__":
    example_file = "paper.json"   # replace with your actual file path
    output_pdf = "Class10_Biology_Paper_Professional.pdf"
    with open(example_file, "r", encoding="utf-8") as f:
        json_paper = json.load(f)

    save_scert_question_paper(json_paper, output_pdf)