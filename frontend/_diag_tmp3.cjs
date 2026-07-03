const { chromium } = require('playwright-core')

async function main() {
  const browser = await chromium.launch()
  const context = await browser.newContext({ viewport: { width: 1400, height: 800 } })
  const page = await context.newPage()

  await page.goto('http://localhost:5173/')
  await page.evaluate(() => {
    sessionStorage.setItem('recruiterId', 'test-recruiter-id')
    sessionStorage.setItem('recruiterEmail', 'recruiter@example.com')
    sessionStorage.setItem('userType', 'recruiter')
  })

  await page.goto('http://localhost:5173/recruiter-dashboard', { waitUntil: 'networkidle' })
  await page.waitForSelector('.rd-scroll-area', { timeout: 10000 })
  const info = await page.evaluate(() => {
    const scrollArea = document.querySelector('.rd-scroll-area')
    let grid = document.querySelector('.rd-jobs-grid')
    if (!grid && scrollArea) {
      grid = document.createElement('div')
      grid.className = 'rd-jobs-grid'
      scrollArea.appendChild(grid)
    }
    for (let i = 0; i < 30; i++) {
      const card = document.createElement('div')
      card.style.minHeight = '300px'
      card.textContent = 'Synthetic ' + i
      grid.appendChild(card)
    }
    const cs = getComputedStyle(scrollArea)
    const before = scrollArea.scrollTop
    scrollArea.scrollTop = 500
    const after = scrollArea.scrollTop
    return {
      overflowY: cs.overflowY,
      clientHeight: scrollArea.clientHeight,
      scrollHeight: scrollArea.scrollHeight,
      scrollBefore: before,
      scrollAfter: after,
    }
  })
  console.log('/recruiter-dashboard', JSON.stringify(info))
  await browser.close()
}

main().catch((e) => { console.error(e); process.exit(1) })
