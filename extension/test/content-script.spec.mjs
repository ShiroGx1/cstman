import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

const assets = new Map([
  ["/", new URL("./harness.html", import.meta.url)],
  ["/src/directive.js", new URL("../src/directive.js", import.meta.url)],
  ["/src/cstman.js", new URL("../src/cstman.js", import.meta.url)],
]);

test.beforeEach(async ({ page }) => {
  await page.route("https://chatgpt.com/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const file = assets.get(path);
    if (!file) return route.fulfill({ status: 404, body: "not found" });
    await route.fulfill({
      status: 200,
      contentType: path.endsWith(".js") ? "text/javascript" : "text/html",
      body: await readFile(file),
    });
  });
  await page.goto("https://chatgpt.com/");
  await expect(page.locator("#cstman-indicator")).toBeVisible();
});

test("first Enter sends full primer and later click sends short reminder exactly once", async ({ page }) => {
  await page.evaluate(() => {
    window.cstmanTest.type("first prompt");
    window.cstmanTest.pressEnter();
  });
  await expect.poll(() => page.evaluate(() => window.cstmanTest.transcript())).toHaveLength(1);
  let transcript = await page.evaluate(() => window.cstmanTest.transcript());
  expect(transcript[0]).toContain("[CSTMAN mode is ON");
  expect(transcript[0]).toContain("Mode CSTMAN");
  expect(transcript[0]).toMatch(/\n\nfirst prompt$/);

  await page.waitForTimeout(250);
  await page.evaluate(() => {
    window.cstmanTest.type("second prompt");
    window.cstmanTest.clickSend();
  });
  await expect.poll(() => page.evaluate(() => window.cstmanTest.transcript())).toHaveLength(2);
  transcript = await page.evaluate(() => window.cstmanTest.transcript());
  expect(transcript[1]).toMatch(/^\[stay in cstman mode — CSTMAN\]\n{2,}second prompt$/);
  expect(transcript[1].match(/\[stay in cstman mode/g)).toHaveLength(1);
});

test("site disable and indicator toggle preserve raw outgoing prompt", async ({ page }) => {
  await page.evaluate(async () => {
    await window.cstmanTest.setStorage({ sites: { "chatgpt.com": false } });
    window.cstmanTest.type("site disabled");
    window.cstmanTest.clickSend();
  });
  await expect.poll(() => page.evaluate(() => window.cstmanTest.transcript())).toEqual(["site disabled"]);

  await page.evaluate(() => window.cstmanTest.setStorage({ sites: {}, enabled: true, level: "ultracave" }));
  await expect(page.locator("#cstman-indicator")).toContainText("ultracave");
  await page.locator("#cstman-indicator").click();
  await expect(page.locator("#cstman-indicator")).toBeHidden();
  await page.evaluate(() => {
    window.cstmanTest.type("master disabled");
    window.cstmanTest.clickSend();
  });
  await expect.poll(() => page.evaluate(() => window.cstmanTest.transcript())).toEqual([
    "site disabled",
    "master disabled",
  ]);
});

test("modifier Enter, blank draft, and already-prefixed prompt never get duplicate injection", async ({ page }) => {
  await page.evaluate(() => {
    window.cstmanTest.type("shift newline");
    window.cstmanTest.pressEnter({ shiftKey: true });
  });
  await page.waitForTimeout(80);
  expect(await page.evaluate(() => window.cstmanTest.transcript())).toEqual([]);

  await page.evaluate(() => {
    window.cstmanTest.type("   ");
    window.cstmanTest.clickSend();
  });
  await page.waitForTimeout(80);
  expect(await page.evaluate(() => window.cstmanTest.transcript())).toEqual([]);

  await page.evaluate(() => {
    window.cstmanTest.type("[stay in cstman mode — CSTMAN]\n\nalready prefixed");
    window.cstmanTest.clickSend();
  });
  await expect.poll(() => page.evaluate(() => window.cstmanTest.transcript())).toEqual([
    "[stay in cstman mode — CSTMAN]\n\nalready prefixed",
  ]);
});
