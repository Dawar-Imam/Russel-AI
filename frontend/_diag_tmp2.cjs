const { chromium } = require('playwright-core')

async function check(page, path, listSelector, scrollSelector) {
  await page.goto('http://localhost:5173' + path, { waitUntil: 'networkidle' })
  await page.waitForSelector(scrollSelector, { timeout: 10000 })
  const info = await page.evaluate(({ listSelector, scrollSelector }) => {
    const scrollArea = document.querySelector(scrollSelector)
    let list = document.querySelector(listSelector)
    if (!list && scrollArea) {
      list = document.createElement('div')
      list.className = listSelector.replace('.', '')
      scrollArea.appendChild(list)
    }
    if (list) {
      for (let i = 0; i < 30; i++) {
        const card = document.createElement('div')
        card.style.minHeight = '300px'
        card.textContent = 'Synthetic card ' + i
        list.appendChild(card)
      }
    }
    const el = scrollArea
    const cs = el ? getComputedStyle(el) : null
    const before = el.scrollTop
    el.scrollTop = 500
    const after = el.scrollTop
    return {
      found: !!el,
      overflowY: cs && cs.overflowY,
      clientHeight: el && el.clientHeight,
      scrollHeight: el && el.scrollHeight,
      scrollBefore: before,
      scrollAfter: after,
    }
  }, { listSelector, scrollSelector })
  console.log(path, JSON.stringify(info))
}

async function main() {
  const browser = await chromium.launch()
  const context = await browser.newContext({ viewport: { width: 1400, height: 800 } })
  const page = await context.newPage()

  // Sign in as candidate via sessionStorage before first navigation
  await page.goto('http://localhost:5173/')
  await page.evaluate(() => {
    sessionStorage.setItem('candidateId', 'test-candidate-id')
    sessionStorage.setItem('candidateEmail', 'test@example.com')
    sessionStorage.setItem('userType', 'candidate')
  })

  await check(page, '/jobs', '.jobs-list', '.jobs-scroll-area')
  await check(page, '/my-applications', '.my-apps-list', '.my-apps-scroll-area')

  await browser.close()
}

main().catch((e) => { console.error(e); process.exit(1) })
