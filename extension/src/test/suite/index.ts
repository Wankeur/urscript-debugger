import * as path from "path";
import Mocha from "mocha";
import { glob } from "glob";

export async function run(): Promise<void> {
  const mocha = new Mocha({ ui: "tdd", timeout: 60000, color: true });
  const testsRoot = path.resolve(__dirname, ".");

  const files = await glob("**/*.test.js", { cwd: testsRoot });
  files.forEach((f) => mocha.addFile(path.resolve(testsRoot, f)));

  return new Promise((resolve, reject) => {
    mocha.run((failures: number) => {
      if (failures > 0) {
        reject(new Error(`${failures} test(s) ont échoué.`));
      } else {
        resolve();
      }
    });
  });
}
