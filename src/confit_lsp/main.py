"""
TOML LSP Server with element validation and hover support.
"""

import logging
from pathlib import Path
from typing import Optional, Dict

import tomlkit
from pygls.lsp.server import LanguageServer
from lsprotocol.types import (
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_DID_CHANGE,
    INITIALIZE,
    TEXT_DOCUMENT_HOVER,
    TEXT_DOCUMENT_DEFINITION,
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    CompletionParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    DidChangeTextDocumentParams,
    Diagnostic,
    DiagnosticSeverity,
    InsertTextFormat,
    Position,
    PublishDiagnosticsParams,
    Range,
    Hover,
    MarkupContent,
    MarkupKind,
    Location,
    HoverParams,
    DefinitionParams,
    InitializeParams,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server = LanguageServer("config-lsp", "v0.1")


class ElementsStore:
    """Store and manage elements from elements.toml"""

    def __init__(self):
        self.elements: Dict[str, str] = {}
        self.elements_file_path: Optional[Path] = None

    def load_elements(self, workspace_root: Path):
        """Load elements from elements.toml"""
        elements_path = workspace_root / "elements.toml"

        if not elements_path.exists():
            logger.warning(f"elements.toml not found at {elements_path}")
            self.elements = {}
            return

        try:
            with elements_path.open("r") as f:
                doc = tomlkit.load(f)

            self.elements = {}
            for key, value in doc.items():
                if isinstance(value, str):
                    self.elements[key] = value

            self.elements_file_path = elements_path
            logger.info(f"Loaded {len(self.elements)} elements from elements.toml")
        except Exception as e:
            logger.error(f"Error loading elements.toml: {e}")
            self.elements = {}

    def get_element(self, key: str) -> Optional[str]:
        """Get element description by key"""
        return self.elements.get(key)

    def has_element(self, key: str) -> bool:
        """Check if element exists"""
        return key in self.elements


elements_store = ElementsStore()


def find_key_positions(content: str, doc: tomlkit.TOMLDocument) -> list:
    """
    Find positions of 'element' keys in the TOML document.
    Returns list of (line, col_start, col_end, value, path)
    """
    positions = []
    lines = content.split("\n")

    def visit_item(item, path="", section_line_offset=0):
        if isinstance(item, dict):
            for key, value in item.items():
                # Search for 'element' key in current dict
                if key == "element":
                    # Find the line containing this key
                    search_prefix = f"{path}." if path else ""
                    key_pattern = f"{key} ="

                    for line_idx, line in enumerate(lines):
                        if key_pattern in line:
                            col_start = line.find(key)
                            if col_start != -1:
                                col_end = col_start + len(key)
                                positions.append(
                                    {
                                        "line": line_idx,
                                        "col_start": col_start,
                                        "col_end": col_end,
                                        "value": value,
                                        "path": f"{path}.{key}" if path else key,
                                    }
                                )
                                break

                # Recursively visit nested structures
                new_path = f"{path}.{key}" if path else key
                visit_item(value, new_path)

    visit_item(doc)
    return positions


def validate_config(uri: str, content: str) -> list[Diagnostic]:
    """Validate config.toml and return diagnostics"""
    diagnostics = []

    try:
        doc = tomlkit.parse(content)
        positions = find_key_positions(content, doc)

        for pos in positions:
            value = pos["value"]
            line = pos["line"]
            col_start = pos["col_start"]
            col_end = pos["col_end"]

            # Check if value is a string
            if not isinstance(value, str):
                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=line, character=col_start),
                            end=Position(line=line, character=col_end),
                        ),
                        message=f"Element value must be a string, got {type(value).__name__}",
                        severity=DiagnosticSeverity.Error,
                        source="toml-lsp",
                    )
                )
                continue

            # Check if element exists in elements.toml
            if not elements_store.has_element(value):
                # Find the value position for better error highlighting
                lines = content.split("\n")
                value_line = lines[line]
                value_start = value_line.find(f'"{value}"')
                if value_start == -1:
                    value_start = value_line.find(f"'{value}'")

                if value_start != -1:
                    value_end = value_start + len(value) + 2  # Include quotes
                    diagnostics.append(
                        Diagnostic(
                            range=Range(
                                start=Position(line=line, character=value_start),
                                end=Position(line=line, character=value_end),
                            ),
                            message=f"Element '{value}' not found in elements.toml",
                            severity=DiagnosticSeverity.Error,
                            source="toml-lsp",
                        )
                    )

    except Exception as e:
        logger.error(f"Error validating document: {e}")

    return diagnostics


@server.feature(INITIALIZE)
async def initialize(params: InitializeParams):
    """Initialize the server and load elements.toml"""
    if params.root_uri:
        workspace_root = Path(params.root_uri.replace("file://", ""))
        elements_store.load_elements(workspace_root)
    return


