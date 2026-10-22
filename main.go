// The Debug extension for rhun: it declares Delve, debugpy and lldb-dap as debuggers (extension.ini)
// and prepares Go and Python launches before rhun starts the adapter (feature debug, debug-resolve).
package main

import (
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"

	"github.com/rhun-editor/extension-protocol/go/rhunext"
)

type debug struct {
	project string
}

func (d *debug) Ready(ext *rhunext.Ext, project string) { d.project = project }

func (d *debug) Run(ext *rhunext.Ext, command string, doc rhunext.Doc) {
	switch command {
	case "debug.install_delve":
		ext.Term("go install github.com/go-delve/delve/cmd/dlv@latest")
	case "debug.install_debugpy":
		ext.Term(d.python("") + " -m pip install debugpy")
	}
}

func (d *debug) Event(ext *rhunext.Ext, ev rhunext.Event) {}

// ResolveDebug fills in a Go or Python configuration (C needs nothing).
func (d *debug) ResolveDebug(ext *rhunext.Ext, req rhunext.DebugResolveRequest) (rhunext.DebugConfig, error) {
	switch req.Type {
	case "go":
		return d.resolveGo(ext, req)
	case "python":
		return d.resolvePython(req)
	}
	return nil, nil
}

// resolveGo: the active file's package when there is no program, test mode for a _test.go file,
// "Test at cursor" (testAtCursor = yes) as -test.run ^TestXxx$, and a clear refusal outside a module.
func (d *debug) resolveGo(ext *rhunext.Ext, req rhunext.DebugResolveRequest) (rhunext.DebugConfig, error) {
	c := append(rhunext.DebugConfig(nil), req.Config...)
	program := c.String("program")
	if program == "" {
		switch {
		case req.Path != "":
			program = wire(filepath.Dir(req.Path))
		case d.project != "":
			program = d.project
		default:
			return nil, errors.New("no program: open a Go file or set program in launch.ini")
		}
		c.Set("program", rhunext.DebugStr(program))
	}
	dir := program
	if strings.HasSuffix(program, ".go") {
		dir = filepath.Dir(program)
	}
	if req.Request == "launch" && !d.inModule(dir) {
		return nil, errors.New("no Go module (go.mod) in " + wire(dir) + " or above it")
	}
	if c.String("mode") == "" {
		mode := "debug"
		if strings.HasSuffix(req.Path, "_test.go") {
			mode = "test"
		}
		c.Set("mode", rhunext.DebugStr(mode))
	}
	if v, ok := c.Get("testAtCursor"); ok {
		c.Remove("testAtCursor")
		if (v.Kind == rhunext.DebugString && (v.S == "yes" || v.S == "true")) || (v.Kind == rhunext.DebugBool && v.B) {
			if req.Doc == 0 {
				return nil, errors.New("Test at cursor needs a Go test file open")
			}
			text, _, err := ext.TextContext(req.Context, req.Doc)
			if err != nil {
				return nil, err
			}
			name := testAt(string(text), req.At.Line)
			if name == "" {
				return nil, errors.New("the cursor is not in a test function (func TestXxx)")
			}
			c.Set("mode", rhunext.DebugStr("test"))
			c.SetList("args", append(c.List("args"), "-test.run", "^"+name+"$"))
		}
	}
	return c, nil
}

var testFunc = regexp.MustCompile(`^func\s+(Test[A-Za-z0-9_]*)\s*\(`)

// testAt finds the test function the line (1-based) is in: the nearest func TestXxx( at or above it
func testAt(text string, line int) string {
	lines := strings.Split(text, "\n")
	if line > len(lines) {
		line = len(lines)
	}
	for i := line - 1; i >= 0; i-- {
		if m := testFunc.FindStringSubmatch(lines[i]); m != nil {
			return m[1]
		}
		if strings.HasPrefix(lines[i], "func ") {
			return ""
		}
	}
	return ""
}

// inModule: a go.mod in dir or a folder above it, up to the project's root (both cleaned: rhun's
// C:/w/app is C:\w\app like the folders filepath.Dir gives on Windows)
func (d *debug) inModule(dir string) bool {
	dir = filepath.Clean(dir)
	project := ""
	if d.project != "" {
		project = filepath.Clean(d.project)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			return true
		}
		up := filepath.Dir(dir)
		if up == dir || (project != "" && !strings.HasPrefix(up, project)) {
			return false
		}
		dir = up
	}
}

// resolvePython: the project's virtual environment when python is not set, and the program in the
// terminal (it reads input there) when console is not set
func (d *debug) resolvePython(req rhunext.DebugResolveRequest) (rhunext.DebugConfig, error) {
	c := append(rhunext.DebugConfig(nil), req.Config...)
	changed := false
	if c.String("python") == "" {
		if p := d.python(""); p != "python3" {
			c.Set("python", rhunext.DebugStr(p))
			changed = true
		}
	}
	if _, ok := c.Get("console"); !ok {
		c.Set("console", rhunext.DebugStr("integratedTerminal"))
		changed = true
	}
	if !changed {
		return nil, nil
	}
	return c, nil
}

// python: the project's .venv or venv interpreter, else python3
func (d *debug) python(fallback string) string {
	if d.project != "" {
		rel := filepath.Join("bin", "python")
		if runtime.GOOS == "windows" {
			rel = filepath.Join("Scripts", "python.exe")
		}
		for _, env := range []string{".venv", "venv"} {
			p := filepath.Join(d.project, env, rel)
			if _, err := os.Stat(p); err == nil {
				return wire(p)
			}
		}
	}
	if fallback != "" {
		return fallback
	}
	return "python3"
}

// wire is a path as rhun writes and expects it: forward slashes on Windows too (C:/w/app). The
// paths the extension puts in a configuration go through it; the paths rhun sends are used as given.
func wire(p string) string {
	return filepath.ToSlash(p)
}

func main() {
	if err := rhunext.RunWith([]string{rhunext.FeatureDebug}, &debug{}); err != nil {
		os.Exit(1)
	}
}
