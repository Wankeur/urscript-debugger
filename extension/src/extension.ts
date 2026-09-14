import * as path from "path";
import * as vscode from "vscode";
import { checkLicense, clearLicenseKey, openPurchasePage, promptForLicenseKey } from "./license";

export function activate(context: vscode.ExtensionContext) {
  const factory = new UrscriptDebugAdapterDescriptorFactory(context);
  context.subscriptions.push(vscode.debug.registerDebugAdapterDescriptorFactory("urscript", factory));

  context.subscriptions.push(
    vscode.commands.registerCommand("urscript-debugger.enterLicenseKey", () => promptForLicenseKey(context))
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("urscript-debugger.clearLicenseKey", async () => {
      await clearLicenseKey(context);
      vscode.window.showInformationMessage("License removed.");
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("urscript-debugger.buyPremiumLicense", () => openPurchasePage())
  );
}

class UrscriptDebugAdapterDescriptorFactory implements vscode.DebugAdapterDescriptorFactory {
  constructor(private readonly context: vscode.ExtensionContext) {}

  async createDebugAdapterDescriptor(
    _session: vscode.DebugSession
  ): Promise<vscode.DebugAdapterDescriptor> {
    const scriptPath = path.join(this.context.extensionPath, "server", "dap_server.py");
    const pythonPath = process.platform === "win32" ? "python" : "python3";
    const licensed = await checkLicense(this.context);
    return new vscode.DebugAdapterExecutable(pythonPath, [scriptPath], {
      env: { ...process.env, URSCRIPT_LICENSED: licensed ? "1" : "0" } as { [key: string]: string },
    });
  }
}

export function deactivate() {}
