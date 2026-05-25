const { chromium } = require('/home/reck/Janitor-Agent/node_modules/playwright');

const url = process.argv[2];

if (!url) {
  console.error('Usage: node extract-text.js <url>');
  process.exit(1);
}

let browser;

(async () => {
  browser = await chromium.launch({ headless: true });

  const page = await browser.newPage();

  await page.goto(url, { waitUntil: 'networkidle' });

  const text = await page.textContent('body');

  console.log(text.slice(0, 2000));
})()
  .catch((err) => {
    console.error('Error:', err.message);
    process.exit(1);
  })
  .finally(async () => {
    if (browser) {
      await browser.close();
    }
  });
