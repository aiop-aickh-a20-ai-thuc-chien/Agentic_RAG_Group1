import re

out_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\tmp\inspect_output.txt"

with open(out_path, "r", encoding="utf-8") as f:
    text = f.read()

# Split by the separator "--------------------------------------------------------------------------------\n"
sections = text.split("-" * 80 + "\n")

print(f"Total matching sections: {len(sections)}")

# For each section, print the header line (first line)
for idx, sec in enumerate(sections):
    if not sec.strip():
        continue
    first_line = sec.splitlines()[0]
    print(f"Sec {idx}: {first_line}")
