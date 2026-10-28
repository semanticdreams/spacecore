import { readdir, readFile, writeFile } from 'node:fs/promises'
import { basename, dirname, join, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const defaultDocsDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const compare = (left, right) => left < right ? -1 : left > right ? 1 : 0
const dateOf = (path) => basename(path).match(/^(\d{4}-\d{2}-\d{2})(?:-|\.)/)?.[1] ?? ''

export function record_title(markdown, path)
{
    const lines = markdown.replace(/^\uFEFF/, '').split(/\r?\n/)
    let start = 0
    if (lines[0]?.trim() === '---') {
        const end = lines.findIndex((line, index) => index > 0 && line.trim() === '---')
        start = end < 0 ? lines.length : end + 1
    }
    let fence = null
    for (const line of lines.slice(start)) {
        const marker = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/)
        if (fence) {
            if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2].trim()) fence = null
            continue
        }
        if (marker) { fence = marker[1]; continue }
        const heading = line.match(/^ {0,3}#\s+(.+?)(?:\s+#+)?\s*$/)
        if (heading) return heading[1]
    }
    return basename(path, '.md').replace(/^\d{4}-\d{2}-\d{2}-/, '').replace(/[-_]/g, ' ')
}

function literal_label(text)
{
    const entities = { '<': '&lt;', '>': '&gt;', '{': '&#123;', '}': '&#125;' }
    return text.replace(/&/g, '&amp;').replace(/[<>{}]/g, (char) => entities[char])
        .replace(/[\\[\]`*_!|]/g, '\\$&')
}

function section(title, records)
{
    const lines = [`## ${title}`, '']
    let month = null
    if (!records.length) lines.push('No records yet.', '')
    for (const record of records) {
        const date = dateOf(record.path)
        const group = date.slice(0, 7) || 'Undated'
        if (month !== group) { lines.push(`### ${group}`, ''); month = group }
        const href = record.path.split('/').map((part) => encodeURIComponent(part)
            .replace(/[!'()*]/g, (char) => `%${char.charCodeAt(0).toString(16).toUpperCase()}`)).join('/')
        lines.push(`- ${date ? `${date} — ` : ''}[${literal_label(record.title)}](./${href})`)
    }
    return lines.join('\n') + '\n'
}

export function format_record_index(records, kind)
{
    if (kind !== 'plans' && kind !== 'specs') throw new Error(`Unknown record kind: ${kind}`)
    const ordered = [...records].sort((left, right) =>
        compare(dateOf(right.path), dateOf(left.path)) || compare(left.path, right.path))
    const title = kind === 'plans' ? 'Implementation plans and progress' : 'Design specs'
    const header = `---\ntype: index\noutline: [2, 3]\n---\n\n# ${title}\n\n` +
        '[Development records overview](/dev/development-records) · ' +
        '[Design specs](/specs/) · [Plans and progress](/plans/)\n\n' +
        'Generated from the Markdown records in this directory, newest first. ' +
        'Indexes refresh when the docs development server starts or the docs build runs.\n\n'
    if (kind === 'specs') return header + section('Design specs', ordered)
    const progress = (record) => basename(record.path).endsWith('-progress.md')
    return header + section('Implementation plans', ordered.filter((record) => !progress(record))) +
        '\n' + section('Progress ledgers', ordered.filter(progress))
}

async function scan_records(directory, prefix = '')
{
    const records = []
    for (const entry of await readdir(directory, { withFileTypes: true })) {
        const path = prefix + entry.name
        const absolute = join(directory, entry.name)
        if (entry.isDirectory()) records.push(...await scan_records(absolute, path + '/'))
        else if (entry.isFile() && entry.name.endsWith('.md') && path !== 'index.md') {
            records.push({ path, title: record_title(await readFile(absolute, 'utf8'), path) })
        }
    }
    return records
}

export async function generate_record_indexes(options = {})
{
    const docsDir = options.docsDir ?? defaultDocsDir
    // Complete both inventories before changing either index; read failures
    // must not masquerade as an empty or partially published directory.
    const [plans, specs] = await Promise.all(['plans', 'specs'].map((kind) => scan_records(join(docsDir, kind))))
    const output = { plans: format_record_index(plans, 'plans'), specs: format_record_index(specs, 'specs') }
    for (const kind of ['plans', 'specs']) await writeFile(join(docsDir, kind, 'index.md'), output[kind], 'utf8')
    return output
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
    await generate_record_indexes()
}
