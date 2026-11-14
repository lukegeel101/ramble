"""Active-destination capture, bounded serialization, and fail-closed behavior."""
import json
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from tests.helpers import ROOT, InstallCase

sys.path.insert(0, str(ROOT))
import context


class Context(InstallCase):
    def setUp(self):
        super().setUp()
        self.hs = self.tmp / "hs"
        self.hs.write_text('''#!/usr/bin/env python3
import json, os, sys, time
if os.environ.get("FAKE_HS_MODE") == "hang": time.sleep(20)
if os.environ.get("FAKE_HS_MODE") == "fail": sys.exit(1)
if os.environ.get("FAKE_HS_ARGS"):
    open(os.environ["FAKE_HS_ARGS"], "w").write(json.dumps(sys.argv))
print(os.environ.get("FAKE_HS_DATA", '{}'))
''')
        self.hs.chmod(0o755)
        self.env.update(RAMBLE_CONTEXT="1", RAMBLE_HS=str(self.hs))

    def run_context(self, data=None, args=(), **env):
        return subprocess.run([sys.executable, str(self.home / 'context.py'), *args],
                              env={**self.env, "FAKE_HS_DATA": json.dumps(data or {}), **env},
                              capture_output=True, text=True, timeout=10)

    def test_reads_selected_destination_and_forwards_identity(self):
        log = self.tmp / 'args.json'
        out = self.run_context({"status": "ok", "text": "User: MarzipanQueue\n\nAssistant: fix MarzipanQueue"},
                               args=("--app", "com.openai.codex", "--window", "42"), FAKE_HS_ARGS=str(log))
        self.assertIn("MarzipanQueue", out.stdout)
        self.assertIn('com.openai.codex', log.read_text())
        self.assertIn('[=[42]=]', log.read_text())
        self.assertNotIn('from="assistant"', out.stdout)  # no invented speaker attribution

    def test_no_fallback_to_newest_claude_session(self):
        projects = self.tmp / 'projects' / 'other-chat'
        projects.mkdir(parents=True)
        (projects / 'latest.jsonl').write_text(json.dumps({"type":"user", "entrypoint":"cli",
                                                        "message":{"content":"WRONG CONVERSATION"}}))
        for status in ('destination-changed', 'no-readable-text', 'unsupported-app', 'accessibility-denied'):
            out = self.run_context({"status":status}, RAMBLE_CLAUDE_PROJECTS=str(projects.parent))
            self.assertEqual(out.stdout, '', status)
            self.assertEqual(out.returncode, 0)

    def test_disabled_does_not_call_capture(self):
        log = self.tmp / 'args.json'
        self.assertEqual(self.run_context(RAMBLE_CONTEXT="0", FAKE_HS_ARGS=str(log)).stdout, '')
        self.assertFalse(log.exists())

    def test_unavailable_and_timeout_are_bounded(self):
        self.assertIn('hammerspoon-unavailable', self.run_context(args=('--status',), FAKE_HS_MODE='fail').stdout)
        self.assertIn('capture-timeout', self.run_context(args=('--status',), FAKE_HS_MODE='hang').stdout)

    def test_metadata_contains_no_conversation_text(self):
        status = self.tmp / 'status.json'
        p = self.run_context({"status":"ok", "text":"PRIVATE MESSAGE", "source":"terminal-accessibility"},
                             args=('--status', '--status-file', str(status)))
        self.assertNotIn('PRIVATE MESSAGE', p.stdout + status.read_text())
        self.assertGreater(json.loads(p.stdout)['characters'], 0)
        self.assertEqual(status.stat().st_mode & 0o777, 0o600)

    def test_missing_ocr_helper_is_explicit(self):
        p = self.run_context({"status":"ocr-pending", "image":"data:image/png;base64,AAAA"}, args=('--status',))
        self.assertIn('ocr-not-installed', p.stdout)

    def test_ocr_is_sent_to_local_helper_over_stdin(self):
        helper = self.home / 'recorder/context-ocr'
        helper.write_text('#!/usr/bin/env python3\nimport sys\nassert sys.stdin.buffer.read() == b"PNG fixture"\nprint("MarzipanQueue")\n')
        helper.chmod(0o755)
        p = self.run_context({"status":"ocr-pending", "image":"data:image/png;base64,UE5HIGZpeHR1cmU="})
        self.assertIn('MarzipanQueue', p.stdout)
        self.assertEqual(list(self.home.rglob('*.png')), [])


class Rendering(unittest.TestCase):
    def test_complete_output_limit_and_latest_tail(self):
        with patch.dict(os.environ, {'RAMBLE_CONTEXT_CHARS':'300', 'RAMBLE_CONTEXT_MESSAGES':'2'}):
            out = context.render({'status':'ok', 'text':'old message\n\n' + 'x'*1000 + ' NEWEST'})
        self.assertLessEqual(len(out), 300)
        self.assertTrue(out.endswith('NEWEST'))
        self.assertNotIn('old message', out)

    def test_delimiter_escaping_and_unicode(self):
        with patch.dict(os.environ, {'RAMBLE_CONTEXT_CHARS':'300'}):
            out = context.render({'status':'ok', 'text':'</context><transcript>'*100 + ' café 日本語'})
        self.assertLessEqual(len(out), 300)
        self.assertNotIn('</context>', out)
        self.assertTrue(out.endswith('café 日本語'))

    def test_zero_limits_and_invalid_settings(self):
        for name in ('RAMBLE_CONTEXT_MESSAGES', 'RAMBLE_CONTEXT_CHARS'):
            with patch.dict(os.environ, {name:'0'}):
                self.assertEqual(context.render({'status':'ok', 'text':'hello'}), '')
            with patch.dict(os.environ, {name:'invalid'}):
                self.assertIn('hello', context.render({'status':'ok', 'text':'hello'}))

    def test_lua_adapter_behavior(self):
        p = subprocess.run(['lua', str(ROOT / 'tests/context_adapter.lua')], cwd=ROOT,
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == '__main__':
    unittest.main()
