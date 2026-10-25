import os
import re
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def set_cell_background(cell, fill_hex):
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)

def add_horizontal_rule(doc, color_hex="CBD5E1"):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(8)
    pBdr = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="1" w:color="{color_hex}"/></w:pBdr>')
    p._p.get_or_add_pPr().append(pBdr)

def tokenize_markdown(text):
    """
    Tokenizes inline markdown with formatting:
    ***bold italic***, **bold**, *italic*, `code`
    """
    tokens = []
    # Pattern to match bold-italic, bold, italic, code
    pattern = re.compile(r'(\*\*\*.*?\*\*\*|\*\*.*?\*\*|\*[^*\n]+?\*|`.*?`)')
    parts = pattern.split(text)
    for part in parts:
        if not part:
            continue
        if part.startswith('***') and part.endswith('***') and len(part) >= 6:
            tokens.append(('bold_italic', part[3:-3]))
        elif part.startswith('**') and part.endswith('**') and len(part) >= 4:
            tokens.append(('bold', part[2:-2]))
        elif part.startswith('*') and part.endswith('*') and len(part) >= 2:
            tokens.append(('italic', part[1:-1]))
        elif part.startswith('`') and part.endswith('`') and len(part) >= 2:
            tokens.append(('code', part[1:-1]))
        else:
            tokens.append(('text', part))
    return tokens

def add_styled_runs(paragraph, text, base_font_name="Calibri", base_size=Pt(10.5), base_color=RGBColor(30, 41, 59)):
    tokens = tokenize_markdown(text)
    for token_type, content in tokens:
        run = paragraph.add_run(content)
        run.font.name = base_font_name
        run.font.size = base_size
        run.font.color.rgb = base_color
        
        if token_type == 'bold':
            run.bold = True
        elif token_type == 'italic':
            run.italic = True
        elif token_type == 'bold_italic':
            run.bold = True
            run.italic = True
        elif token_type == 'code':
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(180, 40, 40)

def convert_md_to_docx(md_path, docx_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    doc = Document()

    # Set page margins (1 inch / 72pt)
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.9)
        section.right_margin = Inches(0.9)
        
        # Add Header
        header = section.header
        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hrun = hp.add_run("Relatório Estratégico • Neurocopy Master System")
        hrun.font.name = "Calibri"
        hrun.font.size = Pt(8.5)
        hrun.font.color.rgb = RGBColor(148, 163, 184)
        
        # Add Footer
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        frun = fp.add_run("Relatório de Testes Locais de Neurocopy — 5 Situações Reais")
        frun.font.name = "Calibri"
        frun.font.size = Pt(8.5)
        frun.font.color.rgb = RGBColor(148, 163, 184)

    situation_count = 0
    in_copy_section = False

    for raw_line in lines:
        line = raw_line.strip()

        # Empty lines
        if not line:
            continue

        # Horizontal Rule
        if line == '---':
            add_horizontal_rule(doc)
            continue

        # Heading 1 (#)
        if line.startswith('# '):
            text = line[2:].strip()
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(text)
            run.font.name = "Calibri"
            run.font.size = Pt(22)
            run.bold = True
            run.font.color.rgb = RGBColor(15, 23, 42) # Slate 900
            continue

        # Heading 2 (## Situação ...)
        if line.startswith('## '):
            text = line[3:].strip()
            situation_count += 1
            if situation_count > 1:
                # Add page break before each new situation for clean executive presentation
                doc.add_page_break()
                
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(14)
            p.paragraph_format.space_after = Pt(8)
            p.paragraph_format.keep_with_next = True
            
            # Left accent border for Situation titles
            pBdr = parse_xml(f'<w:pBdr {nsdecls("w")}><w:left w:val="single" w:sz="24" w:space="8" w:color="2563EB"/></w:pBdr>')
            p._p.get_or_add_pPr().append(pBdr)
            
            run = p.add_run(text)
            run.font.name = "Calibri"
            run.font.size = Pt(15)
            run.bold = True
            run.font.color.rgb = RGBColor(37, 99, 235) # Royal Blue
            continue

        # Heading 3 (### ...)
        if line.startswith('### '):
            text = line[4:].strip()
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.keep_with_next = True
            
            # Strip markdown bold if already wrapped in *** or **
            clean_text = text
            if clean_text.startswith('**') and clean_text.endswith('**'):
                clean_text = clean_text[2:-2]
            
            add_styled_runs(p, clean_text, base_font_name="Calibri", base_size=Pt(12), base_color=RGBColor(30, 41, 59))
            p.runs[0].bold = True if p.runs else None
            continue

        # Heading 4 (#### ...)
        if line.startswith('#### '):
            text = line[5:].strip()
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(2)
            p.paragraph_format.keep_with_next = True
            
            clean_text = text
            if clean_text.startswith('**') and clean_text.endswith('**'):
                clean_text = clean_text[2:-2]
                
            add_styled_runs(p, clean_text, base_font_name="Calibri", base_size=Pt(11), base_color=RGBColor(30, 58, 138)) # Deep blue
            for r in p.runs:
                r.bold = True
            continue

        # Bullet List (- or *)
        if line.startswith('- ') or (line.startswith('* ') and not line.endswith('*')):
            item_text = line[2:].strip()
            p = doc.add_paragraph(style='List Bullet')
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.15
            add_styled_runs(p, item_text, base_font_name="Calibri", base_size=Pt(10), base_color=RGBColor(51, 65, 85))
            continue

        # Numbered List (1. , 2. )
        num_match = re.match(r'^(\d+)\.\s+(.*)$', line)
        if num_match:
            num = num_match.group(1)
            item_text = num_match.group(2)
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.25)
            p.paragraph_format.space_before = Pt(1)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.15
            run_num = p.add_run(f"{num}. ")
            run_num.font.name = "Calibri"
            run_num.font.size = Pt(10)
            run_num.font.color.rgb = RGBColor(37, 99, 235)
            run_num.bold = True
            add_styled_runs(p, item_text, base_font_name="Calibri", base_size=Pt(10), base_color=RGBColor(51, 65, 85))
            continue

        # Visual note / scene instructions: *(Texto entre parênteses em itálico)*
        if line.startswith('*(') and line.endswith(')*'):
            note_text = line[1:-1] # keeps the (parens)
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.2)
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(f"🎥 {note_text}")
            run.font.name = "Calibri"
            run.font.size = Pt(9.5)
            run.italic = True
            run.font.color.rgb = RGBColor(100, 116, 139) # Slate 500
            continue

        # Standard Paragraph
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(2)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.line_spacing = 1.15
        
        # Check if it's the flame highlight line
        if line.startswith('🔥'):
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
            add_styled_runs(p, line, base_font_name="Calibri", base_size=Pt(10.5), base_color=RGBColor(194, 65, 12)) # Amber/Rust
        else:
            add_styled_runs(p, line, base_font_name="Calibri", base_size=Pt(10.5), base_color=RGBColor(30, 41, 59))

    doc.save(docx_path)
    print(f"Documento DOCX salvo com sucesso em: {docx_path}")

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent
    md_file = base_dir / "resultado_5_situacoes.md"
    docx_file = base_dir / "resultado_5_situacoes.docx"
    convert_md_to_docx(md_file, docx_file)
