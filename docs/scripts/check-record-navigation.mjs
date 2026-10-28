import assert from 'node:assert/strict'
import { lstat, readdir, readFile } from 'node:fs/promises'
import { dirname, join, resolve, sep } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const defaultDocsDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const overview = '/dev/development-records'
const commonLinks = [overview, '/plans/', '/specs/', '/plans/#progress-ledgers']
const preservation = '/plans/2026-10-28-development-records-progress'
const review = '/plans/2026-10-28-opencode-session-graph-review-progress'
const design = '/specs/2026-10-26-opencode-session-graph-exposure-design'
const selinux = '/dev/features/record-publication-selinux'
const live = '/dev/features/live-dev'
const relatedLinks = [
    ['/dev/', overview], [overview, preservation],
    [preservation, review], [review, preservation],
    [review, design], [design, review], [review, selinux], [selinux, review],
    [live, preservation], [preservation, live + '#development-records'],
]
const origin = 'https://docs.invalid'

function route_key(url)
{
    return url.pathname.replace(/\.html$/, '').replace(/\/index$/, '/') + url.hash
}

function links_in(html, source)
{
    return [...html.matchAll(/<a\b[^>]*\bhref="([^"]*)"/g)]
        .map((match) => new URL(match[1].replace(/&amp;/g, '&'), origin + source))
        .filter((url) => url.origin === origin).map(route_key)
}

export async function check_record_navigation(options = {})
{
    const docsDir = options.docsDir ?? defaultDocsDir
    const distDir = options.distDir ?? join(docsDir, '.vitepress/dist')
    const pages = new Map()
    async function page(route)
    {
        const url = new URL(route, origin)
        const path = decodeURIComponent(url.pathname)
        const filename = path.endsWith('/') ? path + 'index.html' : path.endsWith('.html') ? path : path + '.html'
        if (!pages.has(filename)) pages.set(filename, await readFile(join(distDir, filename.slice(1)), 'utf8'))
        const html = pages.get(filename)
        if (url.hash) assert.ok(html.includes(`id="${decodeURIComponent(url.hash.slice(1))}"`), `Missing anchor ${route}`)
        return html
    }
    async function require_links(html, source, targets)
    {
        const links = new Set(links_in(html, source))
        for (const target of targets) {
            assert.ok(links.has(route_key(new URL(target, origin))), `Missing navigation link ${source} -> ${target}`)
            await page(target)
        }
    }

    await require_links(await page(overview), overview, commonLinks.slice(1))
    await require_links(await page('/dev/'), '/dev/', [overview])
    const counts = {}
    for (const kind of ['plans', 'specs']) {
        const root = join(docsDir, kind)
        // Inventory independently of the generator, including nested index.md.
        const records = []
        for (const path of await readdir(root, { recursive: true })) {
            if (path !== 'index.md' && path.endsWith('.md') && (await lstat(join(root, path))).isFile()) {
                records.push(`/${kind}/${path.slice(0, -3).split(sep).map(encodeURIComponent).join('/')}`)
            }
        }
        const route = `/${kind}/`
        const index = await page(route)
        await require_links(index, route, commonLinks)
        const listed = [...new Set(links_in(index, route).map((key) => key.split('#')[0])
            .filter((key) => key.startsWith(route) && key !== route))]
        assert.deepEqual(listed.sort(), records.map((record) => route_key(new URL(record, origin))).sort(), `${kind} record inventory differs from built index`)
        for (const record of records) {
            const html = await page(record)
            const sidebar = html.match(/<aside\b[^>]*class="[^"]*VPSidebar[^\"]*"[^>]*>([\s\S]*?)<\/aside>/)?.[1]
            assert.ok(sidebar, `Missing record sidebar: ${record}`)
            await require_links(sidebar, record, commonLinks)
        }
        counts[kind] = records.length
    }
    for (const [source, target] of options.relatedLinks ?? relatedLinks) {
        await require_links(await page(source), source, [target])
    }
    return counts
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
    console.log('Built record navigation verified:', await check_record_navigation())
}
