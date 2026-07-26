'use strict';

const cp = require('child_process');
const vscode = require('vscode');

class KoscheiClient {
  constructor(context, diagnostics) {
    this.context = context;
    this.diagnostics = diagnostics;
    this.nextId = 1;
    this.pending = new Map();
    this.buffer = Buffer.alloc(0);
    this.disposables = [];
    this.process = null;
  }

  async start() {
    const config = vscode.workspace.getConfiguration('koschei.server');
    const command = config.get('command', 'ks-lsp');
    const args = config.get('args', []);

    this.process = cp.spawn(command, args, {
      cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true
    });

    this.process.stdout.on('data', chunk => this.onData(chunk));
    this.process.stderr.on('data', chunk => {
      const text = chunk.toString('utf8').trim();
      if (text) console.error(`[Koschei LSP] ${text}`);
    });
    this.process.on('error', error => {
      vscode.window.showErrorMessage(`Koschei LSP başlatılamadı: ${error.message}`);
      this.rejectAll(error);
    });
    this.process.on('exit', code => {
      if (code !== 0 && code !== null) {
        vscode.window.showWarningMessage(`Koschei LSP kapandı (kod ${code}).`);
      }
      this.rejectAll(new Error('Koschei LSP kapandı.'));
    });

    await this.request('initialize', {
      processId: process.pid,
      rootUri: vscode.workspace.workspaceFolders?.[0]?.uri.toString() ?? null,
      capabilities: {}
    });
    this.notify('initialized', {});

    for (const document of vscode.workspace.textDocuments) {
      if (document.languageId === 'koschei') this.open(document);
    }

    this.disposables.push(
      vscode.workspace.onDidOpenTextDocument(document => {
        if (document.languageId === 'koschei') this.open(document);
      }),
      vscode.workspace.onDidChangeTextDocument(event => {
        if (event.document.languageId === 'koschei') this.change(event.document);
      }),
      vscode.workspace.onDidCloseTextDocument(document => {
        if (document.languageId === 'koschei') this.close(document);
      }),
      vscode.languages.registerDocumentFormattingEditProvider('koschei', {
        provideDocumentFormattingEdits: async document => {
          const edits = await this.request('textDocument/formatting', {
            textDocument: {uri: document.uri.toString()},
            options: {tabSize: 4, insertSpaces: true}
          });
          return (edits || []).map(edit => new vscode.TextEdit(
            this.range(edit.range),
            edit.newText
          ));
        }
      }),
      vscode.languages.registerHoverProvider('koschei', {
        provideHover: async (document, position) => {
          const result = await this.request('textDocument/hover', {
            textDocument: {uri: document.uri.toString()},
            position: {line: position.line, character: position.character}
          });
          if (!result?.contents) return null;
          const value = typeof result.contents === 'string'
            ? result.contents
            : result.contents.value;
          return new vscode.Hover(new vscode.MarkdownString(value));
        }
      }),
      vscode.languages.registerDefinitionProvider('koschei', {
        provideDefinition: async (document, position) => {
          const result = await this.request('textDocument/definition', {
            textDocument: {uri: document.uri.toString()},
            position: {line: position.line, character: position.character}
          });
          if (!result) return null;
          return new vscode.Location(vscode.Uri.parse(result.uri), this.range(result.range));
        }
      }),
      vscode.languages.registerDocumentSymbolProvider('koschei', {
        provideDocumentSymbols: async document => {
          const result = await this.request('textDocument/documentSymbol', {
            textDocument: {uri: document.uri.toString()}
          });
          return (result || []).map(item => new vscode.DocumentSymbol(
            item.name,
            item.detail || '',
            Math.max(0, item.kind - 1),
            this.range(item.range),
            this.range(item.selectionRange)
          ));
        }
      }),
      vscode.languages.registerCompletionItemProvider('koschei', {
        provideCompletionItems: async (document, position) => {
          const result = await this.request('textDocument/completion', {
            textDocument: {uri: document.uri.toString()},
            position: {line: position.line, character: position.character}
          });
          return (result || []).map(item => {
            const completion = new vscode.CompletionItem(
              item.label,
              Math.max(0, item.kind - 1)
            );
            completion.detail = item.detail;
            return completion;
          });
        }
      }, '.')
    );
  }

