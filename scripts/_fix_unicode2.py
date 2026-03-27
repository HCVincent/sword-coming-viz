"""Fix remaining unicode escapes."""
import pathlib, re

p = pathlib.Path(r"d:\code\NovelVisualization\SwordComing\scripts\build_swordcoming_writer_insights.py")
data = p.read_text(encoding="utf-8")

lines = data.split('\n')
changed = False
for i, line in enumerate(lines):
    if '\\u' in line and '_score_foreshadow' not in line:
        # Only fix lines that actually have escaped unicode (not real \u in strings)
        # Check if this is inside the _score function area
        pass
    if '"\\u' in line or "'\\u" in line:
        original = line
        fixed = re.sub(r'(?<!\\)\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), line)
        if fixed != original:
            lines[i] = fixed
            print(f"Line {i+1}: fixed unicode escapes")
            changed = True

if changed:
    data = '\n'.join(lines)
    p.write_text(data, encoding="utf-8")
    print("All unicode escapes fixed")
else:
    print("No remaining unicode escapes found")
