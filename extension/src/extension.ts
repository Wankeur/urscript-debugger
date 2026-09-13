import * as path from "path";
import * as vscode from "vscode";

export function activate(context: vscode.ExtensionContext) {
  const factory = new UrscriptDebugAdapterDescriptorFactory();
  context.subscriptions.push(vscode.debug.registerDebugAdapterDescriptorFactory("urscript", factory));
}

class UrscriptDebugAdapterDescriptorFactory implements vscode.DebugAdapterDescriptorFactory {
  createDebugAdapterDescriptor(
    _session: vscode.DebugSession
  ): vscode.ProviderResult<vscode.DebugAdapterDescriptor> {
    const serverDir = path.join(__dirname, "..", "..", "server");
    const pythonPath = path.join(serverDir, ".venv", "bin", "python");
    const scriptPath = path.join(serverDir, "dap_server.py");
    return new vscode.DebugAdapterExecutable(pythonPath, [scriptPath]);
  }
}

export function deactivate() {}
