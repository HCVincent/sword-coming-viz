"""Fix the unicode escape issue in the f-string."""
import pathlib

p = pathlib.Path(r"d:\code\NovelVisualization\SwordComing\scripts\build_swordcoming_writer_insights.py")
data = p.read_text(encoding="utf-8")

# The raw string in the patch preserved \uXXXX as literal backslash-u sequences.
# We need to replace those two f-string lines with actual Chinese characters.

old_summary = (
    '                "summary": (\n'
    '                    f"{label}\\u5728{(\'\\u3001\'.join(seasons) if seasons else \'\\u5f53\\u524d\\u8303\\u56f4\')}\\u5f62\\u6210\\u201c\\u524d\\u6bb5\\u57cb\\u7ebf\\uff0c\\u540e\\u6bb5\\u5151\\u73b0\\u201d\\u7684\\u63a8\\u8fdb\\u7ed3\\u6784\\uff0c"\n'
    '                    f"\\u91cd\\u70b9\\u89d2\\u8272\\u5305\\u62ec{(\'\\u3001\'.join(focus_roles) if focus_roles else \'\\u591a\\u4f4d\\u4eba\\u7269\')}\\u3002"\n'
    '                ),\n'
)

new_summary = (
    '                "summary": (\n'
    '                    f"{label}\u5728{(\'\u3001\'.join(seasons) if seasons else \'\u5f53\u524d\u8303\u56f4\')}\u5f62\u6210\u201c\u524d\u6bb5\u57cb\u7ebf\uff0c\u540e\u6bb5\u5151\u73b0\u201d\u7684\u63a8\u8fdb\u7ed3\u6784\uff0c"\n'
    '                    f"\u91cd\u70b9\u89d2\u8272\u5305\u62ec{(\'\u3001\'.join(focus_roles) if focus_roles else \'\u591a\u4f4d\u4eba\u7269\')}\u3002"\n'
    '                ),\n'
)

if old_summary in data:
    data = data.replace(old_summary, new_summary)
    p.write_text(data, encoding="utf-8")
    print("Fixed unicode escapes in f-string")
else:
    print("Old summary not found - checking manually")
    # Let's find the line and fix it directly
    lines = data.split('\n')
    for i, line in enumerate(lines):
        if '\\u5728' in line and 'label' in line:
            print(f"Found at line {i+1}: {line[:100]}")
            # Replace all \\uXXXX with actual unicode
            import re
            fixed = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), line)
            lines[i] = fixed
            print(f"Fixed to: {fixed[:100]}")
        if '\\u91cd' in line:
            print(f"Found at line {i+1}: {line[:100]}")
            import re
            fixed = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), line)
            lines[i] = fixed
            print(f"Fixed to: {fixed[:100]}")
    data = '\n'.join(lines)
    p.write_text(data, encoding="utf-8")
    print("Fixed via line-by-line replacement")
