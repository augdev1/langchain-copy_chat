import os
import re
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# Register TrueType fonts from Windows
pdfmetrics.registerFont(TTFont('Calibri', 'C:/Windows/Fonts/calibri.ttf'))
pdfmetrics.registerFont(TTFont('Calibri-Bold', 'C:/Windows/Fonts/calibrib.ttf'))
pdfmetrics.registerFont(TTFont('Calibri-Italic', 'C:/Windows/Fonts/calibrii.ttf'))
pdfmetrics.registerFont(TTFont('Calibri-BoldItalic', 'C:/Windows/Fonts/calibriz.ttf'))

# Fallback fonts
pdfmetrics.registerFontFamily(
    'Calibri',
    normal='Calibri',
    bold='Calibri-Bold',
    italic='Calibri-Italic',
    boldItalic='Calibri-BoldItalic'
)

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super(NumberedCanvas, self).showPage()
        super(NumberedCanvas, self).save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Calibri", 8.5)
        self.setFillColor(colors.HexColor("#64748B"))
        
        # Header (pages > 1)
        if self._pageNumber > 1:
            self.drawString(45, 805, "Relatório Estratégico de Neurocopy")
            self.drawRightString(550, 805, "5 Situações de Teste")
            self.setStrokeColor(colors.HexColor("#E2E8F0"))
            self.setLineWidth(0.5)
            self.line(45, 798, 550, 798)
            
        # Footer
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.5)
        self.line(45, 45, 550, 45)
        self.drawString(45, 32, "Confidencial • Uso Estratégico de Conteúdo")
        self.drawRightString(550, 32, f"Página {self._pageNumber} de {page_count}")
        self.restoreState()

def md_to_reportlab(text):
    """
    Converts markdown formatting to ReportLab XML tags:
    **text** -> <b>text</b>
    *text* -> <i>text</i>
    `code` -> <font face="Courier" color="#B91C1C">code</font>
    """
    # Replace code blocks
    text = re.sub(r'`([^`]+)`', r'<font face="Courier" color="#991B1B">\1</font>', text)
    # Replace bold
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    # Replace italic (single asterisk not adjacent to another)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<i>\1</i>', text)
    # Clean & chars for XML
    text = text.replace('& ', '&amp; ')
    return text

def generate_pdf(md_path, pdf_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=45,
        rightMargin=45,
        topMargin=55,
        bottomMargin=55
    )

    styles = getSampleStyleSheet()

    # Custom styles
    style_title = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Calibri-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=6
    )

    style_meta = ParagraphStyle(
        'MetaSubtitle',
        parent=styles['Normal'],
        fontName='Calibri',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#475569"),
        spaceAfter=14
    )

    style_h2 = ParagraphStyle(
        'SituationHeading',
        parent=styles['Normal'],
        fontName='Calibri-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1D4ED8"),
        spaceBefore=12,
        spaceAfter=10,
        keepWithNext=True
    )

    style_h3 = ParagraphStyle(
        'SectionH3',
        parent=styles['Normal'],
        fontName='Calibri-Bold',
        fontSize=11.5,
        leading=15,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )

    style_h4 = ParagraphStyle(
        'ScreenH4',
        parent=styles['Normal'],
        fontName='Calibri-Bold',
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#2563EB"),
        spaceBefore=8,
        spaceAfter=3,
        keepWithNext=True
    )

    style_body = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Calibri',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1E293B"),
        spaceAfter=4
    )

    style_bullet = ParagraphStyle(
        'BulletCustom',
        parent=styles['Normal'],
        fontName='Calibri',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#334155"),
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=3
    )

    style_visual_note = ParagraphStyle(
        'VisualNote',
        parent=styles['Normal'],
        fontName='Calibri-Italic',
        fontSize=9,
        leading=12.5,
        textColor=colors.HexColor("#64748B"),
        leftIndent=12,
        spaceBefore=2,
        spaceAfter=5
    )

    style_highlight = ParagraphStyle(
        'HighlightLine',
        parent=styles['Normal'],
        fontName='Calibri-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#C2410C"),
        spaceBefore=4,
        spaceAfter=6
    )

    lines = content.splitlines()
    story = []

    situation_count = 0
    in_briefing_box = False
    briefing_items = []

    for line in lines:
        s = line.strip()

        if not s:
            continue

        if s == '---':
            story.append(Spacer(1, 4))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0"), spaceAfter=8))
            continue

        if s.startswith('# '):
            text = md_to_reportlab(s[2:].strip())
            story.append(Paragraph(text, style_title))
            continue

        if s.startswith('**Modelo Utilizado:**'):
            text = md_to_reportlab(s)
            story.append(Paragraph(text, style_meta))
            continue

        if s.startswith('## '):
            situation_count += 1
            if situation_count > 1:
                story.append(PageBreak())
                
            text = md_to_reportlab(s[3:].strip())
            # Badge header box
            t = Table(
                [[Paragraph(f"<b>{text}</b>", style_h2)]],
                colWidths=[505]
            )
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EFF6FF")),
                ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#BFDBFE")),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('LEFTPADDING', (0,0), (-1,-1), 10),
                ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ]))
            story.append(t)
            story.append(Spacer(1, 8))
            continue

        if s.startswith('### '):
            text = md_to_reportlab(s[4:].strip())
            story.append(Paragraph(text, style_h3))
            continue

        if s.startswith('#### '):
            text = md_to_reportlab(s[5:].strip())
            story.append(Paragraph(text, style_h4))
            continue

        if s.startswith('- ') or (s.startswith('* ') and not s.endswith('*')):
            bullet_text = s[2:].strip()
            text = md_to_reportlab(f"• {bullet_text}")
            story.append(Paragraph(text, style_bullet))
            continue

        num_match = re.match(r'^(\d+)\.\s+(.*)$', s)
        if num_match:
            num = num_match.group(1)
            item_text = num_match.group(2)
            text = md_to_reportlab(f"<b>{num}.</b> {item_text}")
            p_style = ParagraphStyle(
                f'NumList_{num}',
                parent=style_bullet,
                leftIndent=18,
                firstLineIndent=-12
            )
            story.append(Paragraph(text, p_style))
            continue

        if s.startswith('*(') and s.endswith(')*'):
            note_content = s[1:-1]
            text = md_to_reportlab(f"🎥 {note_content}")
            story.append(Paragraph(text, style_visual_note))
            continue

        if s.startswith('🔥'):
            text = md_to_reportlab(s)
            story.append(Paragraph(text, style_highlight))
            continue

        # Standard paragraph
        text = md_to_reportlab(s)
        story.append(Paragraph(text, style_body))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"PDF gerado com sucesso em: {pdf_path}")

if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parent.parent
    md_file = base_dir / "resultado_5_situacoes.md"
    pdf_file = base_dir / "resultado_5_situacoes.pdf"
    generate_pdf(md_file, pdf_file)
