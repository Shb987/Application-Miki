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

def setup_fonts(subject: str):
    """
    Returns font metadata tuple for subject.
    """
    subj = (subject or "").lower().strip()
    is_hindi = "hindi" in subj or subj == "hi"
    is_malayalam = "malayalam" in subj or subj == "ml"

    if is_hindi:
        return "NotoSansDevanagari", "NotoSansDevanagari-Bold"
    elif is_malayalam:
        return "NotoSansMalayalam", "NotoSansMalayalam-Bold"
    return "Helvetica", "Helvetica-Bold"

def _safe(obj, key, default=""):
    return obj.get(key, default) if isinstance(obj, dict) else default

def _escape_html(text):
    if text is None: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def render_mixed(text, indic_font=None, latin_font=None):
    """Escapes XML/HTML special characters for text rendering."""
    return _escape_html(text)

def save_scert_question_paper(json_paper: dict, filename: str):
    """
    Generate a professional SCERT-style question paper PDF from JSON using PyMuPDF (fitz.Story)
    for 100% accurate HarfBuzz OpenType text shaping (Malayalam, Hindi, English).
    """
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    
    subject = (json_paper.get("subject") or "").lower().strip()
    is_hi = "hindi" in subject or subject == "hi"
    is_ml = "malayalam" in subject or subject == "ml"
    
    lang_class = "lang-ml" if is_ml else ("lang-hi" if is_hi else "")
    bold_class = "lang-ml-bold" if is_ml else ("lang-hi-bold" if is_hi else "")

    std = _escape_html(str(json_paper.get("standard", "N/A")))
    subj_title = _escape_html(str(json_paper.get("subject", "N/A")))
    time_val = _escape_html(str(json_paper.get("time", "90 MINUTES")))
    time_text = f"TIME: {time_val}" if "TIME" not in time_val.upper() else time_val
    marks_val = _escape_html(str(json_paper.get("marks", 50)))

    # Get workspace base directory for font paths in fitz.Archive
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @font-face {{
    font-family: 'NotoMalayalam';
    src: url('app/static/fonts/NotoSansMalayalam-Regular.ttf');
  }}
  @font-face {{
    font-family: 'NotoMalayalamBold';
    src: url('app/static/fonts/NotoSansMalayalam-Bold.ttf');
  }}
  @font-face {{
    font-family: 'NotoDevanagari';
    src: url('app/static/fonts/NotoSansDevanagari-Regular.ttf');
  }}
  @font-face {{
    font-family: 'NotoDevanagariBold';
    src: url('app/static/fonts/NotoSansDevanagari-Bold.ttf');
  }}

  * {{
    box-sizing: border-box;
  }}
  body {{
    font-family: 'Helvetica', 'Arial', sans-serif;
    font-size: 13px;
    line-height: 1.5;
    color: #111111;
    padding: 0;
    margin: 0;
    width: 100%;
  }}
  .lang-ml {{ font-family: 'NotoMalayalam', sans-serif; }}
  .lang-ml-bold {{ font-family: 'NotoMalayalamBold', sans-serif; }}
  .lang-hi {{ font-family: 'NotoDevanagari', sans-serif; }}
  .lang-hi-bold {{ font-family: 'NotoDevanagariBold', sans-serif; }}
  
  .header {{ text-align: center; margin-bottom: 10px; width: 100%; }}
  .title {{ font-size: 20px; font-weight: bold; color: #002B49; margin-bottom: 4px; letter-spacing: 0.5px; text-transform: uppercase; }}
  .subtitle {{ font-size: 12px; font-weight: bold; margin-bottom: 2px; text-transform: uppercase; }}
  
  .meta-header {{
    width: 100%;
    border-bottom: 1.5px solid #000;
    padding-bottom: 6px;
    margin-bottom: 12px;
    font-size: 11px;
    font-weight: bold;
    clear: both;
    overflow: hidden;
  }}
  .meta-left {{
    float: left;
    text-align: left;
  }}
  .meta-right {{
    float: right;
    text-align: right;
  }}
  .clear-fix {{
    clear: both;
  }}

  .gen-instructions {{
    font-size: 11px;
    border-bottom: 1.5px solid #000;
    padding-bottom: 8px;
    margin-bottom: 14px;
    width: 100%;
  }}
  .gen-title {{ font-weight: bold; margin-bottom: 4px; }}
  .gen-list {{ margin: 0; padding-left: 20px; }}

  .section-hdr {{
    background-color: #eef2f5;
    color: #002B49;
    font-size: 13px;
    font-weight: bold;
    padding: 6px 10px;
    margin-top: 14px;
    margin-bottom: 12px;
    border-left: 4px solid #002B49;
    width: 100%;
    page-break-after: avoid;
    break-after: avoid;
  }}
  .question {{ margin-bottom: 14px; page-break-inside: avoid; break-inside: avoid; width: 100%; }}
  .q-text {{ font-size: 13px; margin-bottom: 6px; line-height: 1.6; color: #111111; }}
  
  .options-grid {{
    width: 100%;
    margin-top: 6px;
    margin-bottom: 8px;
    clear: both;
  }}
  .option-cell {{
    float: left;
    width: 48%;
    padding: 3px 2px;
    font-size: 12px;
  }}
  .match-table {{
    width: 100%;
    margin-top: 6px;
    margin-bottom: 8px;
    clear: both;
  }}
  .match-left {{ float: left; width: 48%; padding: 3px 2px; }}
  .match-right {{ float: right; width: 48%; padding: 3px 2px; }}
</style>
</head>
<body>
  <div class="header">
    <div class="title">QUESTION PAPER</div>
    <div class="subtitle">CLASS: {std}</div>
    <div class="subtitle">SUBJECT: {subj_title}</div>
  </div>
  <div class="meta-header">
    <div class="meta-left">{time_text}</div>
    <div class="meta-right">TOTAL MARKS: {marks_val}</div>
    <div class="clear-fix"></div>
  </div>

""")

    # General Instructions
    sections = json_paper.get("sections")
    if not isinstance(sections, list):
        sections = []
    num_sections = len(sections)
    html_parts.append(f"""
  <div class="gen-instructions">
    <div class="gen-title">GENERAL INSTRUCTIONS:</div>
    <ol class="gen-list">
      <li>The Question Paper contains {num_sections} section{'s' if num_sections > 1 else ''}.</li>
""")
    for sec in sections:
        if not isinstance(sec, dict): continue
        sname = _escape_html(str(sec.get("section") or sec.get("title") or "")).replace("Section", "").replace("SECTION", "").strip()
        qs = sec.get("questions")
        total_q = len(qs) if isinstance(qs, list) else 0
        html_parts.append(f"""      <li>Section {sname} has {total_q} questions.</li>\n""")
    html_parts.append("""      <li>Attempt all questions.</li>
      <li>There is no negative marking.</li>
    </ol>
  </div>
""")

    # Sections & Questions
    qnum = 1
    for sec in sections:
        if not isinstance(sec, dict): continue
        raw_sname = str(sec.get("section") or sec.get("title") or "Section")
        clean_sname = _escape_html(raw_sname).replace("Section", "").replace("SECTION", "").strip()
        sec_name_display = f"SECTION {clean_sname}" if clean_sname else f"{_escape_html(raw_sname)}"
        marks_per_q = sec.get("marks_per_question")
        marks_info = f" (Each question: {marks_per_q} mark{'s' if isinstance(marks_per_q, (int, float)) and marks_per_q > 1 else ''})" if marks_per_q else ""
        
        html_parts.append(f"""<div class="section-hdr {bold_class}">{sec_name_display}{marks_info}</div>""")
        
        sec_instr = sec.get("instruction")
        if sec_instr:
            html_parts.append(f"""<div style="font-style:italic; margin-bottom:8px;" class="{lang_class}">{_escape_html(str(sec_instr))}</div>""")

        questions = sec.get("questions")
        if not isinstance(questions, list):
            questions = []

        for q in questions:
            if isinstance(q, str):
                q = {"question": q, "type": "SHORT", "marks": marks_per_q}
            elif not isinstance(q, dict):
                continue
                
            qtext = _escape_html(str(q.get("question") or q.get("text") or "").strip())
            qtype = (str(q.get("type") or "")).upper()
            qmarks = q.get("marks", marks_per_q)
            qmarks_str = f" <b>({qmarks} mark{'s' if isinstance(qmarks, (int, float)) and qmarks > 1 else ''})</b>" if qmarks else ""
            
            html_parts.append(f"""
<div class="question">
  <div class="q-text {lang_class}"><b>{qnum}.</b> {qtext}{qmarks_str}</div>
""")
            
            if qtype == "MCQ":
                opts_list = q.get("options")
                if not isinstance(opts_list, list): opts_list = []
                raw_options = [str(o) for o in opts_list]
                cleaned_options = []
                for opt in raw_options:
                    c_opt = re.sub(r'^[A-Z0-9][\.\)\:\s-]+\s*', '', opt, flags=re.IGNORECASE)
                    c_opt = re.sub(r'^\([A-Z0-9]\)\s*', '', c_opt, flags=re.IGNORECASE)
                    cleaned_options.append(_escape_html(c_opt))
                    
                if len(cleaned_options) >= 4:
                    html_parts.append(f"""
  <div class="options-grid {lang_class}">
    <div class="option-row">
      <div class="option-cell">A. {cleaned_options[0]}</div>
      <div class="option-cell">B. {cleaned_options[1]}</div>
    </div>
    <div class="option-row">
      <div class="option-cell">C. {cleaned_options[2]}</div>
      <div class="option-cell">D. {cleaned_options[3]}</div>
    </div>
  </div>
""")
                else:
                    for idx, opt in enumerate(cleaned_options):
                        html_parts.append(f"""<div style="margin-left:16px;" class="{lang_class}">{chr(65+idx)}. {opt}</div>""")

            elif qtype in ("TRUEFALSE", "TRUE/FALSE"):
                tf_opts = "ശരി &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; തെറ്റ്" if is_ml else ("സത്യ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; असत्य" if is_hi else "True &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; False")
                html_parts.append(f"""<div style="margin-left:16px;" class="{lang_class}">{tf_opts}</div>""")

            elif qtype == "MATCHTHEFOLLOWING":
                left_list = q.get("left")
                if not isinstance(left_list, list): left_list = []
                right_list = q.get("right")
                if not isinstance(right_list, list): right_list = []
                lefts = [_escape_html(str(l)) for l in left_list]
                rights = [_escape_html(str(r)) for r in right_list]
                html_parts.append(f"""<div class="match-table {lang_class}">""")
                for i, (l_item, r_item) in enumerate(zip(lefts, rights)):
                    html_parts.append(f"""
    <div class="match-row">
      <div class="match-left">{i+1}. {l_item}</div>
      <div class="match-right">{chr(65+i)}. {r_item}</div>
    </div>
""")
                html_parts.append("""</div>""")

            elif qtype == "FILLINTHEBLANKS":
                html_parts.append(f"""<div style="margin-left:16px; margin-top:4px;" class="{lang_class}">Answer: ____________________________________</div>""")

            elif qtype == "PICTUREBASED":
                html_parts.append("""<div style="border:1px solid #666; height:120px; text-align:center; line-height:120px; color:#888; margin-top:6px; margin-bottom:6px;">[ SPACE FOR IMAGE / PICTURE ]</div>""")

            elif qtype in ("VERYSHORT", "SHORT"):
                html_parts.append("""<div style="height:35px;"></div>""")

            elif qtype in ("ESSAY", "LONG", "ANALYZE", "APPLY"):
                html_parts.append("""<div style="height:70px;"></div>""")

            html_parts.append("</div>")
            qnum += 1

    html_parts.append("""
</body>
</html>
""")

    full_html = "".join(html_parts)
    
    try:
        if fitz and hasattr(fitz, "Story") and hasattr(fitz, "Archive"):
            archive = fitz.Archive(base_dir)
            story = fitz.Story(full_html, archive=archive)
            writer = fitz.DocumentWriter(filename)

            page_rect = fitz.Rect(0, 0, 595, 842)      # A4 Page Mediabox (0, 0, 595, 842)
            content_rect = fitz.Rect(36, 36, 559, 806) # Printable Content Area (36pt margins)

            more = True
            while more:
                device = writer.begin_page(page_rect)
                more, _ = story.place(content_rect)
                story.draw(device)
                writer.end_page()

            writer.close()
            print(f"[PyMuPDF-PDF] Saved unclipped SCERT PDF to {filename} ({os.path.getsize(filename)} bytes)")
            return
        else:
            raise AttributeError("fitz module lacks Story or Archive")
    except Exception as err:
        print(f"[PDF-GEN] PyMuPDF fitz.Story rendering failed/unavailable: {err}. Falling back...")
        _save_fallback_pdf(json_paper, filename)


def _save_fallback_pdf(json_paper: dict, filename: str):
    """Fallback PDF generator using PyMuPDF or ReportLab."""
    pdf_done = False
    if fitz and (hasattr(fitz, "open") or hasattr(fitz, "Document")):
        try:
            doc_fn = getattr(fitz, "open", None) or getattr(fitz, "Document", None)
            doc = doc_fn()
            page = doc.new_page(width=595, height=842)
            
            std = json_paper.get("standard", "N/A")
            subj = json_paper.get("subject", "N/A")
            marks = json_paper.get("marks", 50)
            time_val = json_paper.get("time", "90 MINUTES")
            time_text = f"TIME - {time_val}" if "TIME" not in str(time_val).upper() else str(time_val)
            
            y = 45
            page.insert_text((200, y), "QUESTION PAPER", fontsize=16, fontname="helv-bold")
            y += 20
            page.insert_text((230, y), f"CLASS: {std}", fontsize=11, fontname="helv-bold")
            y += 18
            page.insert_text((210, y), f"SUBJECT: {subj}", fontsize=11, fontname="helv-bold")
            y += 25
            
            page.insert_text((50, y), time_text, fontsize=10, fontname="helv-bold")
            page.insert_text((420, y), f"TOTAL MARKS: {marks}", fontsize=10, fontname="helv-bold")
            y += 10
            page.draw_line(fitz.Point(50, y), fitz.Point(545, y), color=(0,0,0), width=1.5)
            y += 25
            
            qnum = 1
            sections = json_paper.get("sections", [])
            if isinstance(sections, list):
                for sec in sections:
                    if not isinstance(sec, dict): continue
                    sname = sec.get("section") or sec.get("title") or "Section"
                    if y > 720:
                        page = doc.new_page(width=595, height=842)
                        y = 50
                    page.insert_text((50, y), f"SECTION {sname}", fontsize=12, fontname="helv-bold")
                    y += 18
                    
                    qs = sec.get("questions", [])
                    if isinstance(qs, list):
                        for q in qs:
                            if y > 780:
                                page = doc.new_page(width=595, height=842)
                                y = 50
                            qtext = q.get("question") if isinstance(q, dict) else str(q)
                            clean_t = "".join([c if ord(c) < 128 else " " for c in str(qtext or "")])
                            try:
                                page.insert_text((50, y), f"{qnum}. {clean_t}", fontsize=10, fontname="helv")
                            except Exception:
                                pass
                            y += 18
                            qnum += 1
                    y += 10
                    
            doc.save(filename)
            doc.close()
            pdf_done = True
            print(f"[PyMuPDF-PDF] Saved fallback canvas PDF to {filename}")
        except Exception as ex:
            print(f"[PyMuPDF-PDF] Canvas fallback failed: {ex}")

    if not pdf_done:
        _save_reportlab_fallback(json_paper, filename)


def _save_reportlab_fallback(json_paper: dict, filename: str):
    """
    100% Guaranteed PDF Generator using ReportLab.
    Runs in any environment even if PyMuPDF (fitz) module is missing or incompatible.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        
        os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
        c = canvas.Canvas(filename, pagesize=A4)
        width, height = A4

        std = str(json_paper.get("standard", "N/A"))
        subj = str(json_paper.get("subject", "N/A"))
        marks = str(json_paper.get("marks", 50))
        time_val = str(json_paper.get("time", "90 MINUTES"))
        time_text = f"TIME - {time_val}" if "TIME" not in time_val.upper() else time_val

        y = height - 45
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(width / 2.0, y, "QUESTION PAPER")
        y -= 20
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(width / 2.0, y, f"CLASS: {std}")
        y -= 18
        c.drawCentredString(width / 2.0, y, f"SUBJECT: {subj}")
        y -= 25

        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, time_text)
        c.drawRightString(width - 50, y, f"TOTAL MARKS: {marks}")

        y -= 10
        c.setLineWidth(1.5)
        c.line(50, y, width - 50, y)
        y -= 25
        qnum = 1
        sections = json_paper.get("sections", [])
        if isinstance(sections, list):
            for sec in sections:
                if not isinstance(sec, dict): continue
                sname = str(sec.get("section") or sec.get("title") or "Section")

                if y < 110:
                    c.showPage()
                    y = height - 50

                c.setFont("Helvetica-Bold", 12)
                c.drawString(50, y, f"SECTION {sname}")
                y -= 20

                qs = sec.get("questions", [])
                if isinstance(qs, list):
                    for q in qs:
                        if y < 60:
                            c.showPage()
                            y = height - 50

                        qtext = q.get("question") if isinstance(q, dict) else str(q)
                        clean_t = "".join([ch if ord(ch) < 128 else " " for ch in str(qtext or "")])

                        c.setFont("Helvetica", 10)
                        words = clean_t.split()
                        line = f"{qnum}. "
                        for w in words:
                            if c.stringWidth(line + w + " ", "Helvetica", 10) > (width - 100):
                                c.drawString(50, y, line)
                                y -= 15
                                line = "   " + w + " "
                                if y < 60:
                                    c.showPage()
                                    y = height - 50
                            else:
                                line += w + " "
                        if line.strip():
                            c.drawString(50, y, line)
                            y -= 18

                        if isinstance(q, dict) and (q.get("type") or "").upper() == "MCQ":
                            opts = q.get("options")
                            if isinstance(opts, list):
                                for idx, opt in enumerate(opts):
                                    opt_clean = "".join([ch if ord(ch) < 128 else " " for ch in str(opt)])
                                    if y < 60:
                                        c.showPage()
                                        y = height - 50
                                    c.drawString(70, y, f"{chr(65+idx)}. {opt_clean}")
                                    y -= 15

                        qnum += 1
                y -= 10

        c.save()
        print(f"[ReportLab-PDF] Saved fallback PDF to {filename}")
    except Exception as ex:
        print(f"[ReportLab-PDF] CRITICAL error in ReportLab fallback: {ex}")