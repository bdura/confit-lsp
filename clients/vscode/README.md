# confit-lsp

Minimal LSP for [Confit].

## Quickstart

You'll need to install [`vsce`] to compile the extension using:

```shell
cd clients/vscode
vsce package
```

Then, install the extension from the `VSIX` artifact. From the VSCode
Extensions panel: Settings > Install from VSIX.

Open `config.toml`, you should get diagnostics.

Note that the LSP requires `confit-lsp` to be installed:

```shell
uv sync --all-extras
```

[Confit]: https://aphp.github.io/confit/latest/
[`vsce`]: https://code.visualstudio.com/api/working-with-extensions/publishing-extension
