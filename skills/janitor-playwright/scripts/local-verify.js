const { chromium } = require('/home/reck/Janitor-Agent/node_modules/playwright');

const url = process.argv[2];

if (!url) {
  console.error('Usage: node local-verify.js <url>');
  process.exit(1);
}

(async () => {
  const browser = await chromium.launch();
  let status = null;
  let title = null;
  const consoleErrors = [];

  try {
    const page = await browser.newPage();

    page.on('console', msg => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    const response = await page.goto(url, { waitUntil: 'domcontentloaded' });
    status = response.status();
    title = await page.title();

    await page.waitForTimeout(2000);

    console.log(`Status: ${status}`);
    console.log(`Title: ${title}`);
    console.log(`Console errors: ${consoleErrors.length}`);

    if (status === 200) {
      process.exit(0);
    } else {
      process.exit(1);
    }
  } catch (err) {
    console.error(`Error: ${err.message}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
