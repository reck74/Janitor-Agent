const { chromium } = require('/home/reck/Janitor-Agent/node_modules/playwright');

const url = process.argv[2] || 'https://example.com';
const outputPath = process.argv[3] || (process.env.HOME + '/.janitor/screenshots/capture.png');

(async () => {
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.screenshot({ path: outputPath, fullPage: true });
    console.log('Screenshot guardado en: ' + outputPath);
  } catch (e) {
    console.error('Error:', e.message);
    process.exit(1);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
})();
