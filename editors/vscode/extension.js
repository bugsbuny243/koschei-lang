'use strict';

const cp = require('child_process');
const vscode = require('vscode');

/** @param {vscode.ExtensionContext} context */
function activate(context) {
  const diagnostics = vscode.languages.createDiagnosticCollection('koschei');
  context.subscriptions.push(diagnostics);

  const checkDocument = async (document) => {
    if (!document || document.languageId !== 'koschei' || document.isUntitled) {
      return;
    }

    const configuration = vscode.workspace.getConfiguration('koschei');
    const executable = configuration.get('executable', 'ks');
    const language = configuration.get('language', 'en');
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
    const cwd = workspaceFolder ? workspaceFolder.uri.fsPath : document.uri.fsPath;

    cp.execFile(
      executable,
      ['--lang', language, 'check', '--json', document.uri.fsPath],
      { cwd },
      (error, stdout, stderr) => {
        const text = String(stdout || '').trim();
        if (!error) {
          diagnostics.delete(document.uri);
          return;
        }

        let payload;
        try {
          payload = JSON.parse(text);
        } catch (_parseError) {
          const fallback = String(stderr || error.message || 'Koschei check failed').trim();
          const diagnostic = new vscode.Diagnostic(
            new vscode.Range(0, 0, 0, 1),
            fallback,
            vscode.DiagnosticSeverity.Error,
          );
          diagnostic.source = 'koschei';
          diagnostics.set(document.uri, [diagnostic]);
          return;
        }

        const line = Math.max(0, Number(payload.line || 1) - 1);
        const column = Math.max(0, Number(payload.column || 1) - 1);
        const range = new vscode.Range(line, column, line, column + 1);
        const message = payload.code
          ? `${payload.code}: ${payload.message}`
          : String(payload.message || payload.title || 'Koschei check failed');
        const diagnostic = new vscode.Diagnostic(
          range,
          message,
          vscode.DiagnosticSeverity.Error,
        );
        diagnostic.code = payload.code || undefined;
        diagnostic.source = 'koschei';
        diagnostics.set(document.uri, [diagnostic]);
      },
    );
  };

  context.subscriptions.push(
    vscode.commands.registerCommand('koschei.checkFile', () => {
      const editor = vscode.window.activeTextEditor;
      if (editor) {
        checkDocument(editor.document);
      }
    }),
  );

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((document) => {
      const enabled = vscode.workspace
        .getConfiguration('koschei')
        .get('checkOnSave', true);
      if (enabled) {
        checkDocument(document);
      }
    }),
  );

  if (vscode.window.activeTextEditor) {
    checkDocument(vscode.window.activeTextEditor.document);
  }
}

function deactivate() {}

module.exports = { activate, deactivate };
