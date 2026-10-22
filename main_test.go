package main

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"github.com/rhun-editor/extension-protocol/go/rhunext"
)

func TestTestAt(t *testing.T) {
	src := "package x\n\nimport \"testing\"\n\nfunc TestAdd(t *testing.T) {\n\tif 1 != 1 {\n\t}\n}\n\nfunc helper() {\n}\n"
	for _, c := range []struct {
		line int
		want string
	}{{5, "TestAdd"}, {6, "TestAdd"}, {8, "TestAdd"}, {10, ""}, {11, ""}, {2, ""}} {
		if got := testAt(src, c.line); got != c.want {
			t.Errorf("line %d: %q, want %q", c.line, got, c.want)
		}
	}
}

func TestResolveGo(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "go.mod"), []byte("module x\n"), 0o644)
	os.MkdirAll(filepath.Join(dir, "cmd", "app"), 0o755)
	d := &debug{project: filepath.ToSlash(dir)} // the paths as rhun writes them (C:/... on Windows)
	var c rhunext.DebugConfig
	c.Set("type", rhunext.DebugStr("go"))
	out, err := d.resolveGo(nil, rhunext.DebugResolveRequest{Type: "go", Request: "launch", Config: c,
		Path: filepath.ToSlash(filepath.Join(dir, "a_test.go"))})
	if err != nil || out.String("program") != filepath.ToSlash(dir) || out.String("mode") != "test" {
		t.Fatalf("%v %v", out, err)
	}
	// a package below the module's folder: go.mod is found above it
	out, err = d.resolveGo(nil, rhunext.DebugResolveRequest{Type: "go", Request: "launch", Config: c,
		Path: filepath.ToSlash(filepath.Join(dir, "cmd", "app", "main.go"))})
	if err != nil || out.String("program") != filepath.ToSlash(filepath.Join(dir, "cmd", "app")) || out.String("mode") != "debug" {
		t.Fatalf("%v %v", out, err)
	}
	c.Set("program", rhunext.DebugStr(t.TempDir()))
	if _, err := (&debug{}).resolveGo(nil, rhunext.DebugResolveRequest{Type: "go", Request: "launch", Config: c}); err == nil {
		t.Fatal("outside a module")
	}
}

func TestResolvePython(t *testing.T) {
	dir := t.TempDir()
	py := filepath.Join(dir, ".venv", "bin", "python")
	if runtime.GOOS == "windows" {
		py = filepath.Join(dir, ".venv", "Scripts", "python.exe")
	}
	os.MkdirAll(filepath.Dir(py), 0o755)
	os.WriteFile(py, nil, 0o755)
	d := &debug{project: filepath.ToSlash(dir)}
	var c rhunext.DebugConfig
	c.Set("type", rhunext.DebugStr("python"))
	out, _ := d.resolvePython(rhunext.DebugResolveRequest{Config: c})
	if out.String("python") != filepath.ToSlash(py) || out.String("console") != "integratedTerminal" {
		t.Fatalf("%v", out)
	}
	c.Set("console", rhunext.DebugStr("internalConsole"))
	c.Set("python", rhunext.DebugStr("/x/python"))
	if out, _ := d.resolvePython(rhunext.DebugResolveRequest{Config: c}); out != nil {
		t.Fatalf("unchanged: %v", out)
	}
}
