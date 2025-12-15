import os
import json
import argparse



def list_templates(base_dir: str) -> dict[str, str]:
    result = {}
    for name in os.listdir(base_dir):
        p = os.path.join(base_dir, name)
        if not os.path.isdir(p):
            continue
        desc = os.path.join(p, "description.md")
        if os.path.exists(desc):
            try:
                with open(desc, "r", encoding="utf-8") as f:
                    result[name] = f.read().strip()
            except Exception:
                pass
    return result

def embed_sentence_transformers(texts: dict[str, str]) -> dict[str, list[float]]:
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(os.getenv("SENTENCE_MODEL", "template/rag/all-MiniLM-L6-v2"))
        inputs = [texts[k] for k in texts.keys()]
        vecs = model.encode(inputs, normalize_embeddings=True)
        return {k: list(map(float, vecs[i])) for i, k in enumerate(texts.keys())}
    except Exception as e:
        raise RuntimeError(f"sentence-transformers backend failed: {e}")

def save_tensordict(vecs: dict[str, list[float]], output_path: str) -> str:
    try:
        import torch
        td = {k: torch.tensor(v, dtype=torch.float32) for k, v in vecs.items()}
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        torch.save(td, output_path)
        return output_path
    except Exception as e:
        print(f"save_tensordict error: {e}")
        alt = os.path.splitext(output_path)[0] + ".json"
        os.makedirs(os.path.dirname(alt), exist_ok=True)
        with open(alt, "w", encoding="utf-8") as f:
            json.dump(vecs, f)
        return alt

def run(base_dir: str, output_path: str) -> str:
    texts = list_templates(base_dir)
    vecs = embed_sentence_transformers(texts)
    return save_tensordict(vecs, output_path)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=os.path.join(os.path.dirname(__file__), "beamer_descriptions.tensordict.pt"))
    args = parser.parse_args()
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "beamer"))
    p = run(base_dir, args.output)
    print(p)

if __name__ == "__main__":
    main()
