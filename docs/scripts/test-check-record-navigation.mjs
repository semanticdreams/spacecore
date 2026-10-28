import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import test from 'node:test'
import { check_record_navigation } from './check-record-navigation.mjs'

async function fixture(run)
{
    const root = await mkdtemp(join(tmpdir(), 'space-record-navigation-'))
    const distDir = join(root, 'dist')
    const links = '<a href="/dev/development-records.html">Records</a><a href="/plans/">Plans</a><a href="/specs/">Specs</a><a href="/plans/#progress-ledgers">Progress</a>'
    const sidebar = `<aside class="VPSidebar">${links}</aside>`
    const files = {
        'plans/plan.md': '# Plan\n',
        'plans/odd) name(.md': '# Parentheses\n',
        'specs/spec.md': '# Spec\n',
        'dist/dev/index.html': links,
        'dist/dev/development-records.html': links,
        'dist/plans/index.html': sidebar + '<h2 id="progress-ledgers">Progress</h2><a href="./plan.html">Plan</a><a href="./odd%29%20name%28.html">Parentheses</a>',
        'dist/specs/index.html': sidebar + '<a href="./spec.html">Spec</a>',
        'dist/plans/plan.html': sidebar,
        'dist/plans/odd) name(.html': sidebar,
        'dist/specs/spec.html': sidebar,
    }
    try {
        for (const [path, content] of Object.entries(files)) {
            await mkdir(dirname(join(root, path)), { recursive: true })
            await writeFile(join(root, path), content)
        }
        await run({ docsDir: root, distDir, relatedLinks: [] })
    } finally {
        await rm(root, { recursive: true, force: true })
    }
}

test('built navigation covers the independently inventoried records and common sidebars', async () => {
    await fixture(async (options) => assert.deepEqual(await check_record_navigation(options), { plans: 2, specs: 1 }))
})

test('missing anchor fails even when its page exists', async () => {
    await fixture(async (options) => {
        const index = join(options.distDir, 'plans/index.html')
        await writeFile(index, (await readFile(index, 'utf8')).replace('id="progress-ledgers"', 'id="wrong"'))
        await assert.rejects(check_record_navigation(options), /progress-ledgers/)
    })
})

test('an existing record page omitted from the index fails', async () => {
    await fixture(async (options) => {
        const index = join(options.distDir, 'plans/index.html')
        await writeFile(index, (await readFile(index, 'utf8')).replace('<a href="./plan.html">Plan</a>', ''))
        await assert.rejects(check_record_navigation(options), /inventory/)
    })
})

test('a record without the common sidebar fails', async () => {
    await fixture(async (options) => {
        await writeFile(join(options.distDir, 'specs/spec.html'), '<p>Spec</p>')
        await assert.rejects(check_record_navigation(options), /sidebar/)
    })
})
