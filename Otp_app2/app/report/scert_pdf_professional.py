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
import sys
import reportlab

def setup_fonts(subject: str):
    """
    Registers the correct Unicode fonts for Hindi, Malayalam, or English.
    Returns (regular_font_name, bold_font_name).
    """
    subj = (subject or "").lower().strip()
    is_hindi = "hindi" in subj or subj == "hi"
    is_malayalam = "malayalam" in subj or subj == "ml"

    print(f"DEBUG: Python executable: {sys.executable}")
    print(f"DEBUG: ReportLab version: {reportlab.Version}")

    if not (is_hindi or is_malayalam):
        print("DEBUG: English subject detected. Using Helvetica.")
        return "Helvetica", "Helvetica-Bold"

    font_dir = "app/static/fonts"
    if is_hindi:
        reg_filename = "NotoSansDevanagari-Regular.ttf"
        bold_filename = "NotoSansDevanagari-Bold.ttf"
        reg_font_name = "NotoSansDevanagari"
        bold_font_name = "NotoSansDevanagari-Bold"
    else:  # Malayalam
        reg_filename = "NotoSansMalayalam-Regular.ttf"
        bold_filename = "NotoSansMalayalam-Bold.ttf"
        reg_font_name = "NotoSansMalayalam"
        bold_font_name = "NotoSansMalayalam-Bold"

    reg_path = os.path.abspath(os.path.join(font_dir, reg_filename))
    bold_path = os.path.abspath(os.path.join(font_dir, bold_filename))

    print(f"DEBUG: Expected font paths: {reg_path}, {bold_path}")

    if not os.path.exists(reg_path) or os.path.getsize(reg_path) == 0:
        raise Exception(f"CRITICAL: Required font file missing or empty at {reg_path}")
    print(f"DEBUG: Found {reg_path} (size: {os.path.getsize(reg_path)} bytes)")

    if not os.path.exists(bold_path) or os.path.getsize(bold_path) == 0:
        print(f"DEBUG: Bold font missing or empty at {bold_path}. Falling back to regular font for bold.")
        bold_path = reg_path
        bold_font_name = reg_font_name
    else:
        print(f"DEBUG: Found {bold_path} (size: {os.path.getsize(bold_path)} bytes)")

    pdfmetrics.registerFont(TTFont(reg_font_name, reg_path))
    print(f"DEBUG: Registered {reg_font_name}")
    if bold_path != reg_path:
        pdfmetrics.registerFont(TTFont(bold_font_name, bold_path))
        print(f"DEBUG: Registered {bold_font_name}")
    
    return reg_font_name, bold_font_name

def _safe(obj, key, default=""):
    return obj.get(key, default) if isinstance(obj, dict) else default

