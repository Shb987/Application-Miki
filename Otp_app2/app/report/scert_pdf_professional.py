import os
import json
import re
import sys
import fitz  # PyMuPDF for 100% accurate HarfBuzz OpenType complex text shaping

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
  
  .meta-table {{
    width: 100%;
    border-bottom: 1.5px solid #000;
    padding-bottom: 6px;
    margin-bottom: 12px;
    font-size: 11px;
    font-weight: bold;
    table-layout: fixed;
  }}
  .meta-left {{ text-align: left; width: 50%; }}
  .meta-right {{ text-align: right; width: 50%; }}

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
    font-size: 13px;
    font-weight: bold;
    padding: 6px 10px;
    margin-top: 14px;
    margin-bottom: 12px;
    border-left: 4px solid #002B49;
    width: 100%;
  }}
  .question {{ margin-bottom: 14px; page-break-inside: avoid; width: 100%; }}
  .q-text {{ font-size: 13px; margin-bottom: 6px; line-height: 1.6; }}
  
  .options-grid {{
    display: table;
    width: 100%;
    table-layout: fixed;
    margin-top: 6px;
    margin-bottom: 8px;
  }}
  .option-row {{ display: table-row; }}
  .option-cell {{
    display: table-cell;
    width: 50%;
    padding: 3px 8px;
    font-size: 12px;
    vertical-align: top;
  }}
  .match-table {{
    display: table;
    width: 100%;
    table-layout: fixed;
    margin-top: 6px;
    margin-bottom: 8px;
  }}
  .match-row {{ display: table-row; }}
  .match-left {{ display: table-cell; width: 50%; padding: 3px 8px; vertical-align: top; }}
  .match-right {{ display: table-cell; width: 50%; padding: 3px 8px; vertical-align: top; }}
</style>
</head>
<body>
  <div class="header">
    <div class="title">QUESTION PAPER</div>
    <div class="subtitle">CLASS: {std}</div>
    <div class="subtitle">SUBJECT: {subj_title}</div>
  </div>
  <table class="meta-table">
    <tr>
      <td class="meta-left">{time_text}</td>
      <td class="meta-right">TOTAL MARKS: {marks_val}</td>
    </tr>
  </table>
""")

    # General Instructions
    sections = json_paper.get("sections", [])
    num_sections = len(sections)
    html_parts.append(f"""
  <div class="gen-instructions">
    <div class="gen-title">GENERAL INSTRUCTIONS:</div>
    <ol class="gen-list">
      <li>The Question Paper contains {num_sections} section{'s' if num_sections > 1 else ''}.</li>
""")
    for sec in sections:
        sname = _escape_html(sec.get("section") or sec.get("title") or "").replace("Section", "").replace("SECTION", "").strip()
        total_q = len(sec.get("questions", []))
        html_parts.append(f"""      <li>Section {sname} has {total_q} questions.</li>\n""")
    html_parts.append("""      <li>Attempt all questions.</li>
      <li>There is no negative marking.</li>
    </ol>
  </div>
""")

    # Sections & Questions
    qnum = 1
    for sec in sections:
        raw_sname = sec.get("section") or sec.get("title") or "Section"
        clean_sname = _escape_html(raw_sname).replace("Section", "").replace("SECTION", "").strip()
        sec_name_display = f"SECTION {clean_sname}" if clean_sname else f"{_escape_html(raw_sname)}"
        marks_per_q = sec.get("marks_per_question")
        marks_info = f" (Each question: {marks_per_q} mark{'s' if marks_per_q > 1 else ''})" if marks_per_q else ""
        
        html_parts.append(f"""<div class="section-hdr {bold_class}">{sec_name_display}{marks_info}</div>""")
        
        sec_instr = sec.get("instruction")
        if sec_instr:
            html_parts.append(f"""<div style="font-style:italic; margin-bottom:8px;" class="{lang_class}">{_escape_html(sec_instr)}</div>""")

        for q in sec.get("questions", []):
            if not isinstance(q, dict):
                q = {"question": str(q), "type": "SHORT", "marks": marks_per_q}
                
            qtext = _escape_html(q.get("question", "").strip())
            qtype = (q.get("type") or "").upper()
            qmarks = q.get("marks", marks_per_q)
            qmarks_str = f" <b>({qmarks} mark{'s' if qmarks > 1 else ''})</b>" if qmarks else ""
            
            html_parts.append(f"""
<div class="question">
  <div class="q-text {lang_class}"><b>{qnum}.</b> {qtext}{qmarks_str}</div>
""")
            
            if qtype == "MCQ":
                raw_options = [str(o) for o in q.get("options", [])]
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
                tf_opts = "ശരി &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; തെറ്റ്" if is_ml else ("सत्य &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; असत्य" if is_hi else "True &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; False")
                html_parts.append(f"""<div style="margin-left:16px;" class="{lang_class}">{tf_opts}</div>""")

            elif qtype == "MATCHTHEFOLLOWING":
                lefts = [_escape_html(str(l)) for l in q.get("left", [])]
                rights = [_escape_html(str(r)) for r in q.get("right", [])]
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