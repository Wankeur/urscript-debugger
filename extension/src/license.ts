import * as crypto from "crypto";
import * as http from "http";
import * as https from "https";
import * as vscode from "vscode";

const SECRET_KEY = "urscript-debugger.licenseKey";
const DEVICE_ID_KEY = "urscript-debugger.deviceId";
const CACHE_VALID_KEY = "urscript-debugger.licenseCachedValid";
const CACHE_CHECKED_AT_KEY = "urscript-debugger.licenseCheckedAt";
const GRACE_PERIOD_MS = 3 * 24 * 60 * 60 * 1000; // 3 jours hors-ligne tolérés pour un client déjà validé

function getOrCreateDeviceId(context: vscode.ExtensionContext): string {
  let id = context.globalState.get<string>(DEVICE_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    context.globalState.update(DEVICE_ID_KEY, id);
  }
  return id;
}

function getLicenseServerUrl(): string {
  return vscode.workspace.getConfiguration("urscript-debugger").get<string>("licenseServerUrl", "");
}

function postJson(url: string, payload: object, timeoutMs = 4000): Promise<any> {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith("https://") ? https : http;
    const body = Buffer.from(JSON.stringify(payload));
    const req = lib.request(
      url,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": body.length },
        timeout: timeoutMs,
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => {
          try {
            resolve(JSON.parse(data));
          } catch (e) {
            reject(e);
          }
        });
      }
    );
    req.on("error", reject);
    req.on("timeout", () => req.destroy(new Error("timeout")));
    req.write(body);
    req.end();
  });
}

export async function setLicenseKey(context: vscode.ExtensionContext, key: string): Promise<void> {
  await context.secrets.store(SECRET_KEY, key.trim());
  // Invalide le cache pour forcer une revérification immédiate avec la nouvelle clé.
  await context.globalState.update(CACHE_VALID_KEY, undefined);
  await context.globalState.update(CACHE_CHECKED_AT_KEY, undefined);
}

export async function clearLicenseKey(context: vscode.ExtensionContext): Promise<void> {
  await context.secrets.delete(SECRET_KEY);
  await context.globalState.update(CACHE_VALID_KEY, undefined);
  await context.globalState.update(CACHE_CHECKED_AT_KEY, undefined);
}

/** Retourne true si une licence valide (ou en période de grâce hors-ligne) est active. */
export async function checkLicense(context: vscode.ExtensionContext): Promise<boolean> {
  // Utilisé uniquement par la suite de tests E2E pour simuler un état licencié/gratuit
  // sans dépendre d'un vrai serveur de licence.
  const testForceLicensed = vscode.workspace
    .getConfiguration("urscript-debugger")
    .get<boolean>("__testForceLicensed");
  if (testForceLicensed !== undefined) {
    return testForceLicensed;
  }

  const key = await context.secrets.get(SECRET_KEY);
  if (!key) {
    return false;
  }

  const serverUrl = getLicenseServerUrl();
  const deviceId = getOrCreateDeviceId(context);

  if (serverUrl) {
    try {
      const resp = await postJson(`${serverUrl.replace(/\/$/, "")}/licenses/validate`, {
        key,
        device_id: deviceId,
      });
      const valid = resp?.valid === true;
      await context.globalState.update(CACHE_VALID_KEY, valid);
      await context.globalState.update(CACHE_CHECKED_AT_KEY, Date.now());
      return valid;
    } catch {
      // Serveur injoignable : on retombe sur le cache (période de grâce), voir ci-dessous.
    }
  }

  const cachedValid = context.globalState.get<boolean>(CACHE_VALID_KEY, false);
  const checkedAt = context.globalState.get<number>(CACHE_CHECKED_AT_KEY, 0);
  if (cachedValid && Date.now() - checkedAt < GRACE_PERIOD_MS) {
    return true;
  }
  return false;
}

export async function promptForLicenseKey(context: vscode.ExtensionContext): Promise<void> {
  const key = await vscode.window.showInputBox({
    prompt: "Enter your URScript Debugger license key",
    placeHolder: "URSDBG-...",
    ignoreFocusOut: true,
  });
  if (!key) {
    return;
  }
  await setLicenseKey(context, key);
  const valid = await checkLicense(context);
  if (valid) {
    vscode.window.showInformationMessage("License activated — premium features unlocked.");
  } else {
    vscode.window.showErrorMessage("This license key could not be validated. Please check it and try again.");
  }
}
