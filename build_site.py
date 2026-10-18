"""library/*.json 을 모아 대시보드가 읽는 docs/data.js 를 만든다."""
import json
from pathlib import Path

ROOT = Path(__file__).parent
records = [json.loads(p.read_text(encoding="utf-8-sig")) for p in (ROOT / "library").glob("*.json")]
records.sort(key=lambda r: r["published"], reverse=True)

out = ROOT / "docs"
out.mkdir(exist_ok=True)
# .js 로 만들어 두면 file:// 로 열어도, GitHub Pages 에서도 똑같이 동작한다
(out / "data.js").write_text("window.SERMONS = " + json.dumps(records, ensure_ascii=False) + ";\n", encoding="utf-8")
print(f"설교 {len(records)}편 -> docs/data.js")
