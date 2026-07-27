const {defineConfig} = require("@playwright/test");

module.exports = defineConfig({
  testDir: "tests/ui",
  timeout: 30000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.HFSS_STUDIO_URL || "http://127.0.0.1:8765",
    screenshot: "only-on-failure",
    trace: "retain-on-failure"
  }
});