  open(document) {
    this.notify('textDocument/didOpen', {
      textDocument: {
        uri: document.uri.toString(),
        languageId: 'koschei',
        version: document.version,
        text: document.getText()
      }
    });
  }

  change(document) {
    this.notify('textDocument/didChange', {
      textDocument: {uri: document.uri.toString(), version: document.version},
      contentChanges: [{text: document.getText()}]
    });
  }

  close(document) {
    this.notify('textDocument/didClose', {
      textDocument: {uri: document.uri.toString()}
    });
    this.diagnostics.delete(document.uri);
  }

  request(method, params) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, {resolve, reject});
      if (!this.send({jsonrpc: '2.0', id, method, params})) {
        this.pending.delete(id);
        reject(new Error('Koschei LSP bağlantısı açık değil.'));
      }
    });
  }

  notify(method, params) {
    this.send({jsonrpc: '2.0', method, params});
  }

  send(message) {
    if (!this.process?.stdin.writable) return false;
    const payload = Buffer.from(JSON.stringify(message), 'utf8');
    this.process.stdin.write(`Content-Length: ${payload.length}\r\n\r\n`);
    this.process.stdin.write(payload);
    return true;
  }

  onData(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    while (true) {
      const separator = this.buffer.indexOf('\r\n\r\n');
      if (separator < 0) return;
      const header = this.buffer.subarray(0, separator).toString('ascii');
      const match = /Content-Length:\s*(\d+)/i.exec(header);
      if (!match) {
        this.buffer = this.buffer.subarray(separator + 4);
        continue;
      }
      const length = Number(match[1]);
      const start = separator + 4;
      if (this.buffer.length < start + length) return;
      const payload = this.buffer.subarray(start, start + length).toString('utf8');
      this.buffer = this.buffer.subarray(start + length);
      try {
        this.onMessage(JSON.parse(payload));
      } catch (error) {
        console.error('[Koschei LSP] Geçersiz JSON', error);
      }
    }
  }

  onMessage(message) {
    if (Object.prototype.hasOwnProperty.call(message, 'id')) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if (message.error) pending.reject(new Error(message.error.message));
      else pending.resolve(message.result);
      return;
    }

    if (message.method === 'textDocument/publishDiagnostics') {
      const uri = vscode.Uri.parse(message.params.uri);
      const diagnostics = (message.params.diagnostics || []).map(item => {
        const diagnostic = new vscode.Diagnostic(
          this.range(item.range),
          item.message,
          this.severity(item.severity)
        );
        diagnostic.code = item.code;
        diagnostic.source = item.source || 'koschei';
        return diagnostic;
      });
      this.diagnostics.set(uri, diagnostics);
    }
  }

  range(value) {
    return new vscode.Range(
      value.start.line,
      value.start.character,
      value.end.line,
      value.end.character
    );
  }

  severity(value) {
    if (value === 2) return vscode.DiagnosticSeverity.Warning;
    if (value === 3) return vscode.DiagnosticSeverity.Information;
    if (value === 4) return vscode.DiagnosticSeverity.Hint;
    return vscode.DiagnosticSeverity.Error;
  }

  rejectAll(error) {
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
  }

  async dispose() {
    for (const disposable of this.disposables) disposable.dispose();
    this.disposables = [];
    this.diagnostics.clear();
    if (!this.process) return;
    try {
      await this.request('shutdown', null);
      this.notify('exit', null);
    } catch (_) {
      // Process already exited.
    }
    this.process.kill();
    this.process = null;
  }
}

let client;

async function activate(context) {
  const diagnostics = vscode.languages.createDiagnosticCollection('koschei');
  context.subscriptions.push(diagnostics);
  client = new KoscheiClient(context, diagnostics);
  await client.start();
  context.subscriptions.push(
    vscode.commands.registerCommand('koschei.checkFile', () => {
      const document = vscode.window.activeTextEditor?.document;
      if (document?.languageId === 'koschei') client.change(document);
    })
  );
  context.subscriptions.push({dispose: () => client?.dispose()});
}

async function deactivate() {
  await client?.dispose();
  client = undefined;
}

module.exports = {activate, deactivate};
