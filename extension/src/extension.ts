import * as path from "path";
import * as vscode from "vscode";

export function activate(context: vscode.ExtensionContext) {
  const factory = new UrscriptDebugAdapterDescriptorFactory(context.extensionPath);
  context.subscriptions.push(vscode.debug.registerDebugAdapterDescriptorFactory("urscript", factory));
}

class UrscriptDebugAdapterDescriptorFactory implements vscode.DebugAdapterDescriptorFactory {
  constructor(private readonly extensionPath: string) {}

  createDebugAdapterDescriptor(
    _session: vscode.DebugSession
  ): vscode.ProviderResult<vscode.DebugAdapterDescriptor> {
    const scriptPath = path.join(this.extensionPath, "server", "dap_server.py");
    const pythonPath = process.platform === "win32" ? "python" : "python3";
    return new vscode.DebugAdapterExecutable(pythonPath, [scriptPath]);
  }
}

export function deactivate() {}
