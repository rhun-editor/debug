module github.com/rhun-editor/debug

go 1.25

require github.com/rhun-editor/extension-protocol v1.3.0

// the debug feature is on the SDK's parity-debugger branch until it is released
replace github.com/rhun-editor/extension-protocol => /private/tmp/claude-501/-Users-vsh-code-rhun/c1a902c3-537f-4e49-825c-34c002b7817a/scratchpad/impl/debugger/sdk
