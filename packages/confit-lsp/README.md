# `confit-lsp`, an LSP for `confit-lite`

## Quickstart

First off, you need to add `confit-lsp` to your development dependencies:

```shell
uv add --group dev git+ssh://git@github.com/bdura/confit-lite.git#subdirectory=packages/confit-lsp
```

Then, you'll need to add the LSP to your IDE.

### IDE configuration

We provide a basic [VSCode extension].

#### Neovim

```lua
vim.lsp.config['confit-lsp'] = {
  cmd = { 'confit-lsp' },
  filetypes = { 'toml' },
  root_markers = { { 'pyproject.toml' }, '.git' },
}
```

#### Helix

```toml
[language-server.confit-lsp]
command = "confit-lsp"

[[language]]
name = "confit"
scope = "text.toml"
injection-regex = "toml"
file-types = ["toml"]
comment-tokens = "#"
indent = { tab-width = 2, unit = "  " }
language-servers = ["confit-lsp"]
```

[VSCode extension]: ./../../clients/vscode/
