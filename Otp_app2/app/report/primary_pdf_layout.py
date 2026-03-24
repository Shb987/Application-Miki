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

def _safe(obj, key, default=""):
    return obj.get(key, default) if isinstance(obj, dict) else default

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
    # STYLES (Enlarged and Clearer)
    # -------------------
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title", parent=styles["Heading1"], alignment=1, fontSize=20,
        leading=26, spaceAfter=15, fontName="Helvetica-Bold", textColor=colors.darkblue
    )
    hdr_style = ParagraphStyle(
        "Hdr", parent=styles["Normal"], alignment=1, fontSize=14,
        leading=18, spaceAfter=8, fontName="Helvetica-Bold"
    )
    instr_title = ParagraphStyle(
        "InstrTitle", parent=styles["Normal"], fontSize=13,
        fontName="Helvetica-Bold", spaceAfter=6, textColor=colors.darkgreen
    )
    instr_style = ParagraphStyle(
        "Instr", parent=styles["Normal"], fontSize=12, leftIndent=12, leading=18
    )
    section_style = ParagraphStyle(
        "Section", parent=styles["Heading2"], fontSize=15,
        fontName="Helvetica-Bold", backColor=colors.lightcyan,
        spaceBefore=15, spaceAfter=10, leftIndent=6, borderPadding=5
    )
    q_style = ParagraphStyle(
        "Q", parent=styles["Normal"], fontSize=13, leading=20, spaceAfter=6
    )
    opt_style = ParagraphStyle(
        "Opt", parent=styles["Normal"], fontSize=12, leftIndent=24, leading=18
    )
    
    story = []

    # -------------------
    # HEADER
    # -------------------
    story.append(Paragraph("MY QUESTION PAPER", title_style))
    story.append(Paragraph(f"CLASS: { _safe(json_paper, 'standard', 'N/A') }", hdr_style))
    story.append(Paragraph(f"SUBJECT: { _safe(json_paper, 'subject', 'N/A') }", hdr_style))
    story.append(Spacer(1, 10))

    # MARKS row
    marks_total = json_paper.get("marks", 0)
    mm_text = f"Total Marks: {marks_total}"
    time_text = json_paper.get("time", "Time: 60 Minutes")

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
        sec_label = f"PART {sec_name}"
        if marks_per_q:
            sec_label += f"  ({marks_per_q} mark{'s' if marks_per_q>1 else ''} each)"
        story.append(Paragraph(sec_label, section_style))

        sec_instr = sec.get("instruction") or "Read the questions carefully and answer."
        story.append(Paragraph(f"<i>{sec_instr}</i>", instr_style))
        story.append(Spacer(1, 10))

        for q in sec.get("questions", []):
            if not isinstance(q, dict): continue

            qtext = q.get("question", "").strip()
            # Strip "Fill in the blank: " or "Fill in the blanks: " if it exists
            qtext = re.sub(r'^(Fill in the blank(s)?|Fill in the blank)\s*:\s*', '', qtext, flags=re.IGNORECASE)
            
            qtype = (q.get("type") or "").upper()
            q_marks = q.get("marks", marks_per_q)
            q_marks_str = f" [{q_marks}]" if q_marks else ""
            
            story.append(Paragraph(f"<b>{qnum}.</b> {qtext} {q_marks_str}", q_style))

            # --- RENDER BY TYPE ---
            
            if qtype == "MCQ":
                options = [str(o) for o in q.get("options", [])]
                for idx, opt in enumerate(options):
                    # Strip existing "A.", "B.", "A:", "1:", "A)", "(A)" etc to avoid repetition
                    # We look for a Letter or Number at start followed by punctuation/spaces
                    clean_opt = re.sub(r'^[A-Z0-9][\.\)\:\s-]+\s*', '', opt, flags=re.IGNORECASE)
                    clean_opt = re.sub(r'^\([A-Z0-9]\)\s*', '', clean_opt, flags=re.IGNORECASE)
                    # User requested: no brackets ( ) here
                    story.append(Paragraph(f"{chr(65+idx)}. {clean_opt}", opt_style))

            elif qtype in ("TRUEFALSE", "TRUE/FALSE"):
                # Simplified: No brackets, just the words for kids to circle
                story.append(Paragraph("True &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; False", opt_style))

            elif qtype == "FILLINTHEBLANKS":
                story.append(Paragraph("Answer: ____________________________________", opt_style))

            elif qtype == "MATCHTHEFOLLOWING":
                lefts, rights = q.get("left", []), q.get("right", [])
                rows = [[f"{i+1}. {l}", "                  ", r] for i, (l, r) in enumerate(zip(lefts, rights))]
                if rows:
                    mtable = Table(rows, colWidths=[6.5*cm, 4*cm, 6.5*cm])
                    mtable.setStyle(TableStyle([
                        ("FONTSIZE", (0,0), (-1,-1), 11), 
                        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                        ("ALIGN", (1,0), (1,0), "CENTER")
                    ]))
                    story.append(mtable)
                else:
                    story.append(Paragraph("<i>(Match the following items were not provided correctly)</i>", opt_style))

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
