const { chromium } = require('playwright-core')

async function main() {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1400, height: 800 } })
  await page.goto('http://localhost:5173/jobs', { waitUntil: 'networkidle' })
  await page.waitForSelector('.jobs-page', { timeout: 10000 })

  // Ensure enough cards to overflow: inject synthetic cards into whatever list container exists
  const info = await page.evaluate(() => {
    function metrics(el) {
      if (!el) return null
      const cs = getComputedStyle(el)
      return {
        tag: el.tagName,
        cls: el.className,
        display: cs.display,
        overflowY: cs.overflowY,
        height: cs.height,
        clientHeight: el.clientHeight,
        scrollHeight: el.scrollHeight,
        minHeight: cs.minHeight,
        flex: cs.flex,
      }
    }

    const scrollArea = document.querySelector('.jobs-scroll-area')
    let list = document.querySelector('.jobs-list')
    if (!list && scrollArea) {
      list = document.createElement('div')
      list.className = 'jobs-list'
      scrollArea.appendChild(list)
    }
    if (list) {
      for (let i = 0; i < 30; i++) {
        const card = document.createElement('div')
        card.className = 'job-card'
        card.style.minHeight = '300px'
        card.textContent = 'Synthetic card ' + i
        list.appendChild(card)
      }
    }

    const chain = []
    let el = scrollArea
    while (el && el !== document.body) {
      chain.push(metrics(el))
      el = el.parentElement
    }
    return { hasScrollArea: !!scrollArea, hasList: !!list, chain }
  })

  console.log(JSON.stringify(info, null, 2))

  // Try actually scrolling and see if scrollTop changes
  const scrollResult = await page.evaluate(() => {
    const el = document.querySelector('.jobs-scroll-area')
    if (!el) return null
    const before = el.scrollTop
    el.scrollTop = 500
    const after = el.scrollTop
    return { before, after }
  })
  console.log('scrollResult', JSON.stringify(scrollResult))

  await browser.close()
}

main().catch((e) => { console.error(e); process.exit(1) })
