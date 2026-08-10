## MODIFIED Requirements

### Requirement: Model Selection

The adapter SHALL pass the resolved catalog model identifier verbatim via the
`--model` CLI flag before the prompt. Identifier syntax is runtime-provider
specific, not globally required to use `provider/model`: an OpenCode Go
profile receives its provider-native bare model ID (for example,
`minimax-m2.7`), while an OpenCode provider that defines a qualified form
receives that qualified form unchanged. Model catalog validation owns rejection
of known invalid forms before invocation.

ID: REQ-runtime-opencode-001
Source: runtime-opencode Model Selection; model-catalog REQ-model-catalog-002; design.md Decision 2
Scope: v1-mandatory

#### Scenario: Provider-native OpenCode Go model passed via flag

- **WHEN** an OpenCode Go model string `minimax-m2.7` is provided to
  `invoke()`
- **THEN** the command includes `--model minimax-m2.7` before the prompt
- **AND** the adapter does not prepend `opencode-go/`

#### Scenario: Qualified provider model is preserved

- **WHEN** a valid qualified OpenCode provider model string such as
  `anthropic/claude-sonnet-4-5` is provided to `invoke()`
- **THEN** the command includes that exact string after `--model`
- **AND** the adapter does not strip or rewrite its provider segment

#### Scenario: No model specified

- **WHEN** no model is provided
- **THEN** the `--model` flag is omitted and OpenCode uses its configured
  default
