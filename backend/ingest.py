import argparse
import sys
import uuid
from pathlib import Path

# Add backend directory to sys.path so app modules are resolvable
BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.services.document_parser import document_parser
from app.services.qdrant_service import qdrant_service

GUIDELINE_METADATA = {
    "cgtmse_overview.md": {
        "title": "CGTMSE Overview & Framework",
        "section": "Overview & Framework",
        "url": "https://www.cgtmse.in"
    },
    "cgtmse_eligibility.md": {
        "title": "CGTMSE Eligibility Criteria",
        "section": "Eligibility Criteria",
        "url": "https://www.cgtmse.in"
    },
    "cgtmse_coverage_slabs.md": {
        "title": "CGTMSE Guarantee Coverage Slabs",
        "section": "Guarantee Coverage Slabs",
        "url": "https://www.cgtmse.in"
    },
    "cgtmse_agf_calculator.md": {
        "title": "CGTMSE Annual Guarantee Fee (AGF)",
        "section": "Annual Guarantee Fee (AGF)",
        "url": "https://www.cgtmse.in"
    },
    "cgtmse_documentation_checklist.md": {
        "title": "CGTMSE Documentation & Appraisal Checklist",
        "section": "Documentation & Appraisal",
        "url": "https://www.cgtmse.in"
    },
    "cgtmse_claims_npa.md": {
        "title": "CGTMSE NPA & Claim Settlement Procedures",
        "section": "NPA & Claim Settlement",
        "url": "https://www.cgtmse.in"
    },
    "cgtmse_gms_100_faqs.md": {
        "title": "CGTMSE GMS 100 Operational FAQs",
        "section": "GMS Operational FAQs",
        "url": "https://www.cgtmse.in/gms"
    }
}

def ingest_file(file_path: Path, title: str = None, section: str = None, url: str = None, doc_id: str = None):
    print(f"[Ingest] Reading file: {file_path}...")
    try:
        parsed = document_parser.parse_file(file_path)
        meta = GUIDELINE_METADATA.get(file_path.name, {})
        doc_title = title or meta.get("title") or parsed["title"]
        doc_section = section or meta.get("section") or "Official Circular"
        doc_url = url or meta.get("url") or f"https://www.cgtmse.in/circulars/{file_path.name}"
        chunks = document_parser.chunk_text(parsed["content"], chunk_size=800, chunk_overlap=150)
        
        doc_id = doc_id or file_path.stem
        count = qdrant_service.upsert_chunks(
            chunks=chunks,
            title=doc_title,
            section=doc_section,
            url=doc_url,
            doc_id=doc_id
        )
        print(f"  -> SUCCESS: Indexed '{doc_title}' ({count} chunks, doc_id={doc_id})")
        return count
    except Exception as e:
        print(f"  -> FAILED {file_path.name}: {e}")
        return 0

def ingest_directory(dir_path: Path):
    if not dir_path.exists():
        print(f"[Error] Directory not found: {dir_path}")
        return 0

    supported_exts = {".pdf", ".docx", ".txt", ".md", ".json"}
    files = [f for f in sorted(dir_path.glob("*")) if f.suffix.lower() in supported_exts]
    print(f"[Ingest] Found {len(files)} supported document(s) in {dir_path}...")

    total_chunks = 0
    for f in files:
        total_chunks += ingest_file(f)
    print(f"[Ingest Complete] Total {total_chunks} chunks indexed into Qdrant collection '{settings.QDRANT_COLLECTION}'.")
    return total_chunks

def ingest_all():
    """Ingests all available data: 100 GMS FAQs + all default knowledge guidelines."""
    print("=" * 60)
    print("  CGTMSE Assist - Complete Data Ingestion to Qdrant")
    print("=" * 60)

    # 1. Ingest 100 structured FAQs
    json_path = settings.DATA_DIR / "cgtmse_gms_100_faqs.json"
    if json_path.exists():
        print("\n[Phase 1/2] Indexing 100 GMS FAQs from JSON...")
        try:
            from ingest_100_faqs import ingest_faqs
            ingest_faqs()
        except Exception as e:
            print(f"[Error] Ingesting FAQs failed: {e}")
    else:
        print(f"[Warning] FAQ JSON not found at {json_path}")

    # 2. Ingest default knowledge documents
    print("\n[Phase 2/2] Indexing Core Guidelines and Markdown Archives...")
    total_chunks = ingest_directory(settings.DEFAULT_KNOWLEDGE_DIR)

    # 3. Show Final Stats
    show_stats()

def show_stats():
    stats = qdrant_service.get_stats()
    print("=" * 50)
    print("  Qdrant Knowledge Base Stats")
    print("=" * 50)
    for k, v in stats.items():
        print(f"  {k:20}: {v}")
    print("=" * 50)

def clear_all(force: bool = False):
    if not force:
        confirm = input("Are you sure you want to clear the entire Qdrant collection? (y/N): ")
        if confirm.lower() != "y":
            print("Aborted.")
            return
    qdrant_service.clear_collection()
    print("Collection cleared and reinitialized.")

def main():
    parser = argparse.ArgumentParser(description="CGTMSE Knowledge Ingestion CLI")
    parser.add_argument("--all", "-a", action="store_true", help="Ingest all data: 100 GMS FAQs and all default guidelines")
    parser.add_argument("--file", "-f", type=str, help="Path to single file to ingest (.pdf, .docx, .txt, .md, .json)")
    parser.add_argument("--dir", "-d", type=str, help="Directory of files to ingest")
    parser.add_argument("--default", action="store_true", help="Ingest all built-in official CGTMSE guidelines")
    parser.add_argument("--stats", "-s", action="store_true", help="Display Qdrant collection statistics")
    parser.add_argument("--clear", "-c", action="store_true", help="Clear all vectors from the collection")
    parser.add_argument("--force", action="store_true", help="Force action without confirmation prompt")
    parser.add_argument("--title", "-t", type=str, help="Optional custom title for the document")
    parser.add_argument("--section", type=str, help="Optional section/topic name")
    parser.add_argument("--url", type=str, help="Optional source URL")

    args = parser.parse_args()

    if args.stats:
        show_stats()
    elif args.clear:
        clear_all(force=args.force)
    elif args.all:
        ingest_all()
    elif args.default:
        ingest_directory(settings.DEFAULT_KNOWLEDGE_DIR)
    elif args.file:
        ingest_file(Path(args.file), title=args.title, section=args.section, url=args.url)
    elif args.dir:
        ingest_directory(Path(args.dir))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
