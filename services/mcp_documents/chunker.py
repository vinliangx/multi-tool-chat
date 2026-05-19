from config import settings
from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_text(text: str) -> list[dict]:
    size = settings.chunk_size
    overlap = settings.chunk_overlap
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        add_start_index=True,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    docs = splitter.create_documents([text])
    return [{"text": d.page_content, "start_index": d.metadata["start_index"]} for d in docs]
