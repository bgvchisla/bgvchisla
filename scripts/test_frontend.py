#!/usr/bin/env python3
"""Validate inline JavaScript and mobile navigation ARIA markup in index.html."""
from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "index.html"


def inline_scripts(source: str) -> list[str]:
    blocks = re.findall(r"<script\\b([^>]*)>([\\s\\S]*?)</script\\s*>", source, flags=re.IGNORECASE)
    result = []
    for attrs, body in blocks:
        if re.search(r"\\bsrc\\s*=", attrs, flags=re.IGNORECASE):
            continue
        if re.search(r'type\\s*=\\s*["\\']application/(?:ld\\+)?json["\\']', attrs, flags=re.IGNORECASE):
            continue
        if body.strip():
            result.append(body)
    return result


class FrontendIntegrityTests(unittest.TestCase):
    def test_all_inline_javascript_parses(self):
        source = HTML_PATH.read_text(encoding="utf-8")
        scripts = inline_scripts(source)
        self.assertGreater(len(scripts), 0, "No inline JavaScript blocks were found.")
        with tempfile.TemporaryDirectory() as tmp:
            for index, script in enumerate(scripts):
                path = Path(tmp) / f"inline-{index}.js"
                path.write_text(script, encoding="utf-8")
                result = subprocess.run(
                    ["node", "--check", str(path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    f"Inline script {index} has a JavaScript syntax error:\\n{result.stderr}",
                )

    def test_navigation_aria_attributes_are_separate_and_valid(self):
        source = HTML_PATH.read_text(encoding="utf-8")
        self.assertIn("""var ariaCurrent=i===0?' aria-current="page"':'';""", source)
        self.assertIn("""aria-pressed="'+(i?"false":"true")+'"'+ariaCurrent+""", source)
        self.assertNotIn("""aria-pressed="'+(i?"false":"true")+' '+(i===0?""", source)

    def test_all_sixteen_controlled_section_ids_exist(self):
        source = HTML_PATH.read_text(encoding="utf-8")
        for index in range(16):
            self.assertIn(f'id="s{index}"', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
