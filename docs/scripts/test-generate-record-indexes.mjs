import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'

import { format_record_index, generate_record_indexes, record_title } from './generate-record-indexes.mjs'

test('titles come from real headings, not frontmatter or fenced examples', () => {
    const markdown = '---\ntitle: ignored\n# Not a heading\n---\n~~~md\n# Example\n~~~\n```md\n# Another example\n```\n# Actual title\n'
    assert.equal(record_title(markdown, '2026-10-28-fallback.md'), 'Actual title')
    assert.equal(record_title('No heading\n', 'nested/2026-10-28-fallback-title.md'), 'fallback title')
    assert.equal(record_title('    # Indented example\n', 'undated.md'), 'undated')
})

test('indexes group records disjointly, sort by basename date and retain duplicate titles', () => {
    const output = format_record_index([
        { path: '2026-10-27-old.md', title: 'Old' },
        { path: 'nested/2026-10-28-a.md', title: 'Same title' },
        { path: '2026-10-28-b.md', title: 'Same title' },
        { path: '2026-10-28-task-progress.md', title: 'Progress' },
        { path: 'undated.md', title: 'Undated' },
    ], 'plans')
    const [plans, progress] = output.split('## Progress ledgers')
    assert.match(plans, /Implementation plans/)
    assert.doesNotMatch(plans, /task-progress\.md/)
    assert.match(progress, /task-progress\.md/)
    assert.equal((output.match(/\[Same title\]/g) ?? []).length, 2)
    assert.ok(plans.indexOf('2026-10-28-b.md') < plans.indexOf('nested/2026-10-28-a.md'))
    assert.ok(plans.indexOf('nested/2026-10-28-a.md') < plans.indexOf('2026-10-27-old.md'))
    assert.ok(plans.indexOf('2026-10-27-old.md') < plans.indexOf('undated.md'))
    assert.match(plans, /### Undated/)
})

test('labels are literal Markdown/HTML/Vue-safe text and URL path segments are encoded', () => {
    const output = format_record_index([
        { path: 'nested/a b#c.md', title: '[link](target) <tag> {{value}} & `code`' },
    ], 'specs')
    assert.match(output, /\.\/nested\/a%20b%23c\.md/)
    assert.match(output, /\\\[link\\\]/)
    assert.match(output, /&lt;tag&gt;/)
    assert.match(output, /&#123;&#123;value&#125;&#125;/)
    assert.doesNotMatch(output, /<tag>|\{\{value\}\}/)
})

test('generation includes every regular Markdown path, preserves sources and is repeatable', async () => {
    const root = await mkdtemp(join(tmpdir(), 'space-record-index-'))
    try {
        await mkdir(join(root, 'plans/nested'), { recursive: true })
        await mkdir(join(root, 'specs'))
        const sources = {
            'plans/2026-10-28-plan.md': '# Implementation\n',
            'plans/2026-10-28-plan-progress.md': '# Progress\n',
            'plans/nested/index.md': '# Nested record\n',
            'plans/nested/undated.md': '# Undated\n',
            'specs/2026-10-28-design.md': '# Design\n',
        }
        for (const [path, content] of Object.entries(sources)) await writeFile(join(root, path), content)
        await writeFile(join(root, 'plans/index.md'), '# Stale generated index\n')
        await writeFile(join(root, 'plans/not-a-record.txt'), 'ignored')
        const first = await generate_record_indexes({ docsDir: root })
        const actualPaths = ['plans', 'specs'].flatMap((kind) =>
            [...first[kind].matchAll(/\]\(\.\/(.*?)\)/g)].map((match) => `${kind}/${decodeURIComponent(match[1])}`))
        assert.deepEqual(actualPaths.sort(), Object.keys(sources).sort())
        const second = await generate_record_indexes({ docsDir: root })
        assert.deepEqual(second, first)
        for (const [path, content] of Object.entries(sources)) assert.equal(await readFile(join(root, path), 'utf8'), content)
        for (const kind of ['plans', 'specs']) assert.equal(await readFile(join(root, kind, 'index.md'), 'utf8'), first[kind])
    } finally {
        await rm(root, { recursive: true, force: true })
    }
})

test('unbalanced filename parentheses cannot terminate Markdown link targets', () => {
    const output = format_record_index([{ path: 'nested/a) b(.md', title: 'Parentheses' }], 'specs')
    assert.match(output, /\.\/nested\/a%29%20b%28\.md/)
})

test('source read errors fail before publishing any generated index', async () => {
    const root = await mkdtemp(join(tmpdir(), 'space-record-index-error-'))
    try {
        await mkdir(join(root, 'plans'))
        const index = join(root, 'plans/index.md')
        await writeFile(index, 'retained index\n')
        await assert.rejects(generate_record_indexes({ docsDir: root }), { code: 'ENOENT' })
        assert.equal(await readFile(index, 'utf8'), 'retained index\n')
    } finally {
        await rm(root, { recursive: true, force: true })
    }
})
