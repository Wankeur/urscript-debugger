import * as assert from "assert";
import * as net from "net";
import * as vscode from "vscode";

const RENDEZVOUS_PORT = 29998;

interface CapturedMessage {
  direction: "toAdapter" | "fromAdapter";
  message: any;
}

suite("URScript Debugger E2E", () => {
  setup(() => {
    // Isolation entre tests : les breakpoints posés dans un test persistent sinon dans le workspace.
    vscode.debug.removeBreakpoints(vscode.debug.breakpoints);
  });

  test("plusieurs breakpoints consécutifs avec variable visible à chaque arrêt", async function () {
    this.timeout(90000);

    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    assert.ok(workspaceFolder, "Aucun workspace ouvert");

    const scriptUri = vscode.Uri.joinPath(workspaceFolder.uri, "counter_clean.script");
    const doc = await vscode.workspace.openTextDocument(scriptUri);
    await vscode.window.showTextDocument(doc);

    // Ligne 5 (1-indexée dans l'éditeur) = index 4 dans l'API VS Code (0-indexée)
    const bp = new vscode.SourceBreakpoint(new vscode.Location(scriptUri, new vscode.Position(4, 0)));
    vscode.debug.addBreakpoints([bp]);

    const messages: CapturedMessage[] = [];
    const stoppedEvents: any[] = [];

    const trackerDisposable = vscode.debug.registerDebugAdapterTrackerFactory("urscript", {
      createDebugAdapterTracker() {
        return {
          onWillReceiveMessage: (m: any) => messages.push({ direction: "toAdapter", message: m }),
          onDidSendMessage: (m: any) => {
            messages.push({ direction: "fromAdapter", message: m });
            if (m.type === "event" && m.event === "stopped") {
              stoppedEvents.push(m);
            }
          },
        };
      },
    });

    const started = await vscode.debug.startDebugging(workspaceFolder, {
      type: "urscript",
      request: "launch",
      name: "Test E2E",
      program: scriptUri.fsPath,
      ursimHost: "127.0.0.1",
    });
    assert.ok(started, "startDebugging a échoué");

    const session = vscode.debug.activeDebugSession;
    assert.ok(session, "Pas de session de debug active");

    async function waitForStoppedCount(n: number, timeoutMs: number): Promise<void> {
      const deadline = Date.now() + timeoutMs;
      while (stoppedEvents.length < n) {
        if (Date.now() > deadline) {
          throw new Error(`Timeout: seulement ${stoppedEvents.length}/${n} événement(s) 'stopped' reçu(s).`);
        }
        await new Promise((r) => setTimeout(r, 200));
      }
    }

    async function readVariableCounter(): Promise<string | undefined> {
      const threadsResp = await session!.customRequest("threads");
      const threadId = threadsResp.threads[0].id;
      const stResp = await session!.customRequest("stackTrace", { threadId });
      const frameId = stResp.stackFrames[0].id;
      const scopesResp = await session!.customRequest("scopes", { frameId });
      const varsRef = scopesResp.scopes[0].variablesReference;
      const varsResp = await session!.customRequest("variables", { variablesReference: varsRef });
      const counterVar = varsResp.variables.find((v: any) => v.name === "counter");
      return counterVar?.value;
    }

    try {
      await waitForStoppedCount(1, 20000);
      let value = await readVariableCounter();
      console.log("Après 1er arrêt, counter =", value);
      assert.strictEqual(value, "1", `Attendu counter=1 au 1er arrêt, reçu ${value}`);

      await vscode.commands.executeCommand("workbench.action.debug.continue");
      await waitForStoppedCount(2, 20000);
      value = await readVariableCounter();
      console.log("Après 2e arrêt, counter =", value);
      assert.strictEqual(value, "2", `Attendu counter=2 au 2e arrêt, reçu ${value}`);

      await vscode.commands.executeCommand("workbench.action.debug.continue");
      await waitForStoppedCount(3, 20000);
      value = await readVariableCounter();
      console.log("Après 3e arrêt, counter =", value);
      assert.strictEqual(value, "3", `Attendu counter=3 au 3e arrêt, reçu ${value}`);

      await vscode.commands.executeCommand("workbench.action.debug.continue");
    } finally {
      console.log("\n=== TRANSCRIPT DAP COMPLET ===");
      for (const m of messages) {
        console.log(m.direction, JSON.stringify(m.message));
      }
      trackerDisposable.dispose();
      await vscode.commands.executeCommand("workbench.action.debug.stop");
    }
  });

  test("échec propre et signalé si le port de rendez-vous est déjà occupé", async function () {
    this.timeout(30000);

    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    assert.ok(workspaceFolder, "Aucun workspace ouvert");
    const scriptUri = vscode.Uri.joinPath(workspaceFolder.uri, "counter_clean.script");

    // Occupe volontairement le port pour simuler une session précédente mal arrêtée.
    const blocker = net.createServer();
    await new Promise<void>((resolve, reject) => {
      blocker.once("error", reject);
      blocker.listen(RENDEZVOUS_PORT, "0.0.0.0", () => resolve());
    });

    const outputMessages: string[] = [];
    let terminatedReceived = false;

    const trackerDisposable = vscode.debug.registerDebugAdapterTrackerFactory("urscript", {
      createDebugAdapterTracker() {
        return {
          onDidSendMessage: (m: any) => {
            if (m.type === "event" && m.event === "output") {
              outputMessages.push(m.body?.output ?? "");
            }
            if (m.type === "event" && m.event === "terminated") {
              terminatedReceived = true;
            }
          },
        };
      },
    });

    try {
      await vscode.debug.startDebugging(workspaceFolder, {
        type: "urscript",
        request: "launch",
        name: "Test E2E - port occupé",
        program: scriptUri.fsPath,
        ursimHost: "127.0.0.1",
      });

      const deadline = Date.now() + 15000;
      while (!terminatedReceived && Date.now() < deadline) {
        await new Promise((r) => setTimeout(r, 200));
      }

      assert.ok(terminatedReceived, "L'adaptateur aurait dû signaler 'terminated' au lieu de rester bloqué silencieusement");
      assert.ok(
        outputMessages.some((m) => m.toLowerCase().includes("port")),
        `Un message d'erreur mentionnant le port était attendu, reçu: ${JSON.stringify(outputMessages)}`
      );
    } finally {
      trackerDisposable.dispose();
      await vscode.commands.executeCommand("workbench.action.debug.stop");
      await new Promise<void>((resolve) => blocker.close(() => resolve()));
    }
  });

  test("le pas-à-pas (step over) avance ligne par ligne sans breakpoint explicite", async function () {
    this.timeout(60000);

    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    assert.ok(workspaceFolder, "Aucun workspace ouvert");
    const scriptUri = vscode.Uri.joinPath(workspaceFolder.uri, "counter_clean.script");

    // Un seul breakpoint, sur la toute première ligne exécutable, pour amorcer la session.
    const bp = new vscode.SourceBreakpoint(new vscode.Location(scriptUri, new vscode.Position(1, 0)));
    vscode.debug.addBreakpoints([bp]);

    const stoppedLines: number[] = [];
    const stoppedReasons: string[] = [];

    const trackerDisposable = vscode.debug.registerDebugAdapterTrackerFactory("urscript", {
      createDebugAdapterTracker() {
        return {
          onDidSendMessage: (m: any) => {
            if (m.type === "event" && m.event === "stopped") {
              stoppedReasons.push(m.body.reason);
            }
          },
        };
      },
    });

    const started = await vscode.debug.startDebugging(workspaceFolder, {
      type: "urscript",
      request: "launch",
      name: "Test E2E - step over",
      program: scriptUri.fsPath,
      ursimHost: "127.0.0.1",
    });
    assert.ok(started, "startDebugging a échoué");
    const session = vscode.debug.activeDebugSession;
    assert.ok(session, "Pas de session de debug active");

    async function waitForStoppedCount(n: number, timeoutMs: number): Promise<void> {
      const deadline = Date.now() + timeoutMs;
      while (stoppedReasons.length < n) {
        if (Date.now() > deadline) {
          throw new Error(`Timeout: seulement ${stoppedReasons.length}/${n} événement(s) 'stopped' reçu(s).`);
        }
        await new Promise((r) => setTimeout(r, 200));
      }
    }

    async function currentLine(): Promise<number> {
      const threadsResp = await session!.customRequest("threads");
      const stResp = await session!.customRequest("stackTrace", { threadId: threadsResp.threads[0].id });
      return stResp.stackFrames[0].line;
    }

    try {
      await waitForStoppedCount(1, 20000);
      assert.strictEqual(stoppedReasons[0], "breakpoint");
      const line1 = await currentLine();
      stoppedLines.push(line1);
      console.log("Arrêt initial (breakpoint) à la ligne", line1);
      assert.strictEqual(line1, 2, `Attendu arrêt initial ligne 2, reçu ${line1}`);

      // Trois pas-à-pas successifs : la ligne doit avancer à chaque fois (3 -> 5 -> 6),
      // en s'arrêtant même sur des lignes qui ne sont PAS des breakpoints explicites.
      for (const expectedLine of [3, 5, 6]) {
        await vscode.commands.executeCommand("workbench.action.debug.stepOver");
        await waitForStoppedCount(stoppedLines.length + 1, 15000);
        const line = await currentLine();
        stoppedLines.push(line);
        console.log("Après step over, arrêt à la ligne", line, "(raison:", stoppedReasons[stoppedReasons.length - 1] + ")");
        assert.strictEqual(line, expectedLine, `Attendu ligne ${expectedLine}, reçu ${line}`);
        assert.strictEqual(
          stoppedReasons[stoppedReasons.length - 1],
          "step",
          "La raison de l'arrêt après un step over devrait être 'step', pas 'breakpoint'"
        );
      }

      await vscode.commands.executeCommand("workbench.action.debug.continue");
    } finally {
      trackerDisposable.dispose();
      await vscode.commands.executeCommand("workbench.action.debug.stop");
    }
  });

  test("l'édition en direct d'une variable affecte réellement l'exécution", async function () {
    this.timeout(60000);

    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    assert.ok(workspaceFolder, "Aucun workspace ouvert");
    const scriptUri = vscode.Uri.joinPath(workspaceFolder.uri, "counter_clean.script");

    const bp = new vscode.SourceBreakpoint(new vscode.Location(scriptUri, new vscode.Position(4, 0)));
    vscode.debug.addBreakpoints([bp]);

    const stoppedEvents: any[] = [];
    let terminatedReceived = false;

    const trackerDisposable = vscode.debug.registerDebugAdapterTrackerFactory("urscript", {
      createDebugAdapterTracker() {
        return {
          onDidSendMessage: (m: any) => {
            if (m.type === "event" && m.event === "stopped") stoppedEvents.push(m);
            if (m.type === "event" && m.event === "terminated") terminatedReceived = true;
          },
        };
      },
    });

    const started = await vscode.debug.startDebugging(workspaceFolder, {
      type: "urscript",
      request: "launch",
      name: "Test E2E - édition de variable",
      program: scriptUri.fsPath,
      ursimHost: "127.0.0.1",
    });
    assert.ok(started, "startDebugging a échoué");
    const session = vscode.debug.activeDebugSession;
    assert.ok(session, "Pas de session de debug active");

    async function waitFor(predicate: () => boolean, timeoutMs: number): Promise<void> {
      const deadline = Date.now() + timeoutMs;
      while (!predicate()) {
        if (Date.now() > deadline) throw new Error("Timeout en attendant la condition.");
        await new Promise((r) => setTimeout(r, 200));
      }
    }

    try {
      await waitFor(() => stoppedEvents.length >= 1, 20000);

      const threadsResp = await session!.customRequest("threads");
      const stResp = await session!.customRequest("stackTrace", { threadId: threadsResp.threads[0].id });
      const scopesResp = await session!.customRequest("scopes", { frameId: stResp.stackFrames[0].id });
      const varsRef = scopesResp.scopes[0].variablesReference;

      const varsResp = await session!.customRequest("variables", { variablesReference: varsRef });
      const before = varsResp.variables.find((v: any) => v.name === "counter")?.value;
      console.log("counter avant édition:", before);
      assert.strictEqual(before, "1");

      // Édite counter à 10 — comme si l'utilisateur double-cliquait dans le panneau Variables.
      const setResp = await session!.customRequest("setVariable", {
        variablesReference: varsRef,
        name: "counter",
        value: "10",
      });
      console.log("Réponse setVariable:", JSON.stringify(setResp));
      assert.strictEqual(setResp.value, "10.0");

      // La condition de boucle (counter < 3) doit désormais être fausse : le programme doit
      // se terminer directement au prochain continue, PAS s'arrêter à nouveau ligne 5.
      await vscode.commands.executeCommand("workbench.action.debug.continue");
      await waitFor(() => terminatedReceived, 15000);
      assert.strictEqual(stoppedEvents.length, 1, "Le programme n'aurait plus dû s'arrêter après l'édition de counter à 10");
      console.log("Programme terminé directement après édition — la boucle a bien été court-circuitée.");
    } finally {
      trackerDisposable.dispose();
      await vscode.commands.executeCommand("workbench.action.debug.stop");
    }
  });

  test("support multi-fichiers : breakpoints isolés par fichier, un seul fichier lancé à la fois", async function () {
    this.timeout(60000);

    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    assert.ok(workspaceFolder, "Aucun workspace ouvert");
    const scriptA = vscode.Uri.joinPath(workspaceFolder.uri, "counter_clean.script");
    const scriptB = vscode.Uri.joinPath(workspaceFolder.uri, "second_test.script");

    // Un breakpoint dans CHAQUE fichier, mais on ne va lancer que scriptB.
    vscode.debug.addBreakpoints([
      new vscode.SourceBreakpoint(new vscode.Location(scriptA, new vscode.Position(4, 0))), // counter_clean ligne 5
      new vscode.SourceBreakpoint(new vscode.Location(scriptB, new vscode.Position(4, 0))), // second_test ligne 5
    ]);

    const stoppedEvents: any[] = [];
    let terminatedReceived = false;

    const trackerDisposable = vscode.debug.registerDebugAdapterTrackerFactory("urscript", {
      createDebugAdapterTracker() {
        return {
          onDidSendMessage: (m: any) => {
            if (m.type === "event" && m.event === "stopped") stoppedEvents.push(m);
            if (m.type === "event" && m.event === "terminated") terminatedReceived = true;
          },
        };
      },
    });

    const started = await vscode.debug.startDebugging(workspaceFolder, {
      type: "urscript",
      request: "launch",
      name: "Test E2E - multi-fichiers",
      program: scriptB.fsPath, // on lance scriptB, PAS scriptA
      ursimHost: "127.0.0.1",
    });
    assert.ok(started, "startDebugging a échoué");
    const session = vscode.debug.activeDebugSession;
    assert.ok(session, "Pas de session de debug active");

    async function waitFor(predicate: () => boolean, timeoutMs: number): Promise<void> {
      const deadline = Date.now() + timeoutMs;
      while (!predicate()) {
        if (Date.now() > deadline) throw new Error("Timeout en attendant la condition.");
        await new Promise((r) => setTimeout(r, 200));
      }
    }

    try {
      await waitFor(() => stoppedEvents.length >= 1, 20000);
      assert.strictEqual(stoppedEvents.length, 1);

      const threadsResp = await session!.customRequest("threads");
      const stResp = await session!.customRequest("stackTrace", { threadId: threadsResp.threads[0].id });
      assert.strictEqual(
        stResp.stackFrames[0].source.path,
        scriptB.fsPath,
        "L'arrêt aurait dû se produire dans second_test.script, pas dans l'autre fichier"
      );
      assert.strictEqual(stResp.stackFrames[0].line, 5);
      console.log("Arrêt confirmé dans le bon fichier (second_test.script), le breakpoint de counter_clean.script n'a pas interféré.");

      await vscode.commands.executeCommand("workbench.action.debug.continue");
      await waitFor(() => terminatedReceived, 15000);
      assert.strictEqual(
        stoppedEvents.length,
        1,
        "Le breakpoint de l'autre fichier (jamais lancé) n'aurait jamais dû déclencher un arrêt"
      );
    } finally {
      trackerDisposable.dispose();
      await vscode.commands.executeCommand("workbench.action.debug.stop");
    }
  });
});
