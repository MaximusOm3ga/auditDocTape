import re

def chunk_text(text: str, max_chars: int = 1200) -> list[str]:

    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks, current = [], ""

    for p in paras:

        if len(current) + len(p) > max_chars and current:

            chunks.append(current.strip())

            current = ""

        current += p + "\n\n"

    if current.strip():

        chunks.append(current.strip())

    return chunks
