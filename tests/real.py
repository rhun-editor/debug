#!/usr/bin/env python3
"""The extension in rhun for real, headless: Delve on a Go test at the cursor after a prelaunch
build task (launch.ini's before), debugpy in the project's virtual environment with the program
in rhun's terminal, and lldb-dap on a C program. usage: tests/real.py RHUN

Each workflow is skipped with the reason when its tool is missing: dlv (on PATH or RHUN_TEST_DLV),
a python with debugpy in RHUN_TEST_PYTHON (linked as the project's .venv), cc and lldb-dap."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RHUN = Path(sys.argv.pop(1) if len(sys.argv) > 1 else shutil.which('rhun') or 'rhun').resolve()
TARGET = {'darwin': 'macos-arm64', 'linux': 'linux-x86_64'}.get(sys.platform, 'windows-x64')
CONFIG = ('[ui]\nsidebar = false\nagents_panel = false\n[editor]\ncursor_blink = false\n'
          '[files]\nrestore_session = false\nrestore_project = false\n[updates]\ncheck = false\n'
          '[git]\nenabled = false\n')

TASKS = r'''import sys
out, inp = sys.stdout.buffer, sys.stdin.buffer
cmd = b'go vet ./... && echo vetted > vetted.txt'
task = b'build shell 5 %d 0 0\nBuild' % len(cmd) + cmd
out.write(b'hello 1 terminals tasks\n'); out.flush()
for line in inp:
    if line.startswith(b'0 ready '):
        body = b'1\n' + task
        out.write(b'1 tasks-set %d\n' % len(body) + body); out.flush()
    if line.startswith(b'0 bye'):
        break
'''


def tool_dlv():
    p = os.environ.get('RHUN_TEST_DLV') or shutil.which('dlv')
    return p if p and shutil.which('go') else None


def tool_python():
    p = os.environ.get('RHUN_TEST_PYTHON', 'python3')
    ok = subprocess.run([p, '-c', 'import debugpy'], capture_output=True).returncode == 0
    return shutil.which(p) if ok else None


def tool_lldb():
    if sys.platform == 'darwin':
        r = subprocess.run(['xcrun', '-f', 'lldb-dap'], capture_output=True, text=True)
        return r.returncode == 0 and shutil.which('cc')
    return shutil.which('lldb-dap') and shutil.which('cc')


class Real(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='rhun-debug-ext-')
        cls.exts = Path(cls.tmp.name) / 'exts'
        ext = cls.exts / 'rhun-editor/debug'
        (ext / 'bin').mkdir(parents=True)
        exe = 'debug-' + TARGET + ('.exe' if TARGET.startswith('windows') else '')
        subprocess.run(['go', 'build', '-o', str(ext / 'bin' / exe), '.'], cwd=ROOT, check=True,
                       env=dict(os.environ, CGO_ENABLED='0'))
        shutil.copy(ROOT / 'extension.ini', ext)
        shutil.copytree(ROOT / 'debug', ext / 'debug')
        driver = cls.exts / 't/tasks'
        driver.mkdir(parents=True)
        (driver / 'extension.ini').write_text('name = tasks\nowner = t\ntitle = Tasks\nversion = 1\nprotocol = 1\n'
                                              'runtime = python3\nrun = main.py\non = startup\n'
                                              '[needs]\nterminal = run\n', encoding='utf-8')
        (driver / 'main.py').write_text(TASKS, encoding='utf-8')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix='w-', dir=self.tmp.name)).resolve()
        self.proj = self.work / 'proj'
        (self.proj / '.rhun').mkdir(parents=True)
        (self.work / 'config/rhun').mkdir(parents=True)
        (self.work / 'config/rhun/config').write_text(CONFIG, encoding='utf-8')
        self.env = dict(os.environ, HOME=str(self.work), XDG_CONFIG_HOME=str(self.work / 'config'),
                        XDG_STATE_HOME=str(self.work / 'state'), XDG_DATA_HOME=str(self.work / 'data'))

    def run_rhun(self, files, actions, timeout=240):
        script = self.work / 'actions.rsc'
        opens = ['open ' + str(self.proj / f) for f in files]
        script.write_text('\n'.join(['wait 100', *opens, *actions, 'quit']) + '\n', encoding='utf-8')
        r = subprocess.run([str(RHUN), str(self.proj), '--headless', '1000x600', '--scale', '1', '--extensions',
                            str(self.exts), '--script', str(script)], env=self.env, capture_output=True,
                           timeout=timeout)
        self.assertEqual(r.returncode, 0, r.stderr.decode(errors='replace'))
        return r.stdout.decode(errors='replace').splitlines()

    def field(self, line, name):
        for part in line.split(' '):
            if part.startswith(name + '='):
                return part[len(name) + 1:]
        return None

    def sessions(self, out):
        return [l for l in out if l.startswith('session=')]

    @unittest.skipUnless(tool_dlv(), 'needs go and dlv')
    def test_go_test_at_cursor_after_a_build_task(self):
        dlv = Path(tool_dlv())
        cache = Path(tempfile.gettempdir()) / 'rhun-test-go'
        self.env.update(PATH=str(dlv.parent) + os.pathsep + self.env['PATH'], GOCACHE=str(cache / 'cache'),
                        GOPATH=str(cache / 'path'), GOFLAGS='-p=2')
        (self.proj / 'go.mod').write_text('module example.com/calc\n\ngo 1.21\n')
        (self.proj / 'calc.go').write_text('package calc\n\nfunc Add(a, b int) int {\n\ts := a + b\n\treturn s\n}\n')
        (self.proj / 'calc_test.go').write_text(
            'package calc\n\nimport "testing"\n\nfunc TestAdd(t *testing.T) {\n\tif Add(1, 2) != 3 {\n'
            '\t\tt.Fatal("add")\n\t}\n}\n\nfunc TestOther(t *testing.T) {\n\tt.Log("other")\n}\n')
        (self.proj / '.rhun/launch.ini').write_text(
            '[Test at cursor]\ntype = go\nmode = test\nprogram = ${fileDir}\ntestAtCursor = yes\n'
            'args = -test.v\nbefore = build\n')
        out = self.run_rhun(['calc_test.go'], [
            'wait 300', 'key ctrl+g', 'type 6', 'key Return', 'bp %s 4' % (self.proj / 'calc.go'),
            'debug-start Test at cursor', 'wait 800', 'print-dialog', 'dialog yes',     # the task provider
            'wait 8000', 'print-dialog', 'dialog yes',                                   # the Debug extension
            'wait-debug paused 120000', 'print-debug', 'print-stack', 'print-vars', 'bp-clear', 'debug-continue',
            'wait-debug ended 60000', 'print-debug', 'print-console'])
        dialogs = [l for l in out if l.startswith('dialog=')]
        self.assertEqual(dialogs, ['dialog=Let Tasks run programs in proj?', 'dialog=Let Debug run programs in proj?'], out)
        self.assertEqual((self.proj / 'vetted.txt').read_text().strip(), 'vetted')
        s = self.sessions(out)
        self.assertTrue(self.field(s[0], 'at').endswith('calc.go:4'), out)
        self.assertTrue(any(l.startswith('  frame 1 ') and 'TestAdd' in l for l in out), out)
        self.assertIn('  a = 1 : int', out)
        self.assertEqual(self.field(s[1], 'exit'), '0', out)
        self.assertTrue(any('--- PASS: TestAdd' in l for l in out), out)
        self.assertFalse(any('TestOther' in l for l in out), out)

    @unittest.skipUnless(tool_dlv(), 'needs go and dlv')
    def test_go_outside_a_module_is_refused(self):
        (self.proj / 'main.go').write_text('package main\n\nfunc main() {}\n')
        (self.proj / '.rhun/launch.ini').write_text('[Launch package]\ntype = go\nprogram = ${fileDir}\n')
        out = self.run_rhun(['main.go'], ['wait 300', 'debug-start Launch package', 'wait 3000', 'print-console'])
        self.assertTrue(any(l.startswith('error no Go module (go.mod) in ') for l in out), out)

    @unittest.skipUnless(tool_python(), 'needs a python with debugpy (RHUN_TEST_PYTHON)')
    def test_python_in_the_project_venv_and_the_terminal(self):
        venv = self.proj / '.venv/bin'
        venv.mkdir(parents=True)
        (venv / 'python').symlink_to(tool_python())
        (self.proj / 'ask.py').write_text("import sys\nname = input('name? ')\nprint('hello', name, sys.executable)\n")
        (self.proj / '.rhun/launch.ini').write_text('[Current file]\ntype = python\nprogram = ${file}\n')
        out = self.run_rhun(['ask.py'], ['wait 300', 'debug-start Current file', 'wait 3000', 'dialog yes',
                                         'wait-term name?', 'type rhun', 'key Return', 'wait-term hello rhun',
                                         'wait-debug ended 30000', 'print-term', 'print-debug'])
        self.assertTrue(any('hello rhun' in l for l in out), out)
        self.assertTrue(any(str(venv / 'python') in l for l in ''.join(out).split('hello rhun ')[1:]), out)
        self.assertEqual(self.field(self.sessions(out)[0], 'exit'), '0', out)

    @unittest.skipUnless(tool_lldb(), 'needs cc and lldb-dap')
    def test_c_program(self):
        (self.proj / 'hello.c').write_text('#include <stdio.h>\nint add(int a, int b) {\n    int s = a + b;\n'
                                           '    return s;\n}\nint main(void) {\n    printf("%d\\n", add(1, 2));\n'
                                           '    return 3;\n}\n')
        subprocess.run(['cc', '-g', '-O0', '-o', str(self.proj / 'hello'), str(self.proj / 'hello.c')], check=True)
        (self.proj / '.rhun/launch.ini').write_text((ROOT / 'debug/c.ini').read_text())
        out = self.run_rhun(['hello.c'], ['wait 300', 'bp %s 3' % (self.proj / 'hello.c'), 'debug-start Launch program',
                                          'dialog yes', 'wait-debug paused 60000', 'print-debug', 'print-vars',
                                          'bp-clear', 'debug-continue', 'wait-debug ended 30000', 'print-debug'])
        s = self.sessions(out)
        self.assertTrue(self.field(s[0], 'at').endswith('hello.c:3'), out)
        self.assertIn('  a = 1 : int', out)
        self.assertEqual(self.field(s[1], 'exit'), '3', out)


if __name__ == '__main__':
    unittest.main()
