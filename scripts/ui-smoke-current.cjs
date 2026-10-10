// Synthetic browser checks and captures for the current 26-note local site.
// A fresh headless context keeps the user's on-device chat history untouched.
const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const base = (process.env.GOV_ASSISTANT_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');
const target = new URL(base);
if (target.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(target.hostname) || target.pathname !== '/' || target.search || target.hash) {
  throw Error('GOV_ASSISTANT_URL must be a local HTTP origin');
}
const shots = path.join(root, 'evidence', 'screenshots');
const evidenceFile = path.join(root, 'evidence', 'ui-smoke-current.json');
const checks = [];
async function check(name, task) {
  try {
    const detail = await task();
    checks.push({name, result: 'pass', ...(detail ? {detail} : {})});
    console.log(`PASS ${name}`);
  } catch (error) {
    checks.push({name, result: 'fail', detail: String(error)});
    console.error(`FAIL ${name}: ${error}`);
  }
}

async function main() {
  fs.mkdirSync(shots, {recursive: true});
  const launchOptions = {headless: true};
  if (process.env.PLAYWRIGHT_BROWSER_PATH) launchOptions.executablePath = process.env.PLAYWRIGHT_BROWSER_PATH;
  const browser = await chromium.launch(launchOptions);
  try {
    const context = await browser.newContext({viewport: {width: 1440, height: 900}, deviceScaleFactor: 1});
    const page = await context.newPage();
    await page.goto(base, {waitUntil: 'networkidle'});
    await check('Fresh page shows examples, method and current source count', async () => {
      await page.getByRole('heading', {name: 'How answers are handled'}).waitFor();
      await page.getByRole('heading', {name: 'Pick a question or write your own'}).waitFor();
      await page.locator('#site-status').waitFor();
      const siteStatus = await page.locator('#site-status').textContent();
      if (!siteStatus?.includes('26 indexed source notes')) throw Error(`Unexpected status: ${siteStatus}`);
      await page.evaluate(() => document.activeElement?.blur());
      await page.screenshot({path: path.join(shots, 'home.png'), fullPage: true});
    });
    await check('Sources button lists indexed notes and filters by topic', async () => {
      await page.getByRole('button', {name: 'Sources', exact: true}).click();
      await page.getByRole('dialog', {name: 'Source notes'}).waitFor();
      if (await page.locator('#sources-list .directory-item').count() !== 26) throw Error('Expected 26 source rows');
      await page.getByRole('button', {name: 'Visas', exact: true}).click();
      if (await page.locator('#sources-list .directory-item').count() !== 19) throw Error('Expected 19 visa rows');
      await page.getByRole('button', {name: 'Tax', exact: true}).click();
      if (await page.locator('#sources-list .directory-item').count() !== 7) throw Error('Expected 7 tax rows');
      await page.getByRole('button', {name: 'All', exact: true}).click();
      await page.evaluate(() => document.activeElement?.blur());
      await page.screenshot({path: path.join(shots, 'sources-directory.png'), fullPage: true});
      await page.getByRole('button', {name: 'Close sources'}).click();
      return '26 total; 19 visa; 7 tax';
    });
    await check('Topic selection changes suggested questions', async () => {
      await page.getByRole('button', {name: /Visas & immigration/}).click();
      await page.locator('#suggestions').getByRole('button', {name: 'Student visa changes'}).waitFor();
      await page.getByRole('button', {name: /Tax & the ATO/}).click();
      await page.locator('#suggestions').getByRole('button', {name: 'Apply for a TFN'}).waitFor();
    });
    await check('Greeting and help explain the scope without a false source match', async () => {
      const input = page.getByRole('textbox', {name: 'Ask a question'});
      await input.fill('hi');
      await input.press('Enter');
      await page.getByText('HOW TO USE THIS ASSISTANT').waitFor();
      await input.fill('What can you help me with?');
      await input.press('Enter');
      await page.getByText('HOW TO USE THIS ASSISTANT').last().waitFor();
      if (await page.getByText('NO MATCHING SOURCE NOTE').count()) throw Error('Greeting or help was refused');
    });
    await check('Long graduation answer, retrieval details and local feedback survive reload', async () => {
      await page.getByRole('button', {name: 'New chat'}).click();
      await page.getByRole('button', {name: /Visas & immigration/}).click();
      const input = page.getByRole('textbox', {name: 'Ask a question'});
      await input.fill('I’m graduating as an international student in Australia. What should I do next?');
      await input.press('Enter');
      const answer = page.locator('#messages .assistant-message').last();
      await answer.getByText('SOURCE EXTRACT', {exact: true}).waitFor();
      const original = await answer.locator('.message-body > p').first().textContent();
      if (!original || original.length <= 1500 || !original.endsWith('Check the linked government pages for the current rule and your circumstances.')) throw Error(`Incomplete answer length=${original?.length}`);
      await answer.getByRole('button', {name: 'Helpful', exact: true}).click();
      await page.reload({waitUntil: 'networkidle'});
      const restored = page.locator('#messages .assistant-message').last();
      const text = await restored.locator('.message-body > p').first().textContent();
      if (text !== original) throw Error(`History changed answer ${original.length} to ${text?.length}`);
      if (await restored.getByRole('button', {name: 'Helpful', exact: true}).getAttribute('aria-pressed') !== 'true') throw Error('Local feedback did not persist');
      await restored.locator('summary').click();
      await restored.getByText('4 matching source notes').waitFor();
      if (await restored.locator('.retrieval-details li').count() !== 4) throw Error('Expected 4 retrieved note links');
      await page.evaluate(() => document.activeElement?.blur());
      await page.screenshot({path: path.join(shots, 'retrieval-details.png'), fullPage: true});
      return `answer ${original.length} characters; 4 retrieved notes; feedback retained`;
    });
    await check('Synthetic private identifier is blocked before API request', async () => {
      await page.getByRole('button', {name: 'New chat'}).click();
      let requests = 0;
      page.on('request', request => {if (request.url().endsWith('/api/chat')) requests += 1;});
      const input = page.getByRole('textbox', {name: 'Ask a question'});
      await input.fill('My passport number is TEST000; can you check my visa decision?');
      await input.press('Enter');
      await page.getByText('[Personal details removed]').waitFor();
      if (requests !== 0) throw Error(`Private identifier triggered ${requests} API requests`);
    });
    const mobile = await browser.newContext({viewport: {width: 390, height: 844}, deviceScaleFactor: 1});
    const mobilePage = await mobile.newPage();
    await check('Mobile page fits a 390-pixel viewport', async () => {
      await mobilePage.goto(base, {waitUntil: 'networkidle'});
      const width = await mobilePage.evaluate(() => ({page: document.documentElement.scrollWidth, viewport: innerWidth}));
      if (width.page > width.viewport + 1) throw Error(JSON.stringify(width));
      await mobilePage.evaluate(() => document.activeElement?.blur());
      await mobilePage.screenshot({path: path.join(shots, 'mobile-home.png'), fullPage: true});
    });
  } finally {
    await browser.close();
  }
  fs.writeFileSync(evidenceFile, JSON.stringify({created_at_utc: new Date().toISOString(), kind: 'synthetic_browser_smoke', version: 'current-26-note-ui', checks}, null, 2) + '\n');
  console.log(`Saved ${evidenceFile}`);
  if (checks.some(item => item.result === 'fail')) process.exitCode = 1;
}

main().catch(error => {console.error(error); process.exitCode = 1;});