@server.feature(TEXT_DOCUMENT_DID_OPEN)
async def did_open(ls: LanguageServer, params: DidOpenTextDocumentParams):
    """Handle document open event"""
    doc = ls.workspace.get_text_document(params.text_document.uri)

    if doc.uri.endswith("config.toml"):
        diagnostics = validate_config(doc.uri, doc.source)
        payload = PublishDiagnosticsParams(
            uri=doc.uri,
            diagnostics=diagnostics,
        )
        ls.text_document_publish_diagnostics(payload)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
async def did_save(ls: LanguageServer, params: DidSaveTextDocumentParams):
    """Handle document save event"""
    doc = ls.workspace.get_text_document(params.text_document.uri)

    # Reload elements if elements.toml was saved
    if doc.uri.endswith("elements.toml"):
        if ls.workspace.root_path:
            elements_store.load_elements(Path(ls.workspace.root_path))

    # Validate config.toml
    if doc.uri.endswith("config.toml"):
        diagnostics = validate_config(doc.uri, doc.source)
        payload = PublishDiagnosticsParams(
            uri=doc.uri,
            diagnostics=diagnostics,
        )
        ls.text_document_publish_diagnostics(payload)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
async def did_change(ls: LanguageServer, params: DidChangeTextDocumentParams):
    """Handle document change event"""
    doc = ls.workspace.get_text_document(params.text_document.uri)

    if doc.uri.endswith("config.toml"):
        diagnostics = validate_config(doc.uri, doc.source)
        payload = PublishDiagnosticsParams(
            uri=doc.uri,
            diagnostics=diagnostics,
        )
        ls.text_document_publish_diagnostics(payload)


@server.feature(TEXT_DOCUMENT_HOVER)
async def hover(ls: LanguageServer, params: HoverParams) -> Optional[Hover]:
    """Provide hover information for element values"""
    doc = ls.workspace.get_text_document(params.text_document.uri)

    if not doc.uri.endswith("config.toml"):
        return None

    try:
        toml_doc = tomlkit.parse(doc.source)
        positions = find_key_positions(doc.source, toml_doc)

        # Find if cursor is on an element key or value
        cursor_line = params.position.line
        cursor_char = params.position.character

        for pos in positions:
            if pos["line"] == cursor_line:
                value = pos["value"]

                # Check if hovering over the key or value
                if isinstance(value, str) and elements_store.has_element(value):
                    description = elements_store.get_element(value)
                    return Hover(
                        contents=MarkupContent(
                            kind=MarkupKind.Markdown,
                            value=f"**Element: {value}**\n\n{description}",
                        )
                    )

    except Exception as e:
        logger.error(f"Error in hover: {e}")

    return None


@server.feature(TEXT_DOCUMENT_DEFINITION)
async def definition(
    ls: LanguageServer, params: DefinitionParams
) -> Optional[Location]:
    """Go to definition in elements.toml"""
    doc = ls.workspace.get_text_document(params.text_document.uri)

    if not doc.uri.endswith("config.toml"):
        return None

    try:
        toml_doc = tomlkit.parse(doc.source)
        positions = find_key_positions(doc.source, toml_doc)

        cursor_line = params.position.line

        for pos in positions:
            if pos["line"] == cursor_line:
                value = pos["value"]

                if isinstance(value, str) and elements_store.has_element(value):
                    if elements_store.elements_file_path:
                        # Read elements.toml to find the line
                        with elements_store.elements_file_path.open("r") as f:
                            for idx, line in enumerate(f):
                                if line.strip().startswith(f"{value} ="):
                                    return Location(
                                        uri=elements_store.elements_file_path.as_uri(),
                                        range=Range(
                                            start=Position(line=idx, character=0),
                                            end=Position(line=idx, character=len(line)),
                                        ),
                                    )

    except Exception as e:
        logger.error(f"Error in definition: {e}")

    return None


@server.feature(TEXT_DOCUMENT_COMPLETION)
async def completion(
    ls: LanguageServer,
    params: CompletionParams,
) -> Optional[CompletionList]:
    """Provide auto-completion for element values"""
    doc = ls.workspace.get_text_document(params.text_document.uri)

    if not doc.uri.endswith("config.toml"):
        return None

    try:
        lines = doc.source.split("\n")
        cursor_line = params.position.line

        if cursor_line >= len(lines):
            return None

        current_line = lines[cursor_line]

        # Check if we're on an element = line
        if "element" in current_line and "=" in current_line:
            # Create completion items for all elements
            items = []
            for key, description in elements_store.elements.items():
                items.append(
                    CompletionItem(
                        label=key,
                        kind=CompletionItemKind.Value,
                        detail=description[:50] + "..."
                        if len(description) > 50
                        else description,
                        documentation=MarkupContent(
                            kind=MarkupKind.Markdown,
                            value=f"**{key}**\n\n{description}",
                        ),
                        insert_text=f'"{key}"',
                        insert_text_format=InsertTextFormat.PlainText,
                    )
                )

            return CompletionList(is_incomplete=False, items=items)

    except Exception as e:
        logger.error(f"Error in completion: {e}")

    return None


def run():
    server.start_io()


if __name__ == "__main__":
    run()