import itertools
def render_mixed(text, indic_font, latin_font="Helvetica"):
    """Splits text into ASCII and non-ASCII, assigning Helvetica to ASCII to avoid missing Latin glyphs in Noto Sans."""
    if text is None: return ""
    text = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    parts = []
    for is_ascii, group in itertools.groupby(text, key=lambda c: ord(c) < 128):
        font = latin_font if is_ascii else indic_font
        parts.append(f"<font name='{font}'>{''.join(group)}</font>")
    return "".join(parts)

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
    # FONTS & STYLES SETUP
    # -------------------
    subject = _safe(json_paper, "subject", "")
    font_reg, font_bold = setup_fonts(subject)

    styles = getSampleStyleSheet()

    english_title_style = ParagraphStyle("EnglishTitle", parent=styles["Heading1"], alignment=1, fontSize=18, leading=22, spaceAfter=10, fontName="Helvetica-Bold", textColor=colors.darkblue)
    english_hdr_style = ParagraphStyle("EnglishHeader", parent=styles["Normal"], alignment=1, fontSize=12, leading=14, spaceAfter=4, fontName="Helvetica-Bold")
    english_normal = ParagraphStyle("EnglishNormal", parent=styles["Normal"], fontSize=11, leading=16, fontName="Helvetica")
    english_section_style = ParagraphStyle("EnglishSection", parent=styles["Heading2"], fontSize=13, fontName="Helvetica-Bold", backColor=colors.lightgrey, spaceBefore=12, spaceAfter=8, leftIndent=4)

    title_style = ParagraphStyle(
        "Title", parent=styles["Heading1"], alignment=1, fontSize=18,
        leading=22, spaceAfter=10, fontName=font_bold, textColor=colors.darkblue
    )
    hdr_style = ParagraphStyle(
        "Hdr", parent=styles["Normal"], alignment=1, fontSize=12,
        leading=14, spaceAfter=4, fontName=font_bold
    )
    instr_title = ParagraphStyle(
        "InstrTitle", parent=styles["Normal"], fontSize=12,
        fontName="Helvetica-Bold", spaceAfter=4, textColor=colors.darkgreen
    )
    instr_style = ParagraphStyle(
        "Instr", parent=styles["Normal"], fontSize=11, leftIndent=10, leading=16,
        fontName=font_reg
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontSize=13,
        fontName=font_bold, backColor=colors.lightgrey,
        spaceBefore=12, spaceAfter=8, leftIndent=4
    )
    q_style = ParagraphStyle(
        "Q", parent=styles["Normal"], fontSize=11, leading=16, spaceAfter=4,
        fontName=font_reg
    )
    opt_style = ParagraphStyle(
        "Opt", parent=styles["Normal"], fontSize=10, leftIndent=18, leading=14,
        fontName=font_reg
    )
    case_style = ParagraphStyle(
        "Case", parent=styles["Normal"], fontSize=10, backColor=colors.whitesmoke,
        leftIndent=6, rightIndent=6, spaceBefore=6, spaceAfter=6, leading=14,
        fontName=font_reg
    )

    story = []

    # -------------------
    # HEADER
    # -------------------
    story.append(Paragraph("QUESTION PAPER", english_title_style))
    story.append(Paragraph(f"CLASS: {render_mixed(_safe(json_paper, 'standard', 'N/A'), font_bold, 'Helvetica-Bold')}", english_hdr_style))
    story.append(Paragraph(f"SUBJECT: {render_mixed(_safe(json_paper, 'subject', 'N/A'), font_bold, 'Helvetica-Bold')}", english_hdr_style))
    story.append(Spacer(1, 8))

    # TIME / MM row
    
    time_val = json_paper.get("time", "90 MINUTES")
    time_text = f"TIME: {time_val}" if "TIME" not in time_val.upper() else time_val
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
    story.append(Paragraph("<b>GENERAL INSTRUCTIONS:</b>", english_normal))
    gen_instr_list = []

    sections = _safe(json_paper, "sections", [])
    num_sections = len(sections)
    gen_instr_list.append(f"<font name='Helvetica'>The Question Paper contains {num_sections} section{'s' if num_sections > 1 else ''}.</font>")

    for sec in sections:
        sname = sec.get("section")
        total_q = len(sec.get("questions", []))
        attempt = sec.get("attempt", f"{total_q}")
        note = sec.get("note", "")
        text = f"<font name='Helvetica'>Section </font>{render_mixed(sname, font_reg)}<font name='Helvetica'> has {total_q} questions.</font>"
        if note:
            text += f" ({render_mixed(note, font_reg)})"
        gen_instr_list.append(text)

    gen_instr_list.append("<font name='Helvetica'>Attempt all questions.</font>")
    gen_instr_list.append("<font name='Helvetica'>There is no negative marking.</font>")

    for i, inst in enumerate(gen_instr_list, start=1):
        # inst already contains font tags from above, so just wrap the number
        story.append(Paragraph(f"<font name='Helvetica'>{i}.</font> {inst}", english_normal))

    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceBefore=6, spaceAfter=6))
    story.append(Spacer(1, 10))

    # Additional instructions from JSON
    json_instructions = _safe(json_paper, "instructions", [])
    for inst in json_instructions:
        story.append(Paragraph(render_mixed(inst, font_reg), instr_style))
    if json_instructions:
        story.append(Spacer(1, 8))

    # -------------------
    # SECTIONS & QUESTIONS
    # -------------------
    qnum = 1
    for sec in sections:
        sec_name = sec.get("section") or sec.get("title") or "Section"
        marks_per_q = sec.get("marks_per_question", None)
        sec_label = f"<font name='Helvetica'>SECTION</font> {render_mixed(sec_name, font_bold, 'Helvetica-Bold')}"
        if marks_per_q:
            sec_label += f"  <font name='Helvetica-Bold'>(Each question: {marks_per_q} mark{'s' if marks_per_q>1 else ''})</font>"
        story.append(Paragraph(sec_label, english_section_style))

        sec_instr = sec.get("instruction")
        if sec_instr:
            story.append(Paragraph(render_mixed(sec_instr, font_reg), instr_style))
            story.append(Spacer(1, 6))

        if sec.get("case"):
            story.append(Paragraph(render_mixed(sec.get("case"), font_reg), case_style))
            story.append(Spacer(1, 6))

        for q in sec.get("questions", []):
            # Defensive check: in case AI returns a string instead of a dictionary
            if not isinstance(q, dict):
                q = {"question": str(q), "type": "SHORT", "marks": marks_per_q}

            qtext = q.get("question", "").strip()
            qtype = (q.get("type") or "").upper()
            q_marks = q.get("marks", marks_per_q)
            q_marks_str = f" <font name='Helvetica'>({q_marks} mark{'s' if q_marks > 1 else ''})</font>" if q_marks else ""
            story.append(Paragraph(f"<font name='Helvetica'>{qnum}.</font> {render_mixed(qtext, font_reg)}<b>{q_marks_str}</b>", q_style))

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
                    opt_table = Table([[Paragraph(f"<font name='Helvetica'>A.</font> {render_mixed(cleaned_options[0], font_reg)}", opt_style), 
                                        Paragraph(f"<font name='Helvetica'>B.</font> {render_mixed(cleaned_options[1], font_reg)}", opt_style)],
                                       [Paragraph(f"<font name='Helvetica'>C.</font> {render_mixed(cleaned_options[2], font_reg)}", opt_style), 
                                        Paragraph(f"<font name='Helvetica'>D.</font> {render_mixed(cleaned_options[3], font_reg)}", opt_style)]],
                                      colWidths=[9*cm, 7*cm])
                    opt_table.setStyle(TableStyle([
                        ("VALIGN", (0,0), (-1,-1), "TOP"),
                        ("LEFTPADDING", (0,0), (-1,-1), 8),
                        ("RIGHTPADDING", (0,0), (-1,-1), 8),
                    ]))
                    story.append(opt_table)
                else:
                    for idx, opt in enumerate(cleaned_options):
                        story.append(Paragraph(f"<font name='Helvetica'>{chr(65+idx)}.</font> {render_mixed(opt, font_reg)}", opt_style))

            # True/False
            elif qtype in ("TRUEFALSE", "TRUE/FALSE"):
                story.append(Paragraph("True &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; False", english_normal))

            # Match the following
            elif qtype == "MATCHTHEFOLLOWING":
                lefts, rights = q.get("left", []), q.get("right", [])
                rows = [[Paragraph(f"<font name='Helvetica'>{i+1}.</font> {render_mixed(l, font_reg)}", opt_style), 
                         Paragraph(render_mixed(r, font_reg), opt_style)] for i, (l, r) in enumerate(zip(lefts, rights))]
                mtable = Table(rows, colWidths=[9*cm, 7*cm])
                mtable.setStyle(TableStyle([
                    ("VALIGN", (0,0), (-1,-1), "TOP")
                ]))
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
    print(f"Saved PDF to {filename}")

# -------------------
# EXAMPLE USAGE
# -------------------
if __name__ == "__main__":
    example_file = "paper.json"   # replace with your actual file path
    output_pdf = "Class10_Biology_Paper_Professional.pdf"
    with open(example_file, "r", encoding="utf-8") as f:
        json_paper = json.load(f)

    save_scert_question_paper(json_paper, output_pdf)