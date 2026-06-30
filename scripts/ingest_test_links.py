import sys
import pathlib
import os

# Add project root to sys.path to resolve imports
project_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

from dotenv import load_dotenv
load_dotenv()

from agentic_rag.runtime_env import load_local_env
load_local_env()

from agentic_rag.generation.evidence import source_provider_from_env

def main():
    print("=========================================================")
    print("      Ingesting Test URLs from Link_data.txt             ")
    print("=========================================================")

    # Initialize RAG evidence provider
    try:
        provider = source_provider_from_env()
    except Exception as e:
        print(f"Error: Failed to initialize source evidence provider: {e}", file=sys.stderr)
        sys.exit(1)

    urls = [
        "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9",
        "https://shop.vinfastauto.com/vn_vi/car-vf9.html",
        "https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap/cau-hoi-xe-o-to/san-pham/vf-9",
        "https://vinfastauto.com/vn_vi/uu-dai-thanh-vien-vinclub-khi-mua-xe-vinfast",
        "https://vinfastauto.com/vn_vi/le-phi-truoc-ba-o-to-2022",
        "https://vinfastauto.com/vn_vi/muc-thu-phi-duong-bo-nam-2022",
        "https://vinfastauto.com/vn_vi/quy-dinh-phi-kiem-dinh-xe-o-to-moi-nhat"
    ]

    for idx, url in enumerate(urls, 1):
        print(f"\n[{idx}/{len(urls)}] Ingesting URL: {url}...")
        try:
            res = provider.upload_url(url=url)
            chunk_count = 0
            if res.trace and "chunking" in res.trace:
                chunk_count = res.trace["chunking"].get("chunk_count", 0)
            print(f"  [OK] Success! Document ID: {res.document_id}, Chunks: {chunk_count}")
        except Exception as e:
            print(f"  [ERROR] Failed to ingest URL: {e}", file=sys.stderr)

    print("\nIngestion Completed!")

if __name__ == "__main__":
    main()
