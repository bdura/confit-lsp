"""
TOML LSP Server with element validation and hover support.
"""

import logging
from typing import Optional

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

from confit_lsp.descriptor import Data, LineNumber
from confit_lsp.registry import REGISTRY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server = LanguageServer("config-lsp", "v0.1")


def find_key_positions(content: str, doc: tomlkit.TOMLDocument) -> list:
    """
    Find positions of 'factory' keys in the TOML document.
    Returns list of (line, col_start, col_end, value, path)
    """
    positions = []
    lines = content.split("\n")

    def visit_item(item, path="", section_line_offset=0):
        if isinstance(item, dict):
            for key, value in item.items():
                # Search for 'factory' key in current dict
                if key == "factory":
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

            if value not in REGISTRY:
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
                            message=f"Element '{value}' not found in the registry.",
                            severity=DiagnosticSeverity.Error,
                            source="confit-lsp",
                        )
                    )

    except Exception as e:
        logger.error(f"Error validating document: {e}")

    return diagnostics


@server.feature(INITIALIZE)
async def initialize(params: InitializeParams) -> None:
    """Initialize the server."""
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
    """Provide hover information for factories"""

    doc = ls.workspace.get_text_document(params.text_document.uri)
    data = Data.from_source(doc.source)

    if not doc.uri.endswith("config.toml"):
        return None

    try:
        cursor_line = params.position.line

        result = data.line2path.get(LineNumber(cursor_line))

        if result is None:
            return None

        path, key = result

        root = data.data

        for k in path.split("."):
            root = root[k]

        factory = root.get("factory")

        if factory is None:
            return None

        element = REGISTRY.get(factory)

        if element is None:
            return None

        if key == "factory":
            return Hover(
                contents=MarkupContent(
                    kind=MarkupKind.Markdown,
                    value=f"**Factory: {factory}**\n\n{element.docstring}\n\n"
                    + "\n".join(
                        (
                            f"- {field_name}\n"
                            for field_name in element.input_model.model_fields.keys()
                        )
                    ),
                )
            )

        field_info = element.input_model.model_fields.get(key)

        if field_info is None:
            return None

        return Hover(
            contents=MarkupContent(
                kind=MarkupKind.Markdown,
                value=f"**Field: {key}**\n\n{field_info.annotation}",
            )
        )

    except Exception as e:
        logger.error(f"Error in hover: {e}")

    return None


@server.feature(TEXT_DOCUMENT_DEFINITION)
async def definition(
    ls: LanguageServer, params: DefinitionParams
) -> Optional[Location]:
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

                if (
                    isinstance(value, str)
                    and (element := REGISTRY.get(value)) is not None
                ):
                    return element.location

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

        # Check if we're on an `element =` line
        if "element" in current_line and "=" in current_line:
            # Create completion items for all elements
            items = []
            for key, element in REGISTRY.items():
                items.append(
                    CompletionItem(
                        label=key,
                        kind=CompletionItemKind.Value,
                        detail=element.docstring[:50] + "..."
                        if len(element.docstring) > 50
                        else element.docstring,
                        documentation=MarkupContent(
                            kind=MarkupKind.Markdown,
                            value=f"**{key}**\n\n{element.docstring}",
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
