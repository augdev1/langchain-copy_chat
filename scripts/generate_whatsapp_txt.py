import re
from pathlib import Path

def convert_md_to_whatsapp_txt(md_path, txt_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.splitlines()
    out_lines = []

    for line in lines:
        s = line.rstrip()

        # Divider
        if s.strip() == '---':
            out_lines.append("────────────────────────────────────────")
            continue

        # Header 1
        if s.startswith('# '):
            text = s[2:].strip()
            out_lines.append(f"*{text.upper()}*")
            continue

        # Header 2 (Situation)
        if s.startswith('## '):
            text = s[3:].strip()
            out_lines.append("")
            out_lines.append("════════════════════════════════════════")
            out_lines.append(f"📌 *{text.upper()}*")
            out_lines.append("════════════════════════════════════════")
            continue

        # Header 3
        if s.startswith('### '):
            text = s[4:].strip()
            clean_text = re.sub(r'^\*\*(.*?)\*\*$', r'\1', text)
            out_lines.append("")
            out_lines.append(f"🔹 *{clean_text}*")
            continue

        # Header 4
        if s.startswith('#### '):
            text = s[5:].strip()
            clean_text = re.sub(r'^\*\*(.*?)\*\*$', r'\1', text)
            out_lines.append("")
            out_lines.append(f"👉 *{clean_text}*")
            continue

        # Visual directions: *(Texto)*
        if s.strip().startswith('*(') and s.strip().endswith(')*'):
            note = s.strip()[1:-1]
            out_lines.append(f"_{note}_")
            continue

        # Correct multi-stage markdown to WhatsApp syntax:
        # 1. Bold & Italic (***text***) -> __W_BOLD_ITALIC__
        s = re.sub(r'\*\*\*(.*?)\*\*\*', r'__W_BI_S__\1__W_BI_E__', s)
        # 2. Bold (**text**) -> __W_BOLD__
        s = re.sub(r'\*\*([^*]+)\*\*', r'__W_B_S__\1__W_B_E__', s)
        # 3. Italic (*text*) -> _text_
        s = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'_\1_', s)
        # 4. Monospace (`code`) -> ```code```
        s = re.sub(r'`([^`]+)`', r'```\1```', s)

        # 5. Resolve placeholders into WhatsApp syntax
        s = s.replace('__W_BI_S__', '*_').replace('__W_BI_E__', '_*')
        s = s.replace('__W_B_S__', '*').replace('__W_B_E__', '*')

        out_lines.append(s)

    result_txt = "\n".join(out_lines)

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(result_txt)

    print(f"Arquivo WhatsApp TXT salvo em: {txt_path}")

if __name__ == '__main__':
    base_dir = Path(__file__).resolve().parent.parent
    md_file = base_dir / "resultado_5_situacoes.md"
    txt_file = base_dir / "resultado_5_situacoes_whatsapp.txt"
    convert_md_to_whatsapp_txt(md_file, txt_file)
