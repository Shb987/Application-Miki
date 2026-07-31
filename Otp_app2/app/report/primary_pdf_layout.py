from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
import json
import os
import re
import sys
import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

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

def save_primary_question_paper(json_paper: dict, filename: str):
    """
    Generate an engaging and child-friendly question paper PDF for Standards 1-5.
    """
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

    # -------------------
    # DOCUMENT SETUP
    # -------------------
    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=40, leftMargin=40,
        topMargin=40, bottomMargin=40
    )

    # -------------------
    # FONTS & STYLES SETUP
    # -------------------
    subject = _safe(json_paper, "subject", "")
    font_reg, font_bold = setup_fonts(subject)

    styles = getSampleStyleSheet()

    english_title_style = ParagraphStyle("EnglishTitle", parent=styles["Heading1"], alignment=1, fontSize=20, leading=26, spaceAfter=15, fontName="Helvetica-Bold", textColor=colors.darkblue)
    english_hdr_style = ParagraphStyle("EnglishHeader", parent=styles["Normal"], alignment=1, fontSize=14, leading=18, spaceAfter=8, fontName="Helvetica-Bold")
    english_normal = ParagraphStyle("EnglishNormal", parent=styles["Normal"], fontSize=12, leading=18, fontName="Helvetica")
    english_section_style = ParagraphStyle("EnglishSection", parent=styles["Heading2"], fontSize=15, fontName="Helvetica-Bold", backColor=colors.lightcyan, spaceBefore=15, spaceAfter=10, leftIndent=6, borderPadding=5)

    title_style = ParagraphStyle(
        "Title", parent=styles["Heading1"], alignment=1, fontSize=20,
        leading=26, spaceAfter=15, fontName=font_bold, textColor=colors.darkblue
    )
    hdr_style = ParagraphStyle(
        "Hdr", parent=styles["Normal"], alignment=1, fontSize=14,
        leading=18, spaceAfter=8, fontName=font_bold
    )
    instr_title = ParagraphStyle(
        "InstrTitle", parent=styles["Normal"], fontSize=13,
        fontName="Helvetica-Bold", spaceAfter=6, textColor=colors.darkgreen
    )
    instr_style = ParagraphStyle(
        "Instr", parent=styles["Normal"], fontSize=12, leftIndent=12, leading=18,
        fontName=font_reg
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontSize=15,
        fontName=font_bold, backColor=colors.lightcyan,
        spaceBefore=15, spaceAfter=10, leftIndent=6, borderPadding=5
    )
    q_style = ParagraphStyle(
        "Q", parent=styles["Normal"], fontSize=13, leading=20, spaceAfter=6,
        fontName=font_reg
    )
    opt_style = ParagraphStyle(
        "Opt", parent=styles["Normal"], fontSize=12, leftIndent=24, leading=18,
        fontName=font_reg
    )
    
    story = []

    # -------------------
    # HEADER
    # -------------------
    story.append(Paragraph("MY QUESTION PAPER", english_title_style))
    story.append(Paragraph(f"CLASS: {render_mixed(_safe(json_paper, 'standard', 'N/A'), font_bold, 'Helvetica-Bold')}", english_hdr_style))
    story.append(Paragraph(f"SUBJECT: {render_mixed(_safe(json_paper, 'subject', 'N/A'), font_bold, 'Helvetica-Bold')}", english_hdr_style))
    story.append(Spacer(1, 10))

    # MARKS row
    marks_total = json_paper.get("marks", 0)
    mm_text = f"TOTAL MARKS: {marks_total}"
    time_val = json_paper.get("time", "60 MINUTES")
    time_text = f"TIME: {time_val}" if "TIME" not in time_val.upper() else time_val

    title_row = Table([[time_text, mm_text]], colWidths=[9*cm, 8*cm])
    title_row.setStyle(TableStyle([
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 12),
        ("ALIGN", (0,0), (0,0), "LEFT"),
        ("ALIGN", (1,0), (1,0), "RIGHT"),
    ]))
    story.append(title_row)
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.darkblue, spaceBefore=8, spaceAfter=8))
    story.append(Spacer(1, 8))

    # -------------------
    # SECTIONS & QUESTIONS
    # -------------------
    sections = _safe(json_paper, "sections", [])
    qnum = 1
    for sec in sections:
        sec_name = sec.get("section") or sec.get("title") or "Part"
        marks_per_q = sec.get("marks_per_question", None)
        sec_label = f"<font name='Helvetica-Bold'>PART</font> {render_mixed(sec_name, font_bold, 'Helvetica-Bold')}"
        if marks_per_q:
            sec_label += f"  <font name='Helvetica-Bold'>({marks_per_q} mark{'s' if marks_per_q>1 else ''} each)</font>"
        story.append(Paragraph(sec_label, english_section_style))

        sec_instr = sec.get("instruction") or "Read the questions carefully and answer."
        story.append(Paragraph(f"<i>{render_mixed(sec_instr, font_reg)}</i>", instr_style))
        story.append(Spacer(1, 10))

        for q in sec.get("questions", []):
            if not isinstance(q, dict): continue

            qtext = q.get("question", "").strip()
            # Strip "Fill in the blank: " or "Fill in the blanks: " if it exists
            qtext = re.sub(r'^(Fill in the blank(s)?|Fill in the blank)\s*:\s*', '', qtext, flags=re.IGNORECASE)
            
            qtype = (q.get("type") or "").upper()
            q_marks = q.get("marks", marks_per_q)
            q_marks_str = f" <font name='Helvetica'>[{q_marks}]</font>" if q_marks else ""
            
            story.append(Paragraph(f"<b><font name='Helvetica'>{qnum}.</font></b> {render_mixed(qtext, font_reg)} {q_marks_str}", q_style))

            # --- RENDER BY TYPE ---
            
            if qtype == "MCQ":
                options = [str(o) for o in q.get("options", [])]
                for idx, opt in enumerate(options):
                    # Strip existing "A.", "B.", "A:", "1:", "A)", "(A)" etc to avoid repetition
                    # We look for a Letter or Number at start followed by punctuation/spaces
                    clean_opt = re.sub(r'^[A-Z0-9][\.\)\:\s-]+\s*', '', opt, flags=re.IGNORECASE)
                    clean_opt = re.sub(r'^\([A-Z0-9]\)\s*', '', clean_opt, flags=re.IGNORECASE)
                    # User requested: no brackets ( ) here
                    story.append(Paragraph(f"<font name='Helvetica'>{chr(65+idx)}.</font> {render_mixed(clean_opt, font_reg)}", opt_style))

            elif qtype in ("TRUEFALSE", "TRUE/FALSE"):
                # Simplified: No brackets, just the words for kids to circle
                story.append(Paragraph("True &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; False", english_normal))

            elif qtype == "FILLINTHEBLANKS":
                story.append(Paragraph("Answer: ____________________________________", opt_style))

            elif qtype == "MATCHTHEFOLLOWING":
                lefts, rights = q.get("left", []), q.get("right", [])
                rows = [[Paragraph(f"<font name='Helvetica'>{i+1}.</font> {render_mixed(l, font_reg)}", opt_style), 
                         "                  ", 
                         Paragraph(render_mixed(r, font_reg), opt_style)] for i, (l, r) in enumerate(zip(lefts, rights))]
                if rows:
                    mtable = Table(rows, colWidths=[6.5*cm, 4*cm, 6.5*cm])
                    mtable.setStyle(TableStyle([
                        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                        ("ALIGN", (1,0), (1,0), "CENTER")
                    ]))
                    story.append(mtable)
                else:
                    story.append(Paragraph("<i><font name='Helvetica'>(Match the following items were not provided correctly)</font></i>", opt_style))

            elif qtype == "PICTUREBASED":
                story.append(Spacer(1, 8))
                box = Table([[" [ DRAW OR LOOK AT PICTURE HERE ] "]], colWidths=[16*cm], rowHeights=[4*cm])
                box.setStyle(TableStyle([
                    ("BOX", (0,0), (-1,-1), 1, colors.grey),
                    ("ALIGN", (0,0), (-1,-1), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                    ("TEXTCOLOR", (0,0), (-1,-1), colors.lightgrey)
                ]))
                story.append(box)
            
            elif qtype in ("VERYSHORT", "SHORT"):
                # Multi-line writing space
                story.append(Spacer(1, 15))
                story.append(HRFlowable(width="90%", thickness=0.5, color=colors.lightgrey, spaceBefore=10))
                story.append(HRFlowable(width="90%", thickness=0.5, color=colors.lightgrey, spaceBefore=20))

            story.append(Spacer(1, 12))
            qnum += 1

    # -------------------
    # FOOTER
    # -------------------
    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawRightString(A4[0] - 40, 25, f"Page {canvas.getPageNumber()}")
        canvas.drawCentredString(A4[0]/2, 25, "--- End of paper ---")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return filename
