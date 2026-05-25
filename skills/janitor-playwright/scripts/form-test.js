const { chromium } = require('/home/reck/Janitor-Agent/node_modules/playwright');

async function formTest(url) {
  let browser;

  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();

    console.log(`Navigating to: ${url}`);
    await page.goto(url);

    console.log('Filling email field...');
    await page.fill('input[name="email"]', 'test@janitor.local');

    console.log('Filling password field...');
    await page.fill('input[name="password"]', 'TestPassword123!');

    console.log('Clicking submit button...');
    await page.click('button[type="submit"]');

    console.log('Waiting for navigation...');
    await page.waitForNavigation({ waitUntil: 'networkidle' });

    const finalUrl = page.url();
    const title = await page.title();

    console.log(`Final URL: ${finalUrl}`);
    console.log(`Page title: ${title}`);

    const screenshotPath = '/tmp/form-test-result.png';
    await page.screenshot({ path: screenshotPath });
    console.log(`Screenshot saved to: ${screenshotPath}`);

    return { url: finalUrl, title };
  } catch (error) {
    console.error('Form test failed:', error.message);
    throw error;
  } finally {
    if (browser) {
      await browser.close();
      console.log('Browser closed.');
    }
  }
}

const url = process.argv[2];

if (!url) {
  console.error('Usage: node form-test.js <url>');
  process.exit(1);
}

formTest(url)
  .then(() => {
    console.log('Form test completed successfully.');
    process.exit(0);
  })
  .catch((err) => {
    console.error('Form test failed:', err);
    process.exit(1);
  });
