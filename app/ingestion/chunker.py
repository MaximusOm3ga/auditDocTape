import re
from typing import List

def chunk_text(text: str, max_chars: int = 1200) -> list[str]:

    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    split_paras = []
    for para in paras:
        if re.match(r"^\s*(?:\d+\.[\d.]*|[Ss]ection\s+\d+|[Cc]lause\s+\d+|[Aa]rticle\s+\d+)", para):
            split_paras.append(para)
        else:
            split_paras.append(para)
    chunks = []
    current = ""
    
    for para in split_paras:
        if len(current) + len(para) > max_chars and current:
            chunks.append(current.strip())
            current = ""
        
        current += para + "\n\n"
    
    if current.strip():
        chunks.append(current.strip())
    
    return chunks


def chunk_text_for_spreadsheet(rows: List[List[str]], max_rows_per_chunk: int = 5) -> List[str]:

    if not rows:
        return []
    
    chunks = []
    header = rows[0]
    header_str = " | ".join(str(h) for h in header)
    
    current_chunk = [header_str]
    current_row_count = 0
    
    for row in rows[1:]:
        row_str = " | ".join(str(cell) for cell in row)
        current_chunk.append(row_str)
        current_row_count += 1
        
        if current_row_count >= max_rows_per_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = [header_str]  # Reset with header
            current_row_count = 0
    if len(current_chunk) > 1:
        chunks.append("\n".join(current_chunk))
    
    return chunks


